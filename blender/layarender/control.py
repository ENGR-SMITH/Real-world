"""The scene control plane: a bounded loop that proposes, gates, applies, renders and reviews.

Doc, section 6, is the specification this module implements, including its stopping rules:

* ``preflight`` runs before execution and can reject a plan outright.
* Laya gates the write; a ``human_review`` gate means the gated write is **not** applied.
* After rendering and review, Laya routes the next pass among the routes the deterministic
  layer allows.
* ``accept`` requires *both* Laya's route and every mandatory check passing.
* A candidate that stops improving branches instead of looping, and the loop always ends:
  either accepted, branched, or escalated to a person, within the contract's revision budget.

The creative model sits behind :class:`Planner`. Two ship: a deterministic policy planner that
turns located findings into located edits (so the workflow is runnable and testable with no model
at all), and a callable planner that is the seam for a real creative model. The doc's split of
responsibilities is preserved either way: the planner proposes, Laya routes, the Render MCP
Designer applies, and nothing reviews its own work.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from .adapters.laya_ai import ROUTE_LABELS, LayaAdapter
from .contracts import SceneContract
from .models import (CheckStatus, Decision, DecisionSource, Finding, HardChecks, PatchOp,
                     PatchPlan, PreflightResult, Route, RunState, Round, Severity, ViewRender,
                     VisualReview, _now)
from .policy import OperationPolicy
from .preflight import preflight_plan, summarise_preflight
from .report import final_report
from .reviewer import MeasuredReviewer, load_findings, merge_reviews, render_metadata
from .scene import SceneContext, SceneReadError, SceneSnapshot, read_scene
from .validators import run_scene_checks
from .views import ensure_views, fingerprint_of, required_views, settings_drift

MAX_PLAN_CORRECTIONS = 1
STALL_MIN_DELTA = 0.02


@dataclass
class ControlPlaneConfig:
    """Everything the loop is allowed to do, in one place."""

    shadow_mode: bool = True
    max_rounds: Optional[int] = None
    user_prompt: str = ""
    scene_path: Optional[str] = None
    delivery_path: Optional[str] = None
    run_dir: str = "runs"
    stall_min_delta: float = STALL_MIN_DELTA
    max_plan_corrections: int = MAX_PLAN_CORRECTIONS
    require_approval_callback: Optional[Callable[[PatchPlan, PreflightResult], bool]] = None
    #: name -> existing image path. When a render cannot be produced (no Blender attached, shadow
    #: mode, or a read-only review pass), an existing render is used as evidence for that view.
    #: The record always says it was supplied rather than produced, so the report never implies
    #: this run rendered it.
    existing_views: Dict[str, str] = field(default_factory=dict)
    external_findings_path: Optional[str] = None
    #: A JSON file of what the live scene knows beyond the exported artifact (cameras, lights,
    #: render settings). See :class:`layarender.scene.SceneContext`.
    scene_context_path: Optional[str] = None

    def rounds(self, contract: SceneContract) -> int:
        if self.max_rounds is not None:
            return max(1, self.max_rounds)
        return max(1, int(contract.max_revision_rounds))


class Planner:
    """The creative model's boundary: turn a state into a bounded, located plan."""

    name = "planner"

    def propose(self, state: Dict[str, Any], context: Dict[str, Any]) -> PatchPlan:
        raise NotImplementedError

    def correct(self, state: Dict[str, Any], context: Dict[str, Any],
                rejected: PatchPlan, errors: Sequence[str]) -> Optional[PatchPlan]:
        return None

    def branch(self, state: Dict[str, Any], context: Dict[str, Any]) -> Optional[PatchPlan]:
        return None


def hero_pattern(contract: SceneContract) -> str:
    """The object the workflow treats as the subject, taken from the contract, never invented."""
    explicit = contract.delivery.get("hero_object") if isinstance(contract.delivery, dict) else None
    if isinstance(explicit, str) and explicit:
        return explicit
    if contract.must_have:
        return contract.must_have[0]
    return "*"


def first_object(snapshot: Optional[SceneSnapshot], pattern: str) -> Optional[str]:
    if snapshot is None:
        return None
    exact = snapshot.find(pattern)
    if exact:
        return exact.name
    matched = snapshot.match(pattern)
    return matched[0].name if matched else None


def view_camera(contract: SceneContract, view_name: str) -> str:
    spec = contract.view(view_name)
    return spec.camera if spec else view_name


# Severity order used when the planner has to choose one thing to fix first.
_SEVERITY_ORDER = {Severity.HIGH.value: 0, Severity.MEDIUM.value: 1, Severity.LOW.value: 2}


@dataclass
class PolicyPlanner(Planner):
    """Deterministic planner: one located edit per round, chosen from located evidence.

    Deliberately narrow. It only proposes operations whose effect it can name, it targets a
    single object, and it derives that target from the contract or from a finding that already
    names one. A criterion it cannot fix produces no plan at all, which the loop turns into an
    escalation rather than a guess.
    """

    name: str = "policy_planner"
    counter: int = 0

    def _next_id(self, label: str) -> str:
        self.counter += 1
        return "candidate-%s-%02d" % (label, self.counter)

    def propose(self, state: Dict[str, Any], context: Dict[str, Any]) -> PatchPlan:
        contract: SceneContract = context["contract"]
        snapshot: Optional[SceneSnapshot] = context.get("snapshot")
        checks: Optional[HardChecks] = context.get("checks")
        review: Optional[VisualReview] = context.get("review")
        hero = first_object(snapshot, hero_pattern(contract)) or ""

        failures = [f for f in (checks.failures() if checks else []) if f.mandatory]
        for failure in failures:
            plan = self._plan_for_check(failure.name, failure, hero, contract, snapshot)
            if plan is not None:
                return plan

        located = [f for f in (review.located_findings() if review else []) if f.result == "fail"]
        located.sort(key=lambda finding: _SEVERITY_ORDER.get(finding.severity, 3))
        for finding in located:
            plan = self._plan_for_finding(finding, hero, contract, context)
            if plan is not None:
                return plan

        return PatchPlan(candidate_id=self._next_id("noop"),
                         intent="no located, fixable issue was found",
                         ops=[], addresses=[], proposed_by=self.name)

    # -- evidence to one located operation ----------------------------------------------
    def _plan_for_check(self, name: str, failure: Any, hero: str, contract: SceneContract,
                        snapshot: Optional[SceneSnapshot]) -> Optional[PatchPlan]:
        if name.startswith("dimension:") and snapshot is not None:
            pattern = name.split(":", 2)[1]
            target = first_object(snapshot, pattern)
            obj = snapshot.find(target) if target else None
            dimensions = obj.dimensions() if obj else None
            if not obj or not dimensions:
                return None
            requirement = next((r for r in contract.mandatory_requirements()
                                if r.kind == "dimension" and r.pattern == pattern), None)
            if requirement is None or requirement.axis is None:
                return None
            axis = {"x": 0, "y": 1, "z": 2}.get(requirement.axis.lower())
            if axis is None:
                return None
            current = dimensions[axis]
            low = requirement.min if requirement.min is not None else current
            high = requirement.max if requirement.max is not None else current
            goal = (float(low) + float(high)) / 2.0
            if current <= 0 or goal <= 0:
                return None
            scale = [1.0, 1.0, 1.0]
            scale[axis] = round(goal / current, 6)
            return PatchPlan(
                candidate_id=self._next_id("dimension"),
                intent="bring %s back inside its contracted %s dimension"
                       % (obj.name, requirement.axis),
                ops=[PatchOp(op="set_object_transform", target=obj.name,
                             parameters={"scale": scale}, reason=failure.detail,
                             expected_result="%s = %.4f" % (requirement.axis, goal),
                             reversible=True)],
                addresses=[name], proposed_by=self.name)

        if name.startswith("view_rendered"):
            views = list(failure.expected or [])
            if not views:
                return None
            view = views[0]
            return PatchPlan(
                candidate_id=self._next_id("view"),
                intent="make the required view %s renderable" % view,
                ops=[PatchOp(op="frame_object_in_camera", target=hero,
                             parameters={"camera": view_camera(contract, view)},
                             reason=failure.detail,
                             expected_result="the %s camera frames the subject" % view,
                             reversible=True)],
                addresses=[name], proposed_by=self.name)
        return None

    def _plan_for_finding(self, finding: Finding, hero: str, contract: SceneContract,
                          context: Dict[str, Any]) -> Optional[PatchPlan]:
        target = finding.affected_object or hero
        if not target:
            return None
        criterion = finding.criterion.lower()
        camera = view_camera(contract, finding.view or "hero")
        # A lighting fix needs a real light, and the scene context is the only thing that can name
        # one. Without it the planner proposes nothing rather than aiming a light operation at a
        # mesh -- the preflight would reject that anyway, and a rejected plan wastes a round.
        scene_context = context.get("scene_context")
        light_target = next(iter(scene_context.of_kind("light")) if scene_context else [], None)

        if "inside the frame" in criterion or "legible size" in criterion:
            return PatchPlan(
                candidate_id=self._next_id("framing"),
                intent="reframe %s in the %s view" % (target, finding.view),
                ops=[PatchOp(op="frame_object_in_camera", target=target,
                             parameters={"camera": camera}, reason=finding.evidence,
                             expected_result="subject inside the frame at 40-85% coverage",
                             reversible=True)],
                addresses=[finding.criterion], proposed_by=self.name)

        if "separates from the background" in criterion:
            if light_target is None:
                return None
            return PatchPlan(
                candidate_id=self._next_id("separation"),
                intent="raise silhouette separation in the %s view" % finding.view,
                ops=[PatchOp(op="set_light", target=light_target,
                             parameters={"energy": 1.35, "size": 1.15},
                             reason=finding.evidence,
                             expected_result="subject/background luminance difference over 0.055",
                             reversible=True)],
                addresses=[finding.criterion], proposed_by=self.name)

        if criterion.startswith("highlights"):
            if light_target is None:
                return None
            return PatchPlan(
                candidate_id=self._next_id("clipping"),
                intent="reduce highlight clipping in the %s view" % finding.view,
                ops=[PatchOp(op="set_light", target=light_target, parameters={"energy": 0.8},
                             reason=finding.evidence,
                             expected_result="clipped highlights under 3.5% of the frame",
                             reversible=True)],
                addresses=[finding.criterion], proposed_by=self.name)

        if criterion.startswith("exposure"):
            if light_target is None:
                return None
            return PatchPlan(
                candidate_id=self._next_id("exposure"),
                intent="raise exposure in the %s view" % finding.view,
                ops=[PatchOp(op="set_light", target=light_target, parameters={"energy": 1.6},
                             reason=finding.evidence,
                             expected_result="mean luminance over 0.035", reversible=True)],
                addresses=[finding.criterion], proposed_by=self.name)

        if criterion.startswith("shadows"):
            if light_target is None:
                return None
            return PatchPlan(
                candidate_id=self._next_id("fill"),
                intent="lift crushed shadows in the %s view" % finding.view,
                ops=[PatchOp(op="set_light", target=light_target, parameters={"energy": 1.2},
                             reason=finding.evidence,
                             expected_result="shadow clipping under 30%", reversible=True)],
                addresses=[finding.criterion], proposed_by=self.name)
        return None

    def correct(self, state: Dict[str, Any], context: Dict[str, Any], rejected: PatchPlan,
                errors: Sequence[str]) -> Optional[PatchPlan]:
        """Drop the operations the preflight rejected and keep whatever survives.

        A smaller legal plan is worth one more attempt; inventing a different plan would be
        guessing, which is not this planner's job. If nothing survives, the loop escalates.
        """
        policy: OperationPolicy = context["policy"]
        keep = [op for op in rejected.ops
                if policy.is_allowlisted(op.op) and op.op != "delete_object"]
        if not keep or len(keep) == len(rejected.ops):
            return None
        return PatchPlan(
            candidate_id=rejected.candidate_id + "-corrected",
            intent="%s (reduced after preflight: %s)" % (rejected.intent, "; ".join(errors)[:160]),
            ops=keep, addresses=list(rejected.addresses), branch_label=rejected.branch_label,
            proposed_by=self.name)

    def branch(self, state: Dict[str, Any], context: Dict[str, Any]) -> Optional[PatchPlan]:
        """A genuinely different direction, not another nudge of the same object.

        The one lever this planner owns that is not a local edit: move the hero in depth so the
        composition itself changes, which the doc asks for when local edits stop helping.
        """
        contract: SceneContract = context["contract"]
        snapshot: Optional[SceneSnapshot] = context.get("snapshot")
        hero = first_object(snapshot, hero_pattern(contract)) or ""
        if not hero:
            return None
        return PatchPlan(
            candidate_id=self._next_id("branch"),
            intent="branch: change the hero composition instead of nudging %s again" % hero,
            branch_label="alternate_hero_composition",
            ops=[PatchOp(op="nudge_object", target=hero,
                         parameters={"axis": "z", "delta": 0.15},
                         reason="repeated local edits stopped improving the score",
                         expected_result="a different silhouette against the background",
                         reversible=True)],
            addresses=["composition"], proposed_by=self.name)


@dataclass
class CallablePlanner(Planner):
    """The seam for a real creative model.

    ``propose_fn`` must return a dict shaped like a patch plan. It is coerced into a
    :class:`PatchPlan` and its operations still go through the same preflight, so a creative model
    cannot widen its own scope. The doc's rule -- the creative model "should not be responsible for
    ... inventing unsupported MCP operations" -- is enforced by the preflight rather than by
    trusting the model.
    """

    propose_fn: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]] = None  # type: ignore
    name: str = "creative_model"
    counter: int = 0

    def propose(self, state: Dict[str, Any], context: Dict[str, Any]) -> PatchPlan:
        self.counter += 1
        payload = self.propose_fn(state, context)
        if not isinstance(payload, dict):
            raise TypeError("the creative model must return a plan object, got %s"
                            % type(payload).__name__)
        return PatchPlan(
            candidate_id=str(payload.get("candidate_id") or "candidate-model-%02d" % self.counter),
            intent=str(payload.get("intent") or ""),
            ops=[PatchOp(op=str(item.get("op")), target=item.get("target"),
                         parameters=dict(item.get("parameters") or {}),
                         reason=str(item.get("reason") or ""),
                         expected_result=str(item.get("expected_result") or ""),
                         reversible=bool(item.get("reversible", True)),
                         destructive=bool(item.get("destructive", False)))
                 for item in payload.get("ops", [])],
            addresses=[str(address) for address in payload.get("addresses", [])],
            branch_label=payload.get("branch_label"),
            proposed_by=self.name,
        )


def _slug(text: str, limit: int = 48) -> str:
    """A short, stable, non-boolean label for a criterion.

    Contract criteria are sentences ("silhouette separates from the background"), and Laya's
    documentation warns that choice labels are read verbatim, so the option the model chooses has
    to be something the workflow can also act on and log. A slug keeps the option short while the
    description travels beside it in the question.
    """
    cleaned = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return (cleaned[:limit].rstrip("_") or "finding")


def priority_options(checks: Optional[HardChecks],
                     review: Optional[VisualReview]) -> Dict[str, str]:
    """Which single failing criterion to fix first, as ``{slug: description}``.

    The brief routes each revision to "the single highest-priority failing criterion". Failing hard
    checks are the obvious candidates, but on a scene whose mandatory checks all pass -- which is
    this project's real state -- the only failures left are the measured review's findings, and
    those are exactly what a person would fix. Offering only check names meant the priority
    question was never asked at all on the very scene the workflow is for.

    Failing checks come first because a broken requirement outranks a soft visual criterion.
    """
    options: Dict[str, str] = {}
    for result in (checks.failures() if checks else []):
        options.setdefault(_slug(result.name), (result.detail or result.name)[:160])
    for finding in (review.findings if review else []):
        if finding.result != "fail":
            continue
        where = " on %s" % finding.view if finding.view else ""
        options.setdefault(_slug(finding.criterion),
                           "%s%s" % (finding.criterion, where))
    return dict(list(options.items())[:8])


def build_evidence_pack(state: RunState, contract: SceneContract,
                        snapshot: Optional[SceneSnapshot], checks: Optional[HardChecks] = None,
                        review: Optional[VisualReview] = None,
                        allowed_ops: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """A compact, versioned state record for the planner and for Laya.

    Doc, section 4 step 4: "Create a compact, versioned run state... Avoid sending an entire
    project dump when a focused subset is enough." Object names are capped and only the measured
    summary travels -- never mesh payloads.
    """
    pack: Dict[str, Any] = {
        "task_id": state.task_id,
        "goal": contract.goal,
        "intended_use": contract.intended_use,
        "units": contract.units,
        "visual_targets": list(contract.visual_targets),
        "must_have": list(contract.must_have),
        "scene_limits": {
            "write_scope": contract.write_scope_patterns(),
            "max_revision_rounds": contract.max_revision_rounds,
            "polygon_budget": contract.polygon_budget,
            "required_views": contract.required_view_names(),
        },
        "budget": {"max_rounds": state.max_rounds(), "used": state.rounds_used},
        "allowed_operations": list(allowed_ops or []),
    }
    if snapshot is not None:
        summary = snapshot.summary()
        summary["objects"] = [obj.name for obj in snapshot.objects][:60]
        summary["materials"] = snapshot.materials_in_use()[:40]
        summary.pop("source", None)
        pack["scene"] = summary
    if checks is not None:
        pack["hard_checks"] = checks.summary()
        pack["hard_check_failures"] = [{"name": result.name, "detail": result.detail[:240]}
                                       for result in checks.failures()]
    if review is not None:
        pack["review"] = {
            "views": list(review.views_reviewed),
            "score": review.score(),
            "findings": [
                {"criterion": finding.criterion, "severity": finding.severity,
                 "result": finding.result, "view": finding.view,
                 "object": finding.affected_object, "evidence": finding.evidence[:200],
                 "measured": finding.measured, "confidence": finding.confidence}
                for finding in review.findings[:12]
            ],
        }
    scores = [score for score in state.scores() if score is not None]
    if scores:
        pack["history"] = {"scores": scores, "stalled": state.stalled()}
    return pack


def allowed_routes(state: RunState, checks: Optional[HardChecks], review: Optional[VisualReview],
                   stalled: bool) -> List[str]:
    """The routes the deterministic layer will allow, before Laya is asked anything.

    This is the code that "combine[s] results in code" rather than delegating the whole policy to
    the model:

    * ``accept`` is only offered when every mandatory check passed and no high-severity finding
      remains -- so a model cannot accept a scene the validators reject.
    * ``revise`` is withdrawn once the candidate has stalled, which forces a branch or a person
      instead of another nudge of the same object.
    * nothing but ``human_review`` is offered when the revision budget is spent.
    """
    mandatory_failures = bool(checks.failures()) if checks else False
    high = bool(review.high_severity()) if review else False
    routes: List[str] = []
    if not mandatory_failures and not high:
        routes.append(Route.ACCEPT.value)
    if not stalled:
        routes.append(Route.REVISE.value)
    routes.append(Route.BRANCH.value)
    routes.append(Route.HUMAN_REVIEW.value)
    if state.budget_exhausted():
        return [Route.HUMAN_REVIEW.value]
    return routes


@dataclass
class SceneControlPlane:
    """The orchestrator: propose, gate, apply, render, review, route, and stop."""

    contract: SceneContract
    policy: OperationPolicy
    laya: LayaAdapter
    render: Any  # layarender.adapters.render_mcp.RenderMcpAdapter
    planner: Planner = field(default_factory=PolicyPlanner)
    reviewer: MeasuredReviewer = field(default_factory=MeasuredReviewer)
    config: ControlPlaneConfig = field(default_factory=ControlPlaneConfig)
    snapshot: Optional[SceneSnapshot] = None
    scene_context: Optional[SceneContext] = None
    sources: Dict[str, Any] = field(default_factory=dict)
    trace: List[str] = field(default_factory=list)

    # ---- setup -------------------------------------------------------------------------
    def note(self, message: str) -> None:
        self.trace.append(message)

    def load_scene(self) -> Optional[SceneSnapshot]:
        """Read the editable scene. A failure here is recorded, never fatal."""
        path = self.config.scene_path
        if not path:
            self.snapshot = None
            return None
        try:
            self.snapshot = read_scene(path)
            self.sources["scene_read_error"] = None
        except SceneReadError as error:
            self.snapshot = None
            self.sources["scene_read_error"] = str(error)
            self.note("scene could not be read: %s" % error)
        return self.snapshot

    def start(self, brief: Optional[Dict[str, Any]] = None) -> RunState:
        """Build the run state: brief, contract, scene context, allowed operations and budget."""
        snapshot = self.snapshot if self.snapshot is not None else self.load_scene()
        context = self.scene_context if self.scene_context is not None else self.load_scene_context()
        views = ensure_views(self.contract, self.contract.render_size())
        state = RunState(
            brief=dict(brief or {}),
            contract=self.contract.to_dict(),
            scene=snapshot.summary() if snapshot else {},
            scene_revision=snapshot.revision if snapshot else "",
            allowed_operations=sorted(self.policy.allowed_ops),
            budget={"max_rounds": self.config.rounds(self.contract),
                    "require_approval": bool(self.policy.require_approval_for_broad)},
            modes={"shadow_mode": self.policy.shadow_mode,
                   "planner": self.planner.name,
                   "reviewer": self.reviewer.name},
            versions={"layarender": "1", "laya": self.laya.describe(),
                      "policy": self.policy.describe(), "view_fingerprints":
                          {spec.name: spec.fingerprint() for spec in views},
                      "scene_context": context.to_dict() if context else None},
        )
        if self.sources.get("scene_read_error"):
            state.log("scene_read_failed", detail=self.sources["scene_read_error"])
        state.log("run_started", shadow_mode=self.policy.shadow_mode,
                  max_rounds=state.max_rounds(), scene_revision=state.scene_revision,
                  laya_available=bool(self.laya.describe().get("available")))
        return state

    def context(self, state: RunState, checks: Optional[HardChecks] = None,
                review: Optional[VisualReview] = None) -> Dict[str, Any]:
        return {
            "contract": self.contract,
            "policy": self.policy,
            "snapshot": self.snapshot,
            "checks": checks,
            "review": review,
            "state": state,
            "render": self.render,
            "views": ensure_views(self.contract, self.contract.render_size()),
            "user_prompt": self.config.user_prompt,
            "scene_context": self.scene_context,
        }

    def load_scene_context(self) -> Optional[SceneContext]:
        """Read the scene context, falling back to what the exported scene can prove.

        Without a supplied context the workflow still knows every mesh in the export -- it simply
        knows nothing about cameras or lights, and the preflight then refuses to assume them.
        """
        path = self.config.scene_context_path
        if path and os.path.exists(path):
            try:
                self.scene_context = SceneContext.load(path)
                return self.scene_context
            except (OSError, ValueError) as error:
                self.note("scene context could not be read: %s" % error)
        if self.snapshot is not None:
            self.scene_context = SceneContext.from_snapshot(self.snapshot)
        return self.scene_context

    # ---- one pass ----------------------------------------------------------------------
    def run_round(self, state: RunState, previous: Optional[Round] = None) -> Round:
        index = state.rounds_used
        round_ = Round(index=index)
        context = self.context(state, checks=previous.checks if previous else None,
                               review=previous.review if previous else None)
        pack = build_evidence_pack(state, self.contract, self.snapshot,
                                   checks=context["checks"], review=context["review"],
                                   allowed_ops=sorted(self.policy.allowed_ops))

        # 1. the creative model proposes
        try:
            plan = self.planner.propose(pack, context)
        except Exception as error:
            round_.apply_detail = "planner failed: %s" % error
            round_.route = Decision(route=Route.HUMAN_REVIEW.value,
                                    source=DecisionSource.UNAVAILABLE.value,
                                    reason="the planner raised: %s" % error)
            self.note("planner failed: %s" % error)
            return self._with_unrun_checks(state, round_, context)
        round_.plan = plan
        if not plan.ops:
            # Nothing located to fix. Accept only if there is nothing left to fix.
            checks = context["checks"]
            review = context["review"]
            nothing_left = (checks is not None and checks.passed() and not review.high_severity())
            round_.route = Decision(
                route=Route.ACCEPT.value if nothing_left else Route.HUMAN_REVIEW.value,
                source=DecisionSource.POLICY.value, confidence=0.0,
                reason="the planner found no located, fixable issue"
                       + (" and every mandatory check passed" if nothing_left
                          else "; a person must decide what to do next"))
            if nothing_left:
                round_.checks = checks
                round_.review = review
                round_.score = review.score()
            return self._with_unrun_checks(state, round_, context)

        # 2. deterministic preflight, before anything is asked of Laya
        preflight = preflight_plan(plan, self.contract, self.policy, self.snapshot,
                                   self.scene_context)
        round_.preflight = preflight
        if not preflight.ok:
            self.note("preflight rejected %s: %s" % (plan.candidate_id,
                                                     summarise_preflight(preflight)))
            corrected = None
            if self.config.max_plan_corrections > 0:
                corrected = self.planner.correct(pack, context, plan, preflight.errors)
            if corrected is not None:
                second = preflight_plan(corrected, self.contract, self.policy, self.snapshot,
                                        self.scene_context)
                if second.ok:
                    round_.plan = plan = corrected
                    round_.preflight = preflight = second
            if not preflight.ok:
                round_.route = Decision(route=Route.HUMAN_REVIEW.value,
                                        source=DecisionSource.POLICY.value, confidence=0.0,
                                        reason="preflight rejected the plan: %s"
                                               % summarise_preflight(preflight))
                return self._with_unrun_checks(state, round_, context)

        # 3. approval, when the policy demands it
        approved = False
        if preflight.requires_approval:
            callback = self.config.require_approval_callback
            approved = bool(callback(plan, preflight)) if callback else False
            round_.human_approved = approved
            if not approved:
                round_.route = Decision(
                    route=Route.HUMAN_REVIEW.value, source=DecisionSource.HUMAN.value,
                    confidence=1.0,
                    reason="approval required (%s) and not given" % preflight.approval_reason)
                self.note("paused for approval: %s" % preflight.approval_reason)
                return self._with_unrun_checks(state, round_, context)

        # 4. Laya gates the write
        gate_pack = dict(pack)
        gate_pack["proposed_plan"] = plan.to_dict()
        gate_pack["preflight"] = {"ok": preflight.ok, "warnings": preflight.warnings,
                                  "requires_approval": preflight.requires_approval}
        # One narrow question: may this write happen? The operations are already in the evidence as
        # `proposed_plan`, and the plan is applied whole or not at all, so asking the model to rank
        # the operations would collect an answer nothing consumes -- attention spent and a number
        # logged that implies a choice the workflow never makes.
        decision = self.laya.choose_next_step(
            gate_pack,
            allowed_routes=[Route.REVISE.value, Route.BRANCH.value, Route.HUMAN_REVIEW.value],
            priority_options=None,
            fallback_reason="the workflow must ask a person before its first pass")
        round_.decision = decision
        if decision.route == Route.HUMAN_REVIEW.value:
            round_.route = Decision(
                route=Route.HUMAN_REVIEW.value, source=decision.source, confidence=decision.confidence,
                reason="the gate did not clear the write: %s" % decision.reason,
                priority_criterion=decision.priority_criterion,
                guardrails=list(decision.guardrails), native=decision.native,
                latency_ms=decision.latency_ms)
            self.note("gate blocked the write: %s" % decision.reason)
            return self._with_unrun_checks(state, round_, context)
        if decision.route == Route.BRANCH.value:
            branched = self.planner.branch(pack, context)
            if branched is None:
                round_.route = Decision(route=Route.HUMAN_REVIEW.value,
                                        source=DecisionSource.POLICY.value, confidence=0.0,
                                        reason="Laya asked to branch, but this planner has no "
                                               "alternative direction")
                return self._with_unrun_checks(state, round_, context)
            branch_preflight = preflight_plan(branched, self.contract, self.policy, self.snapshot,
                                              self.scene_context)
            if not branch_preflight.ok:
                round_.route = Decision(route=Route.HUMAN_REVIEW.value,
                                        source=DecisionSource.POLICY.value, confidence=0.0,
                                        reason="the branch plan failed preflight: %s"
                                               % summarise_preflight(branch_preflight))
                return self._with_unrun_checks(state, round_, context)
            round_.plan = plan = branched
            round_.preflight = preflight = branch_preflight

        # 5. apply, then render and review
        receipt = self.render.apply_patch(plan, preflight, self.config.user_prompt, approved=approved)
        round_.applied = bool(receipt.ok)
        round_.apply_detail = receipt.detail
        if self.policy.shadow_mode:
            self.note("shadow mode: %s was not written to the scene" % plan.candidate_id)
        elif not receipt.ok:
            self.note("apply failed: %s" % receipt.detail)
        if receipt.ok and self.config.scene_path:
            self.load_scene()

        # 6. canonical renders
        specs = list(context["views"])
        round_.views = self.render_views(state, round_, specs)

        # 7. deterministic checks on the editable scene, then 8. the visual review
        round_.checks = self.run_checks(round_.views, specs)
        round_.review = self.run_review(round_.views)
        round_.score = round_.review.score() if round_.review else None

        # 9. route the next pass, with the deterministic layer deciding what is even offerable
        round_.route = self.route_next(state, round_)
        return self._with_unrun_checks(state, round_, context)

    # ---- the measurable half of a round -------------------------------------------------
    def render_views(self, state: RunState, round_: Round, specs: List[Any]) -> List[ViewRender]:
        outputs: List[ViewRender] = []
        directory = os.path.join(self.config.run_dir, state.task_id, "renders",
                                 "round-%02d" % round_.index)
        hero = first_object(self.snapshot, hero_pattern(self.contract)) or None
        for spec in specs:
            supplied = self.config.existing_views.get(spec.name)
            if supplied and os.path.exists(supplied):
                outputs.append(ViewRender(
                    name=spec.name, path=supplied, camera=spec.camera, rendered=True,
                    fingerprint=spec.fingerprint(),
                    detail="existing render supplied as evidence; this run did not produce it"))
                continue
            path = os.path.join(directory, "%s.png" % spec.name)
            try:
                record = self.render.render_view(
                    view_name=spec.name, camera=spec.camera, output_path=path,
                    user_prompt=self.config.user_prompt, resolution=spec.resolution,
                    frame_object=hero, engine=spec.engine, samples=spec.samples,
                    film_transparent=spec.film_transparent, look=spec.look)
            except Exception as error:
                record = ViewRender(name=spec.name, path=path, camera=spec.camera,
                                    detail="render raised: %s" % error)
            outputs.append(record)
        return outputs

    def run_checks(self, views: List[ViewRender], specs: List[Any]) -> HardChecks:
        checks = run_scene_checks(self.snapshot, self.contract, views,
                                  self.config.scene_path or "",
                                  self.sources.get("scene_read_error"))
        # Comparability: a render made with different settings is not evidence about the same view.
        by_name = {spec.name: spec for spec in specs}
        for record in views:
            spec = by_name.get(record.name)
            if spec is None or not record.rendered:
                continue
            if record.detail.startswith("existing render supplied"):
                # The image's own metadata is checked against the view it is standing in for, so a
                # supplied render cannot be passed off as evidence about a different camera.
                metadata = render_metadata(record.path or "")
                camera = metadata.get("camera")
                resolution = metadata.get("resolution")
                problems: List[str] = []
                if camera and camera != spec.camera:
                    problems.append("was rendered with camera %r, but the view declares %r"
                                    % (camera, spec.camera))
                if resolution and list(resolution) != list(spec.resolution):
                    problems.append("is %sx%s, but the view declares %sx%s"
                                    % (resolution[0], resolution[1], spec.resolution[0],
                                       spec.resolution[1]))
                if problems:
                    checks.add("view_source:%s" % record.name, CheckStatus.FAIL.value,
                               "the supplied render " + "; ".join(problems), spec.fingerprint(),
                               metadata)
                else:
                    checks.add("view_source:%s" % record.name, CheckStatus.PASS.value,
                               "supplied render matches the declared camera and resolution"
                               if metadata.get("has_metadata") else
                               "supplied render carries no renderer metadata; only the file's "
                               "presence was verified", spec.fingerprint(), metadata)
                continue
            drift = settings_drift(spec.fingerprint(), fingerprint_of(record.fingerprint or {}))
            if drift:
                checks.add("view_comparable:%s" % record.name, CheckStatus.FAIL.value,
                           "; ".join(drift), spec.fingerprint(), record.fingerprint)
            else:
                checks.add("view_comparable:%s" % record.name, CheckStatus.PASS.value,
                           "rendered with the declared settings", spec.fingerprint(),
                           record.fingerprint)
        return checks

    def run_review(self, views: List[ViewRender]) -> VisualReview:
        review = self.reviewer.review(views, self.contract)
        path = self.config.__dict__.get("external_findings_path")
        if path and os.path.exists(path):
            extra = load_findings(path, [view.name for view in views])
            review = merge_reviews(review, VisualReview(
                views_reviewed=[view.name for view in views], findings=extra,
                reviewer=os.path.basename(path),
                notes="findings supplied by an external reviewer"))
        return review

    def route_next(self, state: RunState, round_: Round) -> Decision:
        checks = round_.checks
        review = round_.review
        stalled = state.stalled(self.config.stall_min_delta)
        routes = allowed_routes(state, checks, review, stalled)
        hard_failures = [result.name for result in (checks.failures() if checks else [])]
        pack = build_evidence_pack(state, self.contract, self.snapshot, checks=checks, review=review,
                                   allowed_ops=sorted(self.policy.allowed_ops))
        pack["round"] = round_.index
        pack["applied"] = round_.applied
        pack["apply_detail"] = round_.apply_detail[:240]
        pack["stalled"] = stalled
        priority = priority_options(checks, review)
        pack["priority_options"] = priority
        decision = self.laya.choose_next_step(
            pack, allowed_routes=routes, priority_options=priority or None,
            hard_failures=hard_failures[:8],
            fallback_reason="the revision budget is spent; a person must decide")
        # What the model *asked for* is worth recording even when the answer never became the
        # route. A decision log reading "route=human_review" otherwise hides the case that matters
        # most: a model that wanted to sign the work off while the measured review shows failing
        # views. The gate refusing it is correct, but the disagreement is the finding.
        asked_for = ((decision.native.get("answers") or {}).get("route") or {}).get("label")
        failing_views = sorted({finding.view for finding in (review.findings if review else [])
                                if finding.result == "fail" and finding.view})
        if asked_for == ROUTE_LABELS[Route.ACCEPT.value] and failing_views:
            decision.guardrails.append(
                "the model asked to accept, but measured findings fail on %s"
                % ", ".join(failing_views))

        if decision.route == Route.ACCEPT.value:
            # Double guard: acceptance requires the deterministic half to agree, whatever the model
            # says. The doc states this condition explicitly. It stays here even though
            # `allowed_routes` already withholds accept, because this is the one route that ends
            # the workflow with a claim about the scene.
            if not (checks and checks.passed()) or (review and review.high_severity()):
                decision.guardrails.append(
                    "accept withheld: mandatory checks or high-severity findings disagree")
                decision.route = (Route.REVISE.value if Route.REVISE.value in routes
                                  else Route.HUMAN_REVIEW.value)
        return decision

    # ---- round bookkeeping ---------------------------------------------------------------
    def _unrun_checks(self, detail: str) -> HardChecks:
        """When a round stops before validation, say so per requirement instead of saying nothing."""
        checks = HardChecks()
        for requirement in self.contract.requirements:
            label = requirement.pattern or ",".join(requirement.views) or requirement.path or "scene"
            checks.add("%s:%s" % (requirement.kind, label), CheckStatus.NOT_RUN.value,
                       detail[:300], mandatory=requirement.mandatory)
        return checks

    def _with_unrun_checks(self, state: RunState, round_: Round,
                           context: Dict[str, Any]) -> Round:
        """Finish a round: record it whole, and never leave a check silently absent."""
        if round_.checks is None:
            reason = round_.route.reason if round_.route else "the round stopped before validation"
            detail = "not validated: %s" % reason
            if not round_.applied:
                detail = "no scene write was made, so nothing was validated: %s" % reason
            round_.checks = self._unrun_checks(detail)
        if round_.review is None:
            rendered = any(view.rendered for view in round_.views)
            round_.review = VisualReview(
                views_reviewed=[view.name for view in round_.views if view.rendered],
                findings=[], reviewer=self.reviewer.name,
                notes="no visual claim was made because no view was rendered" if not rendered else "")
            # A round with no rendered evidence has no score. Scoring it 1.0 would read as a
            # perfect result when nothing was measured at all.
            round_.score = round_.review.score() if rendered else None
        round_.finished_at = _now()
        state.rounds.append(round_)
        state.log(
            "round_finished", index=round_.index, applied=round_.applied,
            plan=round_.plan.candidate_id if round_.plan else None,
            decision=round_.decision.route if round_.decision else None,
            decision_source=round_.decision.source if round_.decision else None,
            route=round_.route.route if round_.route else None,
            route_source=round_.route.source if round_.route else None,
            score=round_.score,
            mandatory_failures=[result.name for result in round_.checks.failures()],
            checks_not_run=[result.name for result in round_.checks.not_run()][:12],
            check_transcript=self.render.transcript()[-4:] if hasattr(self.render, "transcript")
            else None,
        )
        return round_

    # ---- the opening assessment ---------------------------------------------------------
    def assess(self, state: RunState) -> Round:
        """Read the current scene and establish evidence before proposing anything.

        Doc, steps 3-4: "Read the actual scene context" and "Build a focused evidence pack". No
        plan is proposed here and nothing is written, so this round does not consume the revision
        budget: it exists so the first proposal is grounded in the real scene and its real renders
        rather than in a guess.
        """
        round_ = Round(index=0)
        context = self.context(state)
        specs = list(context["views"])
        round_.views = self.render_views(state, round_, specs)
        round_.checks = self.run_checks(round_.views, specs)
        round_.review = self.run_review(round_.views)
        round_.score = round_.review.score()
        round_.apply_detail = "opening assessment: the scene was read and validated; no change " \
                              "was proposed or applied"
        round_.route = self.route_next(state, round_)
        state.log(
            "assessed",
            scene_revision=self.snapshot.revision if self.snapshot else None,
            mandatory_failures=[result.name for result in round_.checks.failures()],
            checks_not_run=[result.name for result in round_.checks.not_run()][:8],
            views_rendered=[view.name for view in round_.views if view.rendered],
            views_supplied=[view.name for view in round_.views
                            if view.detail.startswith("existing render supplied")],
            score=round_.score,
        )
        return self._with_unrun_checks(state, round_, context)

    # ---- the loop -----------------------------------------------------------------------
    def run(self, state: Optional[RunState] = None,
            brief: Optional[Dict[str, Any]] = None) -> RunState:
        """Run the bounded control loop and always return a terminal state.

        Four endings are possible and every one of them is recorded: ``accepted``,
        ``needs_human_review``, ``budget_exhausted`` and ``blocked``. The loop cannot spin: it is
        bounded by the contract's revision budget, and every round either applies a plan or stops.
        """
        if state is None:
            state = self.start(brief)
        previous: Optional[Round] = state.current_round
        if previous is None or not state.evidence_ready():
            previous = self.assess(state)
            baseline_route = previous.route.route if previous.route else None
            if baseline_route == Route.ACCEPT.value:
                state.outcome = "accepted"
                state.outcome_detail = ("the scene already satisfies every mandatory check and "
                                        "carries no high-severity finding; nothing was changed")
                self.note(state.outcome_detail)
                state.log("run_finished", outcome=state.outcome, detail=state.outcome_detail,
                          rounds=state.rounds_used, scores=state.scores())
                return state
            if baseline_route == Route.HUMAN_REVIEW.value and not state.evidence_ready():
                state.outcome = "blocked"
                state.human_required = True
                state.escalated = True
                state.outcome_detail = previous.route.reason if previous.route else "blocked"
                self.note(state.outcome_detail)
                state.log("run_finished", outcome=state.outcome, detail=state.outcome_detail,
                          rounds=state.rounds_used, scores=state.scores())
                return state
        while not state.budget_exhausted():
            round_ = self.run_round(state, previous)
            previous = round_
            route = round_.route.route if round_.route else Route.HUMAN_REVIEW.value
            if route == Route.ACCEPT.value:
                state.outcome = "accepted"
                state.outcome_detail = ("accepted after %d round(s): every mandatory check passed "
                                        "and no high-severity finding remained"
                                        % state.rounds_used)
                self.note("accepted after %d round(s)" % state.rounds_used)
                break
            if route == Route.HUMAN_REVIEW.value:
                state.outcome = "needs_human_review"
                state.human_required = True
                state.escalated = True
                state.outcome_detail = round_.route.reason if round_.route else "escalated"
                self.note("escalated to a person: %s" % state.outcome_detail)
                break
            if round_.plan is not None and not round_.plan.ops:
                # A branch or revise route with nothing to do would loop forever. Stop instead.
                state.outcome = "needs_human_review"
                state.human_required = True
                state.escalated = True
                state.outcome_detail = ("the loop had no operation left to apply while routing %s"
                                        % route)
                self.note(state.outcome_detail)
                break
            if route == Route.BRANCH.value:
                state.log("branching", round=round_.index,
                          branch_label=round_.plan.branch_label if round_.plan else None)
        else:
            state.outcome = "budget_exhausted"
            state.human_required = True
            state.escalated = True
            remaining = [result.name for result in (previous.checks.failures()
                                                    if previous and previous.checks else [])]
            state.outcome_detail = (
                "revision budget of %d round(s) is spent with %d mandatory check(s) still failing: %s"
                % (state.max_rounds(), len(remaining), ", ".join(remaining) or "none"))
            self.note(state.outcome_detail)
        state.log("run_finished", outcome=state.outcome, detail=state.outcome_detail,
                  rounds=state.rounds_used, scores=state.scores())
        return state

    def report(self, state: RunState) -> Dict[str, Any]:
        """The delivery report: what ran, what did not, and what remains unresolved."""
        return final_report(state, shadow_mode=self.policy.shadow_mode,
                            trace=list(self.trace))

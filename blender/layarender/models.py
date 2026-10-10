"""Normalized workflow records for the Laya-gated 3D scene control plane.

These types are the workflow's own vocabulary. They are deliberately kept separate from
Laya's native payloads (``laya.decide`` results) and from the Render MCP Designer's tool
arguments, so a change in either native interface cannot leak into the workflow logic.

Nothing here calls a model, an MCP server or the filesystem. Serialization is plain JSON so a
run state can be written to disk, diffed, and replayed.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = "layarender/1"


class Route(str, Enum):
    """The four outcomes the workflow can route a candidate scene to.

    ``REVISE``  apply a small, located edit and render again.
    ``BRANCH``  stop editing this candidate and try a genuinely different direction.
    ``ACCEPT``  finish: every mandatory check passed and no high-severity finding remains.
    ``HUMAN_REVIEW``  stop the loop and hand the evidence to a person.
    """

    REVISE = "revise"
    BRANCH = "branch"
    ACCEPT = "accept"
    HUMAN_REVIEW = "human_review"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_RUN = "not_run"


class DecisionSource(str, Enum):
    """Where a routing decision came from. Recorded on every decision.

    ``LAYA`` is never inferred: only a parsed answer from a real Laya call sets ``LAYA``.
    ``POLICY`` is the deterministic backstop used when hard checks already decide the question.
    ``UNAVAILABLE`` means Laya could not be reached or answered unsafely, and the workflow
    failed closed -- exactly the doc's "Laya times out or returns malformed output" branch.
    """

    LAYA = "laya"
    POLICY = "policy"
    UNAVAILABLE = "unavailable"
    HUMAN = "human"


def _now() -> float:
    return round(time.time(), 3)


def _new_id(prefix: str) -> str:
    return "%s-%s" % (prefix, uuid.uuid4().hex[:10])


@dataclass
class Finding:
    """One located observation about a rendered view.

    A finding is only actionable when it names a view and either an object or an image region.
    :meth:`is_located` enforces that, so vague criticism ("make it better") is rejected by the
    workflow instead of being turned into a broad scene edit.
    """

    criterion: str
    result: str
    severity: str = Severity.MEDIUM.value
    view: Optional[str] = None
    affected_object: Optional[str] = None
    evidence: str = ""
    suggested_fix: Optional[str] = None
    confidence: Optional[float] = None
    region: Optional[List[float]] = None  # [x, y, w, h] in normalized view coordinates
    measured: bool = False
    source: str = "reviewer"

    def is_located(self) -> bool:
        if not self.view:
            return False
        return bool(self.affected_object) or bool(self.region)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CheckResult:
    """One deterministic check. ``status`` is never guessed: it is ``not_run`` until it runs."""

    name: str
    status: str = CheckStatus.NOT_RUN.value
    detail: str = ""
    expected: Any = None
    actual: Any = None
    mandatory: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HardChecks:
    """The deterministic half of the review: measurable scene and delivery facts."""

    results: List[CheckResult] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "", expected: Any = None,
            actual: Any = None, mandatory: bool = True) -> CheckResult:
        result = CheckResult(name=name, status=status, detail=detail, expected=expected,
                             actual=actual, mandatory=mandatory)
        self.results.append(result)
        return result

    def failures(self, mandatory_only: bool = True) -> List[CheckResult]:
        return [r for r in self.results
                if r.status == CheckStatus.FAIL.value and (r.mandatory or not mandatory_only)]

    def not_run(self) -> List[CheckResult]:
        return [r for r in self.results if r.status == CheckStatus.NOT_RUN.value]

    def passed(self, mandatory_only: bool = True) -> bool:
        if mandatory_only and self.failures(True):
            return False
        if not mandatory_only and self.failures(False):
            return False
        return True

    def get(self, name: str) -> Optional[CheckResult]:
        for result in self.results:
            if result.name == name:
                return result
        return None

    def summary(self) -> Dict[str, str]:
        return {r.name: r.status for r in self.results}

    def to_dict(self) -> Dict[str, Any]:
        return {"results": [r.to_dict() for r in self.results]}


@dataclass
class VisualReview:
    """The visual half of the review, tied to the canonical views that were rendered."""

    views_reviewed: List[str] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    reviewer: str = "measured"
    notes: str = ""

    def located_findings(self) -> List[Finding]:
        return [f for f in self.findings if f.is_located()]

    def unlocated_findings(self) -> List[Finding]:
        return [f for f in self.findings if not f.is_located()]

    def high_severity(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == Severity.HIGH.value]

    def score(self) -> float:
        """A bounded, comparable quality score in [0, 1] used to detect stalled candidates.

        Deterministic and monotonic in what the workflow can actually measure: high-severity
        issues cost more than low ones, and unlocated findings are discounted rather than
        silently dropped (they still carry signal, but they are not actionable edits).
        """
        penalty = 0.0
        weights = {Severity.HIGH.value: 3.0, Severity.MEDIUM.value: 1.0, Severity.LOW.value: 0.25}
        for finding in self.findings:
            if finding.result != "fail":
                continue
            weight = weights.get(finding.severity, 1.0)
            penalty += weight if finding.is_located() else weight * 0.5
        return round(max(0.0, 1.0 - penalty / 10.0), 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "views_reviewed": list(self.views_reviewed),
            "findings": [f.to_dict() for f in self.findings],
            "reviewer": self.reviewer,
            "notes": self.notes,
            "score": self.score(),
        }


@dataclass
class PatchOp:
    """One bounded scene operation proposed by the creative model.

    ``op`` is a workflow-level verb, not a tool name. The policy layer maps it to an allowed
    Render MCP Designer tool; an op with no mapping is rejected before anything is executed.
    """

    op: str
    target: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    expected_result: str = ""
    reversible: bool = True
    destructive: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PatchPlan:
    """A candidate change set: bounded, reason-bearing, and preflighted before execution."""

    candidate_id: str
    intent: str = ""
    ops: List[PatchOp] = field(default_factory=list)
    addresses: List[str] = field(default_factory=list)  # criteria or check names this plan targets
    branch_label: Optional[str] = None
    proposed_by: str = "creative_model"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "intent": self.intent,
            "ops": [op.to_dict() for op in self.ops],
            "addresses": list(self.addresses),
            "branch_label": self.branch_label,
            "proposed_by": self.proposed_by,
        }


@dataclass
class PreflightResult:
    """The gate between a proposal and an execution. ``ok`` is required to apply anything."""

    ok: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    requires_approval: bool = False
    approval_reason: str = ""
    checked: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Decision:
    """A normalized routing decision: what to do next, with confidence and provenance."""

    route: str
    confidence: Optional[float] = None
    source: str = DecisionSource.POLICY.value
    reason: str = ""
    priority_criterion: Optional[str] = None
    guardrails: List[str] = field(default_factory=list)
    native: Dict[str, Any] = field(default_factory=dict)
    latency_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ViewRender:
    """A canonical view that was actually rendered (or an explicit record that it was not)."""

    name: str
    path: Optional[str] = None
    rendered: bool = False
    camera: Optional[str] = None
    fingerprint: Dict[str, Any] = field(default_factory=dict)
    detail: str = ""
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Round:
    """One pass of the control loop, kept whole so the run can be audited and replayed."""

    index: int
    plan: Optional[PatchPlan] = None
    preflight: Optional[PreflightResult] = None
    decision: Optional[Decision] = None
    applied: bool = False
    apply_detail: str = ""
    views: List[ViewRender] = field(default_factory=list)
    checks: Optional[HardChecks] = None
    review: Optional[VisualReview] = None
    route: Optional[Decision] = None
    score: Optional[float] = None
    started_at: float = field(default_factory=_now)
    finished_at: Optional[float] = None
    human_approved: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "plan": self.plan.to_dict() if self.plan else None,
            "preflight": self.preflight.to_dict() if self.preflight else None,
            "decision": self.decision.to_dict() if self.decision else None,
            "applied": self.applied,
            "apply_detail": self.apply_detail,
            "views": [v.to_dict() for v in self.views],
            "checks": self.checks.to_dict() if self.checks else None,
            "review": self.review.to_dict() if self.review else None,
            "route": self.route.to_dict() if self.route else None,
            "score": self.score,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "human_approved": self.human_approved,
        }


@dataclass
class RunState:
    """The versioned record the doc calls the evidence pack.

    ``brief``, ``contract`` and ``scene`` are the inputs; ``rounds`` and ``history`` are what
    happened; ``budget`` is the only thing that bounds the loop.
    """

    task_id: str = field(default_factory=lambda: _new_id("scene-run"))
    schema_version: str = SCHEMA_VERSION
    created_at: float = field(default_factory=_now)
    brief: Dict[str, Any] = field(default_factory=dict)
    contract: Dict[str, Any] = field(default_factory=dict)
    scene: Dict[str, Any] = field(default_factory=dict)
    brief_version: int = 1
    contract_version: int = 1
    scene_revision: str = ""
    allowed_operations: List[str] = field(default_factory=list)
    budget: Dict[str, Any] = field(default_factory=dict)
    rounds: List[Round] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    outcome: Optional[str] = None
    outcome_detail: str = ""
    escalated: bool = False
    human_required: bool = False
    modes: Dict[str, Any] = field(default_factory=dict)
    versions: Dict[str, Any] = field(default_factory=dict)

    @property
    def current_round(self) -> Optional[Round]:
        return self.rounds[-1] if self.rounds else None

    @property
    def rounds_used(self) -> int:
        return len(self.rounds)

    def revision_rounds(self) -> int:
        """Rounds that proposed or applied a change.

        The budget bounds *revisions*, not evidence gathering: the doc's max_revision_rounds is
        about how many times the scene may be changed, so the opening assessment round -- which
        reads and validates the scene without proposing anything -- does not consume it.
        """
        return sum(1 for round_ in self.rounds if round_.plan is not None or round_.applied)

    def evidence_ready(self) -> bool:
        """True once some round has produced checks or a visual review to decide from."""
        return any((round_.checks is not None) or (round_.review is not None)
                   for round_ in self.rounds)

    def max_rounds(self, default: int = 3) -> int:
        """The revision budget.

        The run's own ``budget`` wins over the contract's limit: it is what the orchestrator
        actually recorded at start-up, so a resumed or replayed state is bounded by the budget it
        was started with rather than by whatever the contract file says today.
        """
        limits = (self.contract or {}).get("scene_limits") or {}
        candidates = []
        if isinstance(self.budget, dict):
            candidates.append(self.budget.get("max_rounds"))
        candidates.append(limits.get("max_revision_rounds"))
        for value in candidates:
            if value is None:
                continue
            try:
                return max(1, int(value))
            except (TypeError, ValueError):
                continue
        return default

    def budget_exhausted(self, default: int = 3) -> bool:
        return self.revision_rounds() >= self.max_rounds(default)

    def scores(self) -> List[Optional[float]]:
        return [r.score for r in self.rounds]

    def best_score(self) -> Optional[float]:
        values = [s for s in self.scores() if s is not None]
        return max(values) if values else None

    def stalled(self, min_delta: float = 0.02, window: int = 2) -> bool:
        """True when the last ``window + 1`` comparable scores stopped improving.

        This is the ``no_material_improvement(state.history)`` rule: the workflow stops repeating
        the same adjustment and either branches or escalates instead.
        """
        values = [s for s in self.scores() if s is not None]
        if len(values) < window + 1:
            return False
        recent = values[-(window + 1):]
        return (max(recent) - recent[0]) < min_delta

    def log(self, event: str, **fields: Any) -> None:
        entry = {"at": _now(), "event": event}
        entry.update(fields)
        self.history.append(entry)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "brief": self.brief,
            "contract": self.contract,
            "scene": self.scene,
            "brief_version": self.brief_version,
            "contract_version": self.contract_version,
            "scene_revision": self.scene_revision,
            "allowed_operations": list(self.allowed_operations),
            "budget": self.budget,
            "rounds": [r.to_dict() for r in self.rounds],
            "history": self.history,
            "outcome": self.outcome,
            "outcome_detail": self.outcome_detail,
            "escalated": self.escalated,
            "human_required": self.human_required,
            "modes": self.modes,
            "versions": self.versions,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)


def load_run_state(path: str) -> RunState:
    """Read a run state written by :meth:`RunState.to_json`."""
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    state = RunState(
        task_id=data.get("task_id", _new_id("scene-run")),
        schema_version=data.get("schema_version", SCHEMA_VERSION),
        created_at=data.get("created_at", _now()),
        brief=data.get("brief", {}),
        contract=data.get("contract", {}),
        scene=data.get("scene", {}),
        brief_version=data.get("brief_version", 1),
        contract_version=data.get("contract_version", 1),
        scene_revision=data.get("scene_revision", ""),
        allowed_operations=list(data.get("allowed_operations", [])),
        budget=data.get("budget", {}),
        history=list(data.get("history", [])),
        outcome=data.get("outcome"),
        outcome_detail=data.get("outcome_detail", ""),
        escalated=data.get("escalated", False),
        human_required=data.get("human_required", False),
        modes=data.get("modes", {}),
        versions=data.get("versions", {}),
    )
    for raw in data.get("rounds", []):
        round_ = Round(index=raw.get("index", 0))
        if raw.get("plan"):
            plan = raw["plan"]
            round_.plan = PatchPlan(
                candidate_id=plan.get("candidate_id", ""),
                intent=plan.get("intent", ""),
                ops=[PatchOp(**op) for op in plan.get("ops", [])],
                addresses=list(plan.get("addresses", [])),
                branch_label=plan.get("branch_label"),
                proposed_by=plan.get("proposed_by", "creative_model"),
            )
        if raw.get("preflight"):
            round_.preflight = PreflightResult(**raw["preflight"])
        if raw.get("decision"):
            round_.decision = Decision(**raw["decision"])
        if raw.get("route"):
            round_.route = Decision(**raw["route"])
        round_.applied = raw.get("applied", False)
        round_.apply_detail = raw.get("apply_detail", "")
        round_.views = [ViewRender(**view) for view in raw.get("views", [])]
        if raw.get("checks"):
            checks = HardChecks()
            checks.results = [CheckResult(**item) for item in raw["checks"].get("results", [])]
            round_.checks = checks
        if raw.get("review"):
            review = raw["review"]
            round_.review = VisualReview(
                views_reviewed=list(review.get("views_reviewed", [])),
                findings=[Finding(**finding) for finding in review.get("findings", [])],
                reviewer=review.get("reviewer", "measured"),
                notes=review.get("notes", ""),
            )
        round_.score = raw.get("score")
        round_.started_at = raw.get("started_at", _now())
        round_.finished_at = raw.get("finished_at")
        round_.human_approved = raw.get("human_approved")
        state.rounds.append(round_)
    return state

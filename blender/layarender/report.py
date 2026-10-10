"""The final report.

Doc, section 4 step 12: "Provide the editable scene/project reference and requested renders or
exports when available; summarize changes, validation actually performed, remaining issues, and
delivery limitations. Do not claim an export or check passed unless it ran."

That last sentence is the whole design of this module. Every summary it produces is a partition
of records that actually exist in the run state:

* checks are split into ``ran`` (pass or fail) and ``not_run``;
* findings are split into ``measured`` (a number was taken from a render) and ``judged``
  (a reviewer's opinion, which the workflow never treats as proof);
* renders are split into files that exist on disk and views that were only recorded;
* unresolved mandatory failures are listed by name.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .models import CheckStatus, Severity, RunState


def _round_summary(round_: Any) -> Dict[str, Any]:
    checks = round_.checks
    review = round_.review
    return {
        "index": round_.index,
        "plan": round_.plan.candidate_id if round_.plan else None,
        "intent": round_.plan.intent if round_.plan else None,
        "operations": [op.op for op in (round_.plan.ops if round_.plan else [])],
        "targets": sorted({op.target for op in (round_.plan.ops if round_.plan else []) if op.target}),
        "preflight_ok": round_.preflight.ok if round_.preflight else None,
        "requires_approval": round_.preflight.requires_approval if round_.preflight else None,
        "applied": round_.applied,
        "apply_detail": round_.apply_detail,
        "gate": round_.decision.to_dict() if round_.decision else None,
        "route": round_.route.to_dict() if round_.route else None,
        "score": round_.score,
        "checks": checks.summary() if checks else {},
        "views_rendered": [view.name for view in round_.views if view.rendered],
        "findings": [finding.to_dict() for finding in (review.findings if review else [])],
    }


def _next_action(rounds: List[Any], measured: List[Dict[str, Any]],
                 judged: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """What the evidence says to do next, in the model's own words where it was confident.

    A run that ends ``needs_human_review`` is only useful to a person if it says what to look at.
    The model's route answer may be the weakest number in the run while its priority answer --
    which failing criterion to fix first -- can be its strongest, because the two questions have
    very different difficulty. Reporting only the route throws that away, so the priority is
    resolved back through the criteria that were actually offered and printed beside it.

    The signal is looked up across every round, most recent first, not just the final one: a gate
    that fails closed replaces the route with ``human_review`` and asks no priority question, so
    the model's one strong, actionable answer usually belongs to an earlier round.
    """
    decisions: List[Any] = []
    indexes: List[Any] = []
    for round_ in rounds:
        decision = round_.route or round_.decision
        if decision is not None:
            decisions.append(decision)
            indexes.append(getattr(round_, "index", None))
    if not decisions:
        return None

    with_priority = [position for position, decision in enumerate(decisions)
                     if decision.priority_criterion]
    chosen = with_priority[-1] if with_priority else len(decisions) - 1
    primary = decisions[chosen]
    answers = (primary.native or {}).get("answers") or {}
    if not (answers.get("route") or {}).get("label"):
        # The route label normally lives on the same payload as the priority answer; if the
        # primary decision carries neither, fall back to the most recent route answer anywhere.
        for decision in reversed(decisions):
            candidate = (decision.native or {}).get("answers") or {}
            if (candidate.get("route") or {}).get("label"):
                answers = candidate
                break
    offered = ((primary.native or {}).get("questions") or {}).get("priority") or {}
    priority = primary.priority_criterion
    priority_answer = answers.get("priority") or {}
    failing_views = sorted({finding.get("view") for finding in measured + judged
                            if finding.get("result") == "fail" and finding.get("view")})
    return {
        "from_round": indexes[chosen],
        "route": primary.route,
        "route_source": primary.source,
        "route_runner": (primary.native or {}).get("runner"),
        "route_confidence": primary.confidence,
        "model_asked_for": (answers.get("route") or {}).get("label"),
        "priority_criterion": priority,
        "priority_offered_as": (offered.get("criteria") or {}).get(priority) if priority else None,
        "priority_confidence": priority_answer.get("answer_confidence"),
        "views_with_failing_findings": failing_views,
        "guardrails": list(primary.guardrails),
    }


def final_report(state: RunState, shadow_mode: bool = True,
                 trace: Optional[List[str]] = None) -> Dict[str, Any]:
    """Build the delivery report from the run state, claiming nothing that did not happen."""
    rounds = state.rounds
    last = rounds[-1] if rounds else None

    ran: Dict[str, str] = {}
    not_run: Dict[str, str] = {}
    failed: Dict[str, str] = {}
    for round_ in rounds:
        if not round_.checks:
            continue
        for result in round_.checks.results:
            if result.status == CheckStatus.NOT_RUN.value:
                not_run[result.name] = result.detail
            else:
                ran[result.name] = result.status
                if result.status == CheckStatus.FAIL.value:
                    failed[result.name] = result.detail

    measured: List[Dict[str, Any]] = []
    judged: List[Dict[str, Any]] = []
    for round_ in rounds:
        for finding in (round_.review.findings if round_.review else []):
            (measured if finding.measured else judged).append(finding.to_dict())

    last_summary = last.checks.summary() if last and last.checks else {}
    unresolved = [{"name": name, "detail": detail} for name, detail in failed.items()
                  if last_summary.get(name) == CheckStatus.FAIL.value]
    high_severity = [finding for finding in measured + judged
                     if finding.get("severity") == Severity.HIGH.value
                     and finding.get("result") == "fail"]

    renders: List[Dict[str, Any]] = []
    for round_ in rounds:
        for view in round_.views:
            exists = bool(view.path and os.path.exists(view.path))
            renders.append({
                "view": view.name, "round": round_.index, "path": view.path,
                "rendered": bool(view.rendered and exists), "detail": view.detail,
                "fingerprint": view.fingerprint or {},
                "stats": view.stats or {},
            })

    delivery = {
        "editable_scene": (state.contract or {}).get("delivery", {}).get("editable_scene"),
        "scene_source": state.scene.get("source"),
        "scene_revision": state.scene_revision,
        "renders": renders,
        "renders_on_disk": [render["path"] for render in renders if render["rendered"]],
    }

    limitations: List[str] = []
    if shadow_mode:
        limitations.append(
            "shadow mode: no operation was written to the scene, so every check describes the "
            "scene as it was read, not a changed scene")
    if any(render["detail"] for render in renders if not render["rendered"]):
        limitations.append("at least one required view has no image on disk")
    if not_run:
        limitations.append("%d check(s) never ran; they are listed, not counted as passes"
                           % len(not_run))
    if state.outcome == "budget_exhausted":
        limitations.append("the revision budget ended the run before the scene converged")
    if judged and not measured:
        limitations.append("every visual finding is a reviewer's judgement; none were measured")

    return {
        "task_id": state.task_id,
        "goal": (state.contract or {}).get("goal"),
        "outcome": state.outcome or "not_finished",
        "outcome_detail": state.outcome_detail,
        "human_required": state.human_required,
        "escalated": state.escalated,
        "rounds_used": state.rounds_used,
        "budget": state.budget,
        "scores": state.scores(),
        "checks_ran": ran,
        "checks_not_run": not_run,
        "checks_failed": failed,
        "unresolved_mandatory_failures": unresolved,
        "measured_findings": measured,
        "judged_findings": judged,
        "high_severity_findings": high_severity,
        "delivery": delivery,
        "next_action": _next_action(rounds, measured, judged),
        "rounds": [_round_summary(round_) for round_ in rounds],
        "versions": state.versions,
        "modes": state.modes,
        "history": state.history,
        "trace": list(trace or []),
        "limitations": limitations,
    }


def render_report_text(report: Dict[str, Any]) -> str:
    """A short human-readable rendering of :func:`final_report`."""
    lines: List[str] = []
    lines.append("task %s" % report.get("task_id"))
    lines.append("goal: %s" % report.get("goal"))
    lines.append("outcome: %s -- %s" % (report.get("outcome"), report.get("outcome_detail")))
    lines.append("rounds used: %s of %s" % (report.get("rounds_used"),
                                            (report.get("budget") or {}).get("max_rounds")))
    action = report.get("next_action") or {}
    if action.get("priority_criterion"):
        lines.append("")
        lines.append("next action (what the evidence points at):")
        lines.append("  highest-priority criterion : %s" % action["priority_criterion"])
        if action.get("priority_offered_as"):
            lines.append("  described as               : %s" % action["priority_offered_as"])
        if action.get("priority_confidence") is not None:
            lines.append("  the model's confidence here: %.3f"
                         % action["priority_confidence"])
        if action.get("views_with_failing_findings"):
            lines.append("  views with failing findings: %s"
                         % ", ".join(action["views_with_failing_findings"]))
        if action.get("model_asked_for"):
            # ``source`` is the decision the workflow finally acted on, which is ``unavailable``
            # whenever the gate fails closed. The runner is the honest provenance of the answer
            # itself, so the two are printed separately rather than one standing in for the other.
            provenance = action.get("route_runner") or action.get("route_source")
            lines.append("  the model's route answer   : %s (from %s, confidence %s)"
                         % (action["model_asked_for"], provenance,
                            action.get("route_confidence")))
    lines.append("")
    lines.append("checks that ran:")
    ran = report.get("checks_ran") or {}
    if ran:
        for name, status in ran.items():
            lines.append("  [%s] %s" % (status, name))
    else:
        lines.append("  (none)")
    lines.append("checks that did NOT run:")
    not_run = report.get("checks_not_run") or {}
    if not_run:
        for name, detail in not_run.items():
            lines.append("  [not_run] %s -- %s" % (name, detail))
    else:
        lines.append("  (none)")
    failures = report.get("unresolved_mandatory_failures") or []
    if failures:
        lines.append("")
        lines.append("unresolved mandatory failures:")
        for failure in failures:
            lines.append("  %s -- %s" % (failure["name"], failure["detail"]))
    measured = report.get("measured_findings") or []
    judged = report.get("judged_findings") or []
    lines.append("")
    lines.append("visual findings: %d measured, %d judged" % (len(measured), len(judged)))
    for finding in (measured + judged)[:12]:
        suggestion = finding.get("suggested_fix")
        suffix = " - %s" % suggestion if suggestion else ""
        lines.append("  [%s/%s] %s (%s)%s"
                     % (finding.get("severity"), finding.get("result"),
                        finding.get("criterion"), finding.get("view"), suffix))
    lines.append("")
    lines.append("routing decisions:")
    for round_ in report.get("rounds") or []:
        gate = round_.get("gate") or {}
        route = round_.get("route") or {}
        lines.append("  round %s: gate=%s (%s) route=%s (%s) score=%s"
                     % (round_.get("index"), gate.get("route"), gate.get("source"),
                        route.get("route"), route.get("source"), round_.get("score")))
        # The source alone cannot separate "the model was not reachable" from "the model
        # answered without enough confidence". Both fail closed, but they call for different
        # fixes, so the calibrated number the gate used and the reason are printed with them.
        for label, decision in (("gate", gate), ("route", route)):
            confidence = decision.get("confidence")
            reason = decision.get("reason") or ""
            if confidence is None and not reason:
                continue
            detail = []
            if confidence is not None:
                detail.append("confidence=%.3f" % confidence)
            if reason:
                detail.append(reason[:200])
            if label == "route":
                for guardrail in decision.get("guardrails") or []:
                    detail.append("guardrail: %s" % guardrail[:200])
            lines.append("      %s: %s" % (label, "; ".join(detail)))
    limitations = report.get("limitations") or []
    if limitations:
        lines.append("")
        lines.append("limitations:")
        for limitation in limitations:
            lines.append("  - %s" % limitation)
    return "\n".join(lines)

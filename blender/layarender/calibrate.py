"""Calibration for the confidence gate: measure, rather than assume, what Laya needs.

The brief's rollout stage 4 says to calibrate the model against your own evidence before letting
it gate writes, and Laya's own documentation says two things that make calibration unavoidable:

* "The base checkpoints are near chance on typed-decisions zero-shot."
* "Avoid boolean-word labels in choice questions... Use semantic labels or opaque labels."

The second warning is the dangerous one for this workflow. If Laya's answer follows a label's
*position* or its *wording* rather than the option it describes, then a route decision is not a
judgement about the scene at all -- it is a coin flip dressed as evidence, and a ``min_confidence``
gate would not catch it, because the model would be just as confident either way.

So this module measures three things, none of which resampling can answer:

1. **Determinism.** Repeated identical calls. Laya is greedy here, so this is a cheap assertion
   that the measurement below is of the model and not of sampling noise.
2. **Position invariance.** The same options in every order. The chosen *label* must not move
   when the options are shuffled. If it does, the answer tracks position and the decision is
   unusable no matter what confidence it reports.
3. **Wording invariance.** The same options with semantic labels, then with opaque ones
   (``option_a``...). Laya's documentation offers both as safe, so both are offered back.

It also tabulates the reported confidence so a threshold can be chosen from evidence: given the
model's own numbers on this project's real states, what fraction of decisions would clear a
given threshold, and what would the rest silently become?
"""
from __future__ import annotations

import itertools
from typing import Any, Dict, List, Optional

#: Opaque labels, for the wording probe. Laya's README names these as the alternative to
#: boolean labels, so a decision that only holds for semantic wording is a real finding.
OPAQUE_LABELS = ["option_a", "option_b", "option_c", "option_d"]

DEFAULT_THRESHOLDS = [0.30, 0.40, 0.50, 0.60, 0.70, 0.80]


def orderings(labels: List[str], limit: int = 8) -> List[List[str]]:
    """Every order of ``labels`` up to ``limit``, baselines first.

    Three options -- the workflow's own route set -- give six orders, which is small enough to
    enumerate rather than sample. More than that switches to rotations plus the reversal, which
    is enough to expose a positional preference without a combinatorial run time.
    """
    if len(labels) <= 1:
        return [list(labels)]
    if len(labels) <= 4:
        permutations = [list(order) for order in itertools.permutations(labels)]
    else:
        permutations = [list(labels), list(reversed(labels))]
        for shift in range(1, len(labels)):
            permutations.append(labels[shift:] + labels[:shift])
    return permutations[:max(limit, 1)]


def _ask(adapter: Any, state: Any, criteria_names: List[str], instructions: str,
         min_confidence: float, priority_options: Optional[List[str]] = None) -> Dict[str, Any]:
    """One real call whose option order is exactly ``criteria_names``."""
    criteria = {name: name.replace("_", " ") for name in criteria_names}
    questions: Dict[str, Dict[str, Any]] = {
        "route": {"type": "choice", "instructions": instructions, "criteria": criteria}
    }
    if priority_options:
        questions["priority"] = {
            "type": "choice",
            "instructions": "Which single failing criterion should be addressed first?",
            "criteria": {option: option.replace("_", " ") for option in priority_options},
        }
    outcome = adapter.evaluate_scene_state(state, questions=questions,
                                          allowed_routes=list(criteria_names))
    answer = outcome["answers"].get("route")
    return {
        "order": list(criteria_names),
        "label": answer.label if answer else None,
        "confidence": (answer.answer_confidence if answer and answer.answer_confidence is not None
                       else (answer.confidence if answer else None)),
        "probabilities": dict(answer.native.get("probabilities") or {}) if answer else {},
        "low_confidence": bool(answer.low_confidence) if answer else None,
        "reason": outcome.get("reason") or "",
        "latency_ms": outcome.get("latency_ms"),
    }


def calibrate_route(adapter: Any, state: Any, allowed_routes: List[str],
                    min_confidence: float = 0.60, priority_options: Optional[List[str]] = None,
                    thresholds: Optional[List[str]] = None,
                    repeat: int = 3, max_orderings: int = 8) -> Dict[str, Any]:
    """Probe the route question and report what the probe actually establishes.

    Every measurement is reported with the evidence behind it. A probe that could not run (no
    runner, or an unusable state) says so instead of returning an empty verdict that a caller
    might read as a pass.
    """
    from .adapters.laya_ai import ROUTE_DESCRIPTIONS, ROUTE_LABELS

    labels = [ROUTE_LABELS[route] for route in allowed_routes if route in ROUTE_LABELS]
    if not labels:
        return {"ok": False, "reason": "no usable route labels for %r" % (allowed_routes,)}
    if not adapter.active_runner():
        return {"ok": False, "reason": "no Laya runner is available, so nothing was measured"}

    instructions = ("Given the scene state and the structured review evidence, which single next "
                    "step is best for this 3D scene?")
    report: Dict[str, Any] = {"ok": True, "labels": labels, "repeat": repeat,
                              "min_confidence": min_confidence}

    # 1. Determinism: the probe below assumes the model is not sampled.
    repeats = [_ask(adapter, state, labels, instructions, min_confidence)
               for _ in range(max(2, repeat))]
    chosen = {entry["label"] for entry in repeats}
    vectors = {tuple(sorted(entry["probabilities"].items())) for entry in repeats}
    report["determinism"] = {
        "calls": len(repeats),
        "distinct_choices": sorted(label for label in chosen if label),
        "distinct_distributions": len(vectors),
        "deterministic": len(chosen) <= 1 and len(vectors) <= 1,
        "baseline": repeats[0],
    }

    # 2. Position invariance: shuffle the options and watch the chosen *label*.
    shuffled = [_ask(adapter, state, order, instructions, min_confidence)
                for order in orderings(labels, max_orderings)]
    positions = {tuple(entry["order"]): entry for entry in shuffled}
    baseline_order = tuple(labels)
    baseline_label = positions.get(baseline_order, {}).get("label")
    moved = [entry for entry in shuffled
             if entry["label"] is not None and entry["label"] != baseline_label]
    # The slot each answer occupied *within its own ordering*. This is what separates a model
    # that reads the options from one that reads the layout: a positional answer lands in the
    # same slot every time even though a different label sits there, so the slots are constant
    # while the labels are not. Indexing the chosen label in the *baseline* order instead would
    # measure where the answer would have sat had the options never moved, which is not the
    # question -- and would report a perfectly text-following model as positional.
    index_by_label = {name: position for position, name in enumerate(labels)}
    chosen_slots = []
    for entry in shuffled:
        if entry["label"] in entry["order"]:
            chosen_slots.append(entry["order"].index(entry["label"]))
    report["position"] = {
        "orderings_tested": len(shuffled),
        "baseline_label": baseline_label,
        "disagreeing_orderings": [
            {"order": entry["order"], "label": entry["label"],
             "confidence": entry["confidence"]} for entry in moved
        ],
        "invariant": not moved,
        "chosen_slots": chosen_slots,
        "single_slot_for_every_order": len(set(chosen_slots)) == 1 if chosen_slots else False,
    }

    # 3. Wording invariance: the same options under opaque labels.
    opaque = OPAQUE_LABELS[:len(labels)]
    relabelled = _ask(adapter, state, opaque, instructions, min_confidence)
    opaque_choice = relabelled["label"]
    report["wording"] = {
        "opaque_labels": opaque,
        "opaque_choice": opaque_choice,
        "opaque_confidence": relabelled["confidence"],
        # The opaque run can only corroborate the semantic one by position, because the labels
        # share no text. A confident opaque answer for a *different* position is the clearest
        # available signal that wording, not meaning, drove the choice.
        "consistent_with_position": (opaque_choice is not None
                                     and opaque_choice in opaque
                                     and opaque.index(opaque_choice)
                                     == (index_by_label.get(baseline_label, -1))),
        "probabilities": relabelled["probabilities"],
    }

    # 4. The threshold table: what the gate would do with the numbers the model just reported.
    distribution = repeats[0]["probabilities"]
    best = max(distribution.values()) if distribution else None
    table = []
    for threshold in (thresholds or DEFAULT_THRESHOLDS):
        cleared = best is not None and best >= threshold
        table.append({
            "threshold": threshold,
            "clears": cleared,
            "reported_confidence": best,
            "outcome": ("Laya routes %s" % repeats[0]["label"]) if cleared
            else "fails closed to a person",
        })
    report["confidence"] = {
        "reported": best,
        "distribution": distribution,
        "thresholds": table,
    }

    # The verdict, stated as the conditions it actually verified.
    report["verdict"] = _verdict(report, min_confidence)
    return report


def _verdict(report: Dict[str, Any], min_confidence: float) -> Dict[str, Any]:
    """Turn the measurements into the one sentence a person needs.

    Trustworthy requires the answer to survive shuffling *and* clear the gate. Either failure is
    named, because they call for different fixes: a positional answer needs different labels,
    while a low confidence needs a calibrated threshold or a person.
    """
    position_ok = bool(report["position"]["invariant"])
    deterministic = bool(report["determinism"]["deterministic"])
    reported = report["confidence"]["reported"]
    clears = reported is not None and reported >= min_confidence
    if position_ok and deterministic and clears:
        summary = ("the route answer survives option reordering and clears %.2f, so the gate is "
                   "deciding on the model's evidence" % min_confidence)
    elif not position_ok:
        summary = ("the route answer moves when the same options are reordered, so it is following "
                   "position rather than meaning; the decision cannot be trusted at any "
                   "confidence and the workflow is right to fail closed")
    elif not deterministic:
        summary = ("the model is not deterministic here, so the confidence numbers are a sample "
                   "rather than a property of the state")
    else:
        summary = ("the route answer is stable but reports %.3f, below the %.2f gate, so every "
                   "decision fails closed to a person until the threshold is calibrated or the "
                   "evidence is strengthened" % (reported if reported is not None else -1.0,
                                                 min_confidence))
    return {"trustworthy": bool(position_ok and deterministic and clears),
            "position_invariant": position_ok,
            "deterministic": deterministic,
            "clears_gate": bool(clears),
            "summary": summary}


def render_calibration_text(report: Dict[str, Any]) -> str:
    """A human-readable calibration report."""
    if not report.get("ok"):
        return "calibration did not run: %s" % report.get("reason", "unknown reason")
    lines: List[str] = []
    lines.append("labels offered: %s" % report["labels"])
    determinism = report["determinism"]
    lines.append("")
    lines.append("determinism:")
    lines.append("  %d identical calls -> %d distinct choice(s), %d distinct distribution(s): %s"
                 % (determinism["calls"], len(determinism["distinct_choices"]),
                    determinism["distinct_distributions"],
                    "deterministic" if determinism["deterministic"] else "NOT deterministic"))
    baseline = determinism["baseline"]
    lines.append("  baseline: %s at confidence %s"
                 % (baseline["label"], baseline["confidence"]))
    for label, probability in sorted((baseline["probabilities"] or {}).items(),
                                     key=lambda item: -item[1]):
        lines.append("    %-22s %.4f" % (label, probability))

    position = report["position"]
    lines.append("")
    lines.append("position invariance (%d orderings):" % position["orderings_tested"])
    lines.append("  chose %s in every ordering: %s"
                 % (position["baseline_label"], "yes" if position["invariant"] else "NO"))
    for entry in position["disagreeing_orderings"]:
        lines.append("    reordered to %s -> chose %s (%.3f)"
                     % (entry["order"], entry["label"], entry["confidence"] or -1.0))

    wording = report["wording"]
    lines.append("")
    lines.append("wording invariance:")
    lines.append("  opaque labels %s -> chose %s (%s)"
                 % (wording["opaque_labels"], wording["opaque_choice"],
                    wording["opaque_confidence"]))
    lines.append("  consistent with the semantic run: %s"
                 % ("yes" if wording["consistent_with_position"] else "NO"))

    confidence = report["confidence"]
    lines.append("")
    lines.append("threshold table (reported confidence %.4f):" % (confidence["reported"] or -1.0))
    for row in confidence["thresholds"]:
        lines.append("  >= %.2f  %-4s  %s" % (row["threshold"],
                                              "yes" if row["clears"] else "no", row["outcome"]))

    verdict = report["verdict"]
    lines.append("")
    lines.append("verdict: %s" % ("TRUSTWORTHY" if verdict["trustworthy"] else "NOT TRUSTWORTHY"))
    lines.append("  %s" % verdict["summary"])
    return "\n".join(lines)

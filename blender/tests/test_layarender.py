"""Runnable checks for layarender. No pytest required: ``python tests/test_layarender.py``.

The suite exists to hold the properties the implementation brief makes non-negotiable:

1. Laya failing (timeout, malformed output, unavailable, low confidence) never yields a route
   that could write to the scene.
2. A plan that is out of scope, out of unit, or unsupported is rejected before execution.
3. A check that did not run is never reported as a pass.
4. ``accept`` requires the deterministic checks to agree with the model.
5. The control loop always terminates.
6. Stale scene references are caught rather than replayed.

The "Laya" used here is a fixture that replays recorded answer shapes -- it is not the model.
The real adapter path is exercised by ``build_laya_adapter`` against the actual Laya CLI in
``tests/test_laya_adapter_live.py`` (skipped when Laya is not installed).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from layarender.adapters.laya_ai import (LayaAnswer, LayaAdapter, LayaMalformed, LayaRunner,
                                         LayaUnavailable, ROUTE_LABELS, _project_answers,
                                         build_laya_adapter)
from layarender.adapters.render_mcp import RenderMcpAdapter
from layarender.adapters.transport import RecordingTransport, TransportError
from layarender.calibrate import calibrate_route, orderings, render_calibration_text
from layarender.contracts import Requirement, SceneContract, ViewSpec
from layarender.control import ControlPlaneConfig, PolicyPlanner, SceneControlPlane, allowed_routes
from layarender.models import (CheckStatus, Decision, Finding, HardChecks, PatchOp, PatchPlan,
                               Route, RunState, Severity, ViewRender)
from layarender.policy import OperationPolicy, policy_from_contract
from layarender.preflight import preflight_plan
from layarender.report import final_report, render_report_text
from layarender.reviewer import findings_from_payload
from layarender.scene import read_scene
from layarender.validators import run_scene_checks

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE = os.path.join(REPO, "jet-kite.glb")
CONTRACT = os.path.join(REPO, "contracts", "jet-kite.json")


# ---------------------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------------------
class FixtureRunner(LayaRunner):
    """Replays answer payloads shaped exactly like Laya's. Not a model; a recorded fixture."""

    name = "fixture"

    def __init__(self, label="revise_candidate", confidence=0.9, raise_with=None,
                 malformed=False):
        self.label = label
        self.confidence = confidence
        self.raise_with = raise_with
        self.malformed = malformed
        self.detail = {}
        self.calls = 0

    def available(self):
        return True

    def answer(self, state_text, questions, min_confidence, timeout):
        self.calls += 1
        if self.raise_with is not None:
            raise self.raise_with
        if self.malformed:
            return {"result": {"unexpected": "shape"}}
        return {"result": {"answers": {
            "route": {"type": "choice", "choice": self.label,
                      "probabilities": {self.label: 0.8},
                      "confidence": self.confidence,
                      "answer_confidence": self.confidence},
        }}, "latency_ms": 3.0}


def _contract_with(**overrides):
    contract = SceneContract(goal="test scene", must_have=["Jet_Fuselage"],
                             write_scope=["Jet_*"], max_revision_rounds=2)
    contract.requirements = [Requirement(kind="object_present", pattern="Jet_Fuselage")]
    for key, value in overrides.items():
        setattr(contract, key, value)
    return contract


def _snapshot():
    return read_scene(SCENE)


# ---------------------------------------------------------------------------------------
# 1. fail closed
# ---------------------------------------------------------------------------------------
def test_unavailable_laya_routes_to_human():
    adapter = build_laya_adapter("none")
    decision = adapter.choose_next_step({"scene": {}}, [Route.REVISE.value, Route.ACCEPT.value])
    assert decision.route == Route.HUMAN_REVIEW.value, decision.route
    assert decision.source == "unavailable", decision.source
    assert "no Laya runner" in decision.reason


def test_timeout_routes_to_human():
    runner = FixtureRunner(raise_with=LayaUnavailable("the laya CLI exceeded 1.0s"))
    adapter = LayaAdapter(runner=runner)
    decision = adapter.choose_next_step({"scene": {}}, [Route.REVISE.value, Route.BRANCH.value])
    assert decision.route == Route.HUMAN_REVIEW.value
    assert decision.source == "unavailable"
    assert "exceeded" in decision.reason


def test_malformed_output_routes_to_human():
    runner = FixtureRunner(malformed=True)
    adapter = LayaAdapter(runner=runner)
    decision = adapter.choose_next_step({"scene": {}}, [Route.REVISE.value])
    assert decision.route == Route.HUMAN_REVIEW.value, decision.route
    assert decision.source == "unavailable"


def test_low_confidence_routes_to_human():
    runner = FixtureRunner(label="revise_candidate", confidence=0.2)
    adapter = LayaAdapter(runner=runner, min_confidence=0.6)
    decision = adapter.choose_next_step({"scene": {}}, [Route.REVISE.value, Route.BRANCH.value])
    assert decision.route == Route.HUMAN_REVIEW.value, decision.route
    assert "confidence threshold" in decision.reason


def test_unexpected_label_is_guarded_not_trusted():
    runner = FixtureRunner(label="something_invented", confidence=0.99)
    adapter = LayaAdapter(runner=runner)
    decision = adapter.choose_next_step({"scene": {}}, [Route.REVISE.value, Route.BRANCH.value])
    assert decision.route == Route.HUMAN_REVIEW.value, decision.route
    assert decision.source == "unavailable"


def test_model_cannot_accept_when_accept_is_illegal():
    runner = FixtureRunner(label=ROUTE_LABELS[Route.ACCEPT.value], confidence=0.99)
    adapter = LayaAdapter(runner=runner)
    decision = adapter.choose_next_step({"scene": {}}, [Route.REVISE.value, Route.BRANCH.value],
                                        hard_failures=["dimension:Jet_Fuselage:z"])
    assert decision.route == Route.REVISE.value, decision.route
    assert decision.guardrails, "the override must be recorded"


def test_projection_reads_laya_answer_shapes():
    answers, malformed = _project_answers(
        {"answers": {"route": {"type": "choice", "choice": "ask_a_person",
                               "probabilities": {"ask_a_person": 0.7, "revise_candidate": 0.3},
                               "confidence": 0.55, "answer_confidence": 0.55}}},
        min_confidence=0.6)
    assert malformed is None
    assert answers["route"].label == "ask_a_person"
    assert answers["route"].low_confidence is True, "below-threshold answers must be flagged"
    assert _project_answers({"answers": {}}, 0.6)[1] is not None


# ---------------------------------------------------------------------------------------
# 2. preflight
# ---------------------------------------------------------------------------------------
def test_preflight_rejects_unknown_operation():
    contract = _contract_with()
    policy = policy_from_contract(contract)
    plan = PatchPlan(candidate_id="c1", ops=[PatchOp(op="teleport_everything")])
    result = preflight_plan(plan, contract, policy, _snapshot())
    assert not result.ok
    assert any("allowlist" in error for error in result.errors)


def test_preflight_rejects_stale_object_reference():
    contract = _contract_with()
    policy = policy_from_contract(contract)
    plan = PatchPlan(candidate_id="c2",
                     ops=[PatchOp(op="nudge_object", target="Jet_Does_Not_Exist",
                                  parameters={"axis": "z", "delta": 0.1})])
    result = preflight_plan(plan, contract, policy, _snapshot())
    assert not result.ok
    assert any("not in the current scene revision" in error for error in result.errors)


def test_preflight_rejects_out_of_scope_target():
    contract = _contract_with(write_scope=["Kite_*"])
    policy = policy_from_contract(contract)
    plan = PatchPlan(candidate_id="c3",
                     ops=[PatchOp(op="nudge_object", target="Jet_Fuselage",
                                  parameters={"axis": "z", "delta": 0.1})])
    result = preflight_plan(plan, contract, policy, _snapshot())
    assert not result.ok
    assert any("write scope" in error for error in result.errors)


def test_preflight_rejects_oversized_move():
    contract = _contract_with()
    policy = policy_from_contract(contract)
    plan = PatchPlan(candidate_id="c4",
                     ops=[PatchOp(op="nudge_object", target="Jet_Fuselage",
                                  parameters={"axis": "z", "delta": 5.0})])
    result = preflight_plan(plan, contract, policy, _snapshot())
    assert not result.ok
    assert any("rewrite, not a revision" in error for error in result.errors)


def test_preflight_rejects_undeclared_and_mistyped_parameters():
    contract = _contract_with()
    policy = policy_from_contract(contract)
    plan = PatchPlan(candidate_id="c5", ops=[PatchOp(op="nudge_object", target="Jet_Fuselage",
                                                    parameters={"axis": "q", "delta": "a lot",
                                                                "smuggle": 1})])
    result = preflight_plan(plan, contract, policy, _snapshot())
    assert not result.ok
    joined = " ".join(result.errors)
    assert "undeclared parameter" in joined
    assert "x/y/z" in joined


def test_preflight_marks_broad_plan_for_approval():
    contract = _contract_with()
    policy = policy_from_contract(contract)
    plan = PatchPlan(candidate_id="c6", ops=[
        PatchOp(op="nudge_object", target="Jet_Fuselage", parameters={"axis": "z", "delta": 0.1}),
        PatchOp(op="nudge_object", target="Jet_Wing_R", parameters={"axis": "z", "delta": 0.1}),
        PatchOp(op="nudge_object", target="Jet_Wing_L", parameters={"axis": "z", "delta": 0.1}),
        PatchOp(op="nudge_object", target="Jet_Canopy", parameters={"axis": "z", "delta": 0.1}),
    ])
    result = preflight_plan(plan, contract, policy, _snapshot())
    assert result.requires_approval, result.to_dict()


def test_deletion_is_never_automatic():
    contract = _contract_with()
    policy = policy_from_contract(contract)
    plan = PatchPlan(candidate_id="c7", ops=[PatchOp(op="delete_object", target="Jet_Canopy")])
    result = preflight_plan(plan, contract, policy, _snapshot())
    assert not result.ok
    assert any("never deletes" in error for error in result.errors)


# ---------------------------------------------------------------------------------------
# 3. validators tell the truth
# ---------------------------------------------------------------------------------------
def test_missing_view_is_not_reported_as_pass():
    contract = SceneContract()
    contract.requirements = [Requirement(kind="view_rendered", views=["hero"])]
    checks = run_scene_checks(_snapshot(), contract, [ViewRender(name="hero")], SCENE)
    result = checks.get("view_rendered")
    assert result.status == CheckStatus.FAIL.value, result.to_dict()


def test_unreadable_scene_marks_requirements_not_run():
    contract = SceneContract()
    contract.requirements = [Requirement(kind="object_present", pattern="Jet_Fuselage"),
                             Requirement(kind="export", path="nope.glb")]
    checks = run_scene_checks(None, contract, [], "missing.glb", RuntimeError("boom"))
    assert checks.get("scene_readable").status == CheckStatus.FAIL.value
    assert checks.get("object_present:Jet_Fuselage").status == CheckStatus.NOT_RUN.value


def test_real_scene_passes_its_contract():
    total = os.path.getsize(CONTRACT)  # the contract file must exist and be parseable
    assert total > 0
    from layarender.contracts import SceneContract as _Contract

    contract = _Contract.load(CONTRACT)
    snapshot = read_scene(SCENE)
    # The real render sheet is supplied, so this asserts the whole contract end to end.
    views = [ViewRender(name=name, path=os.path.join(REPO, "mcp-demo", filename), rendered=True)
             for name, filename in (("hero", "jetkite_hero.png"), ("belly", "jetkite_belly.png"),
                                    ("bay", "jetkite_bay.png"))]
    checks = run_scene_checks(snapshot, contract, views, SCENE)
    assert checks.passed(), ["%s: %s" % (r.name, r.detail) for r in checks.failures()]


def test_export_check_reports_not_run_without_a_path():
    contract = SceneContract()
    contract.requirements = [Requirement(kind="export", path=None)]
    checks = run_scene_checks(_snapshot(), contract, [], SCENE)
    assert checks.get("export:delivery").status == CheckStatus.NOT_RUN.value


# ---------------------------------------------------------------------------------------
# 4. findings must be located
# ---------------------------------------------------------------------------------------
def test_unlocated_findings_are_rejected():
    try:
        findings_from_payload([{"criterion": "make it better", "view": "hero"}], ["hero"])
    except Exception as error:
        assert "no affected_object" in str(error), str(error)
    else:
        raise AssertionError("an unlocated finding was accepted")


def test_finding_to_an_unknown_view_is_rejected():
    try:
        findings_from_payload([{"criterion": "x", "view": "nope",
                                "affected_object": "Jet_Fuselage"}], ["hero"])
    except Exception as error:
        assert "not one of" in str(error), str(error)
    else:
        raise AssertionError("a finding for an unknown view was accepted")


def test_located_findings_are_accepted():
    findings = findings_from_payload(
        [{"criterion": "readable silhouette", "result": "fail", "severity": "high", "view": "hero",
          "affected_object": "Jet_Fuselage", "evidence": "handle overlaps the body",
          "suggested_fix": "offset the handle", "confidence": 0.89}], ["hero"])
    assert findings[0].is_located()
    assert findings[0].severity == "high"
    assert findings[0].measured is False, "an external review is not a measurement"


# ---------------------------------------------------------------------------------------
# 5. the loop always terminates, and accept needs the checks to agree
# ---------------------------------------------------------------------------------------
def _plane(tmpdir, runner, shadow=True, max_rounds=2, planner=None):
    contract = SceneContract.load(CONTRACT)
    policy = policy_from_contract(contract, shadow_mode=shadow)
    render = RenderMcpAdapter(transport=RecordingTransport(), policy=policy)
    config = ControlPlaneConfig(shadow_mode=shadow, max_rounds=max_rounds, scene_path=SCENE,
                                run_dir=tmpdir)
    return SceneControlPlane(contract=contract, policy=policy,
                             laya=LayaAdapter(runner=runner), render=render,
                             planner=planner or PolicyPlanner(), config=config)


def test_loop_terminates_with_unavailable_laya():
    with tempfile.TemporaryDirectory() as tmpdir:
        plane = _plane(tmpdir, None)
        plane.load_scene()
        state = plane.run()
        assert state.outcome in ("needs_human_review", "budget_exhausted"), state.outcome
        assert state.rounds_used <= state.max_rounds()
        assert state.human_required


def test_shadow_mode_writes_nothing():
    with tempfile.TemporaryDirectory() as tmpdir:
        plane = _plane(tmpdir, FixtureRunner(), shadow=True)
        plane.load_scene()
        state = plane.run()
        assert all(not round_.applied for round_ in state.rounds)
        writes = [call for call in plane.render.transport.calls() if not call.read_only]
        assert writes == [], "shadow mode must not issue a write call"


def test_accept_requires_passing_checks():
    contract = SceneContract.load(CONTRACT)
    checks = HardChecks()
    checks.add("dimension:Jet_Fuselage:z", CheckStatus.FAIL.value, "out of tolerance")
    review = None
    routes = allowed_routes(RunState(budget={"max_rounds": 5}), checks, review, stalled=False)
    assert Route.ACCEPT.value not in routes
    assert Route.REVISE.value in routes


def test_high_severity_finding_blocks_accept():
    from layarender.models import VisualReview

    review = VisualReview(findings=[Finding(criterion="silhouette", result="fail",
                                            severity=Severity.HIGH.value, view="hero",
                                            affected_object="Jet_Fuselage")])
    routes = allowed_routes(RunState(budget={"max_rounds": 5}), None, review, stalled=False)
    assert Route.ACCEPT.value not in routes


def test_stall_withdraws_revise():
    state = RunState(budget={"max_rounds": 6})
    for score in (0.5, 0.5, 0.5):
        from layarender.models import Round
        round_ = Round(index=state.rounds_used)
        round_.score = score
        state.rounds.append(round_)
    assert state.stalled() is True
    routes = allowed_routes(state, None, None, stalled=True)
    assert Route.REVISE.value not in routes
    assert Route.BRANCH.value in routes


def test_budget_exhaustion_leaves_only_human_review():
    state = RunState(budget={"max_rounds": 1})
    from layarender.models import Round
    # The budget bounds revisions: a round that proposed a plan counts, the opening assessment
    # round does not. Two revisions against a budget of one is exhausted.
    state.rounds.append(Round(index=0))
    state.rounds.append(Round(index=1, plan=PatchPlan(candidate_id="c", ops=[
        PatchOp(op="nudge_object", target="Jet_Fuselage", parameters={"axis": "z",
                                                                       "delta": 0.1})])))
    assert state.revision_rounds() == 1
    assert state.budget_exhausted() is True
    routes = allowed_routes(state, None, None, stalled=False)
    assert routes == [Route.HUMAN_REVIEW.value], routes


def test_report_separates_ran_from_not_run():
    with tempfile.TemporaryDirectory() as tmpdir:
        plane = _plane(tmpdir, FixtureRunner())
        plane.load_scene()
        state = plane.run()
        report = final_report(state, shadow_mode=True)
        assert report["checks_ran"] or report["checks_not_run"]
        assert report["checks_not_run"], "a shadow run must admit what did not run"
        assert report["limitations"], "a shadow run must state its limitations"
        text = render_report_text(report)
        assert "did NOT run" in text


# ---------------------------------------------------------------------------------------
# 6. budget behaviour and the writer boundary
# ---------------------------------------------------------------------------------------
def test_render_adapter_refuses_unpreflighted_plan():
    contract = SceneContract.load(CONTRACT)
    policy = policy_from_contract(contract, shadow_mode=False)
    adapter = RenderMcpAdapter(transport=RecordingTransport(), policy=policy)
    plan = PatchPlan(candidate_id="c", ops=[PatchOp(op="nudge_object", target="Jet_Fuselage",
                                                   parameters={"axis": "z", "delta": 0.05})])
    from layarender.models import PreflightResult
    receipt = adapter.apply_patch(plan, PreflightResult(ok=False, errors=["nope"]), "prompt")
    assert receipt.ok is False
    assert "preflight" in receipt.detail


def test_render_adapter_needs_approval_for_flagged_plan():
    contract = SceneContract.load(CONTRACT)
    policy = policy_from_contract(contract, shadow_mode=False)
    adapter = RenderMcpAdapter(transport=RecordingTransport(), policy=policy)
    plan = PatchPlan(candidate_id="c", ops=[PatchOp(op="nudge_object", target="Jet_Fuselage",
                                                   parameters={"axis": "z", "delta": 0.05})])
    from layarender.models import PreflightResult
    receipt = adapter.apply_patch(plan, PreflightResult(ok=True, requires_approval=True,
                                                       approval_reason="broad"), "prompt")
    assert receipt.ok is False
    assert "approval required" in receipt.detail


def test_write_calls_are_scoped_bpy_not_freeform():
    from layarender.adapters.render_mcp import build_patch_code

    plan = PatchPlan(candidate_id="c", ops=[
        PatchOp(op="nudge_object", target="Jet_Fuselage", parameters={"axis": "z", "delta": 0.05}),
        PatchOp(op="set_material_param", parameters={"material": "Jet_Skin", "param": "Roughness",
                                                     "value": 0.4}),
    ])
    code = build_patch_code(plan)
    assert "bpy.data.objects.get('Jet_Fuselage')" in code
    assert "assert target is not None" in code
    assert "RECEIPT" in code
    assert "deleted" not in code.lower()


def test_transport_records_instead_of_executing():
    transport = RecordingTransport()
    adapter = RenderMcpAdapter(transport=transport, policy=OperationPolicy(shadow_mode=True))
    try:
        adapter.read_scene("test")
    except Exception:
        pass
    assert transport.calls() and transport.calls()[0].tool == "get_scene_info"
    assert transport.responses()[0].ok is False


def test_json_file_transport_replays_and_fails_loudly():
    from layarender.adapters.transport import JsonFileTransport

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "responses.jsonl")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"tool": "get_scene_info", "ok": True,
                                     "payload": {"objects": 3}}) + "\n")
            handle.write(json.dumps({"tool": "get_scene_info", "ok": False,
                                     "error": "server said no"}) + "\n")
        transport = JsonFileTransport(path)
        assert transport.call("get_scene_info", {}) == {"objects": 3}
        try:
            transport.call("get_scene_info", {})
        except TransportError as error:
            assert "server said no" in str(error)
        else:
            raise AssertionError("a scripted failure was swallowed")


# ---------------------------------------------------------------------------------------
# 7. the calibration probe detects the failure it exists to detect
# ---------------------------------------------------------------------------------------
class TextRunner(LayaRunner):
    """Answers the same label whatever the option order: reads the options, not the position."""

    def __init__(self, label="revise_candidate", confidence=0.8):
        self.label = label
        self.confidence = confidence
        self.detail = {}

    def available(self):
        return True

    def answer(self, state_text, questions, min_confidence, timeout):
        offered = list(questions["route"]["criteria"])
        label = self.label if self.label in offered else offered[0]
        return {"result": {"answers": {"route": {
            "type": "choice", "choice": label,
            "probabilities": {name: (self.confidence if name == label else 0.05)
                              for name in offered},
            "confidence": self.confidence, "answer_confidence": self.confidence}}}}


class PositionalRunner(TextRunner):
    """Answers by position. It looks confident and is worthless: the fixture for the trap."""

    def __init__(self, position=0, confidence=0.9):
        super().__init__(confidence=confidence)
        self.position = position

    def answer(self, state_text, questions, min_confidence, timeout):
        offered = list(questions["route"]["criteria"])
        label = offered[min(self.position, len(offered) - 1)]
        return {"result": {"answers": {"route": {
            "type": "choice", "choice": label,
            "probabilities": {name: (self.confidence if name == label else 0.05)
                              for name in offered},
            "confidence": self.confidence, "answer_confidence": self.confidence}}}}


ROUTES = [Route.REVISE.value, Route.BRANCH.value, Route.HUMAN_REVIEW.value]


def test_orderings_enumerate_every_arrangement_for_the_real_route_set():
    orders = orderings(["a", "b", "c"], 8)
    assert len(orders) == 6
    assert len({tuple(order) for order in orders}) == 6
    assert orders[0] == ["a", "b", "c"], "the offered order must come first"
    assert orderings(["a"], 8) == [["a"]]
    assert len(orderings(list("abcdef"), 8)) <= 8, "a large option set must stay bounded"


def test_calibration_detects_an_answer_that_follows_position():
    """The trap this probe exists for: a confident answer that moves when options do.

    A positional answer reports high confidence, so a threshold cannot catch it. Only reordering
    the options can, which is why the probe reorders them instead of resampling.
    """
    report = calibrate_route(LayaAdapter(runner=PositionalRunner(position=0)), {"scene": {}}, ROUTES,
                             min_confidence=0.60, thresholds=[0.60])
    assert report["ok"]
    assert report["determinism"]["deterministic"]
    assert report["position"]["invariant"] is False, "a positional answer was called invariant"
    assert report["position"]["single_slot_for_every_order"] is True, \
        "the positional pattern was not visible in the recorded slots: %s" \
        % report["position"]["chosen_slots"]
    assert report["verdict"]["trustworthy"] is False
    assert "reorder" in report["verdict"]["summary"], report["verdict"]["summary"]
    assert "NOT TRUSTWORTHY" in render_calibration_text(report)


def test_calibration_confirms_an_answer_that_reads_the_options():
    report = calibrate_route(LayaAdapter(runner=TextRunner(confidence=0.8)), {"scene": {}}, ROUTES,
                             min_confidence=0.60, thresholds=[0.40, 0.90])
    assert report["position"]["invariant"] is True
    # The same probe must not call a text-following model positional: the chosen label is stable
    # while the slot it sits in moves, which is the exact mirror of the positional case.
    assert report["position"]["single_slot_for_every_order"] is False, \
        report["position"]["chosen_slots"]
    assert report["verdict"]["trustworthy"] is True, report["verdict"]["summary"]
    table = {row["threshold"]: row["clears"] for row in report["confidence"]["thresholds"]}
    assert table[0.40] is True and table[0.90] is False, table


def test_calibration_names_a_gate_that_would_never_open():
    """The situation this project is actually in: stable answer, confidence under the gate."""
    report = calibrate_route(LayaAdapter(runner=TextRunner(confidence=0.37)), {"scene": {}}, ROUTES,
                            min_confidence=0.60)
    assert report["position"]["invariant"] is True
    assert report["verdict"]["clears_gate"] is False
    assert report["verdict"]["trustworthy"] is False
    assert "below the 0.60 gate" in report["verdict"]["summary"], report["verdict"]["summary"]


def test_calibration_without_a_runner_says_nothing_was_measured():
    report = calibrate_route(LayaAdapter(runner=None), {"scene": {}}, ROUTES)
    assert report["ok"] is False
    assert "no Laya runner" in report["reason"]
    assert "did not run" in render_calibration_text(report)


def test_an_answer_with_no_legal_route_is_not_calibrated_as_trustworthy():
    report = calibrate_route(LayaAdapter(runner=TextRunner()), {"scene": {}}, ["invented_route"])
    assert report["ok"] is False
    assert "no usable route labels" in report["reason"]


def test_failing_measured_findings_are_recorded_when_they_do_not_block_accept():
    """A disagreement that does not change the route must still survive into the log.

    On the real project Laya's first choice was ``accept_candidate`` while the measured review
    showed the hero silhouette failing to separate from the background and three views clipping
    the subject. Under the contract's own severity policy a *medium* finding does not block
    acceptance -- only a mandatory check or a high-severity finding does, which is the rule the
    brief states. So the route stays ``accept``; what must not happen is for the run to look clean.

    Tightening the rule belongs in the contract (declare the criterion high severity there), not in
    the control plane, which is why this records rather than overrules.
    """
    from layarender.models import Round, VisualReview

    with tempfile.TemporaryDirectory() as tmpdir:
        plane = _plane(tmpdir, FixtureRunner(label=ROUTE_LABELS[Route.ACCEPT.value],
                                            confidence=0.99))
        plane.load_scene()
        state = plane.start()
        round_ = Round(index=0)
        round_.checks = HardChecks()
        round_.checks.add("scene_readable", CheckStatus.PASS.value, "ok")
        round_.review = VisualReview(views_reviewed=["hero"], findings=[
            Finding(criterion="silhouette separates from the background", result="fail",
                    severity=Severity.MEDIUM.value, view="hero", evidence="contrast 0.027")])
        decision = plane.route_next(state, round_)
        assert decision.route == Route.ACCEPT.value, decision.route
        assert any("asked to accept" in guardrail for guardrail in decision.guardrails), \
            decision.guardrails
        assert any("hero" in guardrail for guardrail in decision.guardrails), decision.guardrails


def test_a_high_severity_finding_does_overrule_the_model():
    """The counterpart: where the brief does draw the line, the model is overruled."""
    from layarender.models import Round, VisualReview

    with tempfile.TemporaryDirectory() as tmpdir:
        plane = _plane(tmpdir, FixtureRunner(label=ROUTE_LABELS[Route.ACCEPT.value],
                                            confidence=0.99))
        plane.load_scene()
        state = plane.start()
        round_ = Round(index=0)
        round_.checks = HardChecks()
        round_.checks.add("scene_readable", CheckStatus.PASS.value, "ok")
        round_.review = VisualReview(views_reviewed=["hero"], findings=[
            Finding(criterion="subject fully inside the frame", result="fail",
                    severity=Severity.HIGH.value, view="hero")])
        decision = plane.route_next(state, round_)
        assert decision.route == Route.REVISE.value, decision.route
        # Two layers can overrule an unearned accept: ``allowed_routes`` withholds the route, and
        # the double guard in ``route_next`` catches it if it ever arrives anyway. Asserting which
        # message fired would tie the test to the order of the defenses; what matters is that the
        # model is not followed and that the override is written down.
        assert decision.guardrails, "the model was overruled without recording why"
        assert any("accept" in guardrail for guardrail in decision.guardrails), \
            decision.guardrails
        assert decision.native["allowed_routes"], "the legal routes were not recorded"
        assert Route.ACCEPT.value not in decision.native["allowed_routes"], \
            "accept was offered to the model while a high-severity finding stood"


def test_accepting_clean_evidence_records_no_such_disagreement():
    from layarender.models import Round, VisualReview

    with tempfile.TemporaryDirectory() as tmpdir:
        plane = _plane(tmpdir, FixtureRunner(label=ROUTE_LABELS[Route.ACCEPT.value],
                                            confidence=0.99))
        plane.load_scene()
        state = plane.start()
        round_ = Round(index=0)
        round_.checks = HardChecks()
        round_.checks.add("scene_readable", CheckStatus.PASS.value, "ok")
        round_.review = VisualReview(views_reviewed=["hero"], findings=[])
        decision = plane.route_next(state, round_)
        assert decision.route == Route.ACCEPT.value, decision.route
        assert not decision.guardrails, decision.guardrails


def test_next_action_survives_a_final_round_that_asks_no_priority_question():
    """The failure mode this project is actually in: the gate fails closed on the last round.

    A gate that fails closed replaces the route with ``human_review`` and asks no priority
    question, so the final round holds nothing a person can act on while an earlier round holds
    the model's one strong answer. Reading only the last round would throw that away and leave the
    report with no next action -- which is exactly what happened before this lookup walked back.
    """
    from layarender.models import Round

    state = RunState(budget={"max_rounds": 2})
    early = Decision(
        route=Route.HUMAN_REVIEW.value, source="unavailable", confidence=0.415,
        priority_criterion="subject_fully_inside_the_frame",
        guardrails=["the model asked to accept, but measured findings fail on hero"],
        native={
            "runner": "laya-in-process",
            "questions": {"priority": {"criteria": {
                "subject_fully_inside_the_frame": "subject fully inside the frame on belly"}}},
            "answers": {
                "route": {"label": "accept_candidate", "answer_confidence": 0.415},
                "priority": {"label": "subject_fully_inside_the_frame",
                             "answer_confidence": 0.724},
            },
        })
    late = Decision(
        route=Route.HUMAN_REVIEW.value, source="unavailable", confidence=0.373,
        native={"runner": "laya-in-process", "questions": {"route": {"criteria": {}}},
                "answers": {"route": {"label": "revise_candidate",
                                       "answer_confidence": 0.373}}})
    round_zero = Round(index=0)
    round_zero.route = early
    round_one = Round(index=1)
    round_one.route = late
    state.rounds = [round_zero, round_one]
    state.human_required = True

    action = final_report(state, shadow_mode=True)["next_action"]
    assert action, "the run reports no next action at all"
    assert action["from_round"] == 0, action
    assert action["priority_criterion"] == "subject_fully_inside_the_frame", action
    assert action["priority_offered_as"] == "subject fully inside the frame on belly", action
    assert action["priority_confidence"] == 0.724, action
    assert action["model_asked_for"] == "accept_candidate", action
    assert action["route_runner"] == "laya-in-process", action
    assert action["guardrails"], action
    text = render_report_text(final_report(state, shadow_mode=True))
    assert "next action (what the evidence points at)" in text
    assert "subject_fully_inside_the_frame" in text
    assert "accept_candidate" in text and "laya-in-process" in text


def test_next_action_is_absent_when_no_round_produced_a_decision():
    state = RunState(budget={"max_rounds": 1})
    assert final_report(state)['next_action'] is None


# ---------------------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------------------
def _run_all():
    tests = [(name, value) for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    failures = []
    for name, test in tests:
        try:
            test()
            print("ok   %s" % name)
        except Exception as error:  # noqa: BLE001 - the runner must report any failure
            failures.append((name, "%s: %s" % (type(error).__name__, error)))
            print("FAIL %s -- %s: %s" % (name, type(error).__name__, error))
    print("")
    print("%d passed, %d failed" % (len(tests) - len(failures), len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())

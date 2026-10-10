"""Live checks that run the real Laya checkpoint through the real adapter.

``python tests/test_laya_adapter_live.py``

The rest of the suite substitutes a fixture for Laya, which proves the workflow's *handling* of
an answer without proving that the adapter can produce one. This file closes that gap: it loads
``convaiinnovations/laya`` and asks it the actual route question the control plane asks.

Every test here skips -- it does not fail and it does not pass -- when torch, the Laya package or
the checkpoint are absent, so the file stays safe to run on a machine that has never installed
the runtime. A skip is reported as ``skip`` and does not count as a pass.

These are read-only: the control plane is built in shadow mode over a recording transport, so no
scene write can reach Blender even though the decision path is real.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from layarender.adapters.laya_ai import (LayaAdapter, ROUTE_LABELS, build_laya_adapter,
                                         normalise_route, resolve_local_checkpoint, route_question)
from layarender.adapters.render_mcp import RenderMcpAdapter
from layarender.adapters.transport import RecordingTransport
from layarender.contracts import SceneContract
from layarender.control import ControlPlaneConfig, PolicyPlanner, SceneControlPlane
from layarender.models import DecisionSource, Route
from layarender.policy import policy_from_contract

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE = os.path.join(REPO, "jet-kite.glb")
CONTRACT = os.path.join(REPO, "contracts", "jet-kite.json")
SCENE_CONTEXT = os.path.join(REPO, "contracts", "jet-kite.scene-context.json")
DEMO = os.path.join(REPO, "mcp-demo")
EXISTING_VIEWS = {
    "hero": os.path.join(DEMO, "jetkite_hero.png"),
    "belly": os.path.join(DEMO, "jetkite_belly.png"),
    "bay": os.path.join(DEMO, "jetkite_bay.png"),
    "cockpit": os.path.join(DEMO, "jetkite_cockpit.png"),
}

#: The real facts the workflow measured about this project, used as the state Laya is asked
#: about. A made-up state would test the adapter; this tests the adapter on our own scene.
REAL_STATE = {
    "goal": "a legible, correctly scaled tabletop jet-kite product scene",
    "units": "meters",
    "scene": {
        "objects": 43, "materials": 9, "triangles": 7450,
        "extents": [2.414856, 0.706302, 3.411868],
        "revision": "a49e86e4651986cc",
    },
    "hard_checks": {"ran": 19, "passed": 19, "failed": 0, "not_run": 0},
    "review": {
        "views": ["hero", "belly", "bay", "cockpit"],
        "findings": [
            {"view": "hero", "criterion": "silhouette separates from the background",
             "severity": "medium", "result": "fail", "detail": "contrast 0.027"},
            {"view": "belly", "criterion": "subject fully inside the frame",
             "severity": "medium", "result": "fail", "detail": "subject touches an edge"},
            {"view": "bay", "criterion": "subject fully inside the frame",
             "severity": "medium", "result": "fail", "detail": "subject touches an edge"},
        ],
    },
    "budget": {"max_rounds": 3, "used": 0},
}

ALLOWED = [Route.REVISE.value, Route.BRANCH.value, Route.HUMAN_REVIEW.value]
PRIORITIES = ["silhouette_contrast", "edge_touch", "bay_coverage"]

_adapter_cache: dict = {}


class Skipped(Exception):
    """Raised when the runtime is not installed. Reported as ``skip``, never as a pass."""


def _live_adapter() -> LayaAdapter:
    """One adapter for the whole file, so the checkpoint is loaded once and not per test."""
    if "adapter" not in _adapter_cache:
        adapter = build_laya_adapter(mode="in-process")
        if not adapter.active_runner():
            raise Skipped("no Laya runner is available (torch, the laya package or the "
                          "checkpoint are missing)")
        _adapter_cache["adapter"] = adapter
    return _adapter_cache["adapter"]


# ---------------------------------------------------------------------------------------
# pure checks: these run everywhere, no runtime needed
# ---------------------------------------------------------------------------------------
def _write_checkpoint(directory: str, complete: bool = True) -> str:
    """Build the smallest directory that reads as a Laya checkpoint."""
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "rl_agent_config.json"), "w", encoding="utf-8") as stream:
        stream.write("{}")
    if complete:
        with open(os.path.join(directory, "model.safetensors"), "wb") as stream:
            stream.write(b"\x00" * 8)
    return directory


def test_local_checkpoint_resolution_requires_a_complete_directory():
    """Half a checkpoint is not a checkpoint: both marker files must be present.

    Run against a throwaway HOME so the machine's real ``~/laya_models`` cannot answer for the
    directory under test -- otherwise the test would pass on this machine and fail on a clean one.
    """
    saved = {name: os.environ.get(name) for name in ("LAYA_MODEL_DIR", "HOME", "USERPROFILE")}
    fake_home = tempfile.mkdtemp(prefix="layarender-home-")
    incomplete = os.path.join(fake_home, "incomplete")
    candidate = os.path.join(fake_home, "candidate")
    try:
        os.environ["HOME"] = fake_home
        os.environ["USERPROFILE"] = fake_home
        os.environ["LAYA_MODEL_DIR"] = incomplete

        assert resolve_local_checkpoint("convaiinnovations/laya") == "convaiinnovations/laya", \
            "an empty directory was accepted as a checkpoint"

        _write_checkpoint(incomplete, complete=False)
        assert resolve_local_checkpoint("convaiinnovations/laya") == "convaiinnovations/laya", \
            "a directory without weights was accepted as a checkpoint"

        _write_checkpoint(candidate)
        os.environ["LAYA_MODEL_DIR"] = candidate
        assert resolve_local_checkpoint("convaiinnovations/laya") == candidate, \
            "a complete checkpoint was not preferred"

        # With `LAYA_MODEL_DIR` unset the conventional location is the one consulted.
        os.environ.pop("LAYA_MODEL_DIR")
        conventional = _write_checkpoint(os.path.join(fake_home, "laya_models"))
        assert os.path.normpath(resolve_local_checkpoint("convaiinnovations/laya")) == \
            os.path.normpath(conventional), \
            "the conventional ~/laya_models was not consulted"

        # A caller who named a model on purpose keeps it, even with a local copy present.
        assert resolve_local_checkpoint("some/other-repo") == "some/other-repo"
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        shutil.rmtree(fake_home, ignore_errors=True)


def test_installed_checkpoint_is_detected_when_one_is_present():
    """The 803 MB already on disk should be used instead of being fetched again."""
    home_models = os.path.expanduser("~/laya_models")
    if not os.path.isdir(home_models):
        raise Skipped("no local checkpoint is installed")
    resolved = resolve_local_checkpoint("convaiinnovations/laya")
    assert resolved != "convaiinnovations/laya", \
        "a local checkpoint is installed but the adapter would still go to the Hub"
    assert resolved.startswith(os.path.dirname(home_models)), resolved
    print("     live: weights resolved from %s" % resolved)


def test_route_question_accepts_keys_and_labels_and_rejects_nonsense():
    """Both spellings the codebase uses resolve; anything else is loud, never silent."""
    by_key = route_question(ALLOWED, PRIORITIES)
    assert set(by_key["route"]["criteria"]) == {ROUTE_LABELS[route] for route in ALLOWED}, \
        "a key-spelled route list did not produce every criterion"

    by_label = route_question([normalise_route(label) for label in
                               ["revise_candidate", "branch_composition", "ask_a_person"]],
                              PRIORITIES)
    assert by_label["route"]["criteria"] == by_key["route"]["criteria"], \
        "the two spellings disagree"

    for bad in ([], ["improve_everything"], ["revise", "make_it_pop"]):
        try:
            route_question(bad, PRIORITIES)
        except ValueError:
            pass
        else:
            raise AssertionError("an unusable route list %r produced a question" % (bad,))


def test_unbuildable_question_fails_closed_instead_of_raising():
    """A workflow defect must not take the loop down: it becomes a recorded refusal."""
    adapter = LayaAdapter(runner=None, min_confidence=0.6)
    outcome = adapter.evaluate_scene_state(REAL_STATE, allowed_routes=["not_a_route"])
    assert outcome["route"] is None
    assert "could not be built" in outcome["reason"], outcome["reason"]

    decision = adapter.choose_next_step(REAL_STATE, allowed_routes=["not_a_route"])
    assert decision.route == Route.HUMAN_REVIEW.value
    assert decision.source == DecisionSource.UNAVAILABLE.value


def test_no_runner_is_a_recorded_refusal_not_an_exception():
    adapter = LayaAdapter(runner=None, min_confidence=0.6)
    decision = adapter.choose_next_step(REAL_STATE, allowed_routes=ALLOWED)
    assert decision.route == Route.HUMAN_REVIEW.value
    assert decision.source == DecisionSource.UNAVAILABLE.value
    assert decision.reason and "no Laya runner" in decision.reason


# ---------------------------------------------------------------------------------------
# live checks: skipped unless the real runtime is installed
# ---------------------------------------------------------------------------------------
def test_live_runtime_answers_the_route_question():
    adapter = _live_adapter()
    started = time.time()
    outcome = adapter.evaluate_scene_state(REAL_STATE, allowed_routes=ALLOWED,
                                           priority_options=PRIORITIES)
    elapsed = time.time() - started
    assert outcome["runner"], "the live adapter reported no runner"
    assert outcome["answers"], "the live model returned no answers: %s" % outcome["reason"]

    route = outcome["answers"]["route"]
    assert route.native.get("probabilities"), "the answer carries no probabilities to audit"
    assert abs(sum(route.native["probabilities"].values()) - 1.0) < 0.01, \
        "the choice probabilities do not sum to 1: %r" % route.native["probabilities"]
    assert route.label in {label for label in route.native["probabilities"]}, \
        "the chosen label is not one of the labels it scored"

    priority = outcome["answers"].get("priority")
    assert priority is not None and priority.label in PRIORITIES, \
        "Laya answered the priority question with %r" % (priority.label if priority else None)
    print("     live: %s -> %s in %.1fs" % (route.label, priority.label, elapsed))


def test_live_decision_is_attributed_to_laya_and_records_its_evidence():
    """With the gate relaxed, a real answer must be recorded as a real answer."""
    adapter = _live_adapter()
    adapter.min_confidence = 0.01
    try:
        decision = adapter.choose_next_step(REAL_STATE, allowed_routes=ALLOWED,
                                            priority_options=PRIORITIES,
                                            fallback_reason="budget spent")
    finally:
        adapter.min_confidence = 0.60

    assert decision.source == DecisionSource.LAYA.value, \
        "a live answer was not attributed to Laya: %s" % decision.reason
    assert decision.route in ALLOWED, "Laya chose a route outside the allowed set"
    assert decision.confidence is not None, "the decision recorded no confidence"
    assert decision.native.get("runner"), "the decision does not say which runner answered"
    assert decision.native.get("questions"), "the decision does not record the question asked"
    assert decision.native.get("allowed_routes") == ALLOWED
    assert decision.native.get("caveats"), "the model caveats are not recorded on the decision"
    answered = decision.native["answers"]["route"]
    assert answered["native"].get("probabilities"), "the audit trail lost the probabilities"
    print("     live: source=%s route=%s confidence=%s"
          % (decision.source, decision.route, decision.confidence))


def test_live_confidence_gate_actually_gates():
    """The gate must be enforced on the live path, not only in the fixtures.

    An impossible threshold is the cleanest way to prove it: if a route still came back with
    ``source == "laya"``, the threshold would be decorative.
    """
    adapter = _live_adapter()
    adapter.min_confidence = 0.999
    try:
        decision = adapter.choose_next_step(REAL_STATE, allowed_routes=ALLOWED,
                                            priority_options=PRIORITIES)
    finally:
        adapter.min_confidence = 0.60
    assert decision.route == Route.HUMAN_REVIEW.value, \
        "an impossible confidence gate still allowed %s" % decision.route
    assert decision.source == DecisionSource.UNAVAILABLE.value
    assert "confidence threshold" in decision.reason, decision.reason
    print("     live: gate held -> %s" % decision.reason[:120])


def test_live_flags_are_accepted_by_the_real_cli_interface():
    """The adapter's own question vocabulary must be what the model accepts.

    ``laya.agent`` rejects a choice question with no criteria outright, so an answer that comes
    back at all is evidence the question was well formed.
    """
    runner = _live_adapter().active_runner()
    question = route_question(ALLOWED, PRIORITIES)
    answer = runner.answer(json.dumps(REAL_STATE), question, 0.0, 300.0)
    result = answer["result"]
    assert "answers" in result, "the runner returned %r" % str(result)[:200]
    assert set(result["answers"]) == {"route", "priority"}, \
        "the model answered questions that were not asked: %r" % sorted(result["answers"])

    # The answer's labels must be exactly the criteria offered. Anything else means the model
    # answered a different question than the one the workflow asked -- which is precisely the
    # failure the doc warns about, and the reason a decision cannot be applied unchecked.
    for qid, entry in result["answers"].items():
        offered = set(question[qid]["criteria"])
        assert set(entry["probabilities"]) == offered, \
            "the %s answer scored %r, not the offered %r" % (qid, sorted(entry["probabilities"]),
                                                             sorted(offered))
        assert entry["choice"] in offered, \
            "the %s answer chose %r, which was never offered" % (qid, entry["choice"])

    # The state must actually have reached the model: a silently empty prompt would still
    # produce a well-formed answer, and no amount of shape checking would notice.
    usage = result.get("usage") or {}
    assert usage.get("state_tokens"), "the state did not reach the model: %r" % usage
    assert not usage.get("truncated"), \
        "the state was truncated, so the model did not see all of it: %r" % usage
    assert not usage.get("truncated_questions"), usage
    print("     live: state=%s tokens, in=%s, out=%s"
          % (usage.get("state_tokens"), usage.get("input_tokens"), usage.get("output_tokens")))


def test_live_full_round_records_a_traceable_decision():
    """The whole assessed round, over the real scene and the real renders.

    This is the artifact the user actually runs, so it is the one that has to hold: an assessed
    round whose routing decision is either a real Laya answer or an explicit refusal, with the
    evidence that produced it written down.
    """
    if not all(os.path.exists(path) for path in EXISTING_VIEWS.values()):
        raise Skipped("the canonical demo renders needed for evidence are missing")

    contract = SceneContract.load(CONTRACT)
    policy = policy_from_contract(contract, shadow_mode=True)
    plane = SceneControlPlane(
        contract=contract, policy=policy, laya=_live_adapter(),
        render=RenderMcpAdapter(transport=RecordingTransport(), policy=policy),
        planner=PolicyPlanner(),
        config=ControlPlaneConfig(shadow_mode=True, max_rounds=3, scene_path=SCENE,
                                  existing_views=dict(EXISTING_VIEWS),
                                  scene_context_path=SCENE_CONTEXT,
                                  require_approval_callback=lambda plan, preflight: False),
    )
    plane.load_scene()
    state = plane.start(brief={"goal": contract.goal})
    assessed = plane.assess(state)
    assert assessed.checks and assessed.checks.results, "the assessed round ran no checks"
    assert not assessed.checks.not_run(), \
        "the assessed round left checks unrun: %s" % [r.name for r in assessed.checks.not_run()]
    assert not assessed.checks.failures(), \
        "the assessed round failed a mandatory check: %s" % [r.name for r in
                                                             assessed.checks.failures()]

    decision = plane.route_next(state, assessed)
    assert decision.source in (DecisionSource.LAYA.value, DecisionSource.UNAVAILABLE.value), \
        "the decision came from nowhere traceable: %s" % decision.source
    assert decision.reason, "the decision gives no reason"
    if decision.source == DecisionSource.LAYA.value:
        assert decision.native.get("answers"), "a Laya decision recorded no answers"
    else:
        assert decision.route == Route.HUMAN_REVIEW.value, \
            "a refused decision must land on human review, not %s" % decision.route

    # Nothing may have been written: both the transport and the policy are read-only here.
    assert not plane.render.transport.responses(), "a shadow round issued an MCP call"
    print("     live: full round -> %s (%s)" % (decision.route, decision.source))


# ---------------------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------------------
def _run_all():
    tests = [(name, value) for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    skipped = []
    failures = []
    ran = 0
    for name, test in tests:
        try:
            test()
            ran += 1
            print("ok   %s" % name)
        except Skipped as reason:
            skipped.append(name)
            print("skip %s -- %s" % (name, reason))
        except Exception as error:  # noqa: BLE001 - the runner must report any failure
            failures.append(name)
            print("FAIL %s -- %s: %s" % (name, type(error).__name__, error))
    print("")
    print("%d passed, %d skipped, %d failed" % (ran, len(skipped), len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())

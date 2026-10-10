"""Command line entry point: ``python -m layarender <command>``.

Every command is usable without credentials: the deterministic commands (``inspect``,
``validate``, ``review``, ``contract``) need no model and no MCP server, and ``run`` defaults to
shadow mode, where calls are recorded and nothing is written to the scene.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from .adapters.laya_ai import DEFAULT_MODEL_ID, build_laya_adapter
from .adapters.render_mcp import RenderMcpAdapter
from .adapters.transport import McpClientTransport, RecordingTransport, TransportError
from .calibrate import DEFAULT_THRESHOLDS, calibrate_route, render_calibration_text
from .contracts import SceneContract, compile_from_brief
from .control import (ControlPlaneConfig, PolicyPlanner, SceneControlPlane, allowed_routes,
                      build_evidence_pack)
from .models import load_run_state
from .policy import policy_from_contract
from .report import final_report, render_report_text
from .reviewer import MeasuredReviewer, measure_view
from .scene import SceneReadError, read_scene
from .validators import run_scene_checks
from .views import ensure_views
from .models import ViewRender


def _load_contract(path: str) -> SceneContract:
    return SceneContract.load(path)


def _print(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(payload if isinstance(payload, str) else json.dumps(payload, indent=2, default=str))


def cmd_inspect(args: argparse.Namespace) -> int:
    try:
        snapshot = read_scene(args.scene)
    except SceneReadError as error:
        print("cannot read scene: %s" % error, file=sys.stderr)
        return 2
    if args.json:
        _print(snapshot.to_dict(), True)
        return 0
    summary = snapshot.summary()
    print("scene %s" % summary["source"])
    print("  generator   : %s" % summary["generator"])
    print("  objects     : %s   materials: %s   triangles: %s" % (summary["objects"],
                                                                  summary["materials"],
                                                                  summary["triangles"]))
    print("  dimensions  : %s (units: as declared by the scene)" % summary["dimensions"])
    print("  revision    : %s" % summary["revision"])
    names = [obj.name for obj in snapshot.objects]
    print("  objects     : %s%s" % (", ".join(names[:12]), " ..." if len(names) > 12 else ""))
    return 0


def cmd_contract(args: argparse.Namespace) -> int:
    if args.from_brief:
        with open(args.from_brief, "r", encoding="utf-8") as handle:
            brief = json.load(handle)
        contract = compile_from_brief(brief)
    elif args.contract:
        contract = _load_contract(args.contract)
    else:
        print("pass --contract PATH or --from-brief PATH", file=sys.stderr)
        return 2
    if args.out:
        contract.save(args.out)
        print("wrote %s" % args.out)
    if args.json:
        _print(contract.to_dict(), True)
    else:
        print("goal: %s" % contract.goal)
        print("requirements: %d mandatory of %d" % (len(contract.mandatory_requirements()),
                                                    len(contract.requirements)))
        print("required views: %s" % contract.required_view_names())
        print("write scope: %s   max rounds: %d" % (contract.write_scope_patterns(),
                                                    contract.max_revision_rounds))
    return 0


def _views_from_args(specs: List[str], contract: SceneContract) -> List[ViewRender]:
    """``--view name=path`` supplies renders to validate against."""
    records: List[ViewRender] = []
    declared = {spec.name: spec for spec in ensure_views(contract, contract.render_size())}
    for spec in specs:
        if "=" not in spec:
            print("--view expects name=path, got %r" % spec, file=sys.stderr)
            continue
        name, path = spec.split("=", 1)
        spec_obj = declared.get(name)
        record = ViewRender(name=name, path=path, rendered=os.path.exists(path),
                            camera=spec_obj.camera if spec_obj else None,
                            fingerprint=spec_obj.fingerprint() if spec_obj else {})
        if not record.rendered:
            record.detail = "file not found"
        records.append(record)
    return records


def cmd_validate(args: argparse.Namespace) -> int:
    contract = _load_contract(args.contract)
    snapshot = None
    error: Optional[Exception] = None
    if args.scene:
        try:
            snapshot = read_scene(args.scene)
        except SceneReadError as exception:
            error = exception
    views = _views_from_args(args.view or [], contract)
    checks = run_scene_checks(snapshot, contract, views, args.scene or "(no scene supplied)", error)
    payload = {
        "checks": {result.name: {"status": result.status, "detail": result.detail,
                                 "expected": result.expected, "actual": result.actual,
                                 "mandatory": result.mandatory}
                   for result in checks.results},
        "summary": checks.summary(),
        "passed": checks.passed(),
        "failures": [result.name for result in checks.failures()],
        "not_run": [result.name for result in checks.not_run()],
    }
    if args.json:
        _print(payload, True)
    else:
        for result in checks.results:
            print("[%-7s] %s -- %s" % (result.status, result.name, result.detail))
        print("")
        print("mandatory failures: %s" % (", ".join(payload["failures"]) or "none"))
        print("checks not run    : %s" % (", ".join(payload["not_run"]) or "none"))
    return 0 if checks.passed() else 1


def cmd_review(args: argparse.Namespace) -> int:
    contract = _load_contract(args.contract) if args.contract else None
    views: List[ViewRender] = []
    for spec in args.image or []:
        if "=" not in spec:
            print("--image expects view=path, got %r" % spec, file=sys.stderr)
            return 2
        name, path = spec.split("=", 1)
        views.append(ViewRender(name=name, path=path, rendered=os.path.exists(path)))
    if not views:
        print("pass at least one --image view=path", file=sys.stderr)
        return 2
    findings: List[Dict[str, Any]] = []
    measurements: List[Dict[str, Any]] = []
    for view in views:
        if not view.rendered:
            print("skipping %s: no image at %s" % (view.name, view.path), file=sys.stderr)
            continue
        measurement = measure_view(view)
        view.stats = measurement.to_dict()
        measurements.append(measurement.to_dict())
        if contract is not None:
            review = MeasuredReviewer().review([view], contract)
            findings.extend(finding.to_dict() for finding in review.findings)
    payload = {"measurements": measurements, "findings": findings}
    if args.json:
        _print(payload, True)
    else:
        for measurement in measurements:
            print("%s (%dx%d)" % (measurement["view"], measurement["width"], measurement["height"]))
            print("  coverage             : %.1f%%" % (measurement["coverage"] * 100))
            print("  subject box          : %s" % measurement["subject_box"])
            print("  edge touch           : %s" % measurement["edge_touch"])
            print("  silhouette contrast  : %.4f" % measurement["silhouette_contrast"])
            print("  mean luminance       : %.4f" % measurement["mean_luma"])
            print("  highlight clip       : %.2f%%   shadow clip: %.2f%%"
                  % (measurement["highlight_clip"] * 100, measurement["shadow_clip"] * 100))
        if findings:
            print("")
            print("findings (measured from the images):")
            for finding in findings:
                print("  [%s/%s] %s (%s) -- %s"
                      % (finding["severity"], finding["result"], finding["criterion"],
                         finding["view"], finding["evidence"]))
    return 0


def _build_transport(args: argparse.Namespace) -> Any:
    if args.mcp_command:
        parts = args.mcp_command.split()
        return McpClientTransport(parts[0], parts[1:])
    return RecordingTransport()


def _build_plane(args: argparse.Namespace, contract: SceneContract,
                 apply_changes: bool) -> SceneControlPlane:
    policy = policy_from_contract(contract, shadow_mode=not apply_changes)
    laya = build_laya_adapter(mode=args.laya, model_id=args.laya_model, device=args.laya_device,
                              subfolder=args.laya_subfolder,
                              executable=args.laya_executable.split()
                              if args.laya_executable else "laya",
                              cwd=args.laya_cwd, min_confidence=args.min_confidence,
                              timeout=args.laya_timeout)
    transport = _build_transport(args)
    render = RenderMcpAdapter(transport=transport, policy=policy)
    existing: Dict[str, str] = {}
    for item in args.existing_view or []:
        if "=" in item:
            name, path = item.split("=", 1)
            existing[name] = path
    config = ControlPlaneConfig(
        shadow_mode=policy.shadow_mode, max_rounds=args.max_rounds, user_prompt=args.user_prompt,
        scene_path=args.scene, run_dir=args.run_dir, existing_views=existing,
        external_findings_path=args.findings, scene_context_path=args.scene_context,
        require_approval_callback=(lambda plan, preflight: bool(args.approve)))
    return SceneControlPlane(contract=contract, policy=policy, laya=laya, render=render,
                             planner=PolicyPlanner(), config=config)


def cmd_plan(args: argparse.Namespace) -> int:
    """One round only: propose, preflight, gate, and record. No loop."""
    contract = _load_contract(args.contract)
    plane = _build_plane(args, contract, apply_changes=args.apply)
    plane.load_scene()
    state = plane.start(brief={"goal": contract.goal})
    round_ = plane.run_round(state, previous=None)
    payload = {
        "state": state.to_dict(),
        "report": plane.report(state),
        "recorded_mcp_calls": [call.to_dict() for call in plane.render.transport.calls()]
        if hasattr(plane.render.transport, "calls") else [],
    }
    _write_outputs(plane, state, payload, args)
    if args.json:
        _print(payload, True)
    else:
        print(render_report_text(payload["report"]))
        print("")
        print("recorded MCP calls (not executed in shadow mode): %d"
              % len(payload["recorded_mcp_calls"]))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    contract = _load_contract(args.contract)
    plane = _build_plane(args, contract, apply_changes=args.apply)
    plane.load_scene()
    state = plane.run(brief={"goal": contract.goal})
    payload = {"state": state.to_dict(), "report": plane.report(state),
               "recorded_mcp_calls": [call.to_dict() for call in plane.render.transport.calls()]
               if hasattr(plane.render.transport, "calls") else []}
    _write_outputs(plane, state, payload, args)
    if args.json:
        _print(payload, True)
    else:
        print(render_report_text(payload["report"]))
    return 0 if state.outcome == "accepted" else 1


def _write_outputs(plane: SceneControlPlane, state: Any, payload: Dict[str, Any],
                   args: argparse.Namespace) -> None:
    directory = os.path.join(args.run_dir, state.task_id)
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "run_state.json"), "w", encoding="utf-8") as handle:
        handle.write(state.to_json())
    with open(os.path.join(directory, "report.json"), "w", encoding="utf-8") as handle:
        json.dump(payload["report"], handle, indent=2, default=str)
    if payload.get("recorded_mcp_calls"):
        with open(os.path.join(directory, "mcp_calls.json"), "w", encoding="utf-8") as handle:
            json.dump(payload["recorded_mcp_calls"], handle, indent=2, default=str)
    print("run state : %s" % os.path.join(directory, "run_state.json"))
    print("report    : %s" % os.path.join(directory, "report.json"))


def cmd_calibrate(args: argparse.Namespace) -> int:
    """Measure what the route decision is actually worth before trusting it to gate a write.

    Runs the real question against the real evidence pack this project produces -- the same pack
    ``run`` routes from -- and reports whether the answer survives option reordering, whether the
    model is deterministic, and what a range of thresholds would do. Nothing is written.
    """
    contract = _load_contract(args.contract)
    plane = _build_plane(args, contract, apply_changes=False)
    plane.load_scene()
    state = plane.start(brief={"goal": contract.goal})
    assessed = plane.assess(state)
    pack = build_evidence_pack(state, contract, plane.snapshot, checks=assessed.checks,
                               review=assessed.review,
                               allowed_ops=sorted(plane.policy.allowed_ops))
    pack["round"] = 0
    routes = allowed_routes(state, assessed.checks, assessed.review, False)
    hard = [result.name for result in (assessed.checks.failures() if assessed.checks else [])]

    thresholds = args.thresholds if args.thresholds else list(DEFAULT_THRESHOLDS)
    report = calibrate_route(plane.laya, pack, routes, min_confidence=args.min_confidence,
                             priority_options=hard[:8] or None, thresholds=thresholds,
                             repeat=args.repeat, max_orderings=args.orderings)
    report["run"] = {
        "task_id": state.task_id,
        "allowed_routes": routes,
        "hard_failures": hard,
        "state": plane.laya.describe(),
        "scene_revision": state.scene_revision,
    }
    directory = os.path.join(args.run_dir, state.task_id)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "calibration.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, default=str)

    if args.json:
        _print(report, True)
    else:
        print(render_calibration_text(report))
    print("")
    print("calibration: %s" % path)
    if not report.get("ok"):
        return 2
    return 0 if report["verdict"]["trustworthy"] else 1


def cmd_report(args: argparse.Namespace) -> int:
    state = load_run_state(args.run_state)
    report = final_report(state, shadow_mode=bool(state.modes.get("shadow_mode", True)))
    if args.json:
        _print(report, True)
    else:
        print(render_report_text(report))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="layarender", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect", help="read the editable scene and print its structure")
    inspect.add_argument("scene", help="path to a .glb or .gltf")
    inspect.add_argument("--json", action="store_true")
    inspect.set_defaults(func=cmd_inspect)

    contract = sub.add_parser("contract", help="show, compile or convert a scene contract")
    contract.add_argument("--contract")
    contract.add_argument("--from-brief", help="compile a contract from a brief JSON file")
    contract.add_argument("--out", help="write the contract here")
    contract.add_argument("--json", action="store_true")
    contract.set_defaults(func=cmd_contract)

    validate = sub.add_parser("validate", help="run the deterministic checks")
    validate.add_argument("--contract", required=True)
    validate.add_argument("--scene", help="the editable scene to check")
    validate.add_argument("--view", action="append", metavar="NAME=PATH",
                          help="a rendered view to check against (repeatable)")
    validate.add_argument("--json", action="store_true")
    validate.set_defaults(func=cmd_validate)

    review = sub.add_parser("review", help="measure rendered views and report located findings")
    review.add_argument("--image", action="append", metavar="NAME=PATH", required=True)
    review.add_argument("--contract", help="needed to interpret a view's declared settings")
    review.add_argument("--json", action="store_true")
    review.set_defaults(func=cmd_review)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--contract", required=True)
    common.add_argument("--scene", help="the editable scene the workflow reads")
    common.add_argument("--apply", action="store_true",
                        help="leave shadow mode and actually issue scene writes")
    common.add_argument("--approve", action="store_true",
                        help="approve operations the policy marks as needing approval")
    common.add_argument("--max-rounds", type=int, default=None)
    common.add_argument("--run-dir", default="runs")
    common.add_argument("--user-prompt", default="")
    common.add_argument("--laya", choices=["auto", "in-process", "cli", "mcp", "none"],
                        default="auto")
    common.add_argument("--laya-executable", default=None,
                        help='e.g. "python -m laya.cli" when the Laya checkout is local')
    common.add_argument("--laya-model", default=DEFAULT_MODEL_ID, metavar="ID_OR_PATH",
                        help="Laya checkpoint: a Hub repo id or a local checkpoint directory "
                             "(default: %(default)s; a complete ~/laya_models is preferred when "
                             "present, and $LAYA_MODEL_DIR overrides that)")
    common.add_argument("--laya-device", default=None, help="e.g. cpu, cuda")
    common.add_argument("--laya-subfolder", default=None,
                        help="pick one checkpoint out of a repo that bundles several")
    common.add_argument("--laya-cwd", default=None,
                        help="working directory for the Laya CLI (its checkout root)")
    common.add_argument("--laya-timeout", type=float, default=60.0)
    common.add_argument("--min-confidence", type=float, default=0.60)
    common.add_argument("--mcp-command", default=None,
                        help='spawn a stdio MCP server, e.g. "python blender_mcp_server.py"')
    common.add_argument("--existing-view", action="append", metavar="NAME=PATH", default=[],
                        help="use an existing render as evidence for a view this run cannot "
                             "render (repeatable)")
    common.add_argument("--findings", default=None,
                        help="a JSON file of located findings from an external reviewer")
    common.add_argument("--scene-context", default=None, metavar="PATH",
                        help="JSON file describing cameras/lights the exported scene cannot "
                             "carry (see contracts/jet-kite.scene-context.json)")
    common.add_argument("--json", action="store_true")

    plan = sub.add_parser("plan", parents=[common], help="one round: propose, preflight, gate")
    plan.set_defaults(func=cmd_plan)

    run = sub.add_parser("run", parents=[common], help="run the bounded control loop")
    run.set_defaults(func=cmd_run)

    calibrate = sub.add_parser("calibrate", parents=[common],
                               help="measure whether the Laya route decision can be trusted "
                                    "before letting it gate a write")
    calibrate.add_argument("--thresholds", type=lambda value: [float(part) for part in
                                                               value.split(",") if part.strip()],
                           default=None,
                           help="comma-separated min_confidence values to tabulate")
    calibrate.add_argument("--repeat", type=int, default=3,
                           help="identical calls used to establish determinism")
    calibrate.add_argument("--orderings", type=int, default=8,
                           help="how many option orders to probe")
    calibrate.set_defaults(func=cmd_calibrate)

    report = sub.add_parser("report", help="render the report for a saved run state")
    report.add_argument("--run-state", required=True)
    report.add_argument("--json", action="store_true")
    report.set_defaults(func=cmd_report)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except FileNotFoundError as error:
        print("missing file: %s" % error, file=sys.stderr)
        return 2
    except TransportError as error:
        print("transport error: %s" % error, file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

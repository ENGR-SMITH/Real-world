"""layarender -- a Laya-gated control plane for MCP-driven 3D render work.

The workflow in one sentence, from the implementation brief: *a creative model proposes a
bounded 3D scene plan, validators and a visual reviewer assess the actual scene and its renders,
Laya routes the next step from structured evidence, and the Render MCP Designer makes only
approved scene changes.*

Layers, each with one job and no overlap:

=====================  ==========================================================================
:mod:`contracts`       the brief compiled into mandatory, machine-checkable requirements
:mod:`scene`           reads the editable scene (``.glb``/``.gltf``) without opening Blender
:mod:`policy`          the operation allowlist, write scope, and the approval gates
:mod:`preflight`       rejects out-of-scope, out-of-unit, or unsupported plans before execution
:mod:`validators`      deterministic checks; "not run" is never reported as "pass"
:mod:`reviewer`        located visual findings, measured from the renders or supplied externally
:mod:`adapters`        separate boundaries for Laya (decisions) and the Render MCP Designer (scene)
:mod:`control`         the bounded loop: propose, gate, apply, render, review, route, stop
:mod:`report`          the delivery report, separating what ran from what was judged
=====================  ==========================================================================

Nothing here is on until a caller builds it: every adapter is injected, so a shadow run needs no
credentials, no checkpoint and no write permission.
"""
from .adapters.laya_ai import (LayaAdapter, LayaMalformed, LayaUnavailable, build_laya_adapter)
from .adapters.render_mcp import ApplyReceipt, RenderMcpAdapter, build_patch_code
from .adapters.transport import (CallableTransport, JsonFileTransport, McpClientTransport,
                                 RecordingTransport)
from .contracts import Requirement, SceneContract, ViewSpec, compile_from_brief
from .control import (CallablePlanner, ControlPlaneConfig, Planner, PolicyPlanner,
                      SceneControlPlane)
from .models import (Decision, Finding, PatchOp, PatchPlan, Route, RunState, Severity,
                     load_run_state)
from .policy import OperationPolicy, policy_from_contract
from .preflight import preflight_plan
from .report import final_report, render_report_text
from .reviewer import MeasuredReviewer, findings_from_payload, load_findings
from .scene import SceneReadError, SceneSnapshot, read_scene
from .validators import run_scene_checks
from .views import default_views, ensure_views

__version__ = "1.0.0"

__all__ = [
    "__version__",
    # contracts and views
    "SceneContract", "Requirement", "ViewSpec", "compile_from_brief", "default_views",
    "ensure_views",
    # scene and validation
    "read_scene", "SceneSnapshot", "SceneReadError", "run_scene_checks",
    # policy and preflight
    "OperationPolicy", "policy_from_contract", "preflight_plan",
    # review
    "MeasuredReviewer", "findings_from_payload", "load_findings",
    # adapters
    "LayaAdapter", "build_laya_adapter", "LayaUnavailable", "LayaMalformed",
    "RenderMcpAdapter", "RecordingTransport", "JsonFileTransport", "McpClientTransport",
    "CallableTransport",
    # control
    "SceneControlPlane", "ControlPlaneConfig", "Planner", "PolicyPlanner", "CallablePlanner",
    # records and reporting
    "RunState", "load_run_state", "Route", "Decision", "Finding", "PatchOp", "PatchPlan",
    "Severity", "final_report", "render_report_text",
]

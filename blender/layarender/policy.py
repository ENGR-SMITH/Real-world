"""Workflow policy: what may be read, what may be written, and what needs a person.

Doc, section 3: "Do not let tool descriptions define the full policy... The orchestrator should
explicitly define which operations are read-only, which can write, what scene scope is allowed,
which views must be rendered, what evidence goes to Laya, how many revisions are permitted, and
when human approval is required."

The allowlist below is built from the Render MCP Designer's **verified** tool surface -- the
tools that the connected server actually exposes. Its one write-capable primitive is
``execute_blender_code``, so the workflow never hands it free-form code: it hands it a
:class:`~layarender.models.PatchOp` whose verb is allowlisted, whose target exists in the
current scene snapshot, and whose parameters are type-checked first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------------------------------------------
# Verified Render MCP Designer surface (read from the live server's tool schemas).
# Keep this list in one place: everything downstream treats it as the allowlist.
# ---------------------------------------------------------------------------------------
READ_ONLY_TOOLS: Dict[str, str] = {
    "get_scene_info": "read the current scene summary",
    "get_object_info": "read one object: transform, materials, mesh counts",
    "get_viewport_screenshot": "capture the viewport as an image",
    "describe_node_type": "look up a node's sockets and enum values",
}

WRITE_TOOLS: Dict[str, str] = {
    "execute_blender_code": "run a bounded bpy snippet (the only scene write path)",
}

DELIVERY_TOOLS: Dict[str, str] = {
    "export_scene": "write a .glb/.fbx delivery file",
}

EXTERNAL_TOOLS: Dict[str, str] = {
    "download_polyhaven_asset": "download an asset over the network",
    "search_polyhaven_assets": "search Poly Haven",
    "generate_hyper3d_model_via_text": "generate geometry through a hosted model",
    "generate_hyper3d_model_via_images": "generate geometry through a hosted model",
    "generate_hunyuan3d_model": "generate geometry through a hosted model",
    "get_hyper3d_status": "read hosted-generator status",
}

# Workflow verbs the creative model may propose, mapped to the tool that executes them and the
# risk class that decides the gate. A verb that is absent here cannot be executed at all.
OP_REGISTRY: Dict[str, Dict[str, Any]] = {
    "set_object_transform": {
        "tool": "execute_blender_code",
        "risk": "scene_write",
        "reversible": True,
        "params": {"location": "vector3", "rotation_euler": "vector3", "scale": "vector3"},
        "requires_target": True,
        "target_kind": "mesh",
        "description": "move / rotate / scale one existing object",
    },
    "nudge_object": {
        "tool": "execute_blender_code",
        "risk": "scene_write",
        "reversible": True,
        "params": {"axis": "axis", "delta": "number"},
        "requires_target": True,
        "target_kind": "mesh",
        "description": "offset one object along one axis by a bounded delta",
    },
    "set_material_param": {
        "tool": "execute_blender_code",
        "risk": "scene_write",
        "reversible": True,
        "params": {"material": "string", "param": "string", "value": "number_or_vector"},
        "requires_target": False,
        "target_kind": "any",
        "description": "set one Principled BSDF input on one material",
    },
    "set_camera": {
        "tool": "execute_blender_code",
        "risk": "scene_write",
        "reversible": True,
        "params": {"location": "vector3", "rotation_euler": "vector3", "lens": "number"},
        "requires_target": True,
        "target_kind": "camera",
        "description": "reposition or relens an existing camera",
    },
    "frame_object_in_camera": {
        "tool": "execute_blender_code",
        "risk": "scene_write",
        "reversible": True,
        "params": {"camera": "string"},
        "requires_target": True,
        "target_kind": "mesh",
        "description": "reframe a camera on one object",
    },
    "set_light": {
        "tool": "execute_blender_code",
        "risk": "scene_write",
        "reversible": True,
        "params": {"energy": "number", "size": "number", "color": "vector3"},
        "requires_target": True,
        "target_kind": "light",
        "description": "adjust one existing light",
    },
    "set_render_setting": {
        "tool": "execute_blender_code",
        "risk": "scene_write",
        "reversible": True,
        "params": {"key": "string", "value": "number_or_string"},
        "requires_target": False,
        "target_kind": "any",
        "description": "set one scene render setting",
    },
    "duplicate_object": {
        "tool": "execute_blender_code",
        "risk": "scene_write",
        "reversible": True,
        "params": {"offset": "vector3", "new_name": "string"},
        "requires_target": True,
        "target_kind": "mesh",
        "description": "duplicate one object with a new name",
    },
    "add_primitive": {
        "tool": "execute_blender_code",
        "risk": "scene_write_broad",
        "reversible": True,
        "params": {"primitive": "primitive", "location": "vector3", "size": "number"},
        "requires_target": False,
        "target_kind": "any",
        "description": "add one primitive (ground plane, card, backdrop)",
    },
    "delete_object": {
        "tool": "execute_blender_code",
        "risk": "destructive",
        "reversible": False,
        "params": {},
        "requires_target": True,
        "target_kind": "mesh",
        "description": "delete one object; never automatic",
    },
    "render_view": {
        "tool": "execute_blender_code",
        "risk": "render",
        "reversible": True,
        "params": {"view": "string"},
        "requires_target": False,
        "target_kind": "any",
        "description": "render one canonical view to disk",
    },
    "export_scene": {
        "tool": "export_scene",
        "risk": "delivery",
        "reversible": True,
        "params": {"filepath": "string", "format": "string"},
        "requires_target": False,
        "target_kind": "any",
        "description": "write the delivery file",
    },
}

RISK_SCENE_WRITE = "scene_write"
RISK_SCENE_WRITE_BROAD = "scene_write_broad"
RISK_DESTRUCTIVE = "destructive"

# A plan touching more than this many objects, or more than this many ops, is "broad" and needs
# a person. The doc asks for the smallest reversible edit; these are the bounds that enforce it.
MAX_OPS_PER_PLAN = 3
MAX_TARGETS_PER_PLAN = 2


@dataclass
class OperationPolicy:
    """The workflow's own policy object, independent of any tool description."""

    allowed_read_tools: Set[str] = field(default_factory=lambda: set(READ_ONLY_TOOLS))
    allowed_write_tools: Set[str] = field(default_factory=lambda: set(WRITE_TOOLS))
    allowed_delivery_tools: Set[str] = field(default_factory=lambda: set(DELIVERY_TOOLS))
    allowed_external_tools: Set[str] = field(default_factory=lambda: set(EXTERNAL_TOOLS))
    allowed_ops: Set[str] = field(default_factory=lambda: set(OP_REGISTRY))
    write_scope: List[str] = field(default_factory=lambda: ["*"])
    max_ops_per_plan: int = MAX_OPS_PER_PLAN
    max_targets_per_plan: int = MAX_TARGETS_PER_PLAN
    allow_external_generators: bool = False
    shadow_mode: bool = True
    require_approval_for_destructive: bool = True
    require_approval_for_broad: bool = True

    # ---- capability -------------------------------------------------------------------
    def tool_for(self, op: str) -> Optional[str]:
        entry = OP_REGISTRY.get(op)
        return entry["tool"] if entry else None

    def is_allowlisted(self, op: str) -> bool:
        return op in self.allowed_ops

    def risk_of(self, op: str) -> str:
        entry = OP_REGISTRY.get(op)
        return entry["risk"] if entry else "unknown"

    def reversible(self, op: str) -> bool:
        entry = OP_REGISTRY.get(op)
        return bool(entry and entry["reversible"])

    def params_of(self, op: str) -> Dict[str, str]:
        entry = OP_REGISTRY.get(op)
        return dict(entry.get("params", {})) if entry else {}

    def requires_target(self, op: str) -> bool:
        entry = OP_REGISTRY.get(op)
        return bool(entry and entry.get("requires_target"))

    def target_kind(self, op: str) -> str:
        """What kind of object the operation needs: ``mesh``, ``camera``, ``light`` or ``any``.

        This exists because an exported ``.glb`` carries meshes but not the scene's cameras or
        lights. An operation that needs a camera or a light therefore cannot be verified from the
        exported artifact alone, and the preflight says so instead of assuming the target exists
        and is the right type.
        """
        entry = OP_REGISTRY.get(op)
        return str(entry.get("target_kind", "mesh")) if entry else "mesh"

    # ---- gates ------------------------------------------------------------------------
    def gate(self, op: str, target_count: int = 1, plan_ops: int = 1) -> Dict[str, Any]:
        """Decide whether one operation may run automatically.

        Returns ``{"allowed": bool, "requires_approval": bool, "reason": str}``. The rule the
        doc states is: "Require human approval for destructive, broad, hard-to-reverse, or
        out-of-scope changes."
        """
        if not self.is_allowlisted(op):
            return {"allowed": False, "requires_approval": False,
                    "reason": "operation %r is not in the verified allowlist" % op}
        risk = self.risk_of(op)
        if risk == RISK_DESTRUCTIVE and self.require_approval_for_destructive:
            return {"allowed": True, "requires_approval": True,
                    "reason": "destructive and not reversible"}
        if not self.reversible(op):
            return {"allowed": True, "requires_approval": True,
                    "reason": "operation is not reversible"}
        if risk == RISK_SCENE_WRITE_BROAD and self.require_approval_for_broad:
            return {"allowed": True, "requires_approval": True,
                    "reason": "broad scene change (%s)" % op}
        if plan_ops > self.max_ops_per_plan:
            return {"allowed": True, "requires_approval": True,
                    "reason": "plan proposes %d operations (limit %d)"
                              % (plan_ops, self.max_ops_per_plan)}
        if target_count > self.max_targets_per_plan:
            return {"allowed": True, "requires_approval": True,
                    "reason": "plan touches %d objects (limit %d)"
                              % (target_count, self.max_targets_per_plan)}
        return {"allowed": True, "requires_approval": False, "reason": ""}

    def in_write_scope(self, target: Optional[str]) -> bool:
        """Write scope is expressed as object glob patterns; ``*`` means the whole target scene."""
        import fnmatch

        if not target:
            # Scene-level ops (render settings, exports) are governed by scope presence.
            return bool(self.write_scope)
        return any(fnmatch.fnmatchcase(target, pattern) for pattern in self.write_scope)

    def describe(self) -> Dict[str, Any]:
        return {
            "read_tools": sorted(self.allowed_read_tools),
            "write_tools": sorted(self.allowed_write_tools),
            "delivery_tools": sorted(self.allowed_delivery_tools),
            "external_tools_allowed": self.allow_external_generators,
            "ops": sorted(self.allowed_ops),
            "write_scope": list(self.write_scope),
            "max_ops_per_plan": self.max_ops_per_plan,
            "max_targets_per_plan": self.max_targets_per_plan,
            "shadow_mode": self.shadow_mode,
        }


def policy_from_contract(contract: Any, shadow_mode: bool = True) -> OperationPolicy:
    """Build the policy from a scene contract: the contract owns the write scope."""
    scope = contract.write_scope_patterns() if hasattr(contract, "write_scope_patterns") else ["*"]
    return OperationPolicy(write_scope=list(scope) or ["*"], shadow_mode=shadow_mode)

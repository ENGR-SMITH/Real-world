"""The Render MCP Designer adapter: the only place in the workflow that touches the scene.

Doc, section 3: "Keep Render MCP-specific operations behind a separate adapter." This module is
that boundary. It speaks the server's verified tool surface (``get_scene_info``,
``get_object_info``, ``get_viewport_screenshot``, ``describe_node_type`` to read;
``execute_blender_code`` to write; ``export_scene`` to deliver) and nothing above it needs to
know a tool name.

Two properties matter more than convenience:

* **Allowlisted by construction.** :meth:`RenderMcpAdapter.apply_patch` refuses an operation that
  is not in the policy allowlist or was not preflighted, so a caller cannot reach
  ``execute_blender_code`` with free-form code by mistake.
* **Scoped by construction.** The generated ``bpy`` snippet runs one operation on the targets the
  preflight resolved, then prints a JSON receipt. It never deletes, never saves over the project
  file, and never touches objects outside the plan.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..models import PatchOp, PatchPlan, PreflightResult, ViewRender
from ..policy import OP_REGISTRY, OperationPolicy
from ..scene import SceneSnapshot
from ..views import blender_source, render_arguments

READ_CALL_TIMEOUT_S = 60.0
RETRY_LIMIT = 1  # the doc allows one bounded retry of a supported path, and no more


class RenderMcpError(RuntimeError):
    """A Render MCP Designer call failed in a way the workflow must record, not hide."""


@dataclass
class ApplyReceipt:
    ok: bool
    detail: str = ""
    payload: Any = None
    code: str = ""
    latency_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "detail": self.detail, "payload": self.payload,
                "latency_ms": self.latency_ms}


def _vector3(value: Any) -> Optional[List[float]]:
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return [float(v) for v in value]
    return None


def build_op_code(op: PatchOp) -> str:
    """Compile one allowlisted workflow operation into a bounded ``bpy`` snippet.

    The snippet is defensive: it looks the target up by name, asserts it exists and is the right
    kind of object, performs exactly one change, and prints a JSON receipt that the adapter reads
    back. An operation with no compiler raises, so adding a verb to the registry without a
    compiler fails loudly instead of writing nothing.
    """
    parameters = op.parameters
    target = op.target

    def lookup(kind: Optional[str] = None) -> str:
        lines = ["target = bpy.data.objects.get(%r)" % target,
                 "assert target is not None, 'object %s not found'" % target]
        if kind:
            lines.append("assert target.type == %r, 'object %s is %%s, not %s' %% target.type"
                         % (kind, target, kind))
        return "\n".join(lines)

    if op.op == "nudge_object":
        axis = str(parameters.get("axis", "x")).lower()
        delta = float(parameters.get("delta", 0.0))
        index = {"x": 0, "y": 1, "z": 2}[axis]
        return "\n".join([
            "import bpy", lookup(), "delta = %r" % delta, "index = %d" % index,
            "target.location[index] = target.location[index] + delta",
            "bpy.context.view_layer.update()",
            "print('RECEIPT ' + __import__('json').dumps({'op': 'nudge_object', 'object': target.name, 'location': list(target.location)}))",
        ])

    if op.op == "set_object_transform":
        lines = ["import bpy", lookup()]
        location = _vector3(parameters.get("location"))
        rotation = _vector3(parameters.get("rotation_euler"))
        scale = _vector3(parameters.get("scale"))
        if location:
            lines.append("target.location = %r" % location)
        if rotation:
            lines.append("target.rotation_euler = %r" % rotation)
        if scale:
            lines.append("target.scale = %r" % scale)
        lines.append("bpy.context.view_layer.update()")
        lines.append("print('RECEIPT ' + __import__('json').dumps({'op': 'set_object_transform', "
                     "'object': target.name, 'location': list(target.location), "
                     "'rotation_euler': list(target.rotation_euler), 'scale': list(target.scale)}))")
        return "\n".join(lines)

    if op.op == "set_material_param":
        material = parameters.get("material")
        param = parameters.get("param")
        value = parameters.get("value")
        return "\n".join([
            "import bpy",
            "material = bpy.data.materials.get(%r)" % material,
            "assert material is not None, 'material %s not found'" % material,
            "assert material.use_nodes, 'material %s has no node tree'" % material,
            "node = next((n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)",
            "assert node is not None, 'material %s has no Principled BSDF'" % material,
            "socket = node.inputs.get(%r)" % param,
            "assert socket is not None, 'socket %s not found on %s'" % (param, material),
            "socket.default_value = %r" % (value if not isinstance(value, list) else tuple(value)),
            "material.node_tree.update_tag()",
            "print('RECEIPT ' + __import__('json').dumps({'op': 'set_material_param', "
            "'material': material.name, 'param': socket.name}))",
        ])

    if op.op == "set_light":
        lines = ["import bpy", lookup("LIGHT")]
        if parameters.get("energy") is not None:
            lines.append("target.data.energy = %r" % float(parameters["energy"]))
        if parameters.get("size") is not None:
            lines.append("target.data.size = %r" % float(parameters["size"]))
        color = _vector3(parameters.get("color"))
        if color:
            lines.append("target.data.color = %r" % color)
        lines.append("print('RECEIPT ' + __import__('json').dumps({'op': 'set_light', "
                     "'object': target.name, 'energy': target.data.energy}))")
        return "\n".join(lines)

    if op.op == "set_camera":
        lines = ["import bpy", lookup("CAMERA")]
        location = _vector3(parameters.get("location"))
        rotation = _vector3(parameters.get("rotation_euler"))
        if location:
            lines.append("target.location = %r" % location)
        if rotation:
            lines.append("target.rotation_euler = %r" % rotation)
        if parameters.get("lens") is not None:
            lines.append("target.data.lens = %r" % float(parameters["lens"]))
        lines.append("bpy.context.view_layer.update()")
        lines.append("print('RECEIPT ' + __import__('json').dumps({'op': 'set_camera', "
                     "'object': target.name, 'lens': target.data.lens}))")
        return "\n".join(lines)

    if op.op == "frame_object_in_camera":
        camera = parameters.get("camera") or target
        return "\n".join([
            "import bpy",
            "camera = bpy.data.objects.get(%r)" % camera,
            "assert camera is not None and camera.type == 'CAMERA', 'camera %s not found'" % camera,
            "subject = bpy.data.objects.get(%r)" % target,
            "assert subject is not None, 'object %s not found'" % target,
            "scene = bpy.context.scene",
            "scene.camera = camera",
            "bpy.ops.object.select_all(action='DESELECT')",
            "subject.select_set(True)",
            "bpy.context.view_layer.objects.active = subject",
            "bpy.ops.view3d.camera_to_view_selected()",
            "print('RECEIPT ' + __import__('json').dumps({'op': 'frame_object_in_camera', "
            "'camera': camera.name, 'subject': subject.name, "
            "'location': list(subject.location)}))",
        ])

    if op.op == "set_render_setting":
        key = parameters.get("key")
        value = parameters.get("value")
        return "\n".join([
            "import bpy",
            "scene = bpy.context.scene",
            "render = scene.render",
            "assert hasattr(render, %r) or hasattr(scene, %r), 'unknown render setting %s'"
            % (key, key, key),
            "if hasattr(render, %r): setattr(render, %r, %r)" % (key, key, value),
            "elif hasattr(scene, %r): setattr(scene, %r, %r)" % (key, key, value),
            "print('RECEIPT ' + __import__('json').dumps({'op': 'set_render_setting', "
            "'key': %r, 'value': %r}))" % (key, value),
        ])

    if op.op == "duplicate_object":
        new_name = parameters.get("new_name") or "%s_copy" % target
        offset = _vector3(parameters.get("offset")) or [0.0, 0.0, 0.0]
        return "\n".join([
            "import bpy",
            "source = bpy.data.objects.get(%r)" % target,
            "assert source is not None, 'object %s not found'" % target,
            "duplicate = source.copy()",
            "duplicate.data = source.data.copy()",
            "duplicate.name = %r" % new_name,
            "duplicate.location = source.location + __import__('mathutils').Vector(%r)" % offset,
            "bpy.context.collection.objects.link(duplicate)",
            "print('RECEIPT ' + __import__('json').dumps({'op': 'duplicate_object', "
            "'object': duplicate.name}))",
        ])

    if op.op == "add_primitive":
        primitive = str(parameters.get("primitive", "plane"))
        location = _vector3(parameters.get("location")) or [0.0, 0.0, 0.0]
        size = float(parameters.get("size", 1.0))
        return "\n".join([
            "import bpy",
            "bpy.ops.mesh.primitive_%s_add(location=%r)" % (primitive, location),
            "created = bpy.context.active_object",
            "created.scale = (%r, %r, %r)" % (size, size, size),
            "print('RECEIPT ' + __import__('json').dumps({'op': 'add_primitive', "
            "'object': created.name, 'primitive': %r}))" % primitive,
        ])

    raise RenderMcpError("no compiler for operation %r" % op.op)


def build_patch_code(plan: PatchPlan) -> str:
    """Compile a whole plan into one snippet, so a round makes one scoped write call."""
    parts = ["# layarender patch plan %s" % plan.candidate_id,
             "# %s" % (plan.intent or "no intent recorded")]
    for op in plan.ops:
        parts.append("# --- %s -> %s" % (op.op, op.target or "scene"))
        parts.append(build_op_code(op))
    return "\n\n".join(parts)


@dataclass
class RenderMcpAdapter:
    """Read and write the scene through the verified Render MCP Designer surface."""

    transport: Any
    policy: OperationPolicy
    snapshot: Optional[SceneSnapshot] = None
    retry_limit: int = RETRY_LIMIT
    calls_made: List[Dict[str, Any]] = field(default_factory=list)

    # ---- reads ------------------------------------------------------------------------
    def _call(self, tool: str, arguments: Dict[str, Any], read_only: bool) -> Any:
        if read_only and tool not in self.policy.allowed_read_tools:
            raise RenderMcpError("tool %r is not an allowlisted read tool" % tool)
        if not read_only and tool not in (set(self.policy.allowed_write_tools)
                                         | set(self.policy.allowed_delivery_tools)):
            raise RenderMcpError("tool %r is not an allowlisted write tool" % tool)
        started = time.time()
        attempts = 0
        last_error: Optional[Exception] = None
        while attempts <= self.retry_limit:
            attempts += 1
            try:
                payload = self.transport.call(tool, arguments, read_only=read_only)
                self.calls_made.append({
                    "tool": tool, "arguments": arguments, "read_only": read_only, "ok": True,
                    "attempt": attempts, "latency_ms": round((time.time() - started) * 1000, 2),
                })
                return payload
            except Exception as error:  # NotExecuted included: shadow mode is a normal outcome
                last_error = error
                if type(error).__name__ == "NotExecuted":
                    break
        self.calls_made.append({
            "tool": tool, "arguments": arguments, "read_only": read_only, "ok": False,
            "attempt": attempts, "error": str(last_error),
            "latency_ms": round((time.time() - started) * 1000, 2),
        })
        raise RenderMcpError("call %s failed: %s" % (tool, last_error))

    def read_scene(self, user_prompt: str) -> Any:
        return self._call("get_scene_info", {"user_prompt": user_prompt}, True)

    def read_object(self, name: str, user_prompt: str) -> Any:
        return self._call("get_object_info", {"object_name": name, "user_prompt": user_prompt}, True)

    def screenshot(self, user_prompt: str, max_size: int = 1000) -> Any:
        return self._call("get_viewport_screenshot",
                          {"max_size": max_size, "user_prompt": user_prompt}, True)

    def describe_node(self, bl_idname: str, user_prompt: str,
                      overrides: Optional[Dict[str, Any]] = None) -> Any:
        arguments: Dict[str, Any] = {"bl_idname": bl_idname, "user_prompt": user_prompt}
        if overrides:
            arguments["property_overrides"] = overrides
        return self._call("describe_node_type", arguments, True)

    # ---- writes -----------------------------------------------------------------------
    def apply_patch(self, plan: PatchPlan, preflight: PreflightResult, user_prompt: str,
                    approved: bool = False) -> ApplyReceipt:
        """Apply a preflighted plan. Refuses anything that did not pass preflight."""
        if not preflight.ok:
            return ApplyReceipt(False, "preflight did not pass: %s" % "; ".join(preflight.errors))
        if preflight.requires_approval and not approved:
            return ApplyReceipt(False, "approval required and not given: %s"
                                % preflight.approval_reason)
        if not plan.ops:
            return ApplyReceipt(False, "plan has no operations")
        for op in plan.ops:
            if not self.policy.is_allowlisted(op.op):
                return ApplyReceipt(False, "operation %r is not allowlisted" % op.op)
            tool = OP_REGISTRY[op.op]["tool"]
            if tool not in set(self.policy.allowed_write_tools):
                return ApplyReceipt(False, "operation %r maps to non-write tool %r" % (op.op, tool))
        if self.policy.shadow_mode:
            return ApplyReceipt(False, "shadow mode: no scene write was issued",
                                payload={"plan": plan.to_dict()})

        code = build_patch_code(plan)
        started = time.time()
        try:
            payload = self._call("execute_blender_code",
                                 {"code": code, "user_prompt": user_prompt}, False)
        except RenderMcpError as error:
            return ApplyReceipt(False, str(error), code=code,
                                latency_ms=round((time.time() - started) * 1000, 2))
        return ApplyReceipt(True, "applied %d operation(s)" % len(plan.ops), payload=payload,
                            code=code, latency_ms=round((time.time() - started) * 1000, 2))

    def render_view(self, view_name: str, camera: str, output_path: str,
                    user_prompt: str, resolution: Optional[List[int]] = None,
                    frame_object: Optional[str] = None, engine: str = "BLENDER_EEVEE_NEXT",
                    samples: int = 64, film_transparent: bool = False,
                    look: str = "AgX - Medium High Contrast",
                    scene_settings: Optional[Dict[str, Any]] = None) -> ViewRender:
        """Render one canonical view and report exactly what was rendered.

        The returned :class:`ViewRender` is ``rendered=False`` unless the file really exists,
        so a failed render cannot be counted as a rendered view by the validators.
        """
        from ..contracts import ViewSpec

        spec = ViewSpec(name=view_name, camera=camera, resolution=list(resolution or [1200, 800]),
                        engine=engine, samples=samples, film_transparent=film_transparent,
                        look=look)
        arguments = render_arguments(spec, output_path, scene_settings)
        code = blender_source(arguments, frame_object=frame_object)
        record = ViewRender(name=view_name, path=output_path, camera=camera,
                            fingerprint=arguments, detail="")
        if self.policy.shadow_mode:
            record.detail = "shadow mode: render recorded, not executed"
            return record
        try:
            self._call("execute_blender_code", {"code": code, "user_prompt": user_prompt}, False)
        except RenderMcpError as error:
            record.detail = str(error)
            return record
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            record.rendered = True
            record.detail = "rendered %dx%d" % (arguments["resolution_x"],
                                                arguments["resolution_y"])
        else:
            record.detail = "render call returned but no file was written at %s" % output_path
        return record

    def export(self, filepath: str, user_prompt: str, fmt: str = "glb",
               object_names: Optional[List[str]] = None, apply_modifiers: bool = True) -> Dict[str, Any]:
        arguments: Dict[str, Any] = {"filepath": filepath, "format": fmt,
                                     "apply_modifiers": apply_modifiers,
                                     "user_prompt": user_prompt}
        if object_names:
            arguments["object_names"] = list(object_names)
        if self.policy.shadow_mode:
            return {"ok": False, "detail": "shadow mode: export recorded, not executed",
                    "arguments": arguments}
        try:
            payload = self._call("export_scene", arguments, False)
        except RenderMcpError as error:
            return {"ok": False, "detail": str(error), "arguments": arguments}
        exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0
        return {"ok": exists, "detail": "exported %s" % filepath if exists
                else "export call returned but no file at %s" % filepath,
                "arguments": arguments, "payload": payload}

    # ---- bookkeeping -------------------------------------------------------------------
    def transcript(self) -> List[Dict[str, Any]]:
        return list(self.calls_made)

    def capabilities(self) -> Dict[str, Any]:
        return {
            "read_tools": sorted(self.policy.allowed_read_tools),
            "write_tools": sorted(self.policy.allowed_write_tools),
            "delivery_tools": sorted(self.policy.allowed_delivery_tools),
            "shadow_mode": self.policy.shadow_mode,
            "verified_surface": {
                "execute_blender_code": "the single write primitive; always handed scoped bpy",
                "get_scene_info": "scene summary",
                "get_object_info": "object transform, materials, counts",
                "get_viewport_screenshot": "viewport image",
                "describe_node_type": "node socket/enum schema",
                "export_scene": "glb/fbx delivery",
            },
        }

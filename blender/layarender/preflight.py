"""Deterministic preflight: reject unsupported or out-of-scope plans before execution.

Doc, section 4 step 6: "Validate operation schema and scope; object references; units; transform
ranges; required components; supported materials; geometry or texture limits where measurable;
and whether the change is reversible. Reject unsupported or out-of-scope plans before
execution."

Nothing in this module calls a model or an MCP server. It is the cheapest place to catch a bad
plan, so it runs before the Laya decision rather than after it: a plan that cannot legally run
is never worth a decision round trip.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .contracts import SceneContract
from .models import PatchPlan, PreflightResult
from .policy import OP_REGISTRY, OperationPolicy
from .scene import SceneSnapshot

PRIMITIVES = {"cube", "plane", "cylinder", "sphere", "torus", "circle", "cone", "grid"}
AXES = {"x", "y", "z", "X", "Y", "Z"}

# A "small, located edit" bound: no single transform op may move an object by more than this
# fraction of the scene's largest dimension. Anything larger is a rewrite, not a revision.
MAX_TRANSLATION_FRACTION = 0.25
# Sanity bound on any absolute parameter that is a length in scene units.
MAX_LENGTH_METERS = 100.0


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_vector3(value: Any) -> bool:
    return (isinstance(value, (list, tuple)) and len(value) == 3
            and all(_is_number(component) for component in value))


def _check_param(name: str, kind: str, value: Any, errors: List[str], op: str) -> None:
    if kind == "vector3":
        if not _is_vector3(value):
            errors.append("%s.%s expects 3 numbers, got %r" % (op, name, value))
            return
        for component in value:
            if abs(float(component)) > MAX_LENGTH_METERS:
                errors.append("%s.%s component %r exceeds %s scene units"
                              % (op, name, component, MAX_LENGTH_METERS))
    elif kind == "number":
        if not _is_number(value):
            errors.append("%s.%s expects a number, got %r" % (op, name, value))
    elif kind == "axis":
        if value not in AXES:
            errors.append("%s.%s expects one of x/y/z, got %r" % (op, name, value))
    elif kind == "primitive":
        if value not in PRIMITIVES:
            errors.append("%s.%s expects a supported primitive, got %r" % (op, name, value))
    elif kind == "string":
        if not isinstance(value, str) or not value.strip():
            errors.append("%s.%s expects a non-empty string, got %r" % (op, name, value))
    elif kind == "number_or_string":
        if not (_is_number(value) or isinstance(value, str)):
            errors.append("%s.%s expects a number or string, got %r" % (op, name, value))
    elif kind == "number_or_vector":
        if not (_is_number(value) or _is_vector3(value)):
            errors.append("%s.%s expects a number or 3 numbers, got %r" % (op, name, value))
    else:  # pragma: no cover - a registry typo should be loud, not silent
        errors.append("%s.%s has an unknown parameter type %r" % (op, name, kind))


def _resolve_target(snapshot: Optional[SceneSnapshot], target: str) -> List[str]:
    if snapshot is None:
        return []
    if snapshot.find(target):
        return [target]
    return [obj.name for obj in snapshot.match(target)]


def _known_kind(target: Optional[str], snapshot: Optional[SceneSnapshot],
                scene_context: Any) -> Optional[str]:
    """What kind of object the available evidence says ``target`` is, or ``None`` if unknown."""
    if not target:
        return None
    if scene_context is not None and hasattr(scene_context, "kind_of"):
        kind = scene_context.kind_of(target)
        if kind:
            return str(kind)
    if snapshot is not None and snapshot.find(target):
        return "mesh"
    return None


def _check_target_kind(label: str, target: Optional[str], expected: str,
                       snapshot: Optional[SceneSnapshot], scene_context: Any,
                       errors: List[str], warnings: List[str],
                       result: PreflightResult) -> None:
    """Verify that a target exists *and* is the right kind of thing.

    An exported ``.glb`` proves meshes. A camera or a light target can therefore only be verified
    against the scene context, and when the context does not know the name the operation is not
    rejected outright -- it is marked as needing a person, because the workflow must not assume an
    object it cannot see.
    """
    if expected == "any":
        return
    kind = _known_kind(target, snapshot, scene_context)
    if kind is None:
        if expected == "mesh":
            errors.append("%s targets %r, which is not in the current scene revision %s"
                          % (label, target, snapshot.revision if snapshot else "(no scene read)"))
            return
        result.requires_approval = True
        result.approval_reason = (
            "%s targets %r, whose type cannot be verified from the current scene context (the "
            "exported scene carries no %ss)" % (label, target, expected))
        warnings.append(result.approval_reason)
        return
    if kind != expected:
        errors.append("%s expects a %s but the available evidence says %r is a %s"
                      % (label, expected, target, kind))


def preflight_plan(plan: PatchPlan, contract: SceneContract, policy: OperationPolicy,
                   snapshot: Optional[SceneSnapshot] = None,
                   scene_context: Any = None) -> PreflightResult:
    result = PreflightResult()
    errors = result.errors
    warnings = result.warnings

    if not plan.ops:
        errors.append("plan has no operations")
        result.ok = False
        return result

    if len(plan.ops) > policy.max_ops_per_plan:
        warnings.append("plan proposes %d operations; the doc asks for the smallest reversible edit"
                        % len(plan.ops))

    targets: List[str] = []
    scene_dimensions = snapshot.dimensions() if snapshot else None
    max_dimension = max(scene_dimensions) if scene_dimensions else None
    triangle_delta = 0

    for index, op in enumerate(plan.ops):
        label = "ops[%d](%s)" % (index, op.op)
        result.checked.append(label)

        if not policy.is_allowlisted(op.op):
            errors.append("%s is not an allowlisted operation" % label)
            continue

        entry = OP_REGISTRY[op.op]
        tool = entry["tool"]
        allowed_tools = (set(policy.allowed_write_tools) | set(policy.allowed_delivery_tools))
        if tool not in allowed_tools:
            errors.append("%s maps to tool %r, which the policy does not permit" % (label, tool))

        # --- parameters -------------------------------------------------------------
        declared = entry.get("params", {})
        for name, raw in op.parameters.items():
            if name not in declared:
                errors.append("%s passes undeclared parameter %r" % (label, name))
                continue
            _check_param(name, declared[name], raw, errors, label)
        for name in declared:
            if name not in op.parameters:
                warnings.append("%s omits optional parameter %r" % (label, name))

        # A camera passed as a parameter is a target in every sense that matters, so it is
        # verified the same way a target is.
        camera_parameter = op.parameters.get("camera")
        if isinstance(camera_parameter, str) and camera_parameter:
            _check_target_kind("%s.camera" % label, camera_parameter, "camera", snapshot,
                               scene_context, errors, warnings, result)

        # --- target resolution, scope and kind ---------------------------------------
        if entry.get("requires_target"):
            if not op.target:
                errors.append("%s requires a target object" % label)
                continue
            expected_kind = policy.target_kind(op.op)
            _check_target_kind(label, op.target, expected_kind, snapshot, scene_context, errors,
                               warnings, result)
            resolved = _resolve_target(snapshot, op.target)
            if len(resolved) > 1 and not any(ch in op.target for ch in "*?["):
                warnings.append("%s matched %d objects (%s); the plan should name one"
                                % (label, len(resolved), ", ".join(resolved[:4])))
            if not policy.in_write_scope(op.target) and not any(
                    policy.in_write_scope(name) for name in resolved):
                errors.append("%s targets %r outside the contract write scope %s"
                              % (label, op.target, policy.write_scope))
            targets.extend(resolved or [op.target])

        if op.op == "delete_object":
            errors.append("%s: the workflow never deletes objects automatically" % label)

        # --- unit and scale sanity ---------------------------------------------------
        if op.op == "nudge_object" and max_dimension:
            delta = op.parameters.get("delta")
            if _is_number(delta) and abs(float(delta)) > max_dimension * MAX_TRANSLATION_FRACTION:
                errors.append("%s moves %r by %s units, over %.0f%% of the scene's largest "
                              "dimension (%.3f); that is a rewrite, not a revision"
                              % (label, op.target, delta, MAX_TRANSLATION_FRACTION * 100,
                                 max_dimension))
        if op.op == "set_object_transform":
            location = op.parameters.get("location")
            if _is_vector3(location) and max_dimension:
                if max(abs(float(v)) for v in location) > max_dimension * 4:
                    errors.append("%s places %r far outside the scene bounds"
                                  % (label, op.target))

        # --- geometry budget ---------------------------------------------------------
        if op.op == "add_primitive":
            triangle_delta += 12 if op.parameters.get("primitive") == "cube" else 2
        if op.op == "duplicate_object" and snapshot is not None and op.target:
            source = snapshot.find(op.target)
            if source:
                triangle_delta += source.triangles

        # --- preserve pinned dimensions ---------------------------------------------
        if op.op in ("set_object_transform", "nudge_object") and snapshot is not None:
            for requirement in contract.mandatory_requirements():
                if requirement.kind != "dimension" or not requirement.pattern:
                    continue
                if not any(op.target and (op.target == name or name.startswith(op.target.rstrip("*")))
                           for name in _resolve_target(snapshot, requirement.pattern)):
                    continue
                if op.op == "set_object_transform" and op.parameters.get("scale"):
                    errors.append("%s scales %r, but the contract pins its %s dimension"
                                  % (label, op.target, requirement.axis))

    # --- plan-level gates ------------------------------------------------------------
    unique_targets = sorted(set(targets))
    worst_gate: Optional[Dict[str, Any]] = None
    for op in plan.ops:
        gate = policy.gate(op.op, target_count=len(unique_targets), plan_ops=len(plan.ops))
        if not gate["allowed"]:
            continue
        if gate["requires_approval"] and worst_gate is None:
            worst_gate = gate
    if worst_gate:
        result.requires_approval = True
        result.approval_reason = worst_gate["reason"]

    if contract.polygon_budget and snapshot is not None:
        projected = snapshot.triangles + triangle_delta
        if projected > int(contract.polygon_budget):
            errors.append("plan would take the scene to %d triangles, over the contract budget "
                          "of %d" % (projected, int(contract.polygon_budget)))
    irreversible = [op.op for op in plan.ops if not policy.reversible(op.op)]
    if irreversible:
        warnings.append("non-reversible operations in plan: %s" % ", ".join(irreversible))

    result.ok = not errors
    return result


def summarise_preflight(result: PreflightResult) -> str:
    if result.ok and not result.requires_approval:
        return "preflight ok"
    if result.ok and result.requires_approval:
        return "preflight ok, approval required: %s" % result.approval_reason
    return "preflight rejected: %s" % "; ".join(result.errors)

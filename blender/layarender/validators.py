"""Deterministic validation of the editable scene and the delivery.

Doc, section 4 step 10: "Return findings with severity, evidence, camera/view, affected object
or image region, suggested correction, and confidence. Separately record deterministic
scene/export checks. Never infer hidden geometry or file validity from a single image."

Three rules this module follows literally:

* A check that did not run reports ``not_run``. It never reports ``pass``.
* A render that looks good never satisfies a structural requirement.
* Every failure names what was expected and what was measured, so a repair is possible.

The scene is read from the shipped artifact (``.glb``/``.gltf``) rather than from a render, so
this half of the review is independent of the visual reviewer and of Laya.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .contracts import Requirement, SceneContract
from .models import HardChecks, CheckStatus, ViewRender
from .scene import SceneReadError, SceneSnapshot, read_scene


def _fail(checks: HardChecks, name: str, detail: str, expected: Any = None,
          actual: Any = None, mandatory: bool = True) -> None:
    checks.add(name, CheckStatus.FAIL.value, detail, expected, actual, mandatory)


def _pass(checks: HardChecks, name: str, detail: str, expected: Any = None,
          actual: Any = None, mandatory: bool = True) -> None:
    checks.add(name, CheckStatus.PASS.value, detail, expected, actual, mandatory)


def _not_run(checks: HardChecks, name: str, detail: str, mandatory: bool = True) -> None:
    checks.add(name, CheckStatus.NOT_RUN.value, detail, None, None, mandatory)


def _axis_index(axis: Optional[str]) -> Optional[int]:
    if not axis:
        return None
    mapping = {"x": 0, "y": 1, "z": 2, "width": 0, "height": 2, "depth": 1, "length": 2}
    return mapping.get(axis.lower())


def check_object_present(checks: HardChecks, snapshot: SceneSnapshot, requirement: Requirement) -> None:
    name = "object_present:%s" % requirement.pattern
    matched = snapshot.match(requirement.pattern)
    if len(matched) >= requirement.min_count:
        _pass(checks, name, "%d object(s) match" % len(matched), requirement.min_count,
              [obj.name for obj in matched], requirement.mandatory)
    else:
        _fail(checks, name,
              "no object matches %r; scene has %d objects" % (requirement.pattern, len(snapshot.objects)),
              requirement.min_count, len(matched), requirement.mandatory)


def check_dimension(checks: HardChecks, snapshot: SceneSnapshot, requirement: Requirement) -> None:
    name = "dimension:%s:%s" % (requirement.pattern, requirement.axis)
    axis = _axis_index(requirement.axis)
    if axis is None:
        _not_run(checks, name, "requirement names no axis", requirement.mandatory)
        return
    matched = snapshot.match(requirement.pattern)
    if not matched:
        _fail(checks, name, "no object matches %r" % requirement.pattern, requirement.pattern, None,
              requirement.mandatory)
        return
    measured: List[Dict[str, Any]] = []
    offenders: List[str] = []
    for obj in matched:
        dimensions = obj.dimensions()
        value = dimensions[axis] if dimensions else None
        measured.append({"object": obj.name, requirement.axis: value})
        if value is None:
            offenders.append("%s has no declared bounds" % obj.name)
            continue
        if requirement.min is not None and value < float(requirement.min) - 1e-6:
            offenders.append("%s %s=%.4f < min %.4f" % (obj.name, requirement.axis, value,
                                                        float(requirement.min)))
        if requirement.max is not None and value > float(requirement.max) + 1e-6:
            offenders.append("%s %s=%.4f > max %.4f" % (obj.name, requirement.axis, value,
                                                        float(requirement.max)))
    expected = {"axis": requirement.axis, "min": requirement.min, "max": requirement.max}
    if offenders:
        _fail(checks, name, "; ".join(offenders), expected, measured, requirement.mandatory)
    else:
        _pass(checks, name, "%d object(s) within tolerance" % len(matched), expected, measured,
              requirement.mandatory)


def check_material(checks: HardChecks, snapshot: SceneSnapshot, requirement: Requirement) -> None:
    name = "material:%s" % requirement.pattern
    matched = snapshot.match(requirement.pattern)
    if not matched:
        _fail(checks, name, "no object matches %r" % requirement.pattern, requirement.pattern,
              None, requirement.mandatory)
        return
    problems: List[str] = []
    observed: List[Dict[str, Any]] = []
    for obj in matched:
        observed.append({"object": obj.name, "materials": obj.material_names})
        if requirement.materials:
            if not any(material in requirement.materials for material in obj.material_names):
                problems.append("%s carries %s, none of %s"
                                % (obj.name, obj.material_names or "no material",
                                   requirement.materials))
        elif len(obj.material_names) < requirement.min_materials:
            problems.append("%s carries %d material(s), expected at least %d"
                            % (obj.name, len(obj.material_names), requirement.min_materials))
    expected = {"materials": requirement.materials, "min_materials": requirement.min_materials}
    if problems:
        _fail(checks, name, "; ".join(problems), expected, observed, requirement.mandatory)
    else:
        _pass(checks, name, "materials assigned on %d object(s)" % len(matched), expected,
              observed, requirement.mandatory)


def check_triangle_budget(checks: HardChecks, snapshot: SceneSnapshot,
                         contract: SceneContract, requirement: Optional[Requirement] = None) -> None:
    budget = (requirement.max_triangles if requirement and requirement.max_triangles
              else contract.polygon_budget)
    name = "triangle_budget"
    if not budget:
        _not_run(checks, name, "the contract sets no polygon budget", False)
        return
    actual = snapshot.triangles
    if actual <= int(budget):
        _pass(checks, name, "%d triangles within budget" % actual, int(budget), actual,
              bool(requirement.mandatory if requirement else True))
    else:
        _fail(checks, name, "%d triangles over budget by %d" % (actual, actual - int(budget)),
              int(budget), actual, bool(requirement.mandatory if requirement else True))


def check_no_empty_mesh(checks: HardChecks, snapshot: SceneSnapshot, requirement: Requirement) -> None:
    name = "no_empty_mesh:%s" % requirement.pattern
    matched = snapshot.match(requirement.pattern)
    if not matched:
        _not_run(checks, name, "no object matches %r" % requirement.pattern, requirement.mandatory)
        return
    empty = [obj.name for obj in matched if obj.triangles <= 0]
    if empty:
        _fail(checks, name, "objects with no geometry: %s" % ", ".join(empty), "> 0 triangles",
              empty, requirement.mandatory)
    else:
        _pass(checks, name, "%d object(s) carry geometry" % len(matched), "> 0 triangles",
              None, requirement.mandatory)


def check_view_rendered(checks: HardChecks, views: List[ViewRender], requirement: Requirement) -> None:
    required = requirement.views or []
    by_name = {view.name: view for view in views}
    missing: List[str] = []
    unreadable: List[str] = []
    for name in required:
        view = by_name.get(name)
        if view is None or not view.rendered:
            missing.append(name)
            continue
        if not view.path or not os.path.exists(view.path) or os.path.getsize(view.path) == 0:
            unreadable.append(name)
    if not required:
        _not_run(checks, "view_rendered", "the contract requires no views", requirement.mandatory)
        return
    if missing:
        _fail(checks, "view_rendered", "views not rendered: %s" % ", ".join(missing), required,
              sorted(by_name), requirement.mandatory)
    elif unreadable:
        _fail(checks, "view_rendered", "render files missing or empty: %s" % ", ".join(unreadable),
              required, unreadable, requirement.mandatory)
    else:
        _pass(checks, "view_rendered", "%d required view(s) rendered" % len(required), required,
              sorted(by_name), requirement.mandatory)


def check_export(checks: HardChecks, requirement: Requirement) -> None:
    name = "export:%s" % (requirement.path or "delivery")
    path = requirement.path
    if not path:
        _not_run(checks, name, "no delivery path in the contract", requirement.mandatory)
        return
    if not os.path.exists(path):
        _fail(checks, name, "delivery file does not exist", path, None, requirement.mandatory)
        return
    try:
        snapshot = read_scene(path)
    except SceneReadError as error:
        _fail(checks, name, "delivery file is not readable as glTF: %s" % error, path, None,
              requirement.mandatory)
        return
    if snapshot.objects == []:
        _fail(checks, name, "delivery file contains no meshes", ">= 1 mesh", 0,
              requirement.mandatory)
        return
    _pass(checks, name, "%d objects, %d triangles, %d bytes"
          % (len(snapshot.objects), snapshot.triangles, snapshot.file_bytes),
          path, snapshot.summary(), requirement.mandatory)


def check_scene_readable(checks: HardChecks, path: str, snapshot: Optional[SceneSnapshot],
                         error: Optional[Exception] = None) -> None:
    """The one check the workflow always runs: the editable scene must be readable at all."""
    if snapshot is not None:
        _pass(checks, "scene_readable", "read %s (revision %s)" % (os.path.basename(path),
                                                                  snapshot.revision), path,
              snapshot.revision, True)
    else:
        _fail(checks, "scene_readable", "cannot read the editable scene: %s" % error, path, None, True)


def check_scene_hygiene(checks: HardChecks, snapshot: SceneSnapshot) -> None:
    """Structural facts worth knowing that no contract requirement covers."""
    if not snapshot.objects:
        _fail(checks, "scene_has_geometry", "the scene declares no mesh objects", ">= 1", 0, True)
    else:
        _pass(checks, "scene_has_geometry", "%d mesh object(s)" % len(snapshot.objects), ">= 1",
              len(snapshot.objects), True)
    unbound = [obj.name for obj in snapshot.objects if not obj.material_names]
    if unbound:
        checks.add("materials_bound", CheckStatus.FAIL.value,
                   "objects with no material: %s" % ", ".join(unbound), "every object bound",
                   len(unbound), False)
    else:
        _pass(checks, "materials_bound", "every mesh object carries a material",
              "every object bound", None, False)


def run_scene_checks(snapshot: Optional[SceneSnapshot], contract: SceneContract,
                     views: List[ViewRender], source_path: str,
                     read_error: Optional[Exception] = None) -> HardChecks:
    """Run every deterministic requirement against one scene revision."""
    checks = HardChecks()
    check_scene_readable(checks, source_path, snapshot, read_error)
    if snapshot is None:
        for requirement in contract.mandatory_requirements():
            if requirement.kind in ("export",):
                continue
            _not_run(checks, "%s:%s" % (requirement.kind, requirement.pattern or requirement.views),
                     "skipped: the editable scene could not be read", requirement.mandatory)
        return checks

    check_scene_hygiene(checks, snapshot)

    for requirement in contract.requirements:
        if requirement.kind == "object_present":
            check_object_present(checks, snapshot, requirement)
        elif requirement.kind == "dimension":
            check_dimension(checks, snapshot, requirement)
        elif requirement.kind == "material":
            check_material(checks, snapshot, requirement)
        elif requirement.kind == "triangle_budget":
            check_triangle_budget(checks, snapshot, contract, requirement)
        elif requirement.kind == "no_empty_mesh":
            check_no_empty_mesh(checks, snapshot, requirement)
        elif requirement.kind == "view_rendered":
            check_view_rendered(checks, views, requirement)
        elif requirement.kind == "export":
            check_export(checks, requirement)
        else:
            _not_run(checks, "unknown:%s" % requirement.kind,
                     "the workflow has no validator for kind %r" % requirement.kind,
                     requirement.mandatory)

    # A budget with no explicit requirement still deserves a measurable record.
    if not any(r.kind == "triangle_budget" for r in contract.requirements):
        check_triangle_budget(checks, snapshot, contract)
    return checks

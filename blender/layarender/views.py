"""Canonical views and the deterministic render fingerprint.

Doc, section 4 step 9: "Render canonical views -- Render consistent previews from defined
cameras and settings. Fix resolution, color management, lighting, and render quality so
comparisons are meaningful."

A canonical view is therefore two things at once: a named camera and a frozen settings
fingerprint. :func:`settings_drift` compares the fingerprint a render was produced with against
the one the contract declares, so a render made at a different resolution or look can never be
silently compared against an earlier one.

This module produces the Render MCP Designer call arguments for rendering a view. It does not
call the server; :mod:`layarender.adapters.render_mcp` owns that.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .contracts import SceneContract, ViewSpec


class RenderSettingsError(ValueError):
    """Raised when a view cannot be expressed as a deterministic render."""


def default_views(resolution: Optional[List[int]] = None) -> List[ViewSpec]:
    """A hero view plus orthographic coverage -- the doc's "agreed hero view plus useful
    orthographic or turntable views" for an object-style deliverable."""
    size = list(resolution or [1200, 800])
    return [
        ViewSpec(name="hero", camera="Cam_Hero", resolution=size,
                 purpose="three-quarter hero: silhouette, materials, lighting intent",
                 look="AgX - Medium High Contrast",
                 framing="subject fills 70-85% of frame height, no edge clipping"),
        ViewSpec(name="front", camera="Cam_Front", resolution=size,
                 purpose="orthographic front: symmetry and proportions",
                 framing="centred, whole subject inside the frame"),
        ViewSpec(name="side", camera="Cam_Side", resolution=size,
                 purpose="orthographic side: profile and depth readability",
                 framing="centred, whole subject inside the frame"),
        ViewSpec(name="bays", camera="Cam_Bays", resolution=size,
                 purpose="belly/bay detail: secondary features legible at full-frame",
                 framing="target features occupy the frame centre", mandatory=False),
    ]


def ensure_views(contract: SceneContract, resolution: Optional[List[int]] = None) -> List[ViewSpec]:
    """Return the contract's views, filling in a default set when the contract declares none."""
    if contract.views:
        return list(contract.views)
    return default_views(resolution or contract.render_size())


def required_views(contract: SceneContract, views: List[ViewSpec]) -> List[ViewSpec]:
    required = set(contract.required_view_names())
    selected = [spec for spec in views if spec.name in required]
    return selected or [spec for spec in views if spec.mandatory]


def render_arguments(spec: ViewSpec, output_path: str, scene_settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The settings block a render call must apply for ``spec``.

    Returned as data rather than Blender source so the caller (or a recording transport) can
    assert on it. :func:`blender_source` turns it into the ``bpy`` snippet when a real render
    runs.
    """
    arguments: Dict[str, Any] = {
        "view": spec.name,
        "camera": spec.camera,
        "resolution_x": int(spec.resolution[0]),
        "resolution_y": int(spec.resolution[1]),
        "engine": spec.engine,
        "samples": int(spec.samples),
        "film_transparent": bool(spec.film_transparent),
        "view_transform_look": spec.look,
        "filepath": output_path,
        "file_format": "PNG",
    }
    if scene_settings:
        for key, value in scene_settings.items():
            arguments.setdefault(key, value)
    return arguments


def fingerprint_of(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """The fingerprint of an applied render, in the same shape as :meth:`ViewSpec.fingerprint`."""
    return {
        "camera": arguments.get("camera"),
        "resolution": [arguments.get("resolution_x"), arguments.get("resolution_y")],
        "engine": arguments.get("engine"),
        "samples": arguments.get("samples"),
        "film_transparent": arguments.get("film_transparent"),
        "look": arguments.get("view_transform_look"),
    }


def settings_drift(expected: Dict[str, Any], actual: Dict[str, Any]) -> List[str]:
    """Human-readable differences between two fingerprints. Empty means comparable."""
    drift: List[str] = []
    for key in ("camera", "resolution", "engine", "samples", "film_transparent", "look"):
        if key not in expected:
            continue
        if expected.get(key) != actual.get(key):
            drift.append("%s: expected %r, rendered with %r" % (key, expected.get(key), actual.get(key)))
    return drift


def blender_source(arguments: Dict[str, Any], frame_object: Optional[str] = None) -> str:
    """A ``bpy`` snippet that applies ``arguments`` and renders one frame.

    Kept small and side-effect-scoped: it sets scene render settings, points the named camera,
    optionally reframes on one object, and writes a single PNG. It never deletes or saves over
    the project file, so it is safe to run inside a bounded revision round.
    """
    camera = arguments["camera"]
    lines = [
        "import bpy",
        "scene = bpy.context.scene",
        "camera = bpy.data.objects.get(%r)" % camera,
        "assert camera is not None and camera.type == 'CAMERA', 'camera %s not found'" % camera,
        "scene.camera = camera",
        "scene.render.engine = %r" % arguments.get("engine", "BLENDER_EEVEE_NEXT"),
        "scene.render.resolution_x = %d" % int(arguments.get("resolution_x", 1200)),
        "scene.render.resolution_y = %d" % int(arguments.get("resolution_y", 800)),
        "scene.render.resolution_percentage = 100",
        "scene.render.film_transparent = %s" % ("True" if arguments.get("film_transparent") else "False"),
        "scene.render.image_settings.file_format = 'PNG'",
        "scene.render.filepath = %r" % arguments["filepath"],
    ]
    engine = arguments.get("engine", "")
    if engine == "CYCLES":
        lines.append("scene.cycles.samples = %d" % int(arguments.get("samples", 64)))
    else:
        lines.append("scene.eevee.taa_render_samples = %d" % int(arguments.get("samples", 64)))
    look = arguments.get("view_transform_look")
    if look:
        lines.append("scene.view_settings.look = %r" % look)
    if frame_object:
        lines.append("target = bpy.data.objects.get(%r)" % frame_object)
        lines.append("assert target is not None, 'framing target %s not found'" % frame_object)
        lines.append("bpy.context.view_layer.objects.active = target")
        lines.append("bpy.ops.object.select_all(action='DESELECT')")
        lines.append("target.select_set(True)")
        lines.append("bpy.ops.view3d.camera_to_view_selected()")
    lines.append("bpy.ops.render.render(write_still=True)")
    lines.append("print('RENDERED {} -> {}'.format(%r, scene.render.filepath))" % arguments["view"])
    return "\n".join(lines)


def describe_views(views: List[ViewSpec]) -> List[Dict[str, Any]]:
    return [spec.to_dict() for spec in views]

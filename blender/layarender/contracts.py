"""The scene contract: the bridge from creative intent to executable, checkable requirements.

Doc, section 2: "Turn critique into small, located scene edits" and section 5: the contract
separates *mandatory* requirements from *preferences*. Every mandatory requirement in this
module compiles to a deterministic check in :mod:`layarender.validators`, so "accept" can never
rest on a reviewer's opinion alone.

Field names follow the briefing document's illustrative contract (``goal``, ``units``,
``must_have``, ``scene_limits``, ``visual_targets``, ``delivery``) so the artifact stays
recognisable, with a measurable ``requirements`` layer added because the workflow has to be
able to actually evaluate it.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_MAX_ROUNDS = 3


@dataclass
class Requirement:
    """One mandatory, machine-checkable statement about the editable scene or the delivery.

    ``kind`` selects the check:
      ``object_present``   ``pattern`` must match at least ``min_count`` objects.
      ``dimension``        each object matching ``pattern`` must have ``axis`` extent within
                           ``min``/``max`` (scene units).
      ``material``         every object matching ``pattern`` must carry one of ``materials``
                           (or at least ``min_materials`` materials when the list is empty).
      ``triangle_budget``  the whole scene must stay at or below ``max_triangles``.
      ``view_rendered``    every view named in ``views`` must have been rendered and readable.
      ``export``           the delivery file must exist, be readable as glTF, and be non-empty.
      ``no_empty_mesh``    no object matching ``pattern`` may have zero triangles.
    """

    kind: str
    pattern: str = "*"
    axis: Optional[str] = None
    min: Optional[float] = None
    max: Optional[float] = None
    materials: List[str] = field(default_factory=list)
    min_materials: int = 0
    min_count: int = 1
    max_triangles: Optional[int] = None
    views: List[str] = field(default_factory=list)
    path: Optional[str] = None
    detail: str = ""
    mandatory: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ViewSpec:
    """One canonical view. ``fingerprint`` is what makes two renders comparable."""

    name: str
    camera: str
    resolution: List[int] = field(default_factory=lambda: [1200, 800])
    purpose: str = ""
    engine: str = "BLENDER_EEVEE_NEXT"
    samples: int = 64
    film_transparent: bool = False
    look: str = "AgX - Medium High Contrast"
    framing: str = ""
    mandatory: bool = True

    def fingerprint(self) -> Dict[str, Any]:
        """The part of a view definition that must not drift between iterations."""
        return {
            "camera": self.camera,
            "resolution": list(self.resolution),
            "engine": self.engine,
            "samples": self.samples,
            "film_transparent": self.film_transparent,
            "look": self.look,
        }

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["fingerprint"] = self.fingerprint()
        return data


@dataclass
class SceneContract:
    task_id: str = ""
    goal: str = ""
    units: str = "meters"
    coordinate_system: str = "glTF/Blender right-handed, Y-up on export (Z-up in Blender)"
    intended_use: str = ""
    audience: str = ""

    must_have: List[str] = field(default_factory=list)
    visual_targets: List[str] = field(default_factory=list)
    preferences: List[str] = field(default_factory=list)

    requirements: List[Requirement] = field(default_factory=list)
    views: List[ViewSpec] = field(default_factory=list)

    write_scope: List[str] = field(default_factory=list)
    max_revision_rounds: int = DEFAULT_MAX_ROUNDS
    polygon_budget: Optional[int] = None
    required_views: List[str] = field(default_factory=list)

    delivery: Dict[str, Any] = field(default_factory=dict)
    version: int = 1
    notes: str = ""

    # ---- helpers ----------------------------------------------------------------------
    def mandatory_requirements(self) -> List[Requirement]:
        return [r for r in self.requirements if r.mandatory]

    def view(self, name: str) -> Optional[ViewSpec]:
        for spec in self.views:
            if spec.name == name:
                return spec
        return None

    def required_view_names(self) -> List[str]:
        if self.required_views:
            return list(self.required_views)
        return [spec.name for spec in self.views if spec.mandatory]

    def write_scope_patterns(self) -> List[str]:
        if self.write_scope:
            return list(self.write_scope)
        return ["*"]

    def render_size(self) -> List[int]:
        size = self.delivery.get("render_size")
        if isinstance(size, str) and "x" in size:
            try:
                width, height = size.lower().split("x", 1)
                return [int(width), int(height)]
            except ValueError:
                pass
        if isinstance(size, (list, tuple)) and len(size) == 2:
            return [int(size[0]), int(size[1])]
        return [1200, 800]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["scene_limits"] = {
            "write_scope": list(self.write_scope) or ["target scene only"],
            "max_revision_rounds": self.max_revision_rounds,
            "polygon_budget": self.polygon_budget,
            "required_views": self.required_view_names(),
        }
        data["requirements"] = [r.to_dict() for r in self.requirements]
        data["views"] = [v.to_dict() for v in self.views]
        return data

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneContract":
        limits = data.get("scene_limits") or {}
        contract = cls(
            task_id=data.get("task_id", ""),
            goal=data.get("goal", ""),
            units=data.get("units", "meters"),
            coordinate_system=data.get("coordinate_system", ""),
            intended_use=data.get("intended_use", ""),
            audience=data.get("audience", ""),
            must_have=list(data.get("must_have", [])),
            visual_targets=list(data.get("visual_targets", [])),
            preferences=list(data.get("preferences", [])),
            write_scope=list(limits.get("write_scope") or data.get("write_scope") or []),
            max_revision_rounds=int(limits.get("max_revision_rounds", DEFAULT_MAX_ROUNDS)),
            polygon_budget=limits.get("polygon_budget", data.get("polygon_budget")),
            required_views=list(limits.get("required_views") or data.get("required_views") or []),
            delivery=dict(data.get("delivery", {})),
            version=int(data.get("version", 1)),
            notes=data.get("notes", ""),
        )
        if isinstance(contract.polygon_budget, str) or contract.polygon_budget is None:
            contract.polygon_budget = None
        contract.requirements = [
            Requirement(**{key: value for key, value in item.items()
                           if key in Requirement.__dataclass_fields__})
            for item in data.get("requirements", [])
        ]
        contract.views = []
        for item in data.get("views", []):
            cleaned = {key: value for key, value in item.items()
                       if key in ViewSpec.__dataclass_fields__}
            contract.views.append(ViewSpec(**cleaned))
        return contract

    @classmethod
    def load(cls, path: str) -> "SceneContract":
        with open(path, "r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    def save(self, path: str) -> None:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.to_json())


def compile_from_brief(brief: Dict[str, Any]) -> SceneContract:
    """Turn a short brief into a contract skeleton.

    Only what the brief actually states becomes a requirement. Anything the brief leaves open is
    recorded as a preference or as a note, never as a mandatory check the workflow would invent
    and then fail the scene against.
    """
    contract = SceneContract(
        task_id=brief.get("task_id", ""),
        goal=brief.get("goal", ""),
        units=brief.get("units", "meters"),
        intended_use=brief.get("intended_use", ""),
        audience=brief.get("audience", ""),
        must_have=list(brief.get("must_have", [])),
        visual_targets=list(brief.get("visual_targets", [])),
        preferences=list(brief.get("preferences", [])),
        write_scope=list(brief.get("write_scope", [])),
        delivery=dict(brief.get("delivery", {})),
        polygon_budget=brief.get("polygon_budget"),
        max_revision_rounds=int(brief.get("max_revision_rounds", DEFAULT_MAX_ROUNDS)),
        required_views=list(brief.get("required_views", [])),
        notes=brief.get("notes", ""),
    )
    for pattern in contract.must_have:
        contract.requirements.append(
            Requirement(kind="object_present", pattern=pattern, min_count=1,
                        detail="must_have object from the brief")
        )
    if contract.polygon_budget:
        contract.requirements.append(
            Requirement(kind="triangle_budget", max_triangles=int(contract.polygon_budget),
                        detail="polygon budget from the brief")
        )
    for name in contract.required_view_names():
        contract.views.append(
            ViewSpec(name=name, camera=name, resolution=contract.render_size(),
                     purpose="required by the brief")
        )
    if contract.views:
        contract.requirements.append(
            Requirement(kind="view_rendered", views=contract.required_view_names(),
                        detail="every required view must be rendered")
        )
    delivery = contract.delivery
    for candidate in ("editable_scene", "export_path"):
        path = delivery.get(candidate) if isinstance(delivery, dict) else None
        if isinstance(path, str):
            contract.requirements.append(
                Requirement(kind="export", path=path, detail="delivery artifact from the brief")
            )
    return contract

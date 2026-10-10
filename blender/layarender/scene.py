"""Structural reads of the editable scene.

The doc is explicit that the editable 3D scene, not a polished render, is the source of truth:
"a polished render is not proof that the scene hierarchy, transforms, materials, topology, or
export are correct." This module reads that scene without opening Blender, so the workflow can
validate the shipped artifact (``.glb`` / ``.gltf``) deterministically and offline.

Only glTF's JSON chunk and accessor bounds are read: no mesh payload is decoded, no dependency
beyond the standard library. Dimensions come from the POSITION accessors' declared ``min`` /
``max``, which is exactly the data a viewer uses for its own bounding boxes.
"""
from __future__ import annotations

import json
import os
import struct
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

JSON_CHUNK = 0x4E4F534A  # 'JSON'
BIN_CHUNK = 0x004E4942  # 'BIN\0'


class SceneReadError(RuntimeError):
    """Raised when a scene file cannot be read as glTF."""


@dataclass
class SceneObject:
    name: str
    index: int
    parent: Optional[str] = None
    mesh_index: Optional[int] = None
    material_names: List[str] = field(default_factory=list)
    triangles: int = 0
    vertices: int = 0
    min_bound: Optional[List[float]] = None
    max_bound: Optional[List[float]] = None
    translation: Optional[List[float]] = None
    scale: Optional[List[float]] = None
    has_children: bool = False

    def dimensions(self) -> Optional[List[float]]:
        if not self.min_bound or not self.max_bound:
            return None
        return [round(self.max_bound[i] - self.min_bound[i], 6) for i in range(3)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "index": self.index,
            "parent": self.parent,
            "mesh_index": self.mesh_index,
            "materials": list(self.material_names),
            "triangles": self.triangles,
            "vertices": self.vertices,
            "dimensions": self.dimensions(),
            "min_bound": self.min_bound,
            "max_bound": self.max_bound,
            "translation": self.translation,
            "has_children": self.has_children,
        }


@dataclass
class SceneSnapshot:
    """A stable, comparable description of the editable scene at one revision."""

    source_path: str
    asset: Dict[str, Any] = field(default_factory=dict)
    generator: str = ""
    objects: List[SceneObject] = field(default_factory=list)
    materials: List[str] = field(default_factory=list)
    images: int = 0
    cameras: int = 0
    animations: int = 0
    extensions_used: List[str] = field(default_factory=list)
    file_bytes: int = 0
    bin_bytes: int = 0
    revision: str = ""

    # ---- aggregate measurements -------------------------------------------------------
    @property
    def triangles(self) -> int:
        return sum(obj.triangles for obj in self.objects)

    @property
    def vertices(self) -> int:
        return sum(obj.vertices for obj in self.objects)

    def object_names(self) -> List[str]:
        return [obj.name for obj in self.objects]

    def find(self, name: str) -> Optional[SceneObject]:
        for obj in self.objects:
            if obj.name == name:
                return obj
        return None

    def match(self, pattern: str) -> List[SceneObject]:
        """Prefix/glob-ish match used by contract requirements such as ``Jet_Wing_*``."""
        import fnmatch

        return [obj for obj in self.objects if fnmatch.fnmatchcase(obj.name, pattern)]

    def bounds(self) -> Optional[Tuple[List[float], List[float]]]:
        """Union of every mesh's declared bounds, ignoring node transforms (a declared-space read)."""
        lows: List[float] = []
        highs: List[float] = []
        for obj in self.objects:
            if not obj.min_bound or not obj.max_bound:
                continue
            if not lows:
                lows, highs = list(obj.min_bound), list(obj.max_bound)
                continue
            for axis in range(3):
                lows[axis] = min(lows[axis], obj.min_bound[axis])
                highs[axis] = max(highs[axis], obj.max_bound[axis])
        if not lows:
            return None
        return ([round(v, 6) for v in lows], [round(v, 6) for v in highs])

    def dimensions(self) -> Optional[List[float]]:
        bounds = self.bounds()
        if not bounds:
            return None
        low, high = bounds
        return [round(high[i] - low[i], 6) for i in range(3)]

    def materials_in_use(self) -> List[str]:
        used: List[str] = []
        for obj in self.objects:
            for material in obj.material_names:
                if material not in used:
                    used.append(material)
        return used

    def summary(self) -> Dict[str, Any]:
        dimensions = self.dimensions()
        return {
            "source": self.source_path,
            "generator": self.generator,
            "objects": len(self.objects),
            "materials": len(self.materials),
            "images": self.images,
            "cameras": self.cameras,
            "animations": self.animations,
            "extensions_used": list(self.extensions_used),
            "triangles": self.triangles,
            "vertices": self.vertices,
            "dimensions": dimensions,
            "bounds": self.bounds(),
            "revision": self.revision,
            "file_bytes": self.file_bytes,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary(),
            "objects": [obj.to_dict() for obj in self.objects],
            "materials": list(self.materials),
            "asset": self.asset,
        }


def _read_glb(path: str) -> Tuple[Dict[str, Any], int]:
    with open(path, "rb") as handle:
        data = handle.read()
    if len(data) < 12 or data[:4] != b"glTF":
        raise SceneReadError("%s is not a binary glTF (missing 'glTF' magic)" % path)
    version, _length = struct.unpack_from("<II", data, 4)
    if version != 2:
        raise SceneReadError("%s declares glTF version %d; only version 2 is read" % (path, version))
    offset = 12
    gltf: Optional[Dict[str, Any]] = None
    bin_bytes = 0
    while offset + 8 <= len(data):
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset:offset + chunk_length]
        offset += chunk_length
        if chunk_type == JSON_CHUNK:
            gltf = json.loads(chunk.decode("utf-8"))
        elif chunk_type == BIN_CHUNK:
            bin_bytes += len(chunk)
    if gltf is None:
        raise SceneReadError("%s has no JSON chunk" % path)
    return gltf, bin_bytes


def _read_gltf(path: str) -> Tuple[Dict[str, Any], int]:
    with open(path, "r", encoding="utf-8") as handle:
        gltf = json.load(handle)
    bin_bytes = 0
    for buffer in gltf.get("buffers", []):
        uri = buffer.get("uri")
        if uri and not uri.startswith("data:"):
            candidate = os.path.join(os.path.dirname(path), uri)
            if os.path.exists(candidate):
                bin_bytes += os.path.getsize(candidate)
    return gltf, bin_bytes


def _mesh_measurements(gltf: Dict[str, Any], mesh_index: int) -> Tuple[int, int, Optional[List[float]], Optional[List[float]], List[str]]:
    """Return (triangles, vertices, min_bound, max_bound, material names) for one mesh."""
    triangles = 0
    vertices = 0
    lows: Optional[List[float]] = None
    highs: Optional[List[float]] = None
    material_names: List[str] = []
    materials = gltf.get("materials", [])
    accessors = gltf.get("accessors", [])
    meshes = gltf.get("meshes", [])
    if mesh_index >= len(meshes):
        return triangles, vertices, lows, highs, material_names
    for primitives in meshes[mesh_index].get("primitives", []):
        mode = primitives.get("mode", 4)
        if "indices" in primitives:
            index_accessor = accessors[primitives["indices"]]
            count = int(index_accessor.get("count", 0))
            triangles += count // 3 if mode == 4 else count - 2
        if "attributes" in primitives and "POSITION" in primitives["attributes"]:
            position = accessors[primitives["attributes"]["POSITION"]]
            vertices += int(position.get("count", 0))
            low = position.get("min")
            high = position.get("max")
            if low and high and len(low) == 3 and len(high) == 3:
                if lows is None:
                    lows, highs = list(low), list(high)
                else:
                    for axis in range(3):
                        lows[axis] = min(lows[axis], low[axis])
                        highs[axis] = max(highs[axis], high[axis])
        material_index = primitives.get("material")
        if material_index is not None and material_index < len(materials):
            name = materials[material_index].get("name") or "material_%d" % material_index
            if name not in material_names:
                material_names.append(name)
    return triangles, vertices, lows, highs, material_names


def read_scene(path: str) -> SceneSnapshot:
    """Read a ``.glb`` or ``.gltf`` into a :class:`SceneSnapshot`."""
    if not os.path.exists(path):
        raise SceneReadError("scene file not found: %s" % path)
    if path.lower().endswith(".glb"):
        gltf, bin_bytes = _read_glb(path)
    elif path.lower().endswith((".gltf", ".json")):
        gltf, bin_bytes = _read_gltf(path)
    else:
        raise SceneReadError("unsupported scene format: %s (expected .glb or .gltf)" % path)

    nodes = gltf.get("nodes", [])
    parents: Dict[int, str] = {}
    for index, node in enumerate(nodes):
        for child in node.get("children", []) or []:
            if isinstance(child, int) and child < len(nodes):
                parents[child] = node.get("name") or "node_%d" % index

    objects: List[SceneObject] = []
    for index, node in enumerate(nodes):
        mesh_index = node.get("mesh")
        if mesh_index is None:
            continue
        triangles, vertices, low, high, material_names = _mesh_measurements(gltf, mesh_index)
        objects.append(
            SceneObject(
                name=node.get("name") or "node_%d" % index,
                index=index,
                parent=parents.get(index),
                mesh_index=mesh_index,
                material_names=material_names,
                triangles=triangles,
                vertices=vertices,
                min_bound=[round(float(v), 6) for v in low] if low else None,
                max_bound=[round(float(v), 6) for v in high] if high else None,
                translation=node.get("translation"),
                scale=node.get("scale"),
                has_children=bool(node.get("children")),
            )
        )

    materials = [
        material.get("name") or "material_%d" % index
        for index, material in enumerate(gltf.get("materials", []))
    ]
    asset = gltf.get("asset", {}) or {}
    snapshot = SceneSnapshot(
        source_path=os.path.abspath(path),
        asset=asset,
        generator=str(asset.get("generator", "")),
        objects=objects,
        materials=materials,
        images=len(gltf.get("images", []) or []),
        cameras=len(gltf.get("cameras", []) or []),
        animations=len(gltf.get("animations", []) or []),
        extensions_used=list(gltf.get("extensionsUsed", []) or []),
        file_bytes=os.path.getsize(path),
        bin_bytes=bin_bytes,
    )
    snapshot.revision = _revision_of(snapshot)
    return snapshot


def _revision_of(snapshot: SceneSnapshot) -> str:
    """A cheap content revision: stable across runs, changes whenever the scene does.

    Deliberately not a cryptographic hash of the payload (that would require reading the whole
    binary chunk). The doc's requirement is that a stale patch is never replayed blindly; this
    is enough to notice that the scene changed underneath a plan.
    """
    import hashlib

    payload = "|".join(
        ["%s:%d:%d:%s" % (obj.name, obj.triangles, obj.vertices, ",".join(obj.material_names))
         for obj in snapshot.objects]
    ) + "|%d|%d|%s" % (snapshot.file_bytes, snapshot.triangles, ",".join(snapshot.extensions_used))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass
class SceneContext:
    """What the live scene knows that the exported artifact cannot carry.

    A ``.glb`` holds meshes; a Blender scene also has cameras and lights, and the render settings
    that make two renders comparable. This record is the workflow's declared knowledge of those
    objects, each entry tagged with where the claim came from -- an MCP ``get_scene_info`` call, a
    render's own metadata, or a person -- so an unverified name is never treated as verified.
    """

    source: str = ""
    captured_from: str = ""
    entries: Dict[str, str] = field(default_factory=dict)   # object name -> kind
    evidence: Dict[str, str] = field(default_factory=dict)  # object name -> where it came from
    render_settings: Dict[str, Any] = field(default_factory=dict)

    def kind_of(self, name: str) -> Optional[str]:
        return self.entries.get(name)

    def knows(self, name: str) -> bool:
        return name in self.entries

    def of_kind(self, kind: str) -> List[str]:
        return sorted(name for name, value in self.entries.items() if value == kind)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "captured_from": self.captured_from,
            "entries": dict(self.entries),
            "evidence": dict(self.evidence),
            "render_settings": dict(self.render_settings),
            "cameras": self.of_kind("camera"),
            "lights": self.of_kind("light"),
            "meshes": len(self.of_kind("mesh")),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneContext":
        context = cls(source=data.get("source", ""),
                      captured_from=data.get("captured_from", ""),
                      render_settings=dict(data.get("render_settings", {})))
        entries: Dict[str, str] = {}
        for key, value in (data.get("entries") or {}).items():
            entries[key] = str(value)
        for kind in ("cameras", "lights", "meshes", "objects"):
            for name in data.get(kind, []) or []:
                if isinstance(name, str):
                    entries.setdefault(name, "mesh" if kind in ("meshes", "objects") else kind[:-1])
        context.entries = entries
        context.evidence = {str(k): str(v) for k, v in (data.get("evidence") or {}).items()}
        return context

    @classmethod
    def load(cls, path: str) -> "SceneContext":
        with open(path, "r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    @classmethod
    def from_snapshot(cls, snapshot: SceneSnapshot, source: str = "exported scene") -> "SceneContext":
        """Everything the exported artifact can prove: its meshes, and nothing else."""
        context = cls(source=source, captured_from=snapshot.source_path)
        for obj in snapshot.objects:
            context.entries[obj.name] = "mesh"
            context.evidence[obj.name] = "exported scene %s" % os.path.basename(snapshot.source_path)
        return context


def objects_matching(snapshot: SceneSnapshot, patterns: Iterable[str]) -> List[SceneObject]:
    found: List[SceneObject] = []
    seen: set = set()
    for pattern in patterns:
        for obj in snapshot.match(pattern):
            if obj.name not in seen:
                seen.add(obj.name)
                found.append(obj)
    return found

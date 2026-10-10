"""9f_probe2.py -- the legacy materials that export as white metal.

    blender.exe -b --factory-startup --python 9f_probe2.py

For every material: how many object slots use it, whether it has a Principled BSDF,
its real base colour / metallic / roughness, and for legacy trees the colours hiding
in their BSDF nodes.  This is the list the conversion has to reproduce.
"""
from collections import Counter

import bpy

BLEND = "E:/Reality/ECO/Bussiness/Mall/MiniMarket/Shop_with_people.blend"


def P(*a):
    print("###", *a)
    try:
        import sys
        sys.stdout.flush()
    except Exception:
        pass


def rgba(v):
    try:
        return "(%.3f,%.3f,%.3f,%.2f)" % (v[0], v[1], v[2], v[3])
    except Exception:
        try:
            return "(%.3f,%.3f,%.3f)" % (v[0], v[1], v[2])
        except Exception:
            try:
                return "%.3f" % v
            except Exception:
                return "?"


bpy.ops.wm.open_mainfile(filepath=BLEND)
P("opened")

use = Counter()
for o in bpy.data.objects:
    for s in getattr(o, "material_slots", []) or []:
        if s.material:
            use[s.material.name] += 1
P("object slots by material (top 40):")
for name, n in use.most_common(40):
    P("   ", n, name)

P("--- materials WITHOUT a Principled BSDF ---")
legacy = []
for m in bpy.data.materials:
    if not m.use_nodes:
        legacy.append((m.name, use[m.name], "no-nodes", []))
        continue
    nodes = list(m.node_tree.nodes)
    if any(n.type == "BSDF_PRINCIPLED" for n in nodes):
        continue
    # gather the colours that plausibly mean albedo / gloss
    info = []
    for n in nodes:
        if n.type in ("BSDF_DIFFUSE", "BSDF_GLOSSY", "BSDF_ANISOTROPIC", "EMISSION", "BSDF_TRANSPARENT", "BSDF_TRANSMISSION"):
            c = n.inputs.get("Color")
            r = n.inputs.get("Roughness")
            info.append("%s col=%s%s" % (n.type, rgba(c.default_value) if c else "-",
                                         " rough=%s" % rgba(r.default_value) if r else ""))
        if n.type == "TEX_IMAGE" and n.image:
            info.append("IMG:%s" % n.image.name)
        if n.type == "VALTORGB":
            info.append("VALTORGB")
        if n.type == "MIX_SHADER":
            info.append("MIX")
        if n.type == "FRESNEL":
            info.append("FRESNEL")
        if n.type == "LAYER_WEIGHT":
            info.append("LAYERWEIGHT")
    legacy.append((m.name, use[m.name], ",".join(sorted({n.type for n in nodes})), info))

legacy.sort(key=lambda r: -r[1])
P("count:", len(legacy))
for name, n, kinds, info in legacy:
    P("   ", n, "slots |", name, "| diffuse=%s" % rgba(bpy.data.materials[name].diffuse_color),
      "| metal=%.2f rough=%.2f" % (bpy.data.materials[name].metallic, bpy.data.materials[name].roughness),
      "|", kinds)
    if info:
        P("        ", " ; ".join(info[:6]))

P("--- Principled base colours (to check for white/pink defaults) ---")
whites = 0
for m in bpy.data.materials:
    if not m.use_nodes:
        continue
    for n in m.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            bc = n.inputs.get("Base Color")
            if bc and not bc.is_linked:
                c = tuple(bc.default_value)
                if c[0] > 0.9 and c[1] > 0.9 and c[2] > 0.9:
                    whites += 1
                    if use[m.name]:
                        P("    WHITE", use[m.name], "slots |", m.name)
            break
P("principled materials with an unlinked near-white base:", whites)
P("done")

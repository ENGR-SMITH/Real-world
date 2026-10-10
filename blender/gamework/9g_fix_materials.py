"""9g_fix_materials.py -- make every material exportable, and export lights.

    blender.exe -b --factory-startup --python 9g_fix_materials.py

The previous pass failed because it only linked the new Principled node when the
material output had no link -- and every legacy material already had one, so the
old node tree still drove the export and glTF fell back to white/metal-1/rough-1.

This time the Principled BSDF *replaces* whatever fed the output, and its values
are read out of the legacy nodes (BSDF_DIFFUSE / BSDF_GLOSSY / EMISSION), not from
material.diffuse_color -- which is a meaningless 0.8 grey on nearly all of them.

Also writes lights.json and sky.json so the web build can light the scene the way
the blend does (the export carried no lights: 4 point lights + 1 sun were dropped).
"""
import json
import os
import time

import bpy
from mathutils import Vector

BLEND = "E:/Reality/ECO/Bussiness/Mall/MiniMarket/Shop_with_people.blend"
ASSETS = "E:/Reality/webapp/public/assets"
GLB = ASSETS + "/shop3.glb"


def P(*a):
    print("###", *a)
    try:
        import sys
        sys.stdout.flush()
    except Exception:
        pass


def sock(node, *names):
    for n in names:
        if n in node.inputs:
            return node.inputs[n]
    return None


def lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


NON_ALBEDO = ("normal", "spec", "rough", "bump", "metal", "ao", "opacity",
              "gloss", "mask", "height", "displace")


def albedo_texture(nt, shaders):
    """The image that actually means colour, not the first TEX_IMAGE in the tree.

    Taking texnodes[0] blindly put the boy's *specular* map into Base Color and
    rendered him white, so follow the real links first and use names only as a hint.
    """
    def unwrap(node):
        if node.type == "TEX_IMAGE" and node.image:
            return node
        for i in node.inputs:
            if i.is_linked:
                src = i.links[0].from_node
                if src.type == "TEX_IMAGE" and src.image:
                    return src
        return None

    for sh in shaders:
        inp = sh.inputs.get("Color")
        if inp is not None and inp.is_linked:
            found = unwrap(inp.links[0].from_node)
            if found is not None:
                return found
    imgs = [n for n in nt.nodes if n.type == "TEX_IMAGE" and n.image]
    for n in imgs:
        if not any(k in n.image.name.lower() for k in NON_ALBEDO):
            return n
    return imgs[0] if imgs else None


GLASS = ("bsdf_transparent", "bsdf_translucent")
METAL_WORDS = ("chrom", "chrome", "aluminium", "aluminum", "metal", "stahl",
               "steel", "silber", "edelstahl", "anodized")

t0 = time.time()
bpy.ops.wm.open_mainfile(filepath=BLEND)
P("opened in %.1f s" % (time.time() - t0))

converted = textured = glassy = emissive = untouched = 0
report = []

for m in bpy.data.materials:
    if not m.use_nodes or m.node_tree is None:
        continue
    nt = m.node_tree

    prin = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
    if out is None:
        continue
    existing_prin = prin is not None
    if prin is None:
        prin = nt.nodes.new("ShaderNodeBsdfPrincipled")
        prin.location = (0, 0)

    # a material that already has a sane Principled keeps its own values: the
    # B4W_* family exported correctly and must not be re-derived from diffuse_color
    keep_base = None
    keep_metal = None
    if existing_prin:
        bs = sock(prin, "Base Color")
        if bs is not None and not bs.is_linked:
            c = tuple(bs.default_value)
            if not (c[0] > 0.9 and c[1] > 0.9 and c[2] > 0.9 and not any(n.type == "TEX_IMAGE" and n.image for n in nt.nodes)):
                keep_base = c
        mt = sock(prin, "Metallic")
        rg = sock(prin, "Roughness")
        if mt is not None and rg is not None and (mt.default_value, rg.default_value) != (1.0, 1.0):
            keep_metal = (float(mt.default_value), float(rg.default_value))

    # A material that already exports correctly -- Principled surface, base colour
    # driven by a texture -- must be left exactly alone.  The boy rig is one of
    # these, and an earlier pass of this script stripped his albedo.
    surf = out.inputs["Surface"]
    bs_early = sock(prin, "Base Color")
    if (existing_prin and surf.is_linked and surf.links[0].from_node is prin
            and bs_early is not None and bs_early.is_linked):
        untouched += 1
        continue

    # THE fix: the Principled node becomes the surface, replacing any legacy chain
    nt.links.new(prin.outputs["BSDF"], out.inputs["Surface"])

    types = {n.type for n in nt.nodes}
    is_glass = bool(types & {t.upper() for t in GLASS}) or any(
        n.type in ("BSDF_TRANSPARENT", "BSDF_TRANSLUCENT") for n in nt.nodes)
    emis_nodes = [n for n in nt.nodes if n.type == "EMISSION"]
    glossy = [n for n in nt.nodes if n.type == "BSDF_GLOSSY"]
    diffuse = [n for n in nt.nodes if n.type == "BSDF_DIFFUSE"]
    texnodes = [n for n in nt.nodes if n.type == "TEX_IMAGE" and n.image]

    # ---- base colour: texture first, else the brightest glossy, else diffuse
    tex = albedo_texture(nt, glossy + diffuse + emis_nodes) if texnodes else None
    base = None
    if keep_base is not None:
        pass  # already sane: leave it exactly as Blender has it
    elif tex is not None:
        sock(prin, "Base Color").default_value = (1, 1, 1, 1)
        nt.links.new(tex.outputs["Color"], sock(prin, "Base Color"))
        textured += 1
    else:
        cands = []
        for group in (glossy, diffuse):
            for n in group:
                c = n.inputs.get("Color")
                if c is not None and not c.is_linked:
                    cands.append(tuple(c.default_value))
        if is_glass and glossy:
            c = glossy[0].inputs.get("Color")
            if c is not None and not c.is_linked:
                cands.insert(0, tuple(c.default_value))
        if cands:
            base = max(cands, key=lum)
        elif emis_nodes:
            c = emis_nodes[0].inputs.get("Color")
            base = tuple(c.default_value) if c is not None else None
        if base is None:
            base = tuple(m.diffuse_color)
            if base[0] > 0.75 and base[1] > 0.75 and base[2] > 0.75:
                base = (0.6, 0.6, 0.6, 1.0)  # the 0.8 default grey means "unset"
        sock(prin, "Base Color").default_value = (base[0], base[1], base[2], 1.0)

    # ---- roughness: what the glossy shader was using
    rough = keep_metal[1] if keep_metal else None
    if keep_metal:
        sock(prin, "Metallic").default_value = keep_metal[0]
    if keep_metal:
        pass
    elif glossy:
        r = glossy[0].inputs.get("Roughness")
        if r is not None and not r.is_linked:
            rough = float(r.default_value)
    if is_glass:
        rough = 0.06
    elif rough is None or rough <= 0.0:
        rough = 0.85 if (diffuse and not glossy) else 0.55
    sock(prin, "Roughness").default_value = max(0.04, min(1.0, rough))

    # ---- metallic: only the genuinely metal-named materials
    low = m.name.lower()
    metal = any(w in low for w in METAL_WORDS) and not is_glass
    if not keep_metal:
        sock(prin, "Metallic").default_value = 0.9 if metal else 0.0

    # ---- glass: cheap alpha blending (a transmission pass over 1M tris is slow)
    if is_glass:
        a = sock(prin, "Alpha")
        if a is not None:
            a.default_value = 0.38
        try:
            m.blend_method = "BLEND"
        except Exception:
            pass
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            pass
        try:
            m.show_transparent_back = False
        except Exception:
            pass
        glassy += 1

    # ---- emissive surfaces (lamps, light boxes, neon)
    if emis_nodes:
        c = emis_nodes[0].inputs.get("Color")
        if c is not None:
            ec = tuple(c.default_value)
            es = sock(prin, "Emission Color", "Emission")
            if es is not None:
                es.default_value = (ec[0], ec[1], ec[2], 1.0)
            st = sock(prin, "Emission Strength")
            if st is not None:
                st.default_value = 1.2
            emissive += 1

    m.metallic = sock(prin, "Metallic").default_value
    m.roughness = sock(prin, "Roughness").default_value
    if not existing_prin or tex is not None or is_glass or emis_nodes:
        converted += 1
        report.append("%s | tex=%s base=%s metal=%.2f rough=%.2f%s%s"
                      % (m.name, tex.image.name if tex else "-",
                         ("kept" if keep_base is not None else
                          "tex" if tex else ("(%.2f,%.2f,%.2f)" % tuple(base[:3]))),
                         sock(prin, "Metallic").default_value,
                         sock(prin, "Roughness").default_value,
                         " GLASS" if is_glass else "",
                         " EMIT" if emis_nodes else ""))

P("materials already exportable, left untouched: %d" % untouched)
P("materials touched: %d (textured %d, glass %d, emissive %d)"
  % (converted, textured, glassy, emissive))
P("--- what the export now sees ---")
for r in sorted(report)[:70]:
    P("   ", r)

# ------------------------------------------------------------------ lights.json
lights = []
for o in bpy.data.objects:
    if o.type != "LIGHT":
        continue
    d = o.data
    q = o.matrix_world.to_quaternion()
    lights.append({
        "name": o.name,
        "type": d.type,
        "energy": float(d.energy),
        "color": [float(c) for c in d.color],
        "loc": [float(v) for v in o.matrix_world.translation],
        "dir": [float(v) for v in (q @ Vector((0, 0, -1)))],
        "radius": float(getattr(d, "shadow_soft_size", 0.25) or 0.25),
    })
P("lights exported:", len(lights))
for l in lights:
    P("   ", l["type"], l["name"], "energy=%.1f" % l["energy"], "at", [round(v, 2) for v in l["loc"]])

sky = {}
w = bpy.data.worlds[0] if bpy.data.worlds else None
if w is not None:
    sky["world_color"] = [float(c) for c in w.color]
    if w.use_nodes:
        for n in w.node_tree.nodes:
            if n.type == "TEX_SKY":
                for key in ("sun_elevation", "sun_rotation", "sun_intensity",
                            "altitude", "air_density", "dust_density", "turbidity",
                            "ground_albedo"):
                    if hasattr(n, key):
                        sky[key] = float(getattr(n, key))
            if n.type == "BACKGROUND":
                c = n.inputs.get("Color")
                if c is not None and not c.is_linked:
                    sky["bg_color"] = [float(v) for v in c.default_value]
                s = n.inputs.get("Strength")
                if s is not None and not s.is_linked:
                    sky["bg_strength"] = float(s.default_value)
P("sky:", json.dumps(sky))
os.makedirs(ASSETS, exist_ok=True)
with open(ASSETS + "/lights.json", "w") as fh:
    json.dump({"lights": lights, "sky": sky}, fh, indent=1)

# ---------------------------------------------------------------------- export
want = {
    "filepath": GLB,
    "export_format": "GLB",
    "use_selection": False,
    "export_apply": True,
    "export_yup": True,
    "export_animations": True,
    "export_animation_mode": "ACTIONS",
    "export_materials": "EXPORT",
    "export_image_format": "AUTO",
    "export_skins": True,
    "export_morph": False,
    "export_cameras": False,
    "export_lights": True,
    "export_extras": False,
}
props = set(bpy.ops.export_scene.gltf.get_rna_type().properties.keys())
P("export_lights supported:", "export_lights" in props)
kwargs = {k: v for k, v in want.items() if k in props}
t1 = time.time()
bpy.ops.export_scene.gltf(**kwargs)
P("exported in %.1f s" % (time.time() - t1))
if os.path.exists(GLB):
    P("shop3.glb %.1f MB" % (os.path.getsize(GLB) / 1048576.0))
P("total %.1f s" % (time.time() - t0))

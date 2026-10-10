"""9c_materials.py -- give the blend's materials the colours glTF can carry, re-export.

The glTF export only understands a Principled BSDF with an image texture.  This
scene's materials are older than that, so the exporter fell back to white,
metallic 1, roughness 1 for ~95% of the surfaces -- which is why the web build
looked black and flat next to Blender.

    blender.exe -b --factory-startup --python 9c_materials.py

Step 1 restores a real base colour (and links a texture by name where the blend's
folder holds one), step 2 re-exports to shop2.glb so the old export survives.
"""
import os
import time

import bpy

BLEND = "E:/Reality/ECO/Bussiness/Mall/MiniMarket/Shop_with_people.blend"
ASSETS = "E:/Reality/webapp/public/assets"
GLB = ASSETS + "/shop2.glb"
FOLDER = os.path.dirname(BLEND)
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")


def P(*a):
    print("###", *a)
    try:
        import sys
        sys.stdout.flush()
    except Exception:
        pass


def norm(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


files = [f for f in os.listdir(FOLDER) if f.lower().endswith(IMAGE_EXT)]
by_name = {}
for f in files:
    by_name.setdefault(norm(os.path.splitext(f)[0]), f)
P("image files in the blend's folder: %d" % len(files))

t0 = time.time()
bpy.ops.wm.open_mainfile(filepath=BLEND)
P("opened in %.1f s" % (time.time() - t0))

mats = list(bpy.data.materials)
P("materials %d" % len(mats))

# what do they look like now?
stats = {"principled": 0, "image": 0, "named_match": 0, "white": 0}
rows = []
for m in mats:
    node = None
    has_img = False
    if m.use_nodes and m.node_tree:
        for n in m.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                node = n
            if n.type == "TEX_IMAGE" and n.image:
                has_img = True
    col = tuple(round(c, 3) for c in m.diffuse_color[:3])
    key = norm(m.name.split(".")[0])
    match = by_name.get(key)
    stats["principled"] += 1 if node else 0
    stats["image"] += 1 if has_img else 0
    stats["named_match"] += 1 if match else 0
    stats["white"] += 1 if min(col) > 0.95 else 0
    rows.append((m.name, has_img, col, match or "-"))
P("principled nodes %(principled)d | image textured %(image)d | texture file matching the name %(named_match)d | pure white %(white)d"
  % stats)
for name, has_img, col, match in rows[:30]:
    P("   %-24s img=%-5s colour=%s file=%s" % (name[:24], has_img, col, match))

# ---------------------------------------------------------------- 1. the fix
touched_colour = touched_tex = 0
for m in mats:
    if not m.use_nodes or m.node_tree is None:
        m.use_nodes = True
    nt = m.node_tree
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
    if out is None:
        out = nt.nodes.new("ShaderNodeOutputMaterial")
    node = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if node is None:
        node = nt.nodes.new("ShaderNodeBsdfPrincipled")
        node.location = (0, 0)
    if not out.inputs["Surface"].links:
        nt.links.new(node.outputs["BSDF"], out.inputs["Surface"])

    has_img = any(n.type == "TEX_IMAGE" and n.image for n in nt.nodes)

    # a texture that exists in the folder but was never linked: link it now
    if not has_img:
        f = by_name.get(norm(m.name.split(".")[0]))
        if f:
            try:
                img = bpy.data.images.load(os.path.join(FOLDER, f), check_existing=True)
                tex = nt.nodes.new("ShaderNodeTexImage")
                tex.image = img
                tex.location = (-420, 220)
                uvn = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), node)
                nt.links.new(tex.outputs["Color"], uvn.inputs["Base Color"])
                touched_tex += 1
                has_img = True
            except Exception as exc:
                P("texture link failed for %s: %r" % (m.name, exc))

    if not has_img:
        # no texture anywhere: use the colour Blender shows for this material
        col = m.diffuse_color
        node.inputs["Base Color"].default_value = (col[0], col[1], col[2], 1.0)
        touched_colour += 1

    # legacy materials came out fully metallic AND fully rough, which renders black
    name = m.name.lower()
    metal = any(k in name for k in ("chrom", "aluminium", "metal", "stahl", "edelstahl", "silber"))
    node.inputs["Metallic"].default_value = 0.85 if metal else 0.0
    node.inputs["Roughness"].default_value = 0.28 if metal else 0.62
    m.metallic = 0.85 if metal else 0.0
    m.roughness = 0.28 if metal else 0.62

P("colours restored on %d materials, textures linked on %d" % (touched_colour, touched_tex))
# deliberately NOT saved: the export reads the in-memory scene, and the blend the
# desktop game uses must keep the materials it already renders correctly
P("blend left untouched (%s)" % bpy.data.filepath)

# ---------------------------------------------------------------- 2. re-export
os.makedirs(ASSETS, exist_ok=True)
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
    "export_lights": False,
    "export_extras": False,
}
props = set(bpy.ops.export_scene.gltf.get_rna_type().properties.keys())
kwargs = {k: v for k, v in want.items() if k in props}
t1 = time.time()
bpy.ops.export_scene.gltf(**kwargs)
P("exported in %.1f s" % (time.time() - t1))
if os.path.exists(GLB):
    P("shop2.glb %.1f MB" % (os.path.getsize(GLB) / 1048576.0))
P("total %.1f s" % (time.time() - t0))

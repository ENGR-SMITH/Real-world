"""9b_export_glb.py -- export the deliverable scene to glTF for the Three.js webapp.

    blender.exe -b --factory-startup --python 9b_export_glb.py

Writes E:/Reality/webapp/public/assets/shop.glb (whole scene, both boys included)
and prints the numbers the webapp has to live with: vertex count, image count,
file size, and how long the export took.
"""
import os
import time

import bpy

BLEND = "E:/Reality/ECO/Bussiness/Mall/MiniMarket/Shop_with_people.blend"
OUT = "E:/Reality/webapp/public/assets"
GLB = OUT + "/shop.glb"


def P(*a):
    print("###", *a)
    try:
        import sys
        sys.stdout.flush()
    except Exception:
        pass


os.makedirs(OUT, exist_ok=True)
t0 = time.time()
bpy.ops.wm.open_mainfile(filepath=BLEND)
P("opened in %.1f s" % (time.time() - t0))

objs = list(bpy.data.objects)
P("objects %d" % len(objs))
verts = tris = 0
for o in objs:
    if o.type == "MESH" and o.data is not None:
        verts += len(o.data.vertices)
        tris += len(o.data.loop_triangles) or len(o.data.polygons)
P("mesh verts %d  polys %d" % (verts, tris))
P("materials %d" % len(bpy.data.materials))
imgs = [i for i in bpy.data.images if i.source == "FILE"]
P("images %d, missing on disk: %s" % (
    len(imgs), [i.name for i in imgs if not i.filepath or not os.path.exists(bpy.path.abspath(i.filepath))][:8]))
acts = list(bpy.data.actions)
P("actions %s" % [a.name for a in acts])
arms = [o for o in objs if o.type == "ARMATURE"]
for a in arms:
    P("armature %-12s bones %d" % (a.name, len(a.data.bones)))

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
# the operator's property set moves between Blender versions: pass only what exists
props = set(bpy.ops.export_scene.gltf.get_rna_type().properties.keys())
kwargs = {k: v for k, v in want.items() if k in props}
dropped = sorted(set(want) - set(kwargs))
if dropped:
    P("exporter has no", dropped)

t1 = time.time()
bpy.ops.export_scene.gltf(**kwargs)
P("exported in %.1f s" % (time.time() - t1))
if os.path.exists(GLB):
    mb = os.path.getsize(GLB) / 1048576.0
    P("shop.glb %.1f MB" % mb)
else:
    P("shop.glb MISSING")
P("total %.1f s" % (time.time() - t0))

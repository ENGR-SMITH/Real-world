"""73_what_renders.py -- which kinds of object does the engine actually draw?

Everything my scripts created lately (HUD text, props, test cubes) stays invisible
while the street, the SUV, the tuk-tuk and the boys draw fine.  Put four different
kinds of object two metres in front of the settled camera and see which ones appear:

    QQ_RR   copy of Street_Road    -- an old mesh in a named collection
    QQ_RR2  copy of Prop_Item_1    -- a prop my build script placed
    QQ_PL   bpy.ops plane          -- geometry from an operator, old material
    QQ_CB   bpy.ops cube           -- geometry from an operator, no material

    blender.exe -b hud_test.blend --python 73_what_renders.py
"""

import bpy

P = print
sc = bpy.context.scene
ATM = bpy.data.materials.get("Street_Asphalt")


def drop(*names):
    for nm in names:
        o = bpy.data.objects.get(nm)
        if o:
            bpy.data.objects.remove(o, do_unlink=True)


drop("QQ_RR", "QQ_RR2", "QQ_PL", "QQ_CB")

P("### collection membership check")
for nm in ("Prop_Item_1", "Prop_Item_2", "Street_Road", "HUD_Help", "QQ_F",
           "boy_item_lowpoly" if False else "SUV_root"):
    o = bpy.data.objects.get(nm)
    P("###   %-14s %s" % (nm, [c.name for c in o.users_collection] if o else "missing"))

src = bpy.data.objects.get("Street_Road")
if src:
    rr = src.copy()
    rr.data = src.data.copy()
    rr.name = "QQ_RR"
    rr.parent = None
    rr.matrix_world = src.matrix_world.copy()
    sc.collection.objects.link(rr)
    rr.location = (-5.0, -1.0, 1.5)
    rr.scale = (0.15, 0.05, 0.5)
    P("### QQ_RR copy of Street_Road dims=%s mats=%s" % (
        tuple(round(v, 3) for v in rr.dimensions), [m.name for m in rr.data.materials]))
else:
    P("### Street_Road missing")

prop = bpy.data.objects.get("Prop_Item_1")
if prop:
    p2 = prop.copy()
    p2.data = prop.data.copy()
    p2.name = "QQ_RR2"
    p2.parent = None
    sc.collection.objects.link(p2)
    p2.location = (-4.3, -1.0, 1.5)
    p2.scale = (2.0, 2.0, 2.0)
    P("### QQ_RR2 copy of Prop_Item_1 dims=%s mats=%s" % (
        tuple(round(v, 3) for v in p2.dimensions),
        [m.name if m else None for m in p2.data.materials]))
else:
    P("### Prop_Item_1 missing")

bpy.ops.mesh.primitive_plane_add(size=0.8, location=(-5.5, -1.0, 1.5))
pl = bpy.context.active_object
pl.name = "QQ_PL"
if ATM:
    pl.data.materials.append(ATM)
P("### QQ_PL plane dims=%s mats=%s uv=%s" % (
    tuple(round(v, 3) for v in pl.dimensions),
    [m.name if m else None for m in pl.data.materials],
    [u.name for u in pl.data.uv_layers]))

bpy.ops.mesh.primitive_cube_add(size=0.4, location=(-5.0, -1.0, 2.4))
cb = bpy.context.active_object
cb.name = "QQ_CB"
P("### QQ_CB cube dims=%s" % (tuple(round(v, 3) for v in cb.dimensions),))

P("### saving")
bpy.ops.wm.save_mainfile()
P("### saved %s" % bpy.data.filepath)

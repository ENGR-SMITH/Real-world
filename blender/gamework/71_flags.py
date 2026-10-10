"""71_flags.py -- why do some objects render and the HUD/test cubes not?

Dumps every render- and visibility-relevant flag for objects that certainly draw
(SUV, tuk-tuk, a shop mesh, a pavement mesh) next to the HUD objects and the QQ_
test cubes, plus each object's collection and that collection's view-layer state.

    blender.exe -b Shop_with_people.blend --python 71_flags.py     (no save)
"""

import bpy

P = print
VL = bpy.context.view_layer

FLAGS = ("hide_viewport", "hide_render", "hide_get", "is_holdout", "is_shadow_catcher",
         "display_type", "display_bounds_type", "visible_camera", "visible_diffuse",
         "visible_glossy", "visible_transmission", "visible_volume_scatter",
         "visible_shadow", "show_in_front", "instance_type", "parent_type")


def show(o):
    bits = []
    for f in FLAGS:
        try:
            bits.append("%s=%s" % (f, getattr(o, f)))
        except Exception as exc:
            bits.append("%s=ERR(%s)" % (f, type(exc).__name__))
    P("### %s" % o.name)
    P("###   %s" % " ".join(bits))
    P("###   parent=%s colls=%s type=%s" % (
        o.parent.name if o.parent else None,
        [c.name for c in o.users_collection], o.type))
    if o.type == 'MESH':
        me = o.data
        P("###   verts=%d faces=%d mats=%s" % (
            len(me.vertices), len(me.polygons), [m.name if m else None for m in me.materials]))
        bb = [tuple(round(v, 4) for v in c) for c in o.bound_box]
        P("###   bound_box0/6=%s %s dims=%s" % (
            bb[0], bb[6], tuple(round(v, 4) for v in o.dimensions)))
    for m in (o.data.materials if o.type == 'MESH' and o.data else []):
        if m is None:
            continue
        P("###   mat %s use_nodes=%s blend=%s shadow=%s alpha=%.2f backface=%s" % (
            m.name, m.use_nodes, getattr(m, "blend_method", "?"),
            getattr(m, "shadow_method", "?"), getattr(m, "alpha_threshold", -1) or 0,
            getattr(m, "use_backface_culling", "?")))
        if m.use_nodes:
            P("###     nodes: %s" % [n.bl_idname for n in m.node_tree.nodes])


P("### view layers: %s active=%s" % ([l.name for l in bpy.data.scenes], VL.name))
sc = bpy.context.scene
P("### scene collections: %s" % [c.name for c in sc.collection.children])
for lc in VL.layer_collection.children:
    P("### layer collection %-24s exclude=%s hide_viewport=%s holdout=%s" % (
        lc.name, lc.exclude, lc.hide_viewport, lc.holdout))

P("### --- objects that DO render ---")
for nm in ("SUV_root", "TukTuk_root", "Boy1_RIG", "Street_Road", "Street_Pavement"):
    o = bpy.data.objects.get(nm)
    if o:
        show(o)
    else:
        P("### %s missing" % nm)

P("### --- objects that do NOT render ---")
for nm in ("HUD_Help", "HUD_Title1", "P_DoorOpen", "QQ_F", "QQ_A", "QQ_HUDHELP"):
    o = bpy.data.objects.get(nm)
    if o:
        show(o)
    else:
        P("### %s missing" % nm)

P("### --- a shop mesh that renders ---")
for o in bpy.data.objects:
    if o.type == 'MESH' and ("Shelf" in o.name or "shelf" in o.name):
        show(o)
        break
P("### FLAGS DONE")

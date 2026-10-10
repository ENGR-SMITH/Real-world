import bpy, sys

def p(*a):
    print(*a)
    sys.stdout.flush()

p("=== FILE:", bpy.data.filepath)
sc = bpy.context.scene
p("SCENES:", [s.name for s in bpy.data.scenes])
p("COLLECTIONS(top):", [c.name for c in bpy.data.collections])
p("FRAMES:", sc.frame_start, sc.frame_end, sc.render.fps)
p("UNIT:", sc.unit_settings.system, sc.unit_settings.scale_length)
p("ENGINE:", sc.render.engine)

objs = list(bpy.data.objects)
p("=== OBJCOUNT:", len(objs))
for o in objs:
    par = o.parent.name if o.parent else "-"
    mods = ",".join(m.type for m in o.modifiers)
    p("OBJ|%s|%s|parent=%s|loc=%.3f,%.3f,%.3f|scale=%.3f,%.3f,%.3f|dim=%.3f,%.3f,%.3f|mods=%s" % (
        o.name, o.type, par, o.location[0], o.location[1], o.location[2],
        o.scale[0], o.scale[1], o.scale[2], o.dimensions[0], o.dimensions[1], o.dimensions[2], mods))

p("=== ARMATURES")
for a in bpy.data.armatures:
    p("ARM|%s|bones=%d" % (a.name, len(a.bones)))
    p("   BONES:", [b.name for b in a.bones])

p("=== ACTIONS")
for a in bpy.data.actions:
    users = []
    for o in objs:
        ad = o.animation_data
        if ad and ad.action == a:
            users.append(o.name)
    p("ACT|%s|fcurves=%d|range=%.1f-%.1f|users=%s" % (a.name, len(a.fcurves), a.frame_range[0], a.frame_range[1], users))
    # summarize channels
    chans = sorted(set(fc.data_path for fc in a.fcurves))
    p("   CHAN(%d):" % len(chans), chans[:40])

p("=== NLA")
for o in objs:
    ad = o.animation_data
    if ad and ad.nla_tracks:
        for t in ad.nla_tracks:
            p("NLA|%s|%s|strips=%s" % (o.name, t.name, [(s.name, s.frame_start, s.frame_end) for s in t.strips]))

p("=== MATERIALS:", len(bpy.data.materials))
for m in bpy.data.materials:
    imgs = []
    if m.use_nodes:
        for n in m.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image:
                imgs.append((n.image.name, n.image.filepath, bool(n.image.packed_file)))
    p("MAT|%s|users=%d|nodes=%s|imgs=%s" % (m.name, m.users, m.use_nodes, imgs))

p("=== IMAGES")
for i in bpy.data.images:
    p("IMG|%s|%s|packed=%s|size=%sx%s" % (i.name, i.filepath, bool(i.packed_file), i.size[0], i.size[1]))

p("=== SHAPEKEYS")
for m in bpy.data.meshes:
    if m.shape_keys:
        p("SK|%s|keys=%s" % (m.name, [k.name for k in m.shape_keys.key_blocks]))

p("=== BBOX(all meshes, world)")
import mathutils
mn = [1e18]*3; mx = [-1e18]*3
dg = bpy.context.evaluated_depsgraph_get()
for o in objs:
    if o.type != 'MESH':
        continue
    ob = o.evaluated_get(dg)
    for c in ob.bound_box:
        w = ob.matrix_world @ mathutils.Vector(c)
        for k in range(3):
            mn[k] = min(mn[k], w[k]); mx[k] = max(mx[k], w[k])
p("BBOX min=%s max=%s" % (["%.3f" % v for v in mn], ["%.3f" % v for v in mx]))

p("=== TOOLS/ADDONS that matter")
p("addons:", [a for a in bpy.context.preferences.addons.keys()])
p("DONE")

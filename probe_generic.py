import bpy, sys

p = print
p("=== FILE:", bpy.data.filepath)
sc = bpy.context.scene
p("SCENE_FRAMES", sc.frame_start, sc.frame_end, sc.render.fps, "UNIT", sc.unit_settings.scale_length)
p("OBJCOUNT", len(bpy.data.objects))

for o in bpy.data.objects:
    if o.type == 'ARMATURE' or (o.type == 'MESH' and not o.name.startswith('shape_')):
        p("OBJ|%s|%s|parent=%s|dim=%s|loc=%s|scale=%s|mods=%s" % (
            o.name, o.type, o.parent.name if o.parent else '-',
            ["%.2f" % d for d in o.dimensions],
            ["%.2f" % v for v in o.location],
            ["%.2f" % v for v in o.scale],
            ",".join(m.type for m in o.modifiers)))

p("=== ARMATURES")
for a in bpy.data.armatures:
    p("ARM|%s|bones=%d" % (a.name, len(a.bones)))
    p("BONES|" + a.name + "|" + "|".join(b.name for b in a.bones))

p("=== ACTIONS")
for act in bpy.data.actions:
    us = [o.name for o in bpy.data.objects if o.animation_data and o.animation_data.action == act]
    p("ACT|%s|fcurves=%d|range=%.1f-%.1f|users=%s" % (act.name, len(act.fcurves), act.frame_range[0], act.frame_range[1], us))
    dp = sorted(set(fc.data_path for fc in act.fcurves))
    p("   PATHS(%d)|%s" % (len(dp), dp[:25]))

p("=== NLA")
for o in bpy.data.objects:
    if o.animation_data and o.animation_data.nla_tracks:
        for t in o.animation_data.nla_tracks:
            p("NLA|%s|%s|%s" % (o.name, t.name, [(s.name, s.frame_start, s.frame_end) for s in t.strips]))

p("=== MATS", [m.name for m in bpy.data.materials])
p("=== IMGS", [(i.name, bool(i.packed_file)) for i in bpy.data.images])
p("DONE")

import bpy, sys

def p(*a):
    print(*a); sys.stdout.flush()

p("=== FILE:", bpy.data.filepath)
p("OBJS:", len(bpy.data.objects))
for o in bpy.data.objects:
    if o.type != "MESH":
        p("NONMESH|%s|%s" % (o.name, o.type)); continue
    mats = []
    for s in o.material_slots:
        m = s.material
        if not m:
            mats.append("-"); continue
        try:
            c = m.diffuse_color
            col = "%d,%d,%d" % (round(c[0] * 255), round(c[1] * 255), round(c[2] * 255))
        except Exception:
            col = "?"
        mats.append("%s[%s]" % (m.name, col))
    p("MESH|%s|dim=%.3f,%.3f,%.3f|loc=%.3f,%.3f,%.3f|mats=%s" % (
        o.name, o.dimensions[0], o.dimensions[1], o.dimensions[2],
        o.location[0], o.location[1], o.location[2], " ".join(mats)))

p("=== MATERIALS")
for m in bpy.data.materials:
    c = m.diffuse_color
    p("MAT|%s|rgb=%d,%d,%d|alpha=%.2f|nodes=%s" % (
        m.name, round(c[0] * 255), round(c[1] * 255), round(c[2] * 255), c[3],
        m.use_nodes))

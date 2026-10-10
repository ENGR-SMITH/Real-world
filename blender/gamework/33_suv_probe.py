"""Where is the SUV's pavement-side front door? Render its flank and test a box."""
import bpy
import mathutils

GW = 'E:/Reality/blender/gamework/'
exec(open(GW + 'render_util.py').read())

bpy.context.scene.frame_set(1)
bpy.context.view_layer.update()

body = bpy.data.objects['bmw27-Body']
print("### body parent=%s loc=%s scale=%s" % (body.parent.name if body.parent else None,
                                              tuple(round(v, 3) for v in body.location),
                                              tuple(round(v, 3) for v in body.scale)))
print("### body modifiers:", [(m.type, getattr(m, 'object', None).name if getattr(m, 'object', None) else '') for m in body.modifiers])

dg = bpy.context.evaluated_depsgraph_get()
obe = body.evaluated_get(dg)
me = obe.to_mesh()
mw = obe.matrix_world
mn = [1e18] * 3
mx = [-1e18] * 3
pts = []
for v in me.vertices:
    w = mw @ v.co
    pts.append(w)
    for k in range(3):
        mn[k] = min(mn[k], w[k])
        mx[k] = max(mx[k], w[k])
print("### body world bbox min=%s max=%s" % (["%.3f" % v for v in mn], ["%.3f" % v for v in mx]))

# how are faces spread along y (to find the wheel arches / door gaps)?
buckets = {}
for poly in me.polygons:
    c = mw @ poly.center
    key = round(c.y, 1)
    buckets[key] = buckets.get(key, 0) + 1
print("### face count by y:", " ".join("%.1f:%d" % (k, buckets[k]) for k in sorted(buckets)))

# candidate pavement-side front door box (relative to the car's world bbox)
XSIDE = mx[0]
YFRONT = mx[1]
X0, X1 = XSIDE - 0.32, XSIDE + 0.03
YFRONT, YBACK = YFRONT - 0.72, YFRONT - 1.95
Z0, Z1 = 0.45, 1.62
n = 0
for poly in me.polygons:
    c = mw @ poly.center
    if X0 - 0.30 <= c.x <= X1 and YBACK <= c.y <= YFRONT and Z0 <= c.z <= Z1:
        n += 1
print("### candidate box x %.2f..%.2f y %.2f..%.2f z %.2f..%.2f selects %d of %d faces"
      % (X0 - 0.30, X1, YBACK, YFRONT, Z0, Z1, n, len(me.polygons)))
obe.to_mesh_clear()

cy = (mn[1] + mx[1]) / 2.0
shot('C:/temp/blender_previews/suv_side.png', (-0.5, cy, 1.15), (-8.3, cy, 0.95), lens=26)
shot('C:/temp/blender_previews/suv_34.png', (-1.0, cy - 5.0, 2.0), (-8.3, cy, 0.9), lens=26)
print("SUVP DONE")

### 54_probe_shop.py -- gather everything needed to wire the game into Shop_with_people.blend
import bpy, sys
from mathutils import Vector

FILE = "E:/Reality/ECO/Bussiness/Mall/MiniMarket/Shop_with_people.blend"
bpy.ops.wm.open_mainfile(filepath=FILE)

def P(*a):
    print(*a)

P("### scenes:", [(s.name, s.frame_start, s.frame_end, (s.camera.name if s.camera else None)) for s in bpy.data.scenes])
P("### current scene:", bpy.context.scene.name)
P("### cameras:", [o.name for o in bpy.data.objects if o.type == 'CAMERA'])
P("### lights:", [(o.name, o.type) for o in bpy.data.objects if o.type in ('LIGHT',)][:20])

def wbb(o):
    if o.type != 'MESH' or not o.data.vertices:
        return None
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx

# ---------- shop interior candidates ----------
rows = []
for o in bpy.data.objects:
    if o.type != 'MESH':
        continue
    bb = wbb(o)
    if not bb:
        continue
    mn, mx = bb
    c = (mn + mx) / 2.0
    if -4.5 < c.x < 8.0 and -9.0 < c.y < 9.0 and -0.6 < c.z < 4.5:
        rows.append((round(mx.z, 3), o.name, tuple(round(v, 2) for v in c),
                     tuple(round(v, 2) for v in mx), tuple(round(v, 2) for v in mn)))

P("### SHOP-REGION objects (top z, name, center, max, min) count=%d" % len(rows))
for r in sorted(rows)[:70]:
    P("   ", r)

# ---------- flat tops in the shop (possible shelf surfaces) ----------
tops = []
for ztop, name, c, mx, mn in rows:
    w = mx[0] - mn[0]
    d = mx[1] - mn[1]
    if 0.4 < ztop < 2.0 and w > 0.25 and d > 0.25:
        tops.append((ztop, name, c, mx, mn))
P("### flat tops 0.4<z<2.0 (shelf surfaces) count=%d" % len(tops))
for t in sorted(tops)[:40]:
    P("   ", t)

# ---------- storefront / door region ----------
P("### storefront region objects x in (-6.0,-3.5), z in (-0.4,3.2):")
for o in bpy.data.objects:
    bb = wbb(o)
    if not bb:
        continue
    mn, mx = bb
    c = (mn + mx) / 2.0
    if -6.0 < c.x < -3.5 and -0.4 < c.z < 3.2 and -9 < c.y < 9:
        P("    %-22s c=%s max=%s min=%s" % (o.name, tuple(round(v, 2) for v in c),
                                            tuple(round(v, 2) for v in mx), tuple(round(v, 2) for v in mn)))

# ---------- characters ----------
for nm in ("Boy1_RIG", "Boy2_RIG"):
    o = bpy.data.objects.get(nm)
    if not o:
        P("### MISSING", nm)
        continue
    ad = o.animation_data
    act = ad.action.name if (ad and ad.action) else None
    P("### %s loc=%s scale=%s action=%s" % (nm, tuple(round(v, 3) for v in o.location),
                                            tuple(round(v, 4) for v in o.scale), act))
    P("###   armature bones:", len(o.data.bones))
    P("###   NLA tracks:", [(t.name, [s.name for s in t.strips]) for t in (ad.nla_tracks if ad else [])])
    for b in ("DEF.hand.L", "DEF.hand.R", "hand.L", "IK.hand.L", "chest", "DEF.foot.L", "Root"):
        if b in o.pose.bones:
            pb = o.pose.bones[b]
            P("###   bone %-12s head_world=%s" % (b, tuple(round(v, 3) for v in (o.matrix_world @ pb.head))))

# ---------- props: any object already named like a product ----------
P("### objects whose names hint at shelves/products:")
import re
pat = re.compile(r"shelf|regal|rack|board|product|item|ware|box|bottle|can|stock", re.I)
hits = [o.name for o in bpy.data.objects if pat.search(o.name)]
P("   ", hits[:80], "total", len(hits))

# ---------- vehicles ----------
for nm in ("SUV_root", "TukTuk_root"):
    o = bpy.data.objects.get(nm)
    if not o:
        continue
    ad = o.animation_data
    P("### %s loc=%s rot=%s scale=%s action=%s" % (
        nm, tuple(round(v, 3) for v in o.location),
        tuple(round(v, 3) for v in o.rotation_euler), tuple(round(v, 4) for v in o.scale),
        ad.action.name if (ad and ad.action) else None))
    kids = [c.name for c in o.children]
    P("###   children(%d):" % len(kids), kids[:40])

# ---------- road / pavement ----------
for nm in ("Street_Road", "Street_Pavement", "Street_Kerb", "Street_Line"):
    o = bpy.data.objects.get(nm)
    if o:
        bb = wbb(o)
        P("### %s bbox=%s" % (nm, bb and (tuple(round(v, 2) for v in bb[0]), tuple(round(v, 2) for v in bb[1]))))
P("### road-ish objects:", [o.name for o in bpy.data.objects if o.name.startswith("Street")])

P("### collections:", [c.name for c in bpy.data.collections])
P("### actions (non-dup):", sorted([a.name for a in bpy.data.actions if "." not in a.name and not a.name.endswith("_src")]))
P("ACTIONS_TO_CLEAN:", sorted([a.name for a in bpy.data.actions if a.name.endswith("_src") or (a.name[-4:-1] == "." and a.name[-1].isdigit())]))
P("PROBE DONE")

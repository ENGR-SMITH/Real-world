### 55_wire_scene.py -- prepare Shop_with_people.blend for the game:
###   * back up the current file
###   * drop duplicate clip actions
###   * create the game camera + HUD text objects
###   * place pickable props on real shop surfaces (verified numerically)
### Run: UPBGE/blender.exe --background --factory-startup --python 55_wire_scene.py
import bpy, os, sys, shutil, math
from mathutils import Vector

FILE = "E:/Reality/ECO/Bussiness/Mall/MiniMarket/Shop_with_people.blend"
BACKUP = "E:/UPBGE/Shop_with_people.pregame.blend"

def P(*a):
    print(*a); sys.stdout.flush()

# ------------------------------------------------------------------ backup
if not os.path.exists(BACKUP):
    shutil.copy2(FILE, BACKUP)
    P("### backup made ->", BACKUP)
else:
    P("### backup already present ->", BACKUP)

bpy.ops.wm.open_mainfile(filepath=FILE)
sc = bpy.context.scene
P("### opened, objects=%d" % len(bpy.data.objects))

# ------------------------------------------------------------------ 1. clip actions
KEEP = ("walk", "idle", "reach", "sit")
doomed = []
for a in list(bpy.data.actions):
    base = a.name.split(".")[0].replace("_src", "")
    if base in KEEP and a.name not in KEEP and (a.name.endswith("_src") or (len(a.name) > 4 and a.name[-4] == "." and a.name[-3:].isdigit())):
        doomed.append(a)
for a in doomed:
    nm, n = a.name, a.users
    bpy.data.actions.remove(a)
    P("### removed dup action %-12s (users=%d)" % (nm, n))
for k in KEEP:
    if k in bpy.data.actions:
        bpy.data.actions[k].use_fake_user = True
for nm in ("Boy1_RIG", "Boy2_RIG"):
    o = bpy.data.objects[nm]
    if o.animation_data is None:
        o.animation_data_create()
    o.animation_data.action = bpy.data.actions["walk"]
P("### actions now:", len(bpy.data.actions))

# ------------------------------------------------------------------ 2. storefront probe
def bb(o):
    if o.type == 'MESH' and o.data.vertices:
        pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
        return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
                Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))
    return (Vector(o.matrix_world.translation), Vector(o.matrix_world.translation))

P("### STOREFRONT probe:")
for nm in ("Cube.390", "Cube.392", "Cube.393", "Cube.395", "Cube.398", "Plane.001",
           "Plane.009", "Shop_DoorFrame", "Shop_Door_L", "Shop_Door_R", "Cube.418"):
    o = bpy.data.objects.get(nm)
    if not o:
        P("###   %-16s MISSING" % nm); continue
    mn, mx = bb(o)
    P("###   %-16s min=%s max=%s" % (nm, tuple(round(v, 2) for v in mn), tuple(round(v, 2) for v in mx)))

# ------------------------------------------------------------------ 3. game camera
CAM = "Camera_Game"
cam = bpy.data.objects.get(CAM)
if cam is None:
    cd = bpy.data.cameras.new(CAM)
    cd.lens = 32.0
    cd.clip_start = 0.05
    cd.clip_end = 500.0
    cam = bpy.data.objects.new(CAM, cd)
    sc.collection.objects.link(cam)
    P("### created camera", CAM)
else:
    cam.data.lens = 32.0
    P("### camera exists", CAM)
cam.location = (-3.0, 6.0, 2.4)
cam.rotation_euler = (1.35, 0, 0)
cam.hide_render = False
cam.hide_viewport = False

# ------------------------------------------------------------------ 4. HUD
def unlit_material(name, rgba):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs[0].default_value = rgba
    em.inputs[1].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs[0])
    m.diffuse_color = rgba
    m.use_backface_culling = False
    for attr, val in (("use_shadeless", True), ("emit", 1.0), ("use_cast_shadows", False),
                      ("shadow_method", 'NONE')):
        if hasattr(m, attr):
            try:
                setattr(m, attr, val)
            except Exception:
                pass
    if hasattr(m, "game_settings"):
        P("###   material %s has game_settings: %s" % (name, sorted(dir(m.game_settings))))
    return m

P("### Material game-ish attrs present:", [a for a in dir(bpy.types.Material)
                                          if any(k in a for k in ("shade", "game", "shadow", "lum", "emit", "backface", "blend"))])

FONT = bpy.data.fonts[0] if len(bpy.data.fonts) else None
hud_mat = unlit_material("HUD_Text", (1.0, 1.0, 0.85, 1.0))

def make_hud(name, text, size, local_pos, align='LEFT'):
    o = bpy.data.objects.get(name)
    if o is None:
        cu = bpy.data.curves.new(name, type='FONT')
        o = bpy.data.objects.new(name, cu)
        sc.collection.objects.link(o)
    cu = o.data
    if FONT is not None:
        cu.font = FONT
    cu.body = text
    cu.size = size
    cu.align_x = align
    cu.align_y = 'TOP'
    cu.space_line = 1.1
    o.data.materials.clear()
    o.data.materials.append(hud_mat)
    o.hide_render = False
    o.hide_viewport = False
    o.parent = cam
    o.matrix_parent_inverse.identity()
    o.location = local_pos
    o.rotation_euler = (0, 0, 0)
    o.scale = (1, 1, 1)
    return o

# camera looks down its local -Z; 1.0 m in front is local (0,0,-1)
make_hud("HUD_Prompt", "", 0.055, (-0.47, 0.255, -1.0))
make_hud("HUD_Help", "", 0.030, (-0.47, 0.185, -1.0))
P("### HUD objects:", [o.name for o in bpy.data.objects if o.name.startswith("HUD_")])

# ------------------------------------------------------------------ 5. shelf props
# objects whose AABB is not usable as an occluder/blocker (glass volumes the door was cut through)
SKIP = ("Cube.395", "Cube.398", "Cube.418", "bmw27", "TukTuk", "Wheel", "Car")

def obj_bb(o):
    if o.type != 'MESH' or not o.data.vertices:
        return None
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))

# collect candidate flat tops inside the shop, reachable height, near the door
DOOR = Vector((-4.15, -2.0, 0))
cands = []
meshes = []
for o in bpy.data.objects:
    if o.type != 'MESH' or o.name.startswith("Boy") or o.name.startswith("HUD"):
        continue
    b = obj_bb(o)
    if b:
        meshes.append((o.name, b[0], b[1]))
        mn, mx = b
        c = (mn + mx) / 2.0
        if c.x > -4.2 and c.z >= 0.0:
            if 0.95 <= mx.z <= 1.35 and 0.20 < (mx.x - mn.x) < 0.62 and 0.20 < (mx.y - mn.y) < 0.62:
                cands.append((o.name, mn, mx))

# --- triangle-level geometry tests: the shop's boxes are hollow shells, so AABBs lie.
from mathutils.bvhtree import BVHTree

TREES = []
for o in bpy.data.objects:
    if o.type != 'MESH' or not o.data.polygons:
        continue
    if o.name.startswith(("Boy", "HUD", "Prop_", "shape_")):
        continue
    b = obj_bb(o)
    if not b:
        continue
    mn, mx = b
    if mx.x < -4.3 or mn.x > 8.0 or mx.y < -11.0 or mn.y > 8.0 or mn.z < -0.3 or mn.z > 5.0:
        continue
    mw = o.matrix_world
    verts = [mw @ v.co for v in o.data.vertices]
    polys = [tuple(p.vertices) for p in o.data.polygons]
    TREES.append((o.name, BVHTree.FromPolygons(verts, polys, all_triangles=False, epsilon=0.0)))
P("### built %d BVH trees for the shop region" % len(TREES))


def ray_hit(origin, direction, dist):
    best = (None, 1e9)
    for name, t in TREES:
        loc, nrm, idx, d = t.ray_cast(Vector(origin), Vector(direction), dist)
        if loc is not None and d < best[1]:
            best = (name, d)
    return best


def open_above(x, y, z, h=0.9):
    """True when a column above (x,y,z) is free of real geometry"""
    name, d = ray_hit((x, y, z), (0, 0, 1), h)
    return name is None, name, d


P("### candidates found: %d" % len(cands))
free = []
for name, mn, mx in cands:
    c = (mn + mx) / 2.0
    top = mx.z
    # the top of this box must be its own surface, with clear air above it
    clear, hitname, d = open_above(c.x, c.y, top + 0.02, 0.9)
    # and the box must still be there just below the probe
    bname, bd = ray_hit((c.x, c.y, top - 0.01), (0, 0, -1), 0.6)
    if clear and bname == name:
        free.append((name, c, top, mn, mx))
P("### open tops: %d" % len(free))
for f in free[:14]:
    P("###   open %-14s c=(%.2f, %.2f) top=%.3f  size=%.2f x %.2f" % (f[0], f[1].x, f[1].y, f[2],
                                                                      f[4].x - f[3].x, f[4].y - f[3].y))

P("### free tops: %d" % len(free))

# where can a character stand to reach each top? try the four cardinal facings.
REACH_FWD = 0.43      # how far in front of the rig origin the reach clip puts the hand
REACH_LEFT = 0.128    # and how far to the character's left
DIRS = [("W", Vector((-1, 0, 0)), -90.0), ("E", Vector((1, 0, 0)), 90.0),
        ("S", Vector((0, -1, 0)), 0.0), ("N", Vector((0, 1, 0)), 180.0)]


def approach_for(c):
    """return (stand_xy, yaw, facing) for the first cardinal direction with room"""
    for nm, d, yaw in DIRS:
        left = Vector((-d.y, d.x, 0))
        stand = Vector((c.x, c.y, 0)) - d * REACH_FWD - left * REACH_LEFT
        chest = Vector((stand.x, stand.y, 0.95))
        blocked = []
        for dd in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)):
            hn, hd = ray_hit(chest, dd, 0.24)
            if hn is not None:
                blocked.append(hn)
        fn, fd = ray_hit(Vector((stand.x, stand.y, 1.0)), (0, 0, -1), 1.3)
        if not blocked and fn is not None and fd > 0.85:
            return stand, yaw, nm, fn, fd
    return None

free.sort(key=lambda t: (Vector((t[1].x, t[1].y, 0)) - DOOR).length)
picked = []
for f in free:
    if not all((Vector((f[1].x, f[1].y, 0)) - Vector((g[1].x, g[1].y, 0))).length > 0.34 for g in picked):
        continue
    ap = approach_for(f[1])
    if ap is None:
        P("###   skip %-12s c=(%.2f, %.2f): no clear approach" % (f[0], f[1].x, f[1].y))
        continue
    stand, yaw, dname, fn, fd = ap
    P("###   take %-12s c=(%.2f, %.2f) top=%.3f  approach from %s  stand=(%.2f, %.2f) yaw=%.0f  floor=%s@%.2f"
      % (f[0], f[1].x, f[1].y, f[2], dname, stand.x, stand.y, yaw, fn, fd))
    picked.append((f[0], f[1], f[2], f[3], f[4], stand, yaw))
    if len(picked) >= 4:
        break
P("### picked %d tops" % len(picked))

COLORS = [(1.0, 0.25, 0.15, 1), (0.15, 0.45, 1.0, 1), (1.0, 0.8, 0.1, 1), (0.2, 0.85, 0.35, 1)]
shape_names = []
for i, (board, c, top, mn, mx, stand, yaw) in enumerate(picked):
    w, d, h = 0.11, 0.13, 0.17
    name = "Prop_Item_%d" % (i + 1)
    old = bpy.data.objects.get(name)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    me = bpy.data.meshes.new(name)
    vs = [(-w / 2, -d / 2, 0), (w / 2, -d / 2, 0), (w / 2, d / 2, 0), (-w / 2, d / 2, 0),
          (-w / 2, -d / 2, h), (w / 2, -d / 2, h), (w / 2, d / 2, h), (-w / 2, d / 2, h)]
    fs = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    me.from_pydata(vs, [], fs)
    me.update()
    mat = bpy.data.materials.get("Prop_Mat_%d" % (i + 1)) or bpy.data.materials.new("Prop_Mat_%d" % (i + 1))
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = COLORS[i % 4]
    mat.diffuse_color = COLORS[i % 4]
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    sc.collection.objects.link(ob)
    ob.location = (c.x, c.y, top)
    ob["on_shelf"] = board
    ob["stand_x"] = round(stand.x, 4)
    ob["stand_y"] = round(stand.y, 4)
    ob["yaw_deg"] = round(yaw, 2)
    shape_names.append(name)
    P("### prop %-12s at (%.3f, %.3f, %.3f) on %s" % (name, c.x, c.y, top, board))

# ---- verification, triangle level: the prop must rest on its board and touch nothing else
PW, PD, PH = 0.11, 0.13, 0.17
P("### PROP PLACEMENT CHECK (ray casts against real triangles)")
ok = True
for name in shape_names:
    ob = bpy.data.objects[name]
    c = Vector(ob.location)
    mid = c + Vector((0, 0, PH * 0.5))
    board = ob["on_shelf"]
    problems = []
    # nothing inside the prop volume (rays outward from the centre, half-extent + 1 mm)
    for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1)):
        half = (PW / 2 if d[0] else PD / 2 if d[1] else PH / 2)
        hn, hd = ray_hit(mid, d, half + 0.02)
        if hn is not None:
            problems.append("%s@%.2f" % (hn, hd))
    # the board must be directly under the base
    bn, bd = ray_hit(c + Vector((0, 0, 0.005)), (0, 0, -1), 0.2)
    P("###   %-12s on=%-12s support=%s d=%.3f  intrusions=%s" % (
        name, board, bn, (bd if bn else -1), problems or "none"))
    if problems or bn not in (board, None):
        ok = False

# ---- does the reach pose actually put the hand on the prop?
P("### REACH CHECK (hand position from the authored reach clip)")
import math as _math
for name in shape_names:
    ob = bpy.data.objects[name]
    yaw = _math.radians(ob["yaw_deg"])
    fwd = Vector((_math.sin(yaw), -_math.cos(yaw), 0))
    left = Vector((-fwd.y, fwd.x, 0))
    origin = Vector((ob["stand_x"], ob["stand_y"], 0.063))
    hand = origin + fwd * REACH_FWD + left * REACH_LEFT
    hand.z = 0.063 + 1.067
    gap = Vector((ob.location.x, ob.location.y, ob.location.z + PH * 0.5)) - hand
    P("###   %-12s hand=(%.2f, %.2f, %.2f) prop=(%.2f, %.2f, %.2f) gap=%.3f m" % (
        name, hand.x, hand.y, hand.z, ob.location.x, ob.location.y, ob.location.z + PH * 0.5, gap.length))

P("### placement ok =", ok)

# ------------------------------------------------------------------ 6. scene/render settings
sc.render.resolution_x = 1280
sc.render.resolution_y = 720
sc.render.resolution_percentage = 100
sc.frame_start = 1
sc.frame_end = 240
sc.camera = cam
sc["__main__"] = "game.py"
sc.game_settings.use_frame_rate = True
sc.render.fps = 60
P("### scene camera -> %s, %dx%d, __main__=%r" % (cam.name, sc.render.resolution_x,
                                                   sc.render.resolution_y, sc.get("__main__")))

bpy.ops.wm.save_mainfile()
P("### saved", bpy.data.filepath)
P("WIRE DONE")

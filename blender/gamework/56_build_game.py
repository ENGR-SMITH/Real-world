"""Generate the game's world data, build the HUD, and install game.py into the blend.

Everything the game needs to know about the scene is measured here and written into
the WORLD block of game.py, so the running game never guesses:

  * walkable regions, taken from the real pavement / road / shop floor meshes
  * blocker rectangles, taken from real object bounds
  * clip frame ranges, taken from the actions
  * shelf stand spots, taken from the properties 55_wire_scene.py put on the props
  * vehicle lane / cabin / door data

It finishes with a breadth first search over its own collision model, which proves a
boy can actually walk from the pavement, through the doorway, to every shelf.

Run: UPBGE/blender.exe --background --factory-startup --python 56_build_game.py
"""
import bpy
import math
import os
import re
import sys
from mathutils import Vector

FILE = "E:/Reality/ECO/Bussiness/Mall/MiniMarket/Shop_with_people.blend"
GAME_PY = "E:/Reality/blender/gamework/game.py"


def P(*a):
    print(*a)
    sys.stdout.flush()


bpy.ops.wm.open_mainfile(filepath=FILE)
bpy.context.scene.frame_set(1)
sc = bpy.context.scene


def wbb(o):
    if o.type != 'MESH' or not o.data.vertices:
        return None
    mw = o.matrix_world
    pts = [mw @ v.co for v in o.data.vertices]
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


def flat_bb(o):
    if o.type != 'MESH':
        return None
    mw = o.matrix_world
    bb = [mw @ Vector(c) for c in o.bound_box]
    return (Vector((min(p.x for p in bb), min(p.y for p in bb), min(p.z for p in bb))),
            Vector((max(p.x for p in bb), max(p.y for p in bb), max(p.z for p in bb))))


# ------------------------------------------------------------------ 1. ground regions
def flat_of(name, shrink=0.02):
    o = bpy.data.objects[name]
    mn, mx = flat_bb(o)
    return [round(mn.x + shrink, 3), round(mn.y + shrink, 3), round(mx.x - shrink, 3),
            round(mx.y - shrink, 3), round(mx.z, 3)]


shop = flat_of('Plane.001')
pave = flat_of('Street_Pavement')
road = flat_of('Street_Road')
shop[0] = -4.05                     # keep clear of the storefront band
pave[2] = -4.30
regions = [["door", -4.30, -2.95, -4.05, -1.05, 0.05],
           ["shop", shop[0], shop[1], shop[2], shop[3], shop[4]],
           ["pave", pave[0], pave[1], pave[2], pave[3], pave[4]],
           ["road", road[0], road[1], road[2], road[3], road[4]]]
P("### regions:")
for r in regions:
    P("###   ", r)

wall = [-4.30, -4.05]
doorway = [-2.95, -1.05]

# ------------------------------------------------------------------ 2. blockers
SKIP_PREFIX = ("Boy", "HUD_", "P_", "Prop_", "Shop_Door", "SUV", "bmw27", "TukTuk",
               "Wheel", "Car", "shape_", "WGT", "Camera")
SKIP_EXACT = {"Cube.395", "Cube.398", "Cube.418"}

blockers = []
for o in bpy.data.objects:
    if o.type != 'MESH' or not o.data.vertices:
        continue
    if o.name.startswith(SKIP_PREFIX) or o.name in SKIP_EXACT:
        continue
    b = flat_bb(o)
    if b is None:
        continue
    mn, mx = b
    if mx.z <= 0.70 or mn.z >= 1.50:
        continue                                     # too low to matter / overhead
    if mx.x < road[0] - 0.5 or mn.x > shop[2] + 0.5 or mx.y < -20 or mn.y > 20:
        continue
    w, d = mx.x - mn.x, mx.y - mn.y
    if w * d < 0.04:
        continue
    blockers.append([round(mn.x, 3), round(mn.y, 3), round(mx.x, 3), round(mx.y, 3)])
blockers = sorted(set(map(tuple, blockers)))
blockers = [list(b) for b in blockers]
P("### blockers: %d rects" % len(blockers))

# ------------------------------------------------------------------ 3. clips
clips = {}
for name in ("walk", "idle", "reach", "sit"):
    a = bpy.data.actions.get(name)
    if a is None:
        P("### MISSING CLIP", name)
        continue
    fr = a.frame_range
    clips[name] = [int(round(fr[0])), int(round(fr[1]))]
P("### clips:", clips)

# ------------------------------------------------------------------ 4. props
props = {}
for o in bpy.data.objects:
    if not o.name.startswith("Prop_Item_"):
        continue
    props[o.name] = {"stand": [round(o["stand_x"], 3), round(o["stand_y"], 3)],
                     "yaw": round(math.radians(o["yaw_deg"]), 4)}
    P("### prop %-12s at %s  stand=%s yaw=%.1f deg" % (
        o.name, tuple(round(v, 3) for v in o.location), props[o.name]["stand"],
        o["yaw_deg"]))

# the stand spot has to satisfy the game's own collision rule -- 55_wire_scene.py only
# checked chest-height clearance, which leaves the boy wedged against the shelf edge
PLAYER_R = 0.20
REACH_LEFT = 0.128


def stand_ok(x, y, r=PLAYER_R):
    z = None
    for rr in regions:
        if rr[1] <= x <= rr[3] and rr[2] <= y <= rr[4]:
            z = rr[5]
            break
    if z is None:
        return False
    for b in blockers:
        if b[0] - r < x < b[2] + r and b[1] - r < y < b[3] + r:
            return False
    if wall[0] - r < x < wall[1] + r:
        if not (doorway[0] + r * 0.5 <= y <= doorway[1] - r * 0.5):
            return False
    return True


P("### STAND SPOT CHECK (game collision model, radius %.2f)" % PLAYER_R)
for name in sorted(props):
    p = props[name]
    ob = bpy.data.objects[name]
    c = Vector(ob.location)
    yaw = p["yaw"]
    d = Vector((math.sin(yaw), -math.cos(yaw), 0.0))
    left = Vector((-d.y, d.x, 0.0))
    if stand_ok(p["stand"][0], p["stand"][1]):
        P("###   %-12s ok at %s (%.2f m away)" % (
            name, p["stand"], math.hypot(p["stand"][0] - c.x, p["stand"][1] - c.y)))
        continue
    fixed = None
    for dist in (0.55, 0.68, 0.82, 0.95, 1.10, 1.25):
        cand = Vector((c.x, c.y, 0)) - d * dist - left * REACH_LEFT
        if stand_ok(cand.x, cand.y):
            fixed = (cand, dist)
            break
    if fixed is None:
        P("###   %-12s STILL BLOCKED, no clear stand spot along its facing" % name)
        continue
    cand, dist = fixed
    P("###   %-12s was blocked at %s -> moved out to (%.3f, %.3f), %.2f m from the item" % (
        name, p["stand"], cand.x, cand.y, math.hypot(cand.x - c.x, cand.y - c.y)))
    p["stand"] = [round(cand.x, 3), round(cand.y, 3)]
    ob["stand_x"] = round(cand.x, 4)
    ob["stand_y"] = round(cand.y, 4)

# ------------------------------------------------------------------ 5. door swing sign
def swing_sign(name, angle=96.0):
    o = bpy.data.objects[name]
    base = o.rotation_euler.copy()
    best = None
    for sign in (1.0, -1.0):
        e = base.copy()
        e.z = base.z + math.radians(angle) * sign
        o.rotation_euler = e
        bpy.context.view_layer.update()
        mn, mx = flat_bb(o)
        # inward is +x: the leaf should end up deeper inside the shop
        score = mx.x - mn.x
        if best is None or mx.x > best[1]:
            best = (sign, mx.x, mx.z)
        o.rotation_euler = base
        bpy.context.view_layer.update()
    return best[0]


shop_doors = []
for nm in ("Shop_Door_L", "Shop_Door_R"):
    if nm in bpy.data.objects:
        s = swing_sign(nm)
        shop_doors.append([nm, s])
        P("### %s swing sign %+.0f" % (nm, s))

# ------------------------------------------------------------------ 6. vehicles
def descendants(root):
    """every object below root, however deep -- the SUV body hangs off its armature"""
    out = []
    stack = list(root.children)
    while stack:
        o = stack.pop()
        out.append(o)
        stack.extend(o.children)
    return out


def children_bbox(root):
    mn = Vector((1e18, 1e18, 1e18))
    mx = Vector((-1e18, -1e18, -1e18))
    n = 0
    for o in descendants(root):
        if o.type != 'MESH':
            continue
        b = flat_bb(o)
        if b is None:
            continue
        n += 1
        mn = Vector((min(mn.x, b[0].x), min(mn.y, b[0].y), min(mn.z, b[0].z)))
        mx = Vector((max(mx.x, b[1].x), max(mx.y, b[1].y), max(mx.z, b[1].z)))
    return mn, mx, n


vehicles = {}
for nm in ("SUV_root", "TukTuk_root"):
    root = bpy.data.objects.get(nm)
    if root is None:
        continue
    mn, mx, nkids = children_bbox(root)
    P("### %s: %d mesh parts" % (nm, nkids))
    yaw = math.atan2(math.sin(root.rotation_euler.z), math.cos(root.rotation_euler.z))
    # car forward is local -Y
    fwd = Vector((math.sin(yaw), -math.cos(yaw), 0.0))
    right = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    rel = Vector(((mn + mx) / 2.0) - Vector(root.location))
    body_fwd = rel.dot(fwd)
    body_left = rel.dot(right)
    length = (mx.y - mn.y) if abs(fwd.y) > 0.5 else (mx.x - mn.x)
    width = (mx.x - mn.x) if abs(fwd.y) > 0.5 else (mx.y - mn.y)
    road_lo = road[0] + width * 0.5 + 0.15
    road_hi = road[2] - width * 0.5 - 0.15
    data = {
        "yaw": round(yaw, 4),
        "lane": round(root.location.x if abs(fwd.y) > 0.5 else root.location.y, 3),
        "cruise": 6.0 if nm == "SUV_root" else 4.2,
        "road": [round(road_lo, 3), round(road_hi, 3)],
        "wrap": [-19.0, 19.0],
        "width": round(width, 3),
        "length": round(length, 3),
        "body_fwd": round(body_fwd, 3),
        "reach": round(max(3.6, length * 0.55 + 1.2), 2),
        "getout_side": -1.0 if body_left < 0 else 1.0,
        "tuktuk": nm == "TukTuk_root",
        "door_angle": 48.0,
    }
    if nm == "SUV_root" and "SUV_Door_FR" in bpy.data.objects:
        data["door"] = bpy.data.objects["SUV_Door_FR"]
    else:
        data["door"] = None
    # seat: on the door side, about a third of the way in from the near flank
    door_off = -1.0 if nm == "SUV_root" else 1.0
    fwd_off = body_fwd + (0.45 if nm == "SUV_root" else 0.0)
    seat_up = round(0.39 - root.location.z, 3) if nm == "SUV_root" else round(
        (mn.z + 0.72) - root.location.z + 0.30, 3)
    data["seat"] = [round(fwd_off, 3), round(width * 0.16 * door_off, 3), seat_up]
    data["getout_side"] = door_off
    vehicles[nm] = data
    P("### vehicle %-12s bbox %s %s" % (nm, tuple(round(v, 2) for v in mn), tuple(round(v, 2) for v in mx)))
    P("###    %s" % (data,))

# ------------------------------------------------------------------ 7. HUD
def unlit(name, rgba, strength=1.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs[0].default_value = rgba
    em.inputs[1].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs[0])
    m.diffuse_color = rgba
    return m


cam = bpy.data.objects["Camera_Game"]
cam.data.lens = 32.0
hud_mat = unlit("HUD_Text", (1.0, 1.0, 0.9, 1.0))
FONT = bpy.data.fonts.get("Bfont Regular")

TEXTS = [
    ("HUD_Help", "WASD walk    SHIFT hurry    E action    TAB swap boy    ESC quit", 0.030, (-0.47, -0.278, -1.0)),
    ("HUD_Title1", "playing: Boy 1  (blue shirt)", 0.030, (-0.47, -0.238, -1.0)),
    ("HUD_Title2", "playing: Boy 2  (white shirt)", 0.030, (-0.47, -0.238, -1.0)),
    ("HUD_Carry", "carrying an item -- E to put it down", 0.030, (-0.47, -0.198, -1.0)),
    ("P_DoorOpen", "E   open the shop door", 0.042, (-0.47, 0.268, -1.0)),
    ("P_DoorClose", "E   close the shop door", 0.042, (-0.47, 0.268, -1.0)),
    ("P_Take", "E   take the item off the shelf", 0.042, (-0.47, 0.268, -1.0)),
    ("P_Drop", "E   put the item down", 0.042, (-0.47, 0.268, -1.0)),
    ("P_BusStop", "E   signal the vehicle to stop", 0.042, (-0.47, 0.268, -1.0)),
    ("P_VehDoor", "E   open the vehicle door", 0.042, (-0.47, 0.268, -1.0)),
    ("P_VehEnter", "E   get in and drive", 0.042, (-0.47, 0.268, -1.0)),
    ("P_TukEnter", "E   get into the tuk tuk", 0.042, (-0.47, 0.268, -1.0)),
    ("P_Drive", "W / S  throttle     A / D  steer        E   stop and get out", 0.042, (-0.47, 0.268, -1.0)),
]

for nm, body, size, loc in TEXTS:
    o = bpy.data.objects.get(nm)
    if o is None:
        cu = bpy.data.curves.new(nm, type='FONT')
        o = bpy.data.objects.new(nm, cu)
        sc.collection.objects.link(o)
    cu = o.data
    if FONT is not None:
        cu.font = FONT
    cu.body = body
    cu.size = size
    cu.align_x = 'LEFT'
    cu.align_y = 'TOP'
    o.data.materials.clear()
    o.data.materials.append(hud_mat)
    o.parent = cam
    o.matrix_parent_inverse.identity()
    o.location = loc
    o.rotation_euler = (0, 0, 0)
    o.scale = (1, 1, 1)
    o.hide_viewport = False
    o.hide_render = False
    o.visible_camera = True
for nm in ("HUD_Prompt",):
    o = bpy.data.objects.get(nm)
    if o:
        bpy.data.objects.remove(o, do_unlink=True)
P("### hud objects:", sorted(o.name for o in bpy.data.objects if o.name.startswith(("HUD_", "P_"))))

# ------------------------------------------------------------------ 8. write game.py
world = {
    "regions": regions,
    "wall": wall,
    "doorway": doorway,
    "blockers": blockers,
    "clips": clips,
    "props": props,
    "vehicles": {k: {kk: (vv if not hasattr(vv, "name") else vv.name) for kk, vv in v.items()}
                 for k, v in vehicles.items()},
    "shop_doors": shop_doors,
    "shop_door_angle": 96.0,
    "shop_door_centre": [-4.15, -2.0],
}
src = open(GAME_PY, "r", encoding="utf-8").read()
block = "# >>> WORLD_DATA\nWORLD = " + repr(world) + "\n# <<< WORLD_DATA\n"


def fmt(v, indent=0):
    return repr(v)


pretty = "{\n"
for k, v in world.items():
    pretty += "    %r: %s,\n" % (k, repr(v))
pretty += "}"
block = "# >>> WORLD_DATA\nWORLD = " + pretty + "\n# <<< WORLD_DATA\n"

for marker in ("# >>> WORLD_DATA", "# <<< WORLD_DATA"):
    if marker not in src:
        raise SystemExit("### could not find %r in game.py" % marker)
new = re.sub(r"# >>> WORLD_DATA.*?# <<< WORLD_DATA\n", block, src, flags=re.S)
if "# <<< WORLD_DATA" not in new:
    raise SystemExit("### the WORLD_DATA substitution did not take")
open(GAME_PY, "w", encoding="utf-8").write(new)
P("### game.py regenerated (%d chars, world data %d chars)" % (len(new), len(pretty)))

t = bpy.data.texts.get("game.py")
if t is None:
    t = bpy.data.texts.new("game.py")
t.clear()
t.write(new)
t.use_module = True
P("### installed as text block 'game.py'")

# ------------------------------------------------------------------ 9. game readiness
sc["__main__"] = "game.py"
sc.game_settings.use_frame_rate = True
sc.render.fps = 60
sc.render.resolution_x = 1280
sc.render.resolution_y = 720
sc.render.resolution_percentage = 100
sc.camera = cam
P("### scene fps=%d use_frame_rate=%s __main__=%r camera=%s" % (
    sc.render.fps, sc.game_settings.use_frame_rate, sc.get("__main__"), cam.name))

# ------------------------------------------------------------------ 10. reachability
try:
    import numpy as np
    STEP = 0.10
    x0, x1 = road[0] - 0.3, shop[2] + 0.3
    y0, y1 = -19.8, 19.8
    nx = int((x1 - x0) / STEP) + 1
    ny = int((y1 - y0) / STEP) + 1
    xs = np.array([x0 + i * STEP for i in range(nx)])
    ys = np.array([y0 + j * STEP for j in range(ny)])

    def grid_blocked(r):
        gx, gy = np.meshgrid(xs, ys, indexing='ij')
        g = np.zeros((nx, ny), bool)
        for b in blockers:
            g |= (b[0] - r < gx) & (gx < b[2] + r) & (b[1] - r < gy) & (gy < b[3] + r)
        # storefront band, opening only when the doors are open
        band = (wall[0] - r < gx) & (gx < wall[1] + r)
        opening = (doorway[0] + r * 0.5 <= gy) & (gy <= doorway[1] - r * 0.5)
        g |= band & ~opening
        reg = np.zeros((nx, ny), bool)
        for rr in regions:
            reg |= (rr[1] <= gx) & (gx <= rr[3]) & (rr[2] <= gy) & (gy <= rr[4])
        return reg & ~g

    from collections import deque

    def reach(grid, start, goal, r=0.20):
        si = (int((start[0] - x0) / STEP), int((start[1] - y0) / STEP))
        gi = (int((goal[0] - x0) / STEP), int((goal[1] - y0) / STEP))
        si = (max(0, min(nx - 1, si[0])), max(0, min(ny - 1, si[1])))
        gi = (max(0, min(nx - 1, gi[0])), max(0, min(ny - 1, gi[1])))
        if not grid[si]:
            best, bd = None, 1e9
            ii, jj = np.nonzero(grid)
            if len(ii) == 0:
                return -1
            k = np.argmin((xs[ii] - start[0]) ** 2 + (ys[jj] - start[1]) ** 2)
            si = (ii[k], jj[k])
        if not grid[gi]:
            best, bd = None, 1e9
            ii, jj = np.nonzero(grid)
            k = np.argmin((xs[ii] - goal[0]) ** 2 + (ys[jj] - goal[1]) ** 2)
            gi = (ii[k], jj[k])
            P("###   (goal snapped to the nearest free cell)")
        dist = -np.ones((nx, ny), np.int32)
        dist[si] = 0
        q = deque([si])
        while q:
            i, j = q.popleft()
            if (i, j) == gi:
                return dist[i, j]
            d = dist[i, j] + 1
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                a, b2 = i + di, j + dj
                if 0 <= a < nx and 0 <= b2 < ny and grid[a, b2] and dist[a, b2] < 0:
                    dist[a, b2] = d
                    q.append((a, b2))
        return -1

    GO = grid_blocked(0.20)
    P("### reachability (cell = %.2f m, door OPEN), from the pavement in front of the shop" % STEP)
    start = (-5.0, -2.0)
    for name, goal in [("door passage", (-4.17, -2.0)),
                       ("shop centre", (0.0, 0.0))] + \
                      [(k, tuple(v["stand"])) for k, v in props.items()] + \
                      [("SUV lane", (vehicles.get("SUV_root", {}).get("lane", -8.26), 6.0))]:
        d = reach(GO, start, goal)
        P("###   %-14s %s  -> %s" % (name, tuple(round(c, 2) for c in goal),
                                     ("%.1f m" % (d * STEP)) if d >= 0 else "UNREACHABLE"))
    closed = grid_blocked(0.20)
    # rebuild with the doors shut
    gx, gy = np.meshgrid(xs, ys, indexing='ij')
    band = (wall[0] - 0.20 < gx) & (gx < wall[1] + 0.20)
    reg = np.zeros((nx, ny), bool)
    for rr in regions:
        reg |= (rr[1] <= gx) & (gx <= rr[3]) & (rr[2] <= gy) & (gy <= rr[4])
    g2 = np.zeros((nx, ny), bool)
    for b in blockers:
        g2 |= (b[0] - 0.20 < gx) & (gx < b[2] + 0.20) & (b[1] - 0.20 < gy) & (gy < b[3] + 0.20)
    SHUT = reg & ~(g2 | band)
    d = reach(SHUT, start, (0.0, 0.0))
    P("###   with the door SHUT, the shop is %s" % ("still reachable (!)" if d >= 0 else "sealed off, as intended"))
except ImportError:
    P("### numpy missing, skipped the reachability check")

bpy.ops.wm.save_mainfile()
P("### saved", bpy.data.filepath)
P("BUILD GAME DONE")

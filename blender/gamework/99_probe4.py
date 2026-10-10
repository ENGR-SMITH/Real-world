"""99_probe4.py -- what surfaces exist near the shop counter? (read only, no save)

    blender.exe --background Shop_with_people.blend --python 99_probe4.py
"""
import math
import sys
from collections import deque

import bpy
import numpy as np
from mathutils import Vector

GAME = r"E:/Reality/blender/gamework/game.py"
STEP = 0.05
R = 0.075          # half footprint of a prop item
H = 0.22           # how tall the item sticks up


def P(*a):
    print("###", *a)
    sys.stdout.flush()


# ---------------------------------------------------------------- world model
src = open(GAME, "r", encoding="utf-8").read()
head = src.split("# ================================================================== engine")[0]
ns = {"__name__": "game_head"}
exec(compile(head, "game_head", "exec"), ns)
WORLD = ns["WORLD"]
r = ns["PLAYER_R"]
REGIONS = WORLD["regions"]
BLOCKERS = WORLD["blockers"]
WALL = WORLD["wall"]
DOORWAY = WORLD["doorway"]

x0 = min(g[1] for g in REGIONS)
y0 = min(g[2] for g in REGIONS)
x1 = max(g[3] for g in REGIONS)
y1 = max(g[4] for g in REGIONS)
xs = np.arange(x0, x1 + STEP * 0.5, STEP)
ys = np.arange(y0, y1 + STEP * 0.5, STEP)
NX, NY = len(xs), len(ys)
X = xs[:, None]
Y = ys[None, :]
free = np.zeros((NX, NY), dtype=bool)
for g in REGIONS:
    free |= (X >= g[1]) & (X <= g[3]) & (Y >= g[2]) & (Y <= g[4])
blk = np.zeros((NX, NY), dtype=bool)
for b in BLOCKERS:
    blk |= (X > b[0] - r) & (X < b[2] + r) & (Y > b[1] - r) & (Y < b[3] + r)
free &= ~blk
free &= ~((X > WALL[0] - r) & (X < WALL[1] + r)
          & ~((Y >= DOORWAY[0] + r * 0.5) & (Y <= DOORWAY[1] - r * 0.5)))

boy = bpy.data.objects["Boy1_RIG"]
si = int(round((boy.matrix_world.translation.x - x0) / STEP))
sj = int(round((boy.matrix_world.translation.y - y0) / STEP))
reach = np.zeros_like(free)
q = deque([(si, sj)])
reach[si, sj] = True
while q:
    i, j = q.popleft()
    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ni, nj = i + di, j + dj
        if 0 <= ni < NX and 0 <= nj < NY and free[ni, nj] and not reach[ni, nj]:
            reach[ni, nj] = True
            q.append((ni, nj))
P("walkable cells %d, reachable %d" % (int(free.sum()), int(reach.sum())))

# ---------------------------------------------------------------- geometry
boxes = {}          # name -> (minx,miny,minz, maxx,maxy,maxz)
for o in bpy.data.objects:
    if o.type not in ("MESH", "CURVE", "FONT", "SURFACE"):
        continue
    mn = [1e9] * 3
    mx = [-1e9] * 3
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for k in range(3):
            mn[k] = min(mn[k], w[k])
            mx[k] = max(mx[k], w[k])
    if mx[0] - mn[0] > 60 or mx[1] - mn[1] > 60:
        continue                     # ground planes / backdrop
    boxes[o.name] = (mn[0], mn[1], mn[2], mx[0], mx[1], mx[2])
P("bounding boxes collected: %d" % len(boxes))


def surface_under(x, y, r=R):
    """highest solid top (<=1.45) whose footprint covers the whole item base"""
    best = None
    for name, b in boxes.items():
        if b[0] <= x - r and b[3] >= x + r and b[1] <= y - r and b[4] >= y + r:
            if 0.80 <= b[5] <= 1.45 and (best is None or b[5] > best[0]):
                best = (b[5], name)
    return best


def clear(x, y, ztop, r=R):
    """nothing else occupies the item's box, and nothing hangs over it"""
    for name, b in boxes.items():
        if name.startswith("Prop_Item_"):
            continue
        if b[3] <= x - r or b[0] >= x + r or b[4] <= y - r or b[1] >= y + r:
            continue
        if b[5] > ztop + 0.008 and b[2] < ztop + H + 0.35:
            return name
    return None

props = [o for o in bpy.data.objects if o.name.startswith("Prop_Item_")]
for o in sorted(props, key=lambda o: o.name):
    t = o.matrix_world.translation
    mn = boxes[o.name]
    P("%-13s origin (%.3f, %.3f, %.3f)  bbox x[%.3f,%.3f] y[%.3f,%.3f] z[%.3f,%.3f]" % (
        o.name, t.x, t.y, t.z, mn[0], mn[3], mn[1], mn[4], mn[2], mn[5]))
    under = []
    for name, b in boxes.items():
        if name == o.name:
            continue
        if b[0] - 0.02 <= t.x <= b[3] + 0.02 and b[1] - 0.02 <= t.y <= b[4] + 0.02 and b[5] <= mn[2] + 0.03:
            under.append((b[5], name))
    under.sort(reverse=True)
    for ztop, name in under[:3]:
        P("      rests on %-28s top z=%.3f" % (name, ztop))

# ---------------------------------------------------------------- surfaces
# ---------------------------------------------------------------- candidates
other = [(o.name, o.matrix_world.translation.copy()) for o in props if o.name != "Prop_Item_4"]
cands = []
for cx in np.arange(-0.60, 0.6001, 0.03):
    for cy in np.arange(-4.90, -3.4001, 0.03):
        cx = float(round(cx, 3))
        cy = float(round(cy, 3))
        if min(math.hypot(cx - t.x, cy - t.y) for _, t in other) < 0.28:
            continue
        surf = surface_under(cx, cy)
        if surf is None:
            continue
        ztop, sname = surf
        bad = clear(cx, cy, ztop)
        if bad is not None:
            continue
        d2 = np.where(reach, (X - cx) ** 2 + (Y - cy) ** 2, np.inf)
        k = int(np.argmin(d2))
        i, j = np.unravel_index(k, d2.shape)
        d = math.sqrt(float(d2[i, j]))
        if d >= 1.30:
            continue
        move = math.hypot(cx - 0.443, cy + 3.908)
        cands.append((d, move, cx, cy, ztop, sname))

cands.sort()
P("feasible candidates (x,y): %d" % len(cands))
P("-- best 12 by pick-up distance --")
for d, move, cx, cy, ztop, sname in cands[:12]:
    P("   (%.2f, %.2f)  d=%.3f  surface=%-26s top=%.3f  built-in moves %.2f m" % (
        cx, cy, d, sname, ztop, move))
print()
if cands:
    near = sorted(cands, key=lambda c: c[1])[:8]
    P("-- 8 candidates closest to the item's current spot --")
    for d, move, cx, cy, ztop, sname in near:
        P("   (%.2f, %.2f) d=%.3f surface=%-26s top=%.3f moves %.2f m" % (cx, cy, d, sname, ztop, move))

P("-- objects at counter height (top z 0.85..1.45) in x[-1.2,1.4] y[-5.4,-3.2] --")
for name in sorted(boxes):
    b = boxes[name]
    if name.startswith("Prop_Item_"):
        continue
    if not (0.85 <= b[5] <= 1.45):
        continue
    if b[3] < -1.2 or b[0] > 1.4 or b[4] < -5.4 or b[1] > -3.2:
        continue
    P("   %-30s x[%7.3f,%7.3f] y[%7.3f,%7.3f] z[%6.3f,%6.3f]" % (name, b[0], b[3], b[1], b[4], b[2], b[5]))

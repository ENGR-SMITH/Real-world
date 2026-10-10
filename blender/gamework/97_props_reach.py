"""97_props_reach.py -- does every shelf prop have a REACHABLE stand spot?

Runs in the UPBGE build (background): opens the deliverable, pulls the world model
straight out of game.py (the part above `# ===== engine =====`), rasterises it,
BFS-floods the walkable area from the first boy's spawn, then asks, for each
Prop_Item_*, whether any cell that the player can actually walk to is inside the
game's own pick-up range (prop_dist < 1.45 m).

    blender.exe --background Shop_with_people.blend --python 97_props_reach.py
"""
import math
import sys
from collections import deque

import bpy
import numpy as np

GAME = r"E:/Reality/blender/gamework/game.py"
PICK_RANGE = 1.70          # must match game.py's TAKE_RANGE
STEP = 0.06


def P(*a):
    print("###", *a)
    sys.stdout.flush()


# ---------------------------------------------------------------- world model
src = open(GAME, "r", encoding="utf-8").read()
head = src.split("# ================================================================== engine")[0]
ns = {"__name__": "game_head"}
exec(compile(head, "game_head", "exec"), ns)
WORLD = ns["WORLD"]
can_stand = ns["can_stand"]
PLAYER_R = ns["PLAYER_R"]
REGIONS = WORLD["regions"]
BLOCKERS = WORLD["blockers"]
WALL = WORLD["wall"]
DOORWAY = WORLD["doorway"]
r = PLAYER_R

# ---------------------------------------------------------------- grid + free
x0 = min(g[1] for g in REGIONS)
x1 = max(g[3] for g in REGIONS)
y0 = min(g[2] for g in REGIONS)
y1 = max(g[4] for g in REGIONS)
xs = np.arange(x0, x1 + STEP * 0.5, STEP)
ys = np.arange(y0, y1 + STEP * 0.5, STEP)
NX, NY = len(xs), len(ys)
X = xs[:, None]
Y = ys[None, :]
P("grid %d x %d cells at %.2f m over x[%.2f,%.2f] y[%.2f,%.2f]" % (NX, NY, STEP, x0, x1, y0, y1))

free = np.zeros((NX, NY), dtype=bool)
for g in REGIONS:
    free |= (X >= g[1]) & (X <= g[3]) & (Y >= g[2]) & (Y <= g[4])
P("floor cells: %d" % int(free.sum()))

n = 0
for b in BLOCKERS:
    m = (X > b[0] - r) & (X < b[2] + r) & (Y > b[1] - r) & (Y < b[3] + r)
    if m.any():
        free &= ~m
        n += 1
P("blockers applied: %d" % n)

wall = (X > WALL[0] - r) & (X < WALL[1] + r) & ~((Y >= DOORWAY[0] + r * 0.5) & (Y <= DOORWAY[1] - r * 0.5))
free &= ~wall
P("walkable cells (doors open): %d" % int(free.sum()))

# sanity: the rasteriser must agree with can_stand on a sample
bad = 0
for i in range(0, NX, 7):
    for j in range(0, NY, 7):
        want = can_stand(float(xs[i]), float(ys[j]), r, True)
        if want != bool(free[i, j]):
            bad += 1
P("raster vs can_stand disagreements on sampled cells: %d" % bad)

# ---------------------------------------------------------------- BFS from spawn
spawn = None
ob = bpy.data.objects.get("Boy1_RIG")
if ob is not None:
    spawn = (ob.matrix_world.translation.x, ob.matrix_world.translation.y)
P("spawn (Boy1_RIG):", spawn)


def cell_of(x, y):
    i = int(round((x - x0) / STEP))
    j = int(round((y - y0) / STEP))
    return (max(0, min(NX - 1, i)), max(0, min(NY - 1, j)))


si, sj = cell_of(*spawn)
if not free[si, sj]:
    best = None
    for di in range(-8, 9):
        for dj in range(-8, 9):
            i, j = si + di, sj + dj
            if 0 <= i < NX and 0 <= j < NY and free[i, j]:
                d = di * di + dj * dj
                if best is None or d < best[0]:
                    best = (d, i, j)
    if best is not None:
        si, sj = best[1], best[2]
P("spawn snapped to cell (%d,%d) = (%.2f, %.2f) free=%s" % (si, sj, xs[si], ys[sj], bool(free[si, sj])))

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
P("cells reachable on foot from spawn: %d / %d walkable" % (int(reach.sum()), int(free.sum())))

ri = np.flatnonzero(reach.any(axis=1))
rj = np.flatnonzero(reach.any(axis=0))
P("reachable extent: x[%.2f, %.2f] y[%.2f, %.2f]" % (xs[ri[0]], xs[ri[-1]], ys[rj[0]], ys[rj[-1]]))

# ---------------------------------------------------------------- props
names = sorted(o.name for o in bpy.data.objects if o.name.startswith("Prop_Item_"))
P("props in scene: %s" % names)

RX = xs[reach.any(axis=1)][:, None]
print()
for name in names:
    o = bpy.data.objects[name]
    wx, wy, wz = o.matrix_world.translation
    spot = WORLD["props"].get(name, {}).get("stand")
    P("%s  world (%.3f, %.3f, %.3f)  stand=%s" % (name, wx, wy, wz, spot))

    # nearest REACHABLE cell
    d2 = (X - wx) ** 2 + (Y - wy) ** 2
    d2 = np.where(reach, d2, np.inf)
    k = int(np.argmin(d2))
    i, j = np.unravel_index(k, d2.shape)
    nd = math.sqrt(float(d2[i, j]))
    P("    nearest reachable cell (%.2f, %.2f) -> %.3f m   %s" % (
        xs[i], ys[j], nd, "IN RANGE" if nd < PICK_RANGE else "OUT OF RANGE"))

    # the hand-authored stand spot
    if spot:
        sx, sy = spot
        cs = can_stand(sx, sy, r, True)
        ci, cj = cell_of(sx, sy)
        P("    stand spot (%.2f, %.2f) can_stand=%s  reachable=%s  dist=%.3f m" % (
            sx, sy, cs, bool(reach[ci, cj]), math.hypot(sx - wx, sy - wy)))

    # how much of the in-range ring is walkable?
    ring = (d2 < PICK_RANGE * PICK_RANGE) & reach
    if ring.any():
        i2, j2 = np.nonzero(ring)
        P("    in-range reachable cells: %d   closest (%.2f, %.2f)" % (
            int(ring.sum()), xs[int(i2[0])], ys[int(j2[0])]))
    else:
        P("    *** NO in-range reachable cell ***")
print()

# ---------------------------------------------------------------- scene doors
for name in ("Shop_Door_L", "Shop_Door_R", "SUV_Door_FR"):
    o = bpy.data.objects.get(name)
    P("%-12s %s" % (name, "present" if o else "MISSING"))
P("DONE")

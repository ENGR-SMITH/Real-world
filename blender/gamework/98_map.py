"""98_map.py -- print the walkable map around the shop counter + prop boxes.

    blender.exe --background Shop_with_people.blend --python 98_map.py
"""
import math
import sys
from collections import deque

import bpy
import numpy as np

GAME = r"E:/Reality/blender/gamework/game.py"
STEP = 0.06


def P(*a):
    print("###", *a)
    sys.stdout.flush()


src = open(GAME, "r", encoding="utf-8").read()
head = src.split("# ================================================================== engine")[0]
ns = {"__name__": "game_head"}
exec(compile(head, "game_head", "exec"), ns)
WORLD = ns["WORLD"]
can_stand = ns["can_stand"]
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
wall = (X > WALL[0] - r) & (X < WALL[1] + r) & ~((Y >= DOORWAY[0] + r * 0.5) & (Y <= DOORWAY[1] - r * 0.5))
free &= ~blk
free &= ~wall

ob = bpy.data.objects["Boy1_RIG"]
sx, sy = ob.matrix_world.translation.x, ob.matrix_world.translation.y
si = int(round((sx - x0) / STEP))
sj = int(round((sy - y0) / STEP))
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

# ---------------------------------------------------------------- props
props = {}
for o in bpy.data.objects:
    if o.name.startswith("Prop_Item_"):
        mn = [1e9] * 3
        mx = [-1e9] * 3
        for c in o.bound_box:
            w = o.matrix_world @ __import__("mathutils").Vector(c)
            for k in range(3):
                mn[k] = min(mn[k], w[k])
                mx[k] = max(mx[k], w[k])
        props[o.name] = (o.matrix_world.translation.copy(), mn, mx)
        P("%s  origin (%.3f, %.3f, %.3f)  size (%.3f x %.3f x %.3f)  bbox x[%.3f,%.3f] y[%.3f,%.3f] z[%.3f,%.3f]" % (
            o.name,
            o.matrix_world.translation.x, o.matrix_world.translation.y, o.matrix_world.translation.z,
            mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2],
            mn[0], mx[0], mn[1], mx[1], mn[2], mx[2]))

# ---------------------------------------------------------------- nearest reachable per quadrant
PX, PY = 0.443, -3.908
d2 = (X - PX) ** 2 + (Y - PY) ** 2
for label, mask in (("ALL", reach),
                    ("west (x<0.4)", reach & (X < 0.4)),
                    ("east (x>=0.4)", reach & (X >= 0.4))):
    dd = np.where(mask, d2, np.inf)
    i, j = np.unravel_index(int(np.argmin(dd)), dd.shape)
    if np.isfinite(dd[i, j]):
        P("Prop_Item_4 nearest reachable %-14s (%.2f, %.2f) = %.3f m" % (label, xs[i], ys[j], math.sqrt(dd[i, j])))
    else:
        P("Prop_Item_4 nearest reachable %-14s none" % label)

# ---------------------------------------------------------------- ascii map
XW = (-2.0, 2.4)
YW = (-5.8, -2.4)
i0, i1 = int(round((XW[0] - x0) / STEP)), int(round((XW[1] - x0) / STEP))
j0, j1 = int(round((YW[0] - y0) / STEP)), int(round((YW[1] - y0) / STEP))
P("map x[%.2f,%.2f] y[%.2f,%.2f]  '#'=blocked  '.'=walkable(connected)  ','=free but cut off  '@'=prop" % (
    XW[0], XW[1], YW[0], YW[1]))
grid = []
for j in range(j1, j0 - 1, -1):
    row = []
    for i in range(i0, i1 + 1):
        if not free[i, j]:
            c = "#"
        elif reach[i, j]:
            c = "."
        else:
            c = ","
        for name, (loc, mn, mx) in props.items():
            if i == int(round((loc.x - x0) / STEP)) and j == int(round((loc.y - y0) / STEP)):
                c = "@"
        row.append(c)
    grid.append("".join(row))
# x-axis ruler every 10 cells
rule = []
for i in range(i0, i1 + 1):
    rule.append("|" if abs((xs[i] * 100) % 50) < STEP * 50 else " ")
P("       " + "".join(rule))
for k, row in enumerate(grid):
    yv = YW[1] - k * STEP
    P("%6.2f %s" % (yv, row))
P("DONE")

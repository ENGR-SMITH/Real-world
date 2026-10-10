"""61_hud_where.py -- where exactly do hud_on.png and hud_off.png differ?

Prints, per image row, how many pixels changed strongly (d > 0.5) and weakly
(d > 0.02), so the shape of the change can be read off before trusting any band.

Run: blender --background --factory-startup --python 61_hud_where.py
"""

import bpy
import numpy as np

SHOTS = "E:/UPBGE/shots"


def pixels(path):
    img = bpy.data.images.load(path)
    w, h = img.size
    a = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    return a


on = pixels(SHOTS + "/hud_on.png")
off = pixels(SHOTS + "/hud_off.png")
d = np.abs(on[:, :, :3] - off[:, :, :3]).sum(axis=2)

strong = d > 0.5
weak = d > 0.02
print("### strong %d  weak %d" % (strong.sum(), weak.sum()))
ys, xs = np.nonzero(strong)
if len(xs):
    print("### strong bbox x %d..%d y %d..%d" % (xs.min(), xs.max(), ys.min(), ys.max()))

print("### %-6s %-8s %-8s" % ("row", "strong", "weak"))
for y in range(0, 720, 10):
    s = strong[y:y + 10].sum()
    w = weak[y:y + 10].sum()
    if s or w:
        print("### y %3d..%3d  strong %6d  weak %6d" % (y, y + 9, s, w))

# columns of the strong pixels in the lower half (the HUD prompt sits at y~617..668)
for name, y0, y1 in (("help", 28, 54), ("title", 88, 120), ("prompt", 600, 680)):
    sub = strong[y0:y1]
    xs2 = np.unique(np.nonzero(sub)[1])
    print("### strong cols in band %-6s : %d %s" % (name, len(xs2), xs2[:20]))
print("WHERE DONE")

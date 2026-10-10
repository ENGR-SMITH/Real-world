"""60_hud_diff.py -- is the HUD text really drawn?

59_hud_shot.py takes two screenshots of the same moment, one with the HUD font
objects in front of the lens and one with them moved 40 m behind it. Anything
that differs between the two pictures is HUD pixels; nothing else in the scene
moved (the boys are hidden and no input was given).

Run: blender --background --factory-startup --python 60_hud_diff.py
"""

import bpy
import numpy as np

SHOTS = "E:/UPBGE/shots"
BANDS = [("help", 30, 52), ("title", 90, 118), ("prompt", 600, 680)]


def pixels(path):
    img = bpy.data.images.load(path)
    w, h = img.size
    a = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    return a


on = pixels(SHOTS + "/hud_on.png")
off = pixels(SHOTS + "/hud_off.png")
h, w = on.shape[:2]
d = np.abs(on[:, :, :3] - off[:, :, :3]).sum(axis=2)

print("### image %dx%d" % (w, h))
live = d > 0.02
print("### changed pixels overall: %d (%.4f%%)" % (live.sum(), 100.0 * live.sum() / (w * h)))
ys, xs = np.nonzero(live)
if len(xs):
    print("### changed bbox x %d..%d  y-from-bottom %d..%d" % (xs.min(), xs.max(), ys.min(), ys.max()))

for name, y0, y1 in BANDS:
    band = live[y0:y1, :]
    n = band.sum()
    print("### band %-7s y %d..%d : %d px" % (name, y0, y1, n))
    if n:
        bys, bxs = np.nonzero(band)
        print("###   bbox x %d..%d  y %d..%d  peak %.3f" % (
            bxs.min(), bxs.max(), y0 + bys.min(), y0 + bys.max(), d[y0:y1][band].max()))
        # a line of text lights up many rows in the same columns
        cols = np.unique(bxs)
        runs, start = [], cols[0]
        for i in range(1, len(cols)):
            if cols[i] != cols[i - 1] + 1:
                runs.append((start, cols[i - 1]))
                start = cols[i]
        runs.append((start, cols[-1]))
        print("###   glyph column runs: %d (first %s)" % (len(runs), runs[:4]))

# sanity: the two pictures must be otherwise identical
print("### only-HUD if changed pixels are confined to the bands above")
print("HUD DIFF DONE")

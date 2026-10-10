"""Did the HUD text actually draw? Measure the screenshots the engine produced.

The HUD is emission-only material on font objects a metre in front of a 32 mm camera, so
the text lands in known pixel bands. The text colour is (1.0, 1.0, 0.9) -- luminance
~0.99 -- so look for near-white pixels there, and compare against a control strip of
sky above the prompt.

Run: blender --background --factory-startup --python 58_check_hud.py
"""
import bpy
import glob
import os

SHOTS = sorted(glob.glob("E:/UPBGE/shots/*.png"))
# camera-local 1 m in front: half width 0.5625, half height 0.3164 at lens 32 / 16:9
STRIPS = [
    ("prompt", 617, 668),      # y from the bottom
    ("help", 30, 52),
    ("control", 520, 570),     # empty sky, nothing is drawn here
]


def strip_stats(path, w, h, px):
    out = []
    for name, y0, y1 in STRIPS:
        mx = 0.0
        n = 0
        hi = 0
        for y in range(y0, y1):
            row = y * w * 4
            for x in range(100, 900):
                i = row + x * 4
                lum = 0.3 * px[i] + 0.6 * px[i + 1] + 0.1 * px[i + 2]
                n += 1
                if lum > mx:
                    mx = lum
                if lum > 0.95:
                    hi += 1
        out.append((name, mx, hi / float(max(n, 1))))
    return out


print("### %-32s %s" % ("file", "  ".join("%-22s" % s[0] for s in STRIPS)))
for p in SHOTS[-16:]:
    if "loop_" in p:
        continue
    img = bpy.data.images.load(p)
    w, h = img.size
    px = list(img.pixels)
    bpy.data.images.remove(img)
    st = strip_stats(p, w, h, px)
    print("### %-32s %s" % (os.path.basename(p),
                            "  ".join("max=%.3f hi=%.4f" % (m, f) for _, m, f in st)))
print("CHECK HUD DONE")

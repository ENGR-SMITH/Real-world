"""bandzoom.py -- magnify the pixel bands where the HUD lines should be.

    blender --background --factory-startup --python bandzoom.py -- shot1.png shot2.png

For every shot it cuts the three HUD bands (y counted from the bottom, as in the
accessibility of Blender's pixel arrays), blows them up 3x and writes one
montage of the bands, then embeds it in hudcheck/view.html.
"""

import base64
import os
import sys

import bpy
import numpy as np

OUT_DIR = "E:/Reality/blender/gamework/hudcheck"
BANDS = [("prompt", 600, 690, 0, 900), ("help", 10, 70, 0, 900), ("carry", 120, 175, 0, 900)]
ZOOM = 3


def pixels(path):
    img = bpy.data.images.load(path)
    w, h = img.size
    a = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    return np.clip(a, 0.0, 1.0) ** (1.0 / 2.2)


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parts, labels = [], []
    for p in args:
        a = pixels(p)
        for name, y0, y1, x0, x1 in BANDS:
            crop = a[y0:y1, x0:x1]
            big = np.repeat(np.repeat(crop, ZOOM, axis=0), ZOOM, axis=1)
            pad = np.zeros((big.shape[0] + 4, big.shape[1], 4), dtype=np.float32)
            pad[:, :, 3] = 1.0
            parts.append(big)
            parts.append(pad)
            labels.append("%s %s rows %d..%d" % (os.path.basename(p), name, y0, y1))
    w = max(p.shape[1] for p in parts)
    for i, p in enumerate(parts):
        if p.shape[1] < w:
            filler = np.zeros((p.shape[0], w - p.shape[1], 4), dtype=np.float32)
            filler[:, :, 3] = 1.0
            parts[i] = np.concatenate([p, filler], axis=1)
    canvas = np.concatenate(parts, axis=0)
    h, w = canvas.shape[:2]
    img = bpy.data.images.new("bandzoom", width=w, height=h, alpha=True)
    # Blender stores rows bottom-up both on read and on write -- no flip either way
    img.pixels = canvas.ravel().tolist()
    img.filepath_raw = OUT_DIR + "/bands.png"
    img.file_format = 'PNG'
    img.save()

    b64 = base64.b64encode(open(OUT_DIR + "/bands.png", "rb").read()).decode()
    legend = "".join("<div>%s</div>" % s for s in labels)
    html = ("<!doctype html><html><head><meta charset='utf-8'><title>bands</title>"
            "<style>html,body{margin:0;background:#111;color:#ddd;font:11px monospace}"
            "img{width:100%%;display:block}</style></head><body>%s"
            "<img alt='bands' src='data:image/png;base64,%s'></body></html>" % (legend, b64))
    with open(OUT_DIR + "/view.html", "w") as f:
        f.write(html)
    print("### bandzoom: %d band crops, zoom %dx -> %s/bands.png (%dx%d)"
          % (len(labels), ZOOM, OUT_DIR, w, h))


main()

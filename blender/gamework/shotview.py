"""shotview.py -- put screenshots in front of a pair of eyes.

Stacks the named PNGs (half scale, one per row) into a single montage and writes
it, base64-embedded, to hudcheck/view.html so the preview panel can show it.

    blender --background --factory-startup --python shotview.py -- a.png b.png
    (with no arguments it picks up the newest six skinshots in E:/UPBGE/shots)

Run it, then reload the preview tab.
"""

import base64
import glob
import os
import sys

import bpy
import numpy as np

SHOTS = "E:/UPBGE/shots"
OUT_DIR = "E:/Reality/blender/gamework/hudcheck"
MONTAGE = OUT_DIR + "/montage.png"


def pixels(path):
    img = bpy.data.images.load(path)
    w, h = img.size
    a = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    return np.clip(a, 0.0, 1.0) ** (1.0 / 2.2)      # linear -> sRGB


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not args:
        args = sorted(glob.glob(SHOTS + "/*.png"), key=os.path.getmtime)[-6:]
    rows = [pixels(p)[::2, ::2, :] for p in args]
    w = max(r.shape[1] for r in rows)
    parts = []
    for r in rows:
        parts.append(r)
        pad = np.zeros((6, w, 4), dtype=np.float32)
        pad[:, :, :3] = 0.05
        pad[:, :, 3] = 1.0
        parts.append(pad)
    canvas = np.concatenate(parts, axis=0)
    canvas[:, :, 3] = 1.0

    h = canvas.shape[0]
    img = bpy.data.images.new("shotview", width=w, height=h, alpha=True)
    img.pixels = canvas[::-1].ravel().tolist()
    img.filepath_raw = MONTAGE
    img.file_format = 'PNG'
    img.save()

    b64 = base64.b64encode(open(MONTAGE, "rb").read()).decode()
    html = ("<!doctype html><html><head><meta charset='utf-8'><title>shots</title>"
            "<style>html,body{margin:0;background:#111}img{width:100%%;display:block}"
            "body{font:11px monospace;color:#ddd}</style></head><body>%s"
            "<img alt='shots' src='data:image/png;base64,%s'></body></html>"
            % ("".join("<div>%s</div>" % os.path.basename(p) for p in args), b64))
    with open(OUT_DIR + "/view.html", "w") as f:
        f.write(html)
    print("### shotview: %s -> %s (%dx%d)" % (", ".join(os.path.basename(p) for p in args),
                                              MONTAGE, w, h))


main()

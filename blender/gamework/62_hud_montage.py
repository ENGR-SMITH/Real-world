"""62_hud_montage.py -- one picture that shows the HUD, cropped and stacked.

Top row   : hud_on (left) and hud_off (right), half scale.
Below it  : the prompt band (y 630..700) of each, full width, 2x vertical zoom.

Writes E:/Reality/blender/gamework/hudcheck/montage.png.

Run: blender --background --factory-startup --python 62_hud_montage.py
"""

import bpy
import numpy as np

SHOTS = "E:/UPBGE/shots"
OUT = "E:/Reality/blender/gamework/hudcheck/montage.png"


def pixels(path):
    img = bpy.data.images.load(path)
    w, h = img.size
    a = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    return a


def gamma(a):
    """Blender hands back linear; screenshots are sRGB. Make it look like the PNG."""
    return np.clip(a, 0.0, 1.0) ** (1.0 / 2.2)


def pad(a, width):
    if a.shape[1] >= width:
        return a
    fill = np.zeros((a.shape[0], width - a.shape[1], 4), dtype=np.float32)
    fill[:, :, :3] = 0.1
    fill[:, :, 3] = 1.0
    return np.concatenate([a, fill], axis=1)


on = gamma(pixels(SHOTS + "/hud_on.png"))
off = gamma(pixels(SHOTS + "/hud_off.png"))

half_on, half_off = on[::2, ::2, :], off[::2, ::2, :]
band_on = np.repeat(on[630:700, :, :], 2, axis=0)
band_off = np.repeat(off[630:700, :, :], 2, axis=0)

w = half_on.shape[1] * 2 + 4
sep = np.zeros((half_on.shape[0], 4, 4), dtype=np.float32)
sep[:, :, 3] = 1.0
rows = [pad(np.concatenate([half_on, sep, half_off], axis=1), w),
        np.zeros((6, w, 4), dtype=np.float32),
        pad(band_on, w),
        pad(band_off, w)]
canvas = np.concatenate(rows, axis=0)
canvas[:, :, 3] = 1.0

h = canvas.shape[0]
img = bpy.data.images.new("montage", width=w, height=h, alpha=True)
# Blender images start at the bottom row; our array starts at the top
img.pixels = canvas[::-1].ravel().tolist()
img.filepath_raw = OUT
img.file_format = 'PNG'
img.save()
print("### wrote %s (%dx%d)" % (OUT, w, h))
print("### top row: left = HUD on, right = HUD off; then the prompt band of each")
print("MONTAGE DONE")

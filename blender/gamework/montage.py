"""Build a contact sheet from PNGs:  blender -b --python montage.py -- OUT COLS IMG...
Uses only Blender's bundled numpy - no extra tooling needed.
"""
import bpy
import sys
import numpy as np

argv = sys.argv[sys.argv.index('--') + 1:]
out, cols = argv[0], int(argv[1])
paths = argv[2:]
step = 2 if len(paths) > 4 else 1

tiles = []
w = h = 0
for p in paths:
    im = bpy.data.images.load(p)
    iw, ih = im.size
    a = np.array(im.pixels[:], dtype=np.float32).reshape(ih, iw, 4)
    a = a[::step, ::step]
    tiles.append(a)
    h, w = a.shape[0], a.shape[1]
    bpy.data.images.remove(im)

rows = (len(tiles) + cols - 1) // cols
sheet = np.zeros((rows * h, cols * w, 4), dtype=np.float32)
sheet[..., 3] = 1.0
for i, t in enumerate(tiles):
    r, c = divmod(i, cols)
    sheet[r * h:(r + 1) * h, c * w:(c + 1) * w] = t

img = bpy.data.images.new('sheet', width=cols * w, height=rows * h, alpha=True)
img.pixels = sheet.ravel().tolist()
img.file_format = 'PNG'
img.filepath_raw = out
img.save()
print('MONTAGE', out, cols * w, 'x', rows * h, 'from', len(tiles), 'tiles')

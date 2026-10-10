"""ascii_img.py -- look at a screenshot from the terminal.

The Preview panel shows nothing on this machine, so this prints a coarse colour
map plus a legend of the dominant colours.  Good enough to answer "is the wall in
frame?", "is the text drawn?", "which way is the camera pointing?".

    python ascii_img.py <png> [cols] [rows]
"""

import sys

from PIL import Image
import numpy as np

GLYPHS = " .:-=+*#%@"


def classify(px):
    r, g, b = int(px[0]), int(px[1]), int(px[2])
    mx, mn = max(r, g, b), min(r, g, b)
    lum = (r * 299 + g * 587 + b * 114) // 1000
    if mx - mn < 22:                      # grey/white/black
        return GLYPHS[min(9, lum * 10 // 256)]
    if r >= g and r >= b:
        return "R" if g < 90 and b < 90 else ("O" if g >= b else "M")
    if g >= r and g >= b:
        return "G"
    return "B" if r < 90 else "C"


def main():
    path = sys.argv[1]
    cols = int(sys.argv[2]) if len(sys.argv) > 2 else 78
    rows = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    im = Image.open(path).convert("RGB").resize((cols, rows), Image.NEAREST)
    a = np.asarray(im)
    lum = (a[:, :, 0] * 299 + a[:, :, 1] * 587 + a[:, :, 2] * 114) // 1000
    print("== %s" % path)
    for y in range(rows):
        line = "".join(classify(a[y, x]) for x in range(cols))
        print("%2d|%s| %3d" % (y, line, int(lum[y].mean())))
    # legend: the eight most common colours
    full = np.asarray(Image.open(path).convert("RGB")).reshape(-1, 3)
    uniq, counts = np.unique(full, axis=0, return_counts=True)
    order = np.argsort(counts)[::-1][:10]
    total = full.shape[0]
    print("-- dominant colours (%d px) --" % total)
    for i in order:
        r, g, b = (int(v) for v in uniq[i])
        print("   #%02x%02x%02x  rgb(%3d,%3d,%3d)  %5.1f%%  glyph %s" % (
            r, g, b, r, g, b, 100.0 * counts[i] / total, classify((r, g, b))))


main()

"""90_mini_loop.py -- main loop for the mini scene, used via
`blenderplayer.exe -g noaudio -p 90_mini_loop.py mini.blend`.

makeScreenshot renders from the engine's own camera (`__default__cam__` at
(15.036, -6.696, 8.198)), not from the scene camera.  This run drags that object
onto MiniCam's pose: if the probes then appear where they belong, the fix for the
real game is to drive the engine's camera object.
"""

import bge
from mathutils import Matrix

SHOT = "E:/UPBGE/mini.png"
LOG = "E:/UPBGE/mini.log.txt"


def L(msg):
    f = open(LOG, "a")
    f.write(str(msg) + "\n")
    f.close()


def find(sc, name):
    for o in list(sc.objects):
        if o.name == name:
            return o
    return None


def vec(v):
    return "(" + ", ".join("%.3f" % c for c in v) + ")"


def main():
    n = 0
    sc = bge.logic.getCurrentScene()
    mine = sc.objects.get("MiniCam")
    L("## start active=" + sc.active_camera.name + " mine=" + str(mine))
    if mine is not None:
        sc.active_camera = mine

    eng = find(sc, "__default__cam__")
    if eng is None:
        L("## NO engine camera object")
    else:
        L("## engine camera was at " + vec(eng.worldPosition))

    while True:
        n += 1
        if n >= 10 and eng is not None and mine is not None:
            eng.worldPosition = mine.worldPosition
            eng.worldOrientation = Matrix(mine.worldOrientation)
        if n == 20:
            L("## frame 20 engine cam at " + (vec(eng.worldPosition) if eng else "-"))
            bge.render.makeScreenshot(SHOT)
            L("## screenshot requested")
        if n == 60:
            L("## done")
            bge.logic.endGame()
        bge.logic.NextFrame()


main()

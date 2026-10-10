"""68_hud_ab.py -- one run with the HUD off, one with it on, same fixed frame.

67_hud_depth.py showed the HUD geometry is exactly where it should be: every
object lands at view z = -1.0 with NDC inside the frustum (the prompt band sits
around pixel row 55, the help band around row 670).  The earlier same-frame A/B
told us nothing because makeScreenshot() writes the frame the engine has already
drawn -- flipping a visibility flag mid-frame cannot change it.

So: two whole runs of a deterministic scene, one with the HUD hidden and one
with it shown, both screenshotting the same frame number.  Any difference
between the two images is the HUD.

    BOYHUDB=hidden BOYHIDE=boys BOYDT=0.2 BOYFRAMES=200 \
    BOYSCEN=E:/Reality/blender/gamework/68_hud_ab.py blenderplayer.exe ...blend
"""

import os

import bge

SHOTS = "E:/UPBGE/shots"
FRONT = (-5.0, -2.0)
MODE = os.environ.get("BOYHUDB", "shown")
SHOT_AT = 100


def neutral():
    return {"mx": 0.0, "my": 0.0, "run": False, "use": False, "tab": False}


def setup(g):
    g.hb = {"done": False, "held": 0}
    g.actors[0].place(FRONT[0], FRONT[1], 0.06)
    for v in g.vehs:
        v.speed = 0.0
    g.note("hud ab: mode=%s shot at frame %d" % (MODE, SHOT_AT))


def step(g, frame, dt):
    st = g.hb
    if MODE == "hidden":
        for _, o in g.hud.items():
            o.visible = False
    if st["done"]:
        inp = neutral()
        if st["held"] >= 2:
            inp["quit"] = True
        st["held"] += 1
        return inp
    if frame >= SHOT_AT:
        bge.render.makeScreenshot("%s/ab_%s.png" % (SHOTS, MODE))
        vis = sorted(n for n, o in g.hud.items() if o.visible)
        g.note("hud ab: shot ab_%s.png at frame %d, visible=%s" % (MODE, frame, vis))
        st["done"] = True
    return neutral()


def finish(g):
    g.note("hud ab done at frame %d" % g.frame)

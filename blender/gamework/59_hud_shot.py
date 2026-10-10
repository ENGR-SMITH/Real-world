"""59_hud_shot.py -- one moment, two screenshots: HUD text in place, then hidden.

The HUD is a set of font objects parented to Camera_Game, a metre in front of the
lens, so each line lands in a known pixel band. `game.py` rewrites `visible` on
every frame, so the only way to take a HUD-free control shot is to move the
objects out of the frustum instead.

Run (boys hidden so nothing else in the frame can move between the two shots):

    BOYHIDE=boys BOYDT=0.2 BOYSCEN=E:/Reality/blender/gamework/59_hud_shot.py \
        blenderplayer.exe -g noaudio Shop_with_people.blend

Writes E:/UPBGE/shots/hud_on.png and E:/UPBGE/shots/hud_off.png.
"""

import bge

SHOTS = "E:/UPBGE/shots"
FRONT = (-5.0, -2.0)        # the spot where the shop door prompt appears


def neutral():
    """game.step() indexes every key of the input dict -- never hand it {}."""
    return {"mx": 0.0, "my": 0.0, "run": False, "use": False, "tab": False}


def setup(g):
    st = {"phase": "settle", "t": 0.0}
    g.hudshot = st
    g.actors[0].place(FRONT[0], FRONT[1], 0.06)
    g.note("hud shot: boy placed at %s" % (FRONT,))


def _away(g, dz):
    for o in g.hud.values():
        p = o.localPosition
        o.localPosition = (p[0], p[1], p[2] - dz)


def step(g, frame, dt):
    st = g.hudshot
    st["t"] += dt
    if st["phase"] == "settle":
        # camera lag 8.0 -- give it time to settle, and let the prompt appear
        if st["t"] > 4.0:
            it = g.interaction(g.actors[g.active])
            g.note("hud shot: on frame %d, prompt=%s" % (g.frame, it and it[0]))
            bge.render.makeScreenshot(SHOTS + "/hud_on.png")
            _away(g, 40.0)                       # 40 m behind the camera
            st["phase"] = "hide"
            st["t"] = 0.0
    elif st["phase"] == "hide":
        if st["t"] > 0.4:
            it = g.interaction(g.actors[g.active])
            g.note("hud shot: off frame %d, prompt=%s" % (g.frame, it and it[0]))
            bge.render.makeScreenshot(SHOTS + "/hud_off.png")
            st["phase"] = "leave"
            st["t"] = 0.0
    elif st["phase"] == "leave":
        # makeScreenshot is written during the frame that follows the call
        if st["t"] > 0.4:
            inp = neutral()
            inp["quit"] = True
            return inp
    return neutral()


def finish(g):
    g.note("hud shot done at frame %d" % g.frame)

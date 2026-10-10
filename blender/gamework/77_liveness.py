"""77_liveness.py -- do the screenshots follow the game camera at all?

Two shots of the same run: the first with the camera where the game put it, the
second after hoisting the camera 25 m into the air.  If the second shot is a
bird's eye view, makeScreenshot renders the live game.  If it is the same picture,
the screenshot is not the game view and every screenshot-based check in this
project has been measuring something else.

    BOYHIDE=boys BOYDT=0.2 BOYSCEN=.../77_liveness.py blenderplayer.exe ...
"""

import bge

SHOTS = "E:/UPBGE/shots"
A, B, C = 60, 100, 140


def neutral():
    return {"mx": 0.0, "my": 0.0, "run": False, "use": False, "tab": False}


def setup(g):
    g.lv = {"shot": 0}
    g.actors[0].place(-5.0, -2.0, 0.06)
    for v in g.vehs:
        v.speed = 0.0
    g.note("liveness: boy parked at (-5.0, -2.0), traffic halted")


def step(g, frame, dt):
    st = g.lv
    if st["shot"] == 0 and frame >= A:
        bge.render.makeScreenshot("%s/live_a.png" % SHOTS)
        g.note("liveness: shot A at frame %d, cam %s" % (
            frame, tuple(round(v, 2) for v in g.cam.worldPosition)))
        st["shot"] = 1
    elif st["shot"] == 1 and frame >= B:
        # teleport the boy: the follow camera swings to the new spot within a second
        g.actors[0].place(-5.0, 30.0, 0.06)
        g.note("liveness: boy teleported to y=30")
        st["shot"] = 2
    elif st["shot"] == 2 and frame >= C:
        bge.render.makeScreenshot("%s/live_b.png" % SHOTS)
        g.note("liveness: shot B at frame %d, cam %s" % (
            frame, tuple(round(v, 2) for v in g.cam.worldPosition)))
        st["shot"] = 3
    elif st["shot"] == 3 and frame >= C + 30:
        # makeScreenshot writes out of band: give it frames to land before quitting
        g.note("liveness: cam at quit %s" % (
            tuple(round(v, 2) for v in g.cam.worldPosition),))
        inp = neutral()
        inp["quit"] = True
        return inp
    return neutral()


def finish(g):
    g.note("liveness done at frame %d" % g.frame)

"""63_hud_probe.py -- why can't we see the HUD?

Three screenshots of the same static moment with the HUD font objects placed
three different ways, plus a dump of the camera's local axes.  The traffic is
halted first so nothing but the HUD can move between shots.

    probe_frame1.png    HUD placed 1 m along the camera's real forward axis
    probe_authored.png  HUD placed where the build script put it, local z = -1
    probe_far.png       HUD parked 100 m behind the camera (control)

Run:

    BOYHIDE=boys BOYDT=0.2 BOYSCEN=E:/Reality/blender/gamework/63_hud_probe.py \
        blenderplayer.exe -g noaudio Shop_with_people.blend
"""

import math

import bge
from mathutils import Vector

SHOTS = "E:/UPBGE/shots"
FRONT = (-5.0, -2.0)


def neutral():
    return {"mx": 0.0, "my": 0.0, "run": False, "use": False, "tab": False}


def setup(g):
    g.hp = {"phase": "settle", "t": 0.0, "base": {}, "shots": 0}
    g.actors[0].place(FRONT[0], FRONT[1], 0.06)
    for v in g.vehs:
        v.speed = 0.0
    for name, o in g.hud.items():
        p = o.localPosition
        g.hp["base"][name] = (p[0], p[1])
    g.note("hud probe: boy at %s, traffic halted" % (FRONT,))
    g.note("hud probe: %d hud objects %s" % (len(g.hud), sorted(g.hud)))
    for name, o in sorted(g.hud.items()):
        try:
            ms = o.meshes
            det = "meshes=%d polys=%s" % (len(ms), [m.numPolygons for m in ms])
        except Exception as exc:
            det = "mesh query failed: %r" % (exc,)
        g.note("hud probe:   %-13s visible=%s %s" % (name, o.visible, det))


def axes(g):
    """The camera's world forward/right/up, expressed in the camera's own frame."""
    cam = g.cam
    R = cam.worldOrientation
    Ri = R.inverted()
    fw = Vector((math.sin(g.cam_yaw), -math.cos(g.cam_yaw), 0.0))
    rt = Vector((math.cos(g.cam_yaw), math.sin(g.cam_yaw), 0.0))
    return Ri @ fw, Ri @ rt, Ri @ Vector((0.0, 0.0, 1.0))


def put(g, lf, rl, ul, depth, authored=False):
    for name, o in g.hud.items():
        bx, by = g.hp["base"].get(name, (0.0, 0.0))
        if authored:
            o.localPosition = (bx, by, -1.0)
        else:
            p = lf * depth + rl * bx + ul * by
            o.localPosition = (p[0], p[1], p[2])


def shot(g, name):
    n = g.hp["shots"]
    g.hp["shots"] = n + 1
    path = "%s/%02d_%s" % (SHOTS, n, name)
    bge.render.makeScreenshot(path)
    g.note("hud probe: shot %s at frame %d" % (name, g.frame))


STATES = [("frame1", "probe_frame1.png", 1.0, False),
          ("authored", "probe_authored.png", 1.0, True),
          ("far", "probe_far.png", -100.0, False)]


def step(g, frame, dt):
    st = g.hp
    st["t"] += dt
    if st["phase"] == "settle":
        if st["t"] > 4.0:
            cam = g.cam
            lf, rl, ul = axes(g)
            g.note("hud probe: cam pos %s" % (tuple(round(v, 3) for v in cam.worldPosition),))
            g.note("hud probe: local forward %s right %s up %s" % (
                tuple(round(v, 3) for v in lf), tuple(round(v, 3) for v in rl),
                tuple(round(v, 3) for v in ul)))
            it = g.interaction(g.actors[g.active])
            g.note("hud probe: prompt %s" % (it and it[0],))
            g.note("hud probe: visible %s" % (
                sorted(n for n, o in g.hud.items() if o.visible),))
            st["phase"] = "run"
            st["i"] = 0
            st["t"] = 0.0
            st["armed"] = False
        return neutral()

    if st["i"] >= len(STATES):
        if st["t"] > 0.6:
            inp = neutral()
            inp["quit"] = True
            return inp
        return neutral()

    name, shot_name, depth, authored = STATES[st["i"]]
    if not st["armed"]:
        lf, rl, ul = axes(g)
        put(g, lf, rl, ul, depth, authored=authored)
        shot(g, shot_name)
        st["armed"] = True
        st["t"] = 0.0
    elif st["t"] > 0.4:
        st["i"] += 1
        st["armed"] = False
        st["t"] = 0.0
    return neutral()


def finish(g):
    g.note("hud probe done at frame %d" % g.frame)

"""70_qq_list.py -- does the engine know about the QQ_ test objects at all?

    BOYHIDE=boys BOYDT=0.2 BOYSCEN=E:/Reality/blender/gamework/70_qq_list.py \
        blenderplayer.exe -g noaudio hud_test.blend
"""

import bge

PREFIX = "QQ_"


def neutral():
    return {"mx": 0.0, "my": 0.0, "run": False, "use": False, "tab": False}


def setup(g):
    g.qq = {"t": 0.0}
    sc = g.sc
    objs = [o for o in sc.objects]
    g.note("qq list: engine scene '%s' has %d objects" % (sc.name, len(objs)))
    g.note("qq list: camera=%s active=%s" % (
        getattr(sc, "camera", None), getattr(sc, "active_camera", None)))
    names = sorted(o.name for o in objs if o.name.startswith(PREFIX))
    g.note("qq list: %d QQ_ objects in engine: %s" % (len(names), names))
    for o in objs:
        if not o.name.startswith(PREFIX):
            continue
        g.note("qq list:   %-13s visible=%s world=%s scale=%s meshes=%d" % (
            o.name, o.visible,
            tuple(round(v, 3) for v in o.worldPosition),
            tuple(round(v, 3) for v in o.worldScale),
            len(o.meshes)))
    hud = sorted(n for n in (o.name for o in objs) if n.startswith(("HUD_", "P_")))
    g.note("qq list: hud names in engine: %s" % (hud,))


def step(g, frame, dt):
    g.qq["t"] += dt
    if g.qq["t"] > 1.0:
        inp = neutral()
        inp["quit"] = True
        return inp
    return neutral()


def finish(g):
    g.note("qq list done at frame %d" % g.frame)

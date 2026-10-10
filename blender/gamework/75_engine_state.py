"""75_engine_state.py -- engine-side state of rendering vs invisible objects.

Cycles draws the HUD text and the test cubes fine, so the data is good and the
engine's rasteriser is skipping them.  Dump everything the engine exposes about an
object that certainly draws (the SUV, a boy, the street) beside one that never
does (HUD_Help, QQ_F, QQ_PL): colour and alpha, mesh proxy details, material
settings, occlusion/culling state.

    BOYHIDE=boys BOYDT=0.2 BOYSCEN=.../75_engine_state.py blenderplayer.exe ...
"""

import bge

SHOTS = "E:/UPBGE/shots"
WATCH = ("HUD_Help", "P_DoorOpen", "QQ_F", "QQ_A", "QQ_PL", "QQ_RR",
         "Street_Road", "SUV_root", "Boy1_RIG", "Prop_Item_1")


def neutral():
    return {"mx": 0.0, "my": 0.0, "run": False, "use": False, "tab": False}


def describe(g, o):
    bits = []
    for attr in ("color", "visible", "occlusion", "alpha", "depth", "parent",
                 "worldScale", "scene"):
        try:
            v = getattr(o, attr)
            if hasattr(v, "name"):
                v = v.name
            elif isinstance(v, (list, tuple)):
                v = tuple(round(x, 3) for x in v)
            bits.append("%s=%s" % (attr, v))
        except Exception as exc:
            bits.append("%s=ERR" % attr)
    g.note("engine: %-13s %s" % (o.name, " ".join(bits)))
    try:
        ms = o.meshes
    except Exception:
        ms = []
    if not ms:
        g.note("engine:   (no meshes exposed)")
        return
    m = ms[0]
    try:
        g.note("engine:   mesh numPolygons=%s numVerts=%s" % (
            m.numPolygons, m.getVertexArrayLength(0)))
    except Exception as exc:
        g.note("engine:   mesh query failed %r" % (exc,))
    try:
        for mat in m.materials:
            g.note("engine:   mat %s alpha=%.3f diffuse=%s emit=%s spec=%s" % (
                mat.name, mat.alpha,
                tuple(round(x, 3) for x in mat.diffuse),
                tuple(round(x, 3) for x in getattr(mat, "emit", (0, 0, 0))),
                tuple(round(x, 3) for x in getattr(mat, "specular", (0, 0, 0)))))
    except Exception as exc:
        g.note("engine:   material query failed %r" % (exc,))


def setup(g):
    g.es = {"t": 0.0, "done": False}
    g.actors[0].place(-5.0, -2.0, 0.06)
    for v in g.vehs:
        v.speed = 0.0
    for nm in WATCH:
        o = g.sc.objects.get(nm)
        if o is None:
            g.note("engine: %s MISSING from the scene" % nm)
            continue
        describe(g, o)


def step(g, frame, dt):
    st = g.es
    st["t"] += dt
    if not st["done"] and st["t"] > 4.0:
        bge.render.makeScreenshot("%s/es_shot.png" % SHOTS)
        g.note("engine: shot at frame %d" % frame)
        st["done"] = True
        return neutral()
    if st["done"]:
        inp = neutral()
        inp["quit"] = True
        return inp
    return neutral()


def finish(g):
    g.note("engine state done at frame %d" % g.frame)

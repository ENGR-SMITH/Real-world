"""66_hud_verify.py -- same-frame A/B: HUD hidden vs HUD shown.

63_hud_probe.py moved the HUD between shots, so the frames differed and the
comparison was muddied.  Here the boy is parked, traffic halted, and in a single
step we grab two screenshots of one and the same frame: first with every HUD
object switched off, then with them switched on.  Whatever differs between those
two images is the HUD, and nothing else.

    BOYHIDE=boys BOYDT=0.2 BOYSCEN=E:/Reality/blender/gamework/66_hud_verify.py \
        blenderplayer.exe -g noaudio Shop_with_people.blend
"""

import bge

SHOTS = "E:/UPBGE/shots"
FRONT = (-5.0, -2.0)


def neutral():
    return {"mx": 0.0, "my": 0.0, "run": False, "use": False, "tab": False}


def setup(g):
    g.hv = {"t": 0.0, "done": False}
    g.actors[0].place(FRONT[0], FRONT[1], 0.06)
    for v in g.vehs:
        v.speed = 0.0
    g.note("hud verify: boy parked at %s, traffic halted" % (FRONT,))
    g.note("hud verify: %d hud objects %s" % (len(g.hud), sorted(g.hud)))
    for name, o in sorted(g.hud.items()):
        wp = o.worldPosition
        try:
            nv = o.meshes[0].getVertexArrayLength(0)
        except Exception as exc:
            nv = "? (%r)" % (exc,)
        g.note("hud verify:   %-13s meshes=%d verts=%s visible=%s world=%s" % (
            name, len(o.meshes), nv, o.visible,
            tuple(round(v, 3) for v in wp)))


def shot(g, path):
    bge.render.makeScreenshot(path)


def step(g, frame, dt):
    st = g.hv
    st["t"] += dt
    if not st["done"] and st["t"] > 4.0:
        for _, o in g.hud.items():
            o.visible = False
        shot(g, "%s/hv_hidden.png" % SHOTS)
        for _, o in g.hud.items():
            o.visible = True
        shot(g, "%s/hv_shown.png" % SHOTS)
        it = g.interaction(g.actors[g.active])
        g.note("hud verify: prompt=%s visible now=%s" % (
            it and it[0], sorted(n for n, o in g.hud.items() if o.visible)))
        for _, o in g.hud.items():
            o.visible = True
        g.note("hud verify: two shots written at frame %d" % frame)
        st["done"] = True
        st["t"] = 0.0
        return neutral()
    if st["done"]:
        if st["t"] > 0.6:
            inp = neutral()
            inp["quit"] = True
            return inp
        shot(g, "%s/hv_shown2.png" % SHOTS)
        return neutral()
    return neutral()


def finish(g):
    g.note("hud verify done at frame %d" % g.frame)

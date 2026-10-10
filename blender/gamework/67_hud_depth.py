"""67_hud_depth.py -- where are the HUD objects really, in camera space?

66_hud_verify.py hid and showed every HUD object in the same frame and the two
screenshots came out pixel-identical, so the engine holds the geometry
(meshes=1, ~2 000 verts) but never rasterises it.  The next thing to settle is
whether that is a placement problem or a shading/culling problem: dump the camera
intrinsics, the camera's own matrix, and every HUD object's position in view and
clip space.  A healthy HUD sits at view z ~ -1.0 with |x|,|y| inside the frustum.

    BOYHIDE=boys BOYDT=0.2 BOYSCEN=E:/Reality/blender/gamework/67_hud_depth.py \
        blenderplayer.exe -g noaudio Shop_with_people.blend
"""

import bge
from mathutils import Vector

SHOTS = "E:/UPBGE/shots"
FRONT = (-5.0, -2.0)


def neutral():
    return {"mx": 0.0, "my": 0.0, "run": False, "use": False, "tab": False}


def setup(g):
    g.hd = {"t": 0.0, "done": False}
    g.actors[0].place(FRONT[0], FRONT[1], 0.06)
    for v in g.vehs:
        v.speed = 0.0
    g.note("hud depth: boy parked at %s" % (FRONT,))


def vec(m):
    return tuple(round(v, 4) for v in m)


def report(g):
    cam = g.cam
    g.note("hud depth: cam world %s" % (vec(cam.worldPosition),))
    g.note("hud depth: cam scale %s" % (vec(cam.worldScale),))
    for attr in ("near", "far", "lens", "fov", "ortho_scale", "useViewport", "useViewFrustum"):
        try:
            g.note("hud depth: cam.%s = %s" % (attr, getattr(cam, attr)))
        except Exception as exc:
            g.note("hud depth: cam.%s unavailable (%s)" % (attr, type(exc).__name__))
    def mat(name):
        try:
            m = getattr(cam, name)
        except Exception as exc:
            g.note("hud depth: %s unavailable (%s)" % (name, type(exc).__name__))
            return None
        g.note("hud depth: %s:" % name)
        for r in range(4):
            g.note("hud depth:   %s" % (vec(m[r]),))
        return m

    mat("camera_to_world")
    world2cam = mat("world_to_camera")
    proj = mat("projection_matrix")
    if world2cam is None:
        world2cam = cam.worldOrientation.to_4x4().inverted()
        world2cam.translation = -(world2cam @ cam.worldPosition)

    for name, o in sorted(g.hud.items()):
        p = o.worldPosition
        view = world2cam @ Vector((p[0], p[1], p[2], 1.0))
        line = "hud depth:   %-13s world=%s view=%s" % (name, vec(p), vec(view))
        if proj is not None:
            clip = proj @ view
            w = clip[3] if abs(clip[3]) > 1e-9 else 1e-9
            ndc = (clip[0] / w, clip[1] / w, clip[2] / w)
            line += " ndc=%s" % (vec(ndc),)
        g.note(line)
        d = (Vector(p) - cam.worldPosition).length
        g.note("hud depth:     vis=%s meshes=%d dist_to_cam=%.3f" % (
            o.visible, len(o.meshes), d))


def step(g, frame, dt):
    st = g.hd
    st["t"] += dt
    if not st["done"] and st["t"] > 4.0:
        report(g)
        for _, o in g.hud.items():
            o.visible = False
        bge.render.makeScreenshot("%s/hd_hidden.png" % SHOTS)
        for _, o in g.hud.items():
            o.visible = True
        bge.render.makeScreenshot("%s/hd_shown.png" % SHOTS)
        g.note("hud depth: shots written at frame %d" % frame)
        st["done"] = True
        return neutral()
    if st["done"]:
        st["t"] += 0.0
        if st["t"] > 0.6:
            inp = neutral()
            inp["quit"] = True
            return inp
    return neutral()


def finish(g):
    g.note("hud depth done at frame %d" % g.frame)

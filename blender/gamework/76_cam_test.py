"""76_cam_test.py -- is makeScreenshot rendering from a different camera?

The engine's screenshots look like a wide view from ten metres away, while a
Cycles render from the pose the game reports for Camera_Game is a close-up with
the HUD text across it.  The engine has two notions of "the camera": the scene's
active camera (KX) which game.py sets, and the Blender scene camera, which nothing
touches.  UPBGE's screenshot may use the latter.  Print both, force the Blender
one, and shoot.

    BOYHIDE=boys BOYDT=0.2 BOYSCEN=.../76_cam_test.py blenderplayer.exe ...
"""

import bge

SHOTS = "E:/UPBGE/shots"


def neutral():
    return {"mx": 0.0, "my": 0.0, "run": False, "use": False, "tab": False}


def setup(g):
    g.ct = {"t": 0.0, "done": False}
    g.actors[0].place(-5.0, -2.0, 0.06)
    for v in g.vehs:
        v.speed = 0.0
    try:
        import bpy
    except ImportError:
        g.note("cam test: no bpy in the game session")
        return
    bsc = bpy.context.scene
    cur = bsc.camera
    g.note("cam test: engine active camera = %s" % (
        g.sc.active_camera.name if g.sc.active_camera else None,))
    g.note("cam test: blender scene.camera = %s" % (cur.name if cur else None,))
    g.note("cam test: game camera object is %s at %s" % (
        g.cam.name, tuple(round(v, 3) for v in g.cam.worldPosition)))
    if cur is not None:
        g.note("cam test: that camera sits at %s" % (
            tuple(round(v, 3) for v in cur.matrix_world.translation),))
    if cur is None or cur.name != "Camera_Game":
        bsc.camera = bpy.data.objects.get("Camera_Game")
        g.note("cam test: forced scene.camera to %s" % (
            bsc.camera.name if bsc.camera else None,))


def step(g, frame, dt):
    st = g.ct
    st["t"] += dt
    if not st["done"] and st["t"] > 4.0:
        try:
            import bpy
            g.note("cam test: at shot time scene.camera = %s" % (
                bpy.context.scene.camera.name if bpy.context.scene.camera else None,))
            g.note("cam test: game cam world %s" % (
                tuple(round(v, 3) for v in g.cam.worldPosition),))
        except ImportError:
            pass
        bge.render.makeScreenshot("%s/cam_fixed.png" % SHOTS)
        g.note("cam test: shot at frame %d" % frame)
        st["done"] = True
        return neutral()
    if st["done"]:
        inp = neutral()
        inp["quit"] = True
        return inp
    return neutral()


def finish(g):
    g.note("cam test done at frame %d" % g.frame)

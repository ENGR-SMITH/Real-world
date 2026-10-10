### 51_mainloop_probe.py -- build a tiny scene whose __main__ scene property points at a text block,
### then we run blenderplayer on it and see how the engine invokes the script.
### Run: UPBGE/blender.exe --background --factory-startup --python 51_mainloop_probe.py
import bpy, os, sys

OUT_BLEND = "E:/UPBGE/mainloop.blend"

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
sc = bpy.context.scene
sc.render.resolution_x = 320
sc.render.resolution_y = 180

bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 1))
cube = bpy.context.active_object
cube.name = "TestCube"
bpy.ops.object.camera_add(location=(0, -8, 3), rotation=(1.35, 0, 0))
sc.camera = bpy.context.active_object

SCRIPT = r'''
import bge, os, sys, time

LOG = r"E:/Reality/blender/gamework/mainloop.log"

def _log(msg):
    with open(LOG, "a") as f:
        f.write(msg + "\n")

_log("EXEC t=%.3f" % time.time())
try:
    _log("  bge.version=%r" % (getattr(bge, "version", None),))
    sc = bge.logic.getCurrentScene()
    _log("  scene=%s objs=%d" % (sc.name, len(sc.objects)))
    _log("  keys=%s" % (sorted([d for d in dir(bge.logic) if "key" in d.lower()]),))
    _log("  haslogic.KX=%s" % hasattr(bge.logic, "getCurrentController"))
    _log("  makeScreenshot=%s" % hasattr(bge.render, "makeScreenshot"))
    _log("  active_camera=%s" % (sc.active_camera.name if sc.active_camera else None,))
except Exception as e:
    _log("  ERR %r" % (e,))

# how many times have we been executed?
n = 0
try:
    n = int(open(r"E:/Reality/blender/gamework/mainloop.count").read())
except Exception:
    pass
n += 1
with open(r"E:/Reality/blender/gamework/mainloop.count", "w") as f:
    f.write(str(n))
_log("  exec_count=%d" % n)

if n >= 6:
    _log("STOPPING after %d execs" % n)
    try:
        bge.render.makeScreenshot(r"E:/UPBGE/mainloop_shot.png")
    except Exception as e:
        _log("  shot ERR %r" % (e,))
    bge.logic.endGame()
    raise SystemExit()
'''

txt = bpy.data.texts.new("game.py")
txt.write(SCRIPT)

# the engine-level custom main loop hook
sc["__main__"] = "game.py"

sc.game_settings.use_frame_rate = False
sc.frame_start = 1
sc.frame_end = 100

bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
print("### saved", OUT_BLEND)
print("### scene __main__ =", sc.get("__main__"))
print("MAINLOOP PROBE SETUP DONE")

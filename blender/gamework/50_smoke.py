### 50_smoke.py -- build a tiny UPBGE test scene and prove the in-game API works.
### Run with UPBGE blender.exe --background --factory-startup --python 50_smoke.py
import bpy, os, sys

def p(*a):
    print("STEP", *a)
    sys.stdout.flush()

OUT_BLEND = "E:/UPBGE/smoke.blend"
LOG = "E:/Reality/blender/gamework/smoke.log"

# --- wipe (do NOT use read_factory_settings: it crashes UPBGE's addon re-register)
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
sc = bpy.context.scene
sc.render.resolution_x = 480
sc.render.resolution_y = 270

# --- geometry
p("wipe done")
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 1))
cube = bpy.context.active_object
p("cube added", cube.name)
cube.name = "TestCube"
mat = bpy.data.materials.new("Red")
mat.diffuse_color = (1, 0, 0, 1)
cube.data.materials.append(mat)

bpy.ops.object.camera_add(location=(0, -8, 3), rotation=(1.35, 0, 0))
sc.camera = bpy.context.active_object
p("camera added")

# --- game script as a text datablock
SCRIPT = r'''
import bpy, os, sys
import bge

LOG = r"E:/Reality/blender/gamework/smoke.log"
SHOT = r"E:/UPBGE/smoke_shot.png"

_state = {"n": 0, "logged": False}

def main(cont):
    own = cont.owner
    if not _state["logged"]:
        _state["logged"] = True
        f = open(LOG, "w")
        f.write("### bge imported OK\n")
        f.write("### bge.version = %r\n" % (getattr(bge, "version", None),))
        f.write("### dir(bge) = %s\n" % (sorted([d for d in dir(bge) if not d.startswith("_")]),))
        f.write("### dir(bge.render) = %s\n" % (sorted([d for d in dir(bge.render) if not d.startswith("_")]),))
        f.write("### dir(bge.logic) = %s\n" % (sorted([d for d in dir(bge.logic) if not d.startswith("_")]),))
        f.write("### dir(bge.events) has WKEY: %s\n" % hasattr(bge.events, "WKEY"))
        f.write("### keyboard obj = %r\n" % (bge.logic.keyboard,))
        try:
            f.write("### keyboard.inputs len = %d\n" % len(bge.logic.keyboard.inputs))
        except Exception as e:
            f.write("### keyboard.inputs ERR %r\n" % (e,))
        f.write("### scene objs = %s\n" % (sorted([o.name for o in bge.logic.getCurrentScene().objects]),))
        f.write("### KX_GameObject attrs ok: %s\n" % (hasattr(bge.types.KX_GameObject, "worldPosition"),))
        f.write("### playAction: %s\n" % (hasattr(bge.types.KX_GameObject, "playAction"),))
        f.write("### libLoad: %s\n" % (hasattr(bge.logic, "LibLoad"),))
        f.write("### render.makeScreenshot: %s\n" % (hasattr(bge.render, "makeScreenshot"),))
        f.write("### scene.active_camera = %s\n" % (bge.logic.getCurrentScene().active_camera.name,))
        f.close()

    _state["n"] += 1
    n = _state["n"]
    # move the cube so we can SEE the engine is running
    own.worldPosition = (0, 0, 1.0 + 0.5 * __import__("math").sin(n * 0.2))

    if hasattr(bge.render, "makeScreenshot") and n == 12:
        try:
            bge.render.makeScreenshot(SHOT)
        except Exception as e:
            f = open(LOG, "a"); f.write("### screenshot ERR %r\n" % (e,)); f.close()

    if n >= 30:
        f = open(LOG, "a")
        f.write("### ran %d frames, cube z=%.3f\n" % (n, own.worldPosition.z))
        f.write("### SMOKE OK\n")
        f.close()
        bge.logic.endGame()
'''

txt = bpy.data.texts.new("smoke.py")
txt.write(SCRIPT)
p("text written")

# --- logic bricks: Always(True) -> Python(MODULE smoke.main)
p("about to add sensor")
bpy.ops.logic.sensor_add(type='ALWAYS', object=cube.name)
sens = cube.game.sensors[0]
p("sensor added")
sens.name = "Always"
sens.use_pulse_true_level = True
sens.frequency = 0

bpy.ops.logic.controller_add(type='PYTHON', object=cube.name)
ctrl = cube.game.controllers[0]
ctrl.name = "Py"
ctrl.mode = 'MODULE'
ctrl.module = "smoke.main"

bpy.ops.logic.actuator_add(type='MOTION', object=cube.name)  # keeps brick list valid
cube.game.actuators[0].name = "unused"

links = cube.game.sensors[0].link(ctrl)

print("### sensors", [s.name for s in cube.game.sensors])
print("### controllers", [(c.name, c.mode, getattr(c, "module", None)) for c in cube.game.controllers])

# --- scene game settings
sc.game_settings.use_frame_rate = False
sc.frame_start = 1
sc.frame_end = 100
try:
    sc.game_settings.deprecation_warnings = False
except Exception:
    pass

os.makedirs(os.path.dirname(OUT_BLEND), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
print("### saved", OUT_BLEND)
print("SMOKE SETUP DONE")

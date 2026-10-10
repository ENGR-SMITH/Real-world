"""baseline3.py -- is the scene slow because objects move every frame?

    blenderplayer -g noaudio -p baseline3.py Shop_with_people.blend
"""
import bge
import time

LOG = r"E:/Reality/blender/gamework/baseline3.log"
sc = bge.logic.getCurrentScene()
bge.logic.setMaxLogicFrame(1)
try:
    objs = list(sc.objects.values())
except AttributeError:
    objs = list(sc.objects)

log = open(LOG, "w")


def measure(tag, n=25, mover=None):
    t0 = time.time()
    for i in range(n):
        if mover is not None:
            mover(i)
        bge.logic.NextFrame()
    el = time.time() - t0
    log.write("%-34s %.4f s/frame  (%.2f fps)\n" % (tag, el / float(n), n / max(el, 1e-9)))
    log.flush()
    return el / float(n)


for _ in range(8):
    bge.logic.NextFrame()

cam = sc.active_camera
a = sc.objects.get("Boy1_RIG") or objs[0]
v = sc.objects.get("SUV_root")
cube = sc.objects.get("Cube.001")

log.write("objects=%d  cam=%s\n" % (len(objs), cam.name if cam else None))

measure("1) static, nothing moves")


def spin_rig(i):
    a.worldOrientation = ((0, 0, i * 0.01),)


def move_cube(i):
    if cube:
        cube.worldPosition = (cube.worldPosition.x, cube.worldPosition.y, 0.0)


def move_car(i):
    if v:
        v.worldPosition = (v.worldPosition.x, v.worldPosition.y + 0.01, v.worldPosition.z)


def move_cam(i):
    if cam:
        cam.worldPosition = (cam.worldPosition.x, cam.worldPosition.y, cam.worldPosition.z)


measure("2) one armature spun every frame", mover=spin_rig)
measure("3) static again")
measure("4) one shop box nudged every frame", mover=move_cube)
measure("5) the SUV moved every frame", mover=move_car)
measure("6) the camera moved every frame", mover=move_cam)

log.write("DONE\n")
log.close()

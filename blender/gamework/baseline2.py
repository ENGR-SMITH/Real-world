"""baseline2.py -- how does the frame cost scale with the number of visible objects?

Runs inside blenderplayer on the real scene and measures the same 40-frame window at
several levels of visibility, so one run gives the whole curve.

    blenderplayer -g noaudio -p baseline2.py Shop_with_people.blend
"""
import bge
import time

LOG = r"E:/Reality/blender/gamework/baseline2.log"
sc = bge.logic.getCurrentScene()
bge.logic.setMaxLogicFrame(1)

try:
    objs = list(sc.objects.values())
except AttributeError:
    objs = list(sc.objects)

log = open(LOG, "w")


def visible_count():
    n = 0
    for o in objs:
        try:
            if o.visible:
                n += 1
        except Exception:
            n += 1
    return n


def measure(tag, n=40):
    t0 = time.time()
    for _ in range(n):
        bge.logic.NextFrame()
    el = time.time() - t0
    log.write("%-28s visible=%4d  %.4f s/frame  (%.2f fps)\n" % (tag, visible_count(), el / n, n / el))
    log.flush()


def hide(pred):
    n = 0
    for o in objs:
        if pred(o):
            o.visible = False
            n += 1
    return n


# warm up so shader compilation is not counted
for _ in range(12):
    bge.logic.NextFrame()
log.write("objects=%d  cameras=%d  lights=%d\n" % (len(objs), len(sc.cameras), len(sc.lights)))
measure("1) everything visible")

step = max(1, len(objs) // 8)
sorted_objs = sorted(objs, key=lambda o: o.name)
hide(lambda o: "Cube" in o.name or "Plane" in o.name or "Circle" in o.name or "dose" in o.name)
measure("2) no shop clutter (Cube/Plane/Circle)")

hide(lambda o: "Boy" not in o.name and not o.name.startswith(("Camera", "Sun", "Point", "HUD", "P_", "Prop_")))
measure("3) boys + props + HUD only")

hide(lambda o: o.name.startswith(("HUD", "P_")))
measure("4) boys only, no HUD text")

hide(lambda o: o.name.startswith("Boy"))
measure("5) nothing but the camera and lights")

hide(lambda o: True)
measure("6) empty scene, no lights either")

log.write("DONE\n")
log.close()

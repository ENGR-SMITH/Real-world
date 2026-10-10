"""9a_check_installed.py -- is the saved blend's game.py the one on disk?

    blender.exe -b --factory-startup --python 9a_check_installed.py
"""
import bpy

BLEND = "E:/Reality/ECO/Bussiness/Mall/MiniMarket/Shop_with_people.blend"
SRC = "E:/Reality/blender/gamework/game.py"

bpy.ops.wm.open_mainfile(filepath=BLEND)
body = bpy.data.texts["game.py"].as_string()
with open(SRC, "r", encoding="utf-8") as fh:
    disk = fh.read()

print("### installed bytes %d  disk bytes %d  identical %s" % (len(body), len(disk), body == disk))
for key in ("TAKE_RANGE", "FACE_CONE"):
    print("### %s:" % key, [l.strip() for l in body.splitlines() if l.startswith(key)])
print("### facing_angle present:", "def facing_angle" in body)
print("### pick-up merits the item the boy faces:",
      "faced = [c for c in reach if c[0] < FACE_CONE]" in body)
print("### scene __main__ =", bpy.context.scene.get("__main__"))
print("### file", bpy.data.filepath)

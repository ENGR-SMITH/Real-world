### gtext.py -- install a python source file as a text datablock in a .blend and save.
### Usage: blender --background --python gtext.py -- <blend> <src.py> [textname] [mainloop]
import bpy, sys, os

argv = sys.argv
if "--" in argv:
    argv = argv[argv.index("--") + 1:]
else:
    argv = []

blend = argv[0]
src = argv[1]
name = argv[2] if len(argv) > 2 else "game.py"
mainloop = (argv[3] if len(argv) > 3 else "yes") == "yes"

bpy.ops.wm.open_mainfile(filepath=blend)
code = open(src, "r", encoding="utf-8").read()
t = bpy.data.texts.get(name)
if t is None:
    t = bpy.data.texts.new(name)
t.clear()
t.write(code)
t.use_module = True

for sc in bpy.data.scenes:
    if mainloop:
        sc["__main__"] = name
    else:
        sc["__main__"] = ""

# start on the playable scene
if bpy.data.filepath:
    pass

bpy.ops.wm.save_as_mainfile(filepath=blend)
print("### installed %s as text %r (%d chars) into %s" % (src, name, len(code), blend))
print("### scene __main__ =", bpy.context.scene.get("__main__"))
print("GTEXT DONE")

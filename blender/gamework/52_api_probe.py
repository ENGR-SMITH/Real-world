### swap the game.py text for the API probe and save
import bpy
BLEND = "E:/UPBGE/mainloop.blend"
bpy.ops.wm.open_mainfile(filepath=BLEND)
src = open("E:/Reality/blender/gamework/52_api_probe_text.py").read()
t = bpy.data.texts["game.py"]
t.clear()
t.write(src)
bpy.context.scene["__main__"] = "game.py"
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print("### swapped")

"""94_clean.py -- put mini.blend back to the plain probe scene (no X_cube)."""
import bpy
bpy.ops.wm.open_mainfile(filepath="E:/UPBGE/mini.blend")
for o in list(bpy.data.objects):
    if o.name.startswith("X_"):
        bpy.data.objects.remove(o, do_unlink=True)
print("### removed X_ objects")
bpy.ops.wm.save_mainfile()
print("### saved")

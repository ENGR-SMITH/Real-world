"""91_bigwall.py -- is makeScreenshot rendering from the scene camera at all?

Adds one 4x4 m bright red wall 3 m in front of MiniCam.  If the shot is rendered
from MiniCam the wall covers the frame; if it is rendered from the engine's
__default__cam__ at (15, -6.7, 8.2) the wall is a distant sliver.
"""
import bpy
from mathutils import Vector

bpy.ops.wm.open_mainfile(filepath="E:/UPBGE/mini.blend")
sc = bpy.context.scene
for o in list(bpy.data.objects):
    if o.name.startswith("B_"):
        bpy.data.objects.remove(o, do_unlink=True)
me = bpy.data.meshes.new("B_wall")
me.from_pydata([(-2, -2, 0), (2, -2, 0), (2, 2, 0), (-2, 2, 0)], [], [(0, 1, 2, 3)])
me.update()
m = bpy.data.materials.new("B_mat")
m.use_nodes = True
nt = m.node_tree
nt.nodes.clear()
em = nt.nodes.new("ShaderNodeEmission"); em.inputs[0].default_value = (1, 0, 0, 1)
out = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(em.outputs[0], out.inputs[0])
me.materials.append(m)
o = bpy.data.objects.new("B_wall", me)
sc.collection.objects.link(o)
o.location = (0, 0, -3)
print("### camera=%s B_wall at %s" % (sc.camera.name, tuple(o.location)))
bpy.ops.wm.save_mainfile()
print("### saved")

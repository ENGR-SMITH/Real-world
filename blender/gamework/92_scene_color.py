"""92_scene_color.py -- does the screenshot actually depend on the scene?

Sets the world background to pure magenta and the ground to pure yellow.  If the
next shot is still grey-green with a blue sky, makeScreenshot is not rendering
this scene at all.
"""
import bpy
bpy.ops.wm.open_mainfile(filepath="E:/UPBGE/mini.blend")
sc = bpy.context.scene
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (1.0, 0.0, 1.0, 1.0)
m = bpy.data.materials.get("GroundMat")
nt = m.node_tree
nt.nodes.clear()
em = nt.nodes.new("ShaderNodeEmission")
em.inputs[0].default_value = (1.0, 1.0, 0.0, 1.0)
out = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(em.outputs[0], out.inputs[0])
print("### world=magenta ground=yellow")
bpy.ops.wm.save_mainfile()
print("### saved")

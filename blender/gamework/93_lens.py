"""93_lens.py -- is the screenshot rendered from the engine's __default__cam__?

Drops a 5 m bright red cube centred on the engine default camera at
(15.036, -6.696, 8.198).  If the shot turns red, that camera - and not MiniCam -
is what makeScreenshot renders from.
"""
import bpy
bpy.ops.wm.open_mainfile(filepath="E:/UPBGE/mini.blend")
sc = bpy.context.scene
for o in list(bpy.data.objects):
    if o.name.startswith("X_"):
        bpy.data.objects.remove(o, do_unlink=True)
me = bpy.data.meshes.new("X_cube")
s = 2.5
vs = [(-s, -s, -s), (s, -s, -s), (s, s, -s), (-s, s, -s),
      (-s, -s, s), (s, -s, s), (s, s, s), (-s, s, s)]
fs = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
me.from_pydata(vs, [], fs)
me.update()
m = bpy.data.materials.new("X_mat")
m.use_nodes = True
nt = m.node_tree
nt.nodes.clear()
em = nt.nodes.new("ShaderNodeEmission"); em.inputs[0].default_value = (1, 0, 0, 1)
out = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(em.outputs[0], out.inputs[0])
me.materials.append(m)
o = bpy.data.objects.new("X_cube", me)
sc.collection.objects.link(o)
o.location = (15.036, -6.696, 8.198)
print("### X_cube at", tuple(o.location))
bpy.ops.wm.save_mainfile()
print("### saved")

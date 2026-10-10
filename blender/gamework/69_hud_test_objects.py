"""69_hud_test_objects.py -- control objects that isolate why the HUD stays invisible.

67_hud_depth.py proved the HUD geometry reaches the engine one metre in front of
the lens, inside the frustum, and 66/68 proved it never puts a single pixel on
screen.  So: is it the material, the camera parenting, or the converted mesh?
This drops five test objects into a *copy* of the blend, each varying one thing,
and the run that follows tells us which of them draws.

    A  cube, child of Camera_Game, HUD_Text material      (the HUD's own material)
    B  cube, child of Camera_Game, plain node-less green  (old-style material)
    C  cube, child of Camera_Game, Principled white       (standard node material)
    D  cube, world object 1 m in front of the camera, HUD_Text  (no camera parent)
    E  copy of HUD_Help, world object 1 m in front, HUD_Text    (the real HUD mesh)

    blender.exe -b hud_test.blend --python 69_hud_test_objects.py
"""

import bpy

P = print
CAM = "Camera_Game"


def plain(name, rgba):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = False
    m.diffuse_color = rgba
    return m


def pbr(name, rgba):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = rgba
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    return m


cam = bpy.data.objects[CAM]
sc = bpy.context.scene
hud_mat = bpy.data.materials.get("HUD_Text")
P("### hud material HUD_Text:", hud_mat, "nodes:", hud_mat.use_nodes if hud_mat else None)

for nm in ("QQ_A", "QQ_B", "QQ_C", "QQ_D", "QQ_E", "QQ_F", "QQ_G",
           "QQ_H", "QQ_HUDHELP"):
    o = bpy.data.objects.get(nm)
    if o:
        bpy.data.objects.remove(o, do_unlink=True)

MESH = bpy.data.meshes.new("QQ_cube")
import bmesh
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=0.08)
bm.to_mesh(MESH)
bm.free()

# camera-space cubes
for nm, loc, mat in (("QQ_A", (0.25, 0.15, -1.0), hud_mat),
                     ("QQ_B", (0.25, 0.00, -1.0), plain("QQ_Plain", (0.0, 1.0, 0.0, 1.0))),
                     ("QQ_C", (0.25, -0.15, -1.0), pbr("QQ_PBR", (0.1, 0.3, 1.0, 1.0)))):
    o = bpy.data.objects.new(nm, MESH)
    sc.collection.objects.link(o)
    o.data.materials.clear()
    o.data.materials.append(mat)
    o.parent = cam
    o.matrix_parent_inverse.identity()
    o.location = loc
    o.rotation_euler = (0, 0, 0)
    P("### %s parent=%s local=%s mat=%s" % (nm, o.parent.name, tuple(o.location), mat.name))

# world cubes ~1 m in front of the settled camera (-5.0, 1.35, 1.96) looking -Y, 12 deg down
for nm, loc, mat in (("QQ_D", (-4.75, 0.55, 1.90), hud_mat),
                     ("QQ_E", (-4.75, 0.55, 1.70), hud_mat)):
    o = bpy.data.objects.new(nm, MESH)
    sc.collection.objects.link(o)
    o.data.materials.clear()
    o.data.materials.append(mat)
    o.location = loc
    o.scale = (2.0, 2.0, 2.0)
    P("### %s parent=%s world=%s mat=%s" % (nm, o.parent, tuple(o.location), mat.name))

hud = bpy.data.objects.get("HUD_Help")
if hud:
    e = hud.copy()
    e.data = hud.data.copy()
    e.name = "QQ_HUDHELP"
    e.parent = None
    sc.collection.objects.link(e)
    e.location = (-4.75, 0.55, 1.50)
    P("### QQ_HUDHELP copy of HUD_Help, world=%s verts=%d mats=%s" % (
        tuple(e.location), len(e.data.vertices), [m.name for m in e.data.materials]))
else:
    P("### HUD_Help missing")

# plain world objects on the road: same three materials, ordinary place in the scene
for nm, loc, mat, scl in (
        ("QQ_F", (-8.0, -6.0, 0.5), plain("QQ_Plain", (0.0, 1.0, 0.0, 1.0)), (8, 8, 8)),
        ("QQ_G", (-8.0, -8.0, 0.5), hud_mat, (8, 8, 8)),
        ("QQ_H", (-8.0, -10.0, 0.5), pbr("QQ_PBR", (0.1, 0.3, 1.0, 1.0)), (8, 8, 8))):
    o = bpy.data.objects.new(nm, MESH)
    sc.collection.objects.link(o)
    o.data.materials.clear()
    o.data.materials.append(mat)
    o.location = loc
    o.scale = scl
    P("### %s world=%s scale=%s mat=%s" % (nm, tuple(o.location), scl, mat.name))

P("### saving")
bpy.ops.wm.save_mainfile()
P("### saved %s" % bpy.data.filepath)

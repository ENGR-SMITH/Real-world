"""90_mini.py -- isolate the HUD problem in a tiny scene.

Dark background, dark ground, and probes that each own a unique colour so a
screenshot answers every question at once:

    M_TxtCam   camera child, local (-0.281, 0.095, -1.0)   RED
    M_TxtW1    world space, 1 m in front                   BLUE
    M_Cbe050   world space, 0.50 m, 0.030 cube             GREEN
    M_Cbe100   world space, 1.00 m, 0.060 cube             CYAN
    M_Cbe200   world space, 2.00 m, 0.120 cube             WHITE
    M_Cbe500   world space, 5.00 m, 0.300 cube             YELLOW
    M_Cbe999   world space, 10.0 m, 0.600 cube             MAGENTA

All cubes sit at the same screen spot, so their size on screen is identical and
only the distance differs.

    blender.exe -b --factory-startup --python 90_mini.py      (builds mini.blend)
    blenderplayer.exe -g noaudio -p 90_mini_loop.py mini.blend
"""

import bpy

P = print
OUT = "E:/UPBGE/mini.blend"

sc = bpy.context.scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

# ---------------------------------------------------------------- scene
me = bpy.data.meshes.new("Ground")
me.from_pydata([(-30, -30, 0), (30, -30, 0), (30, 30, 0), (-30, 30, 0)], [], [(0, 1, 2, 3)])
me.update()
gm = bpy.data.materials.new("GroundMat")
gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.06, 0.06, 0.07, 1)
me.materials.append(gm)
ground = bpy.data.objects.new("Ground", me)
# the camera looks down -Z from the origin, so the ground must sit BELOW that
# axis or it hides every probe (the first version of this scene did exactly that)
ground.location = (0.0, 0.0, -1.2)
sc.collection.objects.link(ground)

cd = bpy.data.cameras.new("MiniCam")
cd.lens = 32.0
cd.sensor_width = 36.0
cd.clip_start = 0.05
cd.clip_end = 500.0
cam = bpy.data.objects.new("MiniCam", cd)
cam.location = (0.0, 0.0, 0.0)
cam.rotation_euler = (0.0, 0.0, 0.0)          # looking down -Z, up +Y
sc.collection.objects.link(cam)
sc.camera = cam

wd = bpy.data.worlds.new("MiniWorld")
wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.02, 0.10, 1)
sc.world = wd

# ---------------------------------------------------------------- materials
def unlit(name, rgba):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs[0].default_value = rgba
    em.inputs[1].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs[0])
    m.diffuse_color = rgba
    return m


FONT = bpy.data.fonts.get("Bfont Regular")
HALF_W, HALF_H = 0.5625, 0.3164       # half frustum at 1 m
NDC_X, NDC_Y = -0.55, 0.30


def make_text(name, body, size, loc, rgba, parent):
    cu = bpy.data.curves.new(name, type='FONT')
    o = bpy.data.objects.new(name, cu)
    sc.collection.objects.link(o)
    if FONT is not None:
        cu.font = FONT
    cu.body = body
    cu.size = size
    cu.align_x = 'LEFT'
    cu.align_y = 'TOP'
    o.data.materials.clear()
    o.data.materials.append(unlit(name + "_mat", rgba))
    o.location = loc
    if parent is not None:
        o.parent = parent
        o.matrix_parent_inverse.identity()
    return o


def make_cube(name, size, dist, rgba):
    m = bpy.data.meshes.new(name)
    s = size * 0.5
    vs = [(-s, -s, -s), (s, -s, -s), (s, s, -s), (-s, s, -s),
          (-s, -s, s), (s, -s, s), (s, s, s), (-s, s, s)]
    fs = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    m.from_pydata(vs, [], fs)
    m.update()
    m.materials.append(unlit(name + "_mat", rgba))
    o = bpy.data.objects.new(name, m)
    sc.collection.objects.link(o)
    o.location = (NDC_X * HALF_W * dist, NDC_Y * HALF_H * dist, -dist)
    return o


make_text("M_TxtCam", "HUD CAMERA CHILD", 0.05, (-0.281, 0.095, -1.0), (1, 0, 0, 1), cam)
make_text("M_TxtW1", "HUD WORLD 1M", 0.05, (-0.309, 0.095, -1.0), (0, 0.4, 1, 1), None)

PROBES = [
    ("M_Cbe050", 0.50, 0.030, (0, 1, 0, 1)),
    ("M_Cbe100", 1.00, 0.060, (0, 1, 1, 1)),
    ("M_Cbe200", 2.00, 0.120, (1, 1, 1, 1)),
    ("M_Cbe500", 5.00, 0.300, (1, 1, 0, 1)),
    ("M_Cbe999", 10.0, 0.600, (1, 0, 1, 1)),
]
for nm, dist, size, col in PROBES:
    o = make_cube(nm, size, dist, col)
    P("### %s dist=%.2f size=%.3f loc=%s" % (
        nm, dist, size, tuple(round(v, 3) for v in o.location)))

# ---------------------------------------------------------------- game loop
GAME = '''import bge

SHOT = "__SHOT__"
LOG = "__LOG__"


def L(msg):
    f = open(LOG, "a")
    f.write(str(msg) + "\\n")
    f.close()


def main():
    n = 0
    sc = bge.logic.getCurrentScene()
    L("## start active_camera=%s pos=%s" % (
        sc.active_camera.name, tuple(round(v, 3) for v in sc.active_camera.worldPosition)))
    mine = sc.objects.get("MiniCam")
    if mine is not None:
        sc.active_camera = mine
    while True:
        n += 1
        if n == 20:
            L("## frame 20 active_camera=%s" % sc.active_camera.name)
            bge.render.makeScreenshot(SHOT)
            L("## screenshot requested")
        if n == 60:
            L("## done")
            bge.logic.endGame()
        bge.logic.NextFrame()


main()
'''

txt = bpy.data.texts.get("mini_game.py") or bpy.data.texts.new("mini_game.py")
txt.clear()
txt.write(GAME.replace("__SHOT__", "E:/UPBGE/mini.png").replace("__LOG__", "E:/UPBGE/mini.log.txt"))

sc["__main__"] = "mini_game.py"
sc.game_settings.fps = 60
sc.frame_end = 100

P("### objects:", sorted(o.name for o in sc.objects))
P("### saving", OUT)
bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=False)
P("### saved")

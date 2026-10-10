"""74_cycles_check.py -- is the HUD/test geometry sane, independent of the game engine?

Cycles knows nothing about the engine's draw path: it renders whatever is in the
scene and visible.  Point the saved Camera_Game at the pose the game left it in
(-5.0, 1.35, 1.96), render, and look.  If the HUD text and the test cubes appear
here, the data is fine and the engine's rasteriser is the problem; if they do not,
the objects themselves are broken.

    blender.exe -b hud_test.blend --python 74_cycles_check.py
"""

import bpy
from mathutils import Matrix

P = print
sc = bpy.context.scene
cam = bpy.data.objects["Camera_Game"]
sc.camera = cam
cam.matrix_world = Matrix((
    (-1.0, 0.0, 0.0, -5.0),
    (0.0, -0.2045, 0.9789, 1.35),
    (0.0, 0.9789, 0.2045, 1.96),
    (0.0, 0.0, 0.0, 1.0),
))
P("### camera world %s" % (tuple(round(v, 3) for v in cam.matrix_world.translation),))
P("### cam data clip %.3f..%.1f lens %.1f sensor %.1f" % (
    cam.data.clip_start, cam.data.clip_end, cam.data.lens, cam.data.sensor_width))
P("### cam.data.type=%s" % cam.data.type)
P("### hud/local z: %s" % [
    (o.name, tuple(round(v, 3) for v in o.location))
    for o in bpy.data.objects if o.name.startswith(("HUD_", "P_"))][:3])

sc.render.engine = 'CYCLES'
sc.cycles.samples = 12
sc.cycles.use_denoising = False
sc.render.resolution_x = 640
sc.render.resolution_y = 360
sc.render.resolution_percentage = 100
sc.render.filepath = "E:/UPBGE/cyc_from_gamecam.png"
sc.render.image_settings.file_format = 'PNG'
P("### rendering from the game camera")
bpy.ops.render.render(write_still=True)

# and a camera looking at the HUD from a metre to the side, to read the text
side = bpy.data.objects.new("QQ_SideCam", bpy.data.cameras.new("QQ_SideCam"))
sc.collection.objects.link(side)
side.location = (-5.0, 1.35, 2.6)
rc = side.constraints.new('TRACK_TO')
rc.target = bpy.data.objects.get("HUD_Help")
side.data.lens = 50.0
sc.camera = side
sc.render.filepath = "E:/UPBGE/cyc_hud_side.png"
P("### rendering the HUD from the side")
bpy.ops.render.render(write_still=True)
P("### CYCLES CHECK DONE")

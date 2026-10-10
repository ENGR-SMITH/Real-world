"""Throw-away camera + render helper used to verify the scene while building it."""
import bpy
from mathutils import Vector


def look_at(cam_obj, target):
    d = Vector(target) - cam_obj.location
    cam_obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def shot(path, loc, target, lens=35, engine='BLENDER_WORKBENCH', res=(900, 560), samples=24, frame=None):
    sc = bpy.context.scene
    pe, pc = sc.render.engine, sc.camera
    pf = sc.frame_current
    cd = bpy.data.cameras.new('TMP_SHOT')
    co = bpy.data.objects.new('TMP_SHOT', cd)
    sc.collection.objects.link(co)
    sc.camera = co
    cd.lens = lens
    co.location = loc
    look_at(co, target)
    sc.render.engine = engine
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = path
    if engine != 'BLENDER_WORKBENCH':
        try:
            sc.eevee.taa_render_samples = samples
        except Exception:
            pass
    if frame is not None:
        sc.frame_set(frame)
    bpy.ops.render.render(write_still=True)
    sc.render.engine = pe
    sc.camera = pc
    sc.frame_set(pf)
    bpy.data.objects.remove(co, do_unlink=True)
    bpy.data.cameras.remove(cd)
    print('SHOT', path)

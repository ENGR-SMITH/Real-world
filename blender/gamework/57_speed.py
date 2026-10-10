"""Make the blend run its game properly.

Two problems found while profiling:
  * the scene's render engine is CYCLES, which UPBGE 0.50 does not even ship -- its
    only engine is BLENDER_EEVEE, so the game was running on a fallback path
  * the file was saved with auto-run disabled, so the scene's "__main__" script was
    skipped on load ("scripts disabled for ..., skipping 'game.py'")

Run: UPBGE/blender.exe --background --factory-startup --python 57_speed.py
"""
import bpy

FILE = "E:/Reality/ECO/Bussiness/Mall/MiniMarket/Shop_with_people.blend"

bpy.ops.wm.open_mainfile(filepath=FILE)
sc = bpy.context.scene
g = sc.game_settings

print("### before: engine=%s game.samples=%s samp_per_frame=%s vsync=%s" % (
    sc.render.engine, g.samples, g.samp_per_frame, g.vsync))
print("###   use_frame_rate=%s use_activity_culling=%s use_restrict_animation_updates=%s" % (
    g.use_frame_rate, g.use_activity_culling, g.use_restrict_animation_updates))

sc.render.engine = 'BLENDER_EEVEE'
sc.render.film_transparent = False
g.use_frame_rate = True
g.vsync = bpy.types.SceneGameData.bl_rna.properties['vsync'].enum_items[0].identifier \
    if 'vsync' in bpy.types.SceneGameData.bl_rna.properties else g.vsync
try:
    g.samples = 1
except Exception as e:
    print("### samples not settable:", e)
try:
    g.use_restrict_animation_updates = True
except Exception as e:
    print("### restrict not settable:", e)
try:
    g.use_viewport_render = False
except Exception as e:
    print("### viewport_render not settable:", e)
g.show_fullscreen = False
try:
    g.occlusion_culling_resolution = 256
except Exception as e:
    print("### occlusion not settable:", e)

print("### after : engine=%s game.samples=%s vsync=%s restrict=%s" % (
    sc.render.engine, g.samples, g.vsync, g.use_restrict_animation_updates))
print("### vsync options:",
      [e.identifier for e in bpy.types.SceneGameData.bl_rna.properties['vsync'].enum_items])

# allow this file's scripts to run: this only affects this session's save, the
# user's global preferences are left alone
try:
    bpy.context.preferences.filepaths.use_scripts_auto_execute = True
    print("### auto-execute enabled for this save")
except Exception as e:
    print("### could not set auto-execute:", e)

bpy.ops.wm.save_mainfile()
print("### saved", bpy.data.filepath)
print("SPEED DONE")

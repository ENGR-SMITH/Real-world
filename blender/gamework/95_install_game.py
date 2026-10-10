"""95_install_game.py -- push the game.py on disk into the deliverable's text block.

Re-runs of 56_build_game.py regenerate every world number and the reachability
BFS; when only the script changed, that is wasted work.  This just replaces the
text datablock and saves.

    blender.exe -b --factory-startup --python 95_install_game.py
"""

import bpy

P = print
BLEND = "E:/Reality/ECO/Bussiness/Mall/MiniMarket/Shop_with_people.blend"
SRC = "E:/Reality/blender/gamework/game.py"

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene

with open(SRC, "r", encoding="utf-8") as fh:
    body = fh.read()

txt = bpy.data.texts.get("game.py")
if txt is None:
    txt = bpy.data.texts.new("game.py")
txt.clear()
txt.write(body)
P("### installed %d bytes into the 'game.py' text block" % len(body))

sc["__main__"] = "game.py"
P("### scene__main__ =", sc.get("__main__"))
P("### fps =", sc.game_settings.fps, "engine =", sc.render.engine)

need = ("use_scripts_auto_execute",)
prefs = bpy.context.preferences.filepaths
P("### scripts-auto-execute =", prefs.use_scripts_auto_execute)

bpy.ops.wm.save_mainfile()
P("### saved", bpy.data.filepath)

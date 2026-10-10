"""64_hud_fix.py -- turn the HUD font objects into meshes and save the blend.

Text objects never reach the rasteriser in the UPBGE 0.50 player: the game log
lists all 13 of them, their parent chain is right and they sit a metre in front
of the lens, yet nothing of them shows up in a screenshot. Converting the curve
data to a mesh gives the engine real geometry to draw.

    blender.exe -b Shop_with_people.blend --python 64_hud_fix.py
"""

import bpy

P = print
HUD_PREFIX = ("HUD_", "P_")

bpy.ops.object.select_all(action='DESELECT')
names = []
for o in list(bpy.data.objects):
    if not o.name.startswith(HUD_PREFIX):
        continue
    if o.type == 'MESH':
        names.append((o.name, "already a mesh"))
        continue
    if not o.data:
        names.append((o.name, "no data"))
        continue
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    try:
        bpy.ops.object.convert(target='MESH')
        n = len(o.data.polygons) if o.type == 'MESH' else -1
        names.append((o.name, "%s verts=%d faces=%d" % (o.type, len(o.data.vertices), n)))
    except Exception as exc:
        names.append((o.name, "convert failed: %r" % (exc,)))
    o.select_set(False)

for nm, what in names:
    P("### hud %-14s %s" % (nm, what))

# the parent must survive the conversion, and every glyph needs the emission material
for o in bpy.data.objects:
    if not o.name.startswith(HUD_PREFIX) or o.type != 'MESH':
        continue
    if o.parent is None or o.parent.name != "Camera_Game":
        P("### WARNING %s lost its camera parent (%s)" % (o.name, o.parent))
    if not o.data.materials:
        P("### WARNING %s has no material" % o.name)

P("### saving")
bpy.ops.wm.save_mainfile()
P("### saved %s" % bpy.data.filepath)

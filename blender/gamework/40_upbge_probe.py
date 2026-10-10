"""De-risk: can UPBGE 0.50 open our Blender 4.5 scene, and is the game engine there?"""
import bpy
import sys

print("### blender", bpy.app.version_string, bpy.app.version)
print("### file", bpy.data.filepath)
try:
    import bge
    print("### bge module: YES  submodules:", [n for n in dir(bge) if n in ('logic', 'events', 'render', 'constraints', 'types')])
    from bge import logic, events
    print("### bge.logic attrs:", [n for n in dir(logic) if 'Action' in n or 'action' in n][:12])
    print("### bge.events keys sample:", [n for n in dir(events) if n.startswith('WKEY') or n.startswith('UPARROW') or n.startswith('EKEY')][:10])
except Exception as e:
    print("### bge module: NO ->", repr(e))

cam = bpy.data.objects.get('Camera')
print("### Object.game present:", hasattr(cam, 'game'))
if hasattr(cam, 'game'):
    try:
        print("### physics types:", [i.identifier for i in cam.game.bl_rna.properties['physics_type'].enum_items][:8])
    except Exception as e:
        print("### physics enum err", e)
print("### scene.game present:", hasattr(bpy.context.scene, 'game'))
print("### objects:", len(bpy.data.objects), " meshes:", len(bpy.data.meshes), " actions:", len(bpy.data.actions))
print("### actions:", sorted(a.name for a in bpy.data.actions))
for n in ('Boy1_RIG', 'Boy2_RIG', 'Shop_Door_L', 'Shop_Door_R', 'SUV_Door_FR', 'SUV_root', 'TukTuk_root'):
    o = bpy.data.objects.get(n)
    print("###  %-14s %s" % (n, ('missing' if o is None else
                                '%s verts=%s parent=%s phys=%s' % (o.type, 
                                 getattr(o.data, 'vertices', None) and len(o.data.vertices),
                                 o.parent.name if o.parent else '-',
                                 o.game.physics_type if hasattr(o, 'game') else '?'))))
body = bpy.data.objects.get('Boy1_body')
if body:
    print("### Boy1_body verts:", len(body.data.vertices), "mods:", [m.type for m in body.modifiers],
          "materials:", [ms.material.name for ms in body.material_slots])
print("### texts:", [t.name for t in bpy.data.texts])
print("UPBGE PROBE DONE")

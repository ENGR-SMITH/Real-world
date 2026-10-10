"""96_verify.py -- final state check on the deliverable."""
import bpy
S = "E:/Reality/ECO/Bussiness/Mall/MiniMarket/Shop_with_people.blend"
bpy.ops.wm.open_mainfile(filepath=S)
sc = bpy.context.scene
P = print
P("### file            ", bpy.data.filepath)
P("### scene           ", sc.name, " fps", sc.game_settings.fps, " engine", sc.render.engine)
P("### __main__        ", sc.get("__main__"))
P("### text blocks     ", sorted(t.name for t in bpy.data.texts))
P("### scene camera    ", sc.camera.name if sc.camera else None)
P("### cameras         ", sorted(o.name for o in sc.objects if o.type == 'CAMERA'))
boys = sorted(o.name for o in sc.objects if o.name.startswith("Boy") and o.name.endswith("_RIG"))
P("### rigs            ", boys)
for nm in boys:
    a = bpy.data.objects[nm]
    P("###   %-10s %s scale %.3f" % (nm, tuple(round(v, 2) for v in a.location),
                                    a.scale.x))
P("### clips           ", sorted(x.name for x in bpy.data.actions if x.name in
                                 ("walk", "idle", "reach", "sit")))
hud = sorted(o.name for o in sc.objects if o.name.startswith(("HUD_", "P_")))
kinds = {}
for nm in hud:
    kinds.setdefault(bpy.data.objects[nm].type, []).append(nm)
P("### hud objects %d " % len(hud), {k: len(v) for k, v in kinds.items()})
P("### hud verts       ", sum(len(bpy.data.objects[n].data.vertices)
                              for n in hud if bpy.data.objects[n].type == 'MESH'))
for nm in ("Shop_Door_L", "Shop_Door_R", "SUV_Door_FR", "SUV_root", "TukTuk_root"):
    o = bpy.data.objects.get(nm)
    P("### %-14s %s" % (nm, "present" if o else "MISSING"))
props = sorted(o.name for o in sc.objects if o.name.startswith("Prop_Item_"))
P("### props           ", props)
P("### objects in scene", len(sc.objects))

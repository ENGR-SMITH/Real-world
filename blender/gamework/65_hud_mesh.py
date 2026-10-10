"""65_hud_mesh.py -- the HUD font objects have to become meshes before UPBGE draws them.

63_hud_probe.py proved the HUD objects are alive, parented to Camera_Game, flagged
visible and sitting a metre in front of the lens -- yet the rasteriser reports
`meshes=0` for every one of them, because they are FONT/curve objects and the
UPBGE player only ever draws meshes.

Convert each one in place, keep the name, the camera parent and the HUD_Text
emission material, then print the resulting geometry counts and save.

    blender.exe -b Shop_with_people.blend --python 65_hud_mesh.py
"""

import bpy

P = print
PREFIX = ("HUD_", "P_")
LOG = "E:/UPBGE/hud_mesh.log"
_lines = []


def note(s):
    _lines.append(s)
    P("### " + s)


def dump(o):
    if o.type != 'MESH':
        note("  %-13s type=%s  (no mesh)" % (o.name, o.type))
        return
    me = o.data
    mats = [m.name for m in me.materials] or ["<none>"]
    note("  %-13s mesh verts=%-6d faces=%-6d mats=%s parent=%s cam=%s" % (
        o.name, len(me.vertices), len(me.polygons), mats,
        o.parent.name if o.parent else None, o.visible_camera))


def convert_ops(o):
    """bpy.ops.object.convert in place: keeps name, parent, transform, materials."""
    with bpy.context.temp_override(active_object=o, object=o,
                                   selected_objects=[o],
                                   selected_editable_objects=[o]):
        bpy.ops.object.convert(target='MESH')
    return o.type == 'MESH' and len(o.data.vertices) > 0


def convert_manual(o):
    """Fallback: swap the curve object for a mesh object carrying the same pose."""
    ev = o.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=False)
    if not len(me.vertices):
        return False, me
    name = o.name
    loc, rot, scl = o.location.copy(), o.rotation_euler.copy(), o.scale.copy()
    parent, mpi = o.parent, o.matrix_parent_inverse.copy()
    mats = list(o.data.materials)
    colls = list(o.users_collection)
    hide = o.hide_viewport
    bpy.data.objects.remove(o, do_unlink=True)
    new = bpy.data.objects.new(name, me)
    for c in colls:
        c.objects.link(new)
    for m in mats:
        me.materials.append(m)
    new.parent = parent
    new.matrix_parent_inverse = mpi
    new.location = loc
    new.rotation_euler = rot
    new.scale = scl
    new.hide_viewport = hide
    new.hide_render = False
    new.visible_camera = True
    return True, me


def main():
    cam = bpy.data.objects.get("Camera_Game")
    if cam:
        note("camera '%s' lens=%.1f clip=%.3f..%.1f" % (
            cam.name, cam.data.lens, cam.data.clip_start, cam.data.clip_end))
    else:
        note("camera Camera_Game is MISSING")

    todo = sorted((o.name for o in bpy.data.objects if o.name.startswith(PREFIX)))
    note("hud objects: %d %s" % (len(todo), todo))

    for nm in todo:
        o = bpy.data.objects.get(nm)
        if o is None:
            note("  %-13s vanished" % nm)
            continue
        if o.type == 'MESH':
            note("  %-13s already a mesh" % nm)
            continue
        if o.type != 'FONT':
            note("  %-13s unexpected type %s" % (nm, o.type))
            continue
        ok = False
        try:
            ok = convert_ops(o)
            how = "ops"
        except Exception as exc:
            note("  %-13s ops convert raised %r" % (nm, exc))
            how = "manual"
        if not ok:
            how = "manual"
            try:
                ok, _me = convert_manual(bpy.data.objects.get(nm) or o)
            except Exception as exc:
                note("  %-13s manual convert raised %r" % (nm, exc))
                ok = False
        note("  %-13s converted via %s -> %s" % (nm, how, "ok" if ok else "FAILED"))

    note("after conversion:")
    for nm in todo:
        o = bpy.data.objects.get(nm)
        if o is None:
            note("  %-13s MISSING" % nm)
            continue
        dump(o)

    note("camera parent check:")
    for nm in todo:
        o = bpy.data.objects.get(nm)
        if o is None:
            continue
        if o.parent is None or o.parent.name != "Camera_Game":
            note("  WARNING %s parent is %s" % (nm, o.parent.name if o.parent else None))

    note("saving")
    bpy.ops.wm.save_mainfile()
    note("saved %s" % bpy.data.filepath)

    with open(LOG, "w") as fh:
        fh.write("\n".join(_lines) + "\n")


main()

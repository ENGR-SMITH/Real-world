"""Turn the imported Boy rig into a game-ready character in the live scene.

* unhide it (source file had everything hidden)
* drop authoring-only modifiers, bake the geometric ones (subsurf/solidify/mask/...)
* remove object-level drivers that fight our manual placement
* scale the 12.03-unit rig down to human size and stand it on the pavement
"""
import bpy
import mathutils

ARM_NAME = 'Boy_RIG'
COLL_NAME = 'Boy_character'
TARGET_HEIGHT = 1.62


def p(*a):
    print(*a)


arm = bpy.data.objects[ARM_NAME]
coll = bpy.data.collections.get(COLL_NAME)


def char_meshes():
    return [o for o in bpy.data.objects if o.type == 'MESH' and o.parent is arm]


# ---------------------------------------------------------------- 1. visibility
def unhide():
    if coll:
        # the collection may exist without being linked to the scene (a rolled-back run)
        if coll.name not in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.link(coll)
            p("VIS: re-linked %s to the scene" % coll.name)
        coll.hide_viewport = False
        coll.hide_render = False
        for lc in bpy.context.view_layer.layer_collection.children:
            if lc.collection == coll:
                lc.exclude = False
                lc.hide_viewport = False
    for lc in bpy.context.view_layer.layer_collection.children:
        lc.exclude = False
    for o in [arm] + char_meshes():
        o.hide_viewport = False
        o.hide_render = False
        o.hide_set(False)
    p("VIS: arm visible=%s ; %d meshes" % (arm.visible_get(), len(char_meshes())))


# ---------------------------------------------------------------- 2. modifiers
def clean_modifiers():
    keep, apply_, drop = {'ARMATURE'}, {'SUBSURF', 'SOLIDIFY', 'SHRINKWRAP',
                                        'VERTEX_WEIGHT_MIX', 'MASK', 'MESH_DEFORM'}, \
                          {'BUILD', 'CLOTH', 'COLLISION', 'CORRECTIVE_SMOOTH'}
    for ob in char_meshes():
        if ob.data.users > 1:
            ob.data = ob.data.copy()
        for m in list(ob.modifiers):
            if m.type in keep:
                continue
            if m.type == 'SUBSURF':
                m.levels = 1          # keep the silhouette, quarter the polycount
            if m.type in drop:
                ob.modifiers.remove(m)
                continue
            if m.type in apply_:
                bpy.context.view_layer.objects.active = ob
                try:
                    bpy.ops.object.modifier_apply(modifier=m.name)
                except Exception as e:
                    p("  ! could not apply %s on %s: %s" % (m.name, ob.name, e))
    p("--- after cleanup ---")
    total = 0
    for ob in char_meshes():
        v = len(ob.data.vertices)
        total += v
        p("  %-30s %6d verts  mods=%s" % (ob.name, v, [m.type for m in ob.modifiers]))
    p("TOTAL VERTS %d across %d meshes" % (total, len(char_meshes())))

    # the four *_mesh_deformer helper objects only existed for MeshDeform
    for n in ['boot_heel_mesh_deformer.L', 'boot_heel_mesh_deformer.R',
              'boot_laces_mesh_deformer.L', 'boot_laces_mesh_deformer.R']:
        ob = bpy.data.objects.get(n)
        if ob and not any(m.type == 'MESH_DEFORM' for o in char_meshes() for m in o.modifiers):
            bpy.data.objects.remove(ob, do_unlink=True)
            p("  removed helper", n)


# ---------------------------------------------------------------- 3. drivers
def clean_drivers():
    removed = 0
    for o in [arm] + char_meshes():
        ad = o.animation_data
        if not ad:
            continue
        for d in list(ad.drivers):
            if not d.data_path.startswith('pose.bones'):
                ad.drivers.remove(d)
                removed += 1
    p("DRIVERS: removed %d object-level drivers" % removed)
    # pose-bone drivers that need bpy.context (they error every frame in this scene)
    ctx = 0
    for o in [arm] + char_meshes():
        ad = o.animation_data
        if not ad:
            continue
        for d in list(ad.drivers):
            if 'context' in d.driver.expression:
                try:
                    tgt = o.path_resolve(d.data_path)
                except Exception:
                    tgt = None
                if tgt is not None and hasattr(tgt, '__setitem__') and d.array_index >= 0:
                    try:
                        tgt[d.array_index] = 0
                    except Exception:
                        pass
                ad.drivers.remove(d)
                ctx += 1
    p("DRIVERS: removed %d context-dependent drivers" % ctx)


# ---------------------------------------------------------------- 4. scale + place
def scale_and_place():
    arm.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()

    def world_bbox():
        dg = bpy.context.evaluated_depsgraph_get()
        mn = [1e18] * 3
        mx = [-1e18] * 3
        for ob in char_meshes():
            obe = ob.evaluated_get(dg)
            me = obe.to_mesh()
            for v in me.vertices:
                w = obe.matrix_world @ v.co
                for k in range(3):
                    mn[k] = min(mn[k], w[k])
                    mx[k] = max(mx[k], w[k])
            obe.to_mesh_clear()
        return mn, mx

    mn, mx = world_bbox()
    height = mx[2] - mn[2]
    p("RAW bbox height=%.4f  min=%s max=%s" % (height, ["%.3f" % v for v in mn], ["%.3f" % v for v in mx]))

    s = TARGET_HEIGHT / height
    arm.scale = (s, s, s)
    bpy.context.view_layer.update()
    mn, mx = world_bbox()
    p("SCALED by %.6f -> height=%.4f" % (s, mx[2] - mn[2]))
    p("SCALED bbox min=%s max=%s" % (["%.3f" % v for v in mn], ["%.3f" % v for v in mx]))

    # stand him on the pavement: pavement top = 0.06, x centred in front of the shop
    ground = 0.06
    start_x, start_y = -5.35, 6.0
    arm.location = (start_x - (mn[0] + mx[0]) / 2.0,
                    start_y - (mn[1] + mx[1]) / 2.0,
                    ground - mn[2])
    bpy.context.view_layer.update()
    mn, mx = world_bbox()
    p("PLACED arm.location=%s" % (tuple(round(v, 4) for v in arm.location),))
    p("PLACED bbox min=%s max=%s  -> sole z=%.4f height=%.4f" % (
        ["%.3f" % v for v in mn], ["%.3f" % v for v in mx], mn[2], mx[2] - mn[2]))


unhide()
clean_modifiers()
clean_drivers()
scale_and_place()
p("PREPARE DONE")

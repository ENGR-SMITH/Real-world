"""Make the Boy geometry game-ready and create the two player characters.

* texture stays: nothing new is modelled, the existing meshes are just baked
* subdivision is applied (so Blender's viewport == the game engine's view)
* the single imported boy becomes Boy1_*, then a full copy becomes Boy2_* whose
  shirt material is tinted so the two players are told apart at a glance
"""
import bpy

ARM = 'Boy_RIG'
SUBSURF_LEVEL = 1
# meshes worth subdividing; the rest are already dense enough (hair) or tiny (eyes/teeth)
SUBSURF_APPLY = {'body', 'boot.L', 'boot.R', 'boot_laces.L', 'boot_laces.R',
                 'shirt', 'shorts', 'tongue'}
GROUND = 0.06
POS = {'Boy1': (-5.35, 6.0), 'Boy2': (-5.55, 7.4)}


def p(*a):
    print(*a)


def meshes(arm):
    return [o for o in bpy.data.objects if o.type == 'MESH' and o.parent is arm]


def arm_of(name):
    return bpy.data.objects[name] if name in bpy.data.objects else None


# --------------------------------------------------------------- bake subdivision
def bake_subsurf(arm):
    for ob in meshes(arm):
        for m in list(ob.modifiers):
            if m.type != 'SUBSURF':
                continue
            if ob.name in SUBSURF_APPLY and not (ob.data.shape_keys):
                m.show_viewport = True
                m.levels = SUBSURF_LEVEL
                m.render_levels = SUBSURF_LEVEL + 1
                bpy.context.view_layer.objects.active = ob
                try:
                    bpy.ops.object.modifier_apply(modifier=m.name)
                except Exception as e:
                    p("  ! subsurf apply failed on %s: %s" % (ob.name, e))
            else:
                try:
                    ob.modifiers.remove(m)
                except Exception as e:
                    p("  ! subsurf remove failed on %s: %s" % (ob.name, e))
        # remaining non-armature modifiers cannot run in a game engine: bake or drop
        for m in list(ob.modifiers):
            if m.type in ('ARMATURE',):
                continue
            if m.type in ('SOLIDIFY', 'SHRINKWRAP', 'VERTEX_WEIGHT_MIX', 'MASK', 'MESH_DEFORM'):
                bpy.context.view_layer.objects.active = ob
                try:
                    bpy.ops.object.modifier_apply(modifier=m.name)
                except Exception as e:
                    p("  ! %s apply failed on %s: %s" % (m.type, ob.name, e))
            else:
                try:
                    ob.modifiers.remove(m)
                except Exception as e:
                    p("  ! %s remove failed on %s: %s" % (m.type, ob.name, e))
    p("--- geometry after bake ---")
    total = 0
    for ob in meshes(arm):
        v = len(ob.data.vertices)
        total += v
        p("  %-26s %6d verts  mods=%s" % (ob.name, v, [m.type for m in ob.modifiers]))
    p("TOTAL %d verts in %d meshes" % (total, len(meshes(arm))))


# --------------------------------------------------------------- rename / duplicate
def prefix(arm, pre, new_arm_name):
    for ob in meshes(arm):
        base = ob.name
        for old in ('Boy1_', 'Boy2_', 'Boy_'):
            if base.startswith(old):
                base = base[len(old):]
        ob.name = pre + base
    arm.name = new_arm_name
    arm.data.name = new_arm_name


def duplicate(arm, pre):
    objs = [arm] + meshes(arm)
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.duplicate(linked=False)
    new = [o for o in bpy.context.selected_objects]
    new_arm = [o for o in new if o.type == 'ARMATURE'][0]
    for o in new:
        base = o.name.split('.')[0]
        for old in ('Boy1_', 'Boy2_'):
            if base.startswith(old):
                base = base[len(old):]
        o.name = pre + base
    new_arm.name = pre + 'RIG'
    new_arm.data.name = pre + 'RIG'
    bpy.ops.object.select_all(action='DESELECT')
    return new_arm


def tint(ob, rgb):
    """give this object its own copy of its material with a colour multiply"""
    for slot in ob.material_slots:
        if not slot.material or not slot.material.use_nodes:
            continue
        m = slot.material.copy()
        m.name = slot.material.name + '_' + ob.name
        slot.material = m
        nt = m.node_tree
        bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is None:
            continue
        inp = bsdf.inputs['Base Color']
        if not inp.is_linked:
            inp.default_value = (rgb[0], rgb[1], rgb[2], 1.0)
            continue
        src = inp.links[0].from_socket
        mix = nt.nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.location = (bsdf.location.x - 220, bsdf.location.y + 60)
        cols = [s for s in mix.inputs if s.type == 'RGBA']
        out = [s for s in mix.outputs if s.type == 'RGBA'][0]
        nt.links.new(src, cols[0])
        cols[1].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
        nt.links.new(out, inp)


def place(arm, x, y):
    import mathutils
    dg = bpy.context.evaluated_depsgraph_get()
    mn = [1e18] * 3
    mx = [-1e18] * 3
    for ob in meshes(arm):
        obe = ob.evaluated_get(dg)
        me = obe.to_mesh()
        for v in me.vertices:
            w = obe.matrix_world @ v.co
            for k in range(3):
                mn[k] = min(mn[k], w[k])
                mx[k] = max(mx[k], w[k])
        obe.to_mesh_clear()
    arm.location = (arm.location.x + x - (mn[0] + mx[0]) / 2.0,
                    arm.location.y + y - (mn[1] + mx[1]) / 2.0,
                    arm.location.z + GROUND - mn[2])
    bpy.context.view_layer.update()
    p("PLACED %s -> loc=%s" % (arm.name, tuple(round(v, 3) for v in arm.location)))


def regroup():
    """collect every character object into one tidy collection"""
    coll = bpy.data.collections.get('Boy_character')
    for arm in [bpy.data.objects['Boy1_RIG'], bpy.data.objects['Boy2_RIG']]:
        for ob in [arm] + meshes(arm):
            for c in list(ob.users_collection):
                c.objects.unlink(ob)
            coll.objects.link(ob)
    coll.hide_viewport = False
    coll.hide_render = False
    p("COLLECTION %s now holds %d objects" % (coll.name, len(coll.objects)))


def ensure_boy1():
    if 'Boy1_RIG' in bpy.data.objects:
        return bpy.data.objects['Boy1_RIG']
    if ARM not in bpy.data.objects:
        raise SystemExit('%s vanished' % ARM)
    a = bpy.data.objects[ARM]
    bake_subsurf(a)
    prefix(a, 'Boy1_', 'Boy1_RIG')
    return bpy.data.objects['Boy1_RIG']


arm1 = ensure_boy1()
if 'Boy2_RIG' not in bpy.data.objects:
    arm2 = duplicate(arm1, 'Boy2_')
    tint(bpy.data.objects['Boy2_shirt'], (0.35, 0.55, 1.35))
else:
    p("Boy2 already there")
    arm2 = bpy.data.objects['Boy2_RIG']
place(arm1, *POS['Boy1'])
place(arm2, *POS['Boy2'])
regroup()

for n in ('Boy1_RIG', 'Boy2_RIG'):
    a = bpy.data.objects[n]
    p("%s loc=%s scale=%s meshes=%d" % (n, tuple(round(v, 3) for v in a.location),
                                        tuple(round(v, 4) for v in a.scale), len(meshes(a))))
p("GAME GEOMETRY DONE")

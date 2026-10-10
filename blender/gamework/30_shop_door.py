"""Build the shop entrance the model never had.

The storefront is a full-width glazed front: `Cube.395` is the gold frame
(material Material.011) and `Cube.398` is one big Glas cube. A doorway is cut
through both under the SHOPRITE sign, then two hinged glass leaves plus a frame
are built to fill it, reusing the shop's own materials so nothing looks bolted on.

Leaves are hinged so that rotating them about local Z by -90/+90 degrees swings
them inward into the shop (the game does that at runtime).
"""
import bpy
import bmesh
from mathutils import Vector

GLASS = 'Cube.398'
FRAME = 'Cube.395'
MAT_FRAME = 'Material.011'
MAT_GLASS = 'Glas'

DOOR_CY = -2.00            # centred under the SHOPRITE sign
LEAF_W = 0.95
DOOR_H = 2.55
Z0 = 0.06                  # pavement top
X_PLANE = -4.15            # the frame plane of the shop front
THICK = 0.06

coll = bpy.data.collections.get('Shop_Entrance')
if coll is None:
    coll = bpy.data.collections.new('Shop_Entrance')
    bpy.context.scene.collection.children.link(coll)


def box_mesh(bm, mn, mx, mat_index=0):
    verts = []
    for x in (mn[0], mx[0]):
        for y in (mn[1], mx[1]):
            for z in (mn[2], mx[2]):
                verts.append(bm.verts.new((x, y, z)))
    bm.verts.ensure_lookup_table()
    idx = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    for f in idx:
        face = bm.faces.new([verts[i] for i in f])
        face.material_index = mat_index


def new_obj(name, bm, mats):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    for m in mats:
        ob.data.materials.append(bpy.data.materials[m])
    coll.objects.link(ob)
    return ob


def make_cutter():
    bm = bmesh.new()
    box_mesh(bm, (-6.20, DOOR_CY - LEAF_W - 0.02, Z0 - 0.02),
             (-2.40, DOOR_CY + LEAF_W + 0.02, Z0 + DOOR_H + 0.02))
    return new_obj('TMP_door_cutter', bm, [MAT_FRAME])


def cut_out(cutter):
    for name in (GLASS, FRAME):
        ob = bpy.data.objects.get(name)
        if ob is None:
            continue
        has = any(m.type == 'BOOLEAN' and m.object == cutter for m in ob.modifiers)
        if has:
            continue
        m = ob.modifiers.new('doorway', 'BOOLEAN')
        m.operation = 'DIFFERENCE'
        m.object = cutter
        m.solver = 'EXACT'
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.modifier_apply(modifier=m.name)
        print("cut doorway through", name)


def leaf(name, hinge_y, direction):
    """one glass door leaf; mesh starts at the hinge and runs `direction` in +Y"""
    w, h, t = LEAF_W, DOOR_H, THICK
    border = 0.075
    bm = bmesh.new()
    y0, y1 = 0.0, direction * w
    yi0, yi1 = min(y0, y1), max(y0, y1)
    # border: two verticals, a sill and a head
    for a, b in ((yi0, yi0 + border), (yi1 - border, yi1)):
        box_mesh(bm, (0.0, a, 0.0), (t, b, h), 0)
    box_mesh(bm, (0.0, yi0, 0.0), (t, yi1, border), 0)
    box_mesh(bm, (0.0, yi0, h - border), (t, yi1, h), 0)
    box_mesh(bm, (0.0, yi0 + border, h * 0.62), (t, yi1 - border, h * 0.62 + 0.05), 0)
    # the glass pane itself
    g = 0.012
    quad = bm.verts.new
    v = [quad((t / 2, yi0 + border, border)), quad((t / 2, yi1 - border, border)),
         quad((t / 2, yi1 - border, h - border)), quad((t / 2, yi0 + border, h - border))]
    f = bm.faces.new(v)
    f.material_index = 1
    ob = new_obj(name, bm, [MAT_FRAME, MAT_GLASS])
    ob.location = (X_PLANE, hinge_y, Z0)
    ob.rotation_mode = 'XYZ'
    return ob


def door_frame():
    bm = bmesh.new()
    j = 0.09
    box_mesh(bm, (X_PLANE - 0.03, DOOR_CY - LEAF_W - j, Z0), (X_PLANE + 0.10, DOOR_CY - LEAF_W, Z0 + DOOR_H + j), 0)
    box_mesh(bm, (X_PLANE - 0.03, DOOR_CY + LEAF_W, Z0), (X_PLANE + 0.10, DOOR_CY + LEAF_W + j, Z0 + DOOR_H + j), 0)
    box_mesh(bm, (X_PLANE - 0.03, DOOR_CY - LEAF_W - j, Z0 + DOOR_H), (X_PLANE + 0.10, DOOR_CY + LEAF_W + j, Z0 + DOOR_H + j), 0)
    return new_obj('Shop_DoorFrame', bm, [MAT_FRAME])


if 'Shop_Door_L' in bpy.data.objects:
    print("entrance already built")
else:
    cutter = make_cutter()
    cut_out(cutter)
    bpy.data.objects.remove(cutter, do_unlink=True)
    door_frame()
    l = leaf('Shop_Door_L', DOOR_CY - LEAF_W, +1.0)
    r = leaf('Shop_Door_R', DOOR_CY + LEAF_W, -1.0)
    # handles, so the leaves read as doors
    for ob, sgn in ((l, 1.0), (r, -1.0)):
        bm = bmesh.new()
        y = sgn * (LEAF_W - 0.13)
        box_mesh(bm, (THICK, y - 0.02, 1.02), (THICK + 0.06, y + 0.02, 1.34), 0)
        h = new_obj(ob.name + '_handle', bm, [MAT_FRAME])
        h.parent = ob
        h.matrix_parent_inverse = ob.matrix_world.inverted()
    print("entrance built")

for n in ('Shop_DoorFrame', 'Shop_Door_L', 'Shop_Door_R', 'Shop_Door_L_handle', 'Shop_Door_R_handle'):
    ob = bpy.data.objects.get(n)
    if ob:
        print("  %-22s loc=%s dim=%s mats=%s" % (n, tuple(round(v, 3) for v in ob.location),
                                                 tuple(round(v, 3) for v in ob.dimensions),
                                                 [ms.material.name for ms in ob.material_slots]))
bpy.ops.wm.save_mainfile()
print("### shop door built and saved")
print("SHOP DOOR DONE")

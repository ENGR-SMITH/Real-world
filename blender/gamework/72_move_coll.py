"""72_move_coll.py -- is collection membership why nothing near the camera draws?

Every object that renders lives in a named child collection (Street, SUV_Rigged,
TukTuk, Boy_character, ...); the HUD objects and the QQ_ test cubes all sit in the
master 'Scene Collection'.  Move a few of them into named collections and see if
they appear.

    blender.exe -b hud_test.blend --python 72_move_coll.py
"""

import bpy

P = print
sc = bpy.context.scene


def coll(name):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        sc.collection.children.link(c)
        P("### created collection %s" % name)
    return c


def move(o, c):
    for old in list(o.users_collection):
        if old is not c:
            old.objects.unlink(o)
    c.objects.link(o)
    P("### %-14s -> %s (colls now %s)" % (
        o.name, c.name, [x.name for x in o.users_collection]))


street = coll("Street")
tuktuk = coll("TukTuk")
hudc = coll("HUD")

for nm in ("QQ_F", "QQ_G", "QQ_H", "QQ_D", "QQ_E", "QQ_HUDHELP"):
    o = bpy.data.objects.get(nm)
    if o:
        move(o, street)
    else:
        P("### %s missing" % nm)

for nm in ("QQ_A", "QQ_B", "QQ_C"):
    o = bpy.data.objects.get(nm)
    if o:
        move(o, tuktuk)
    else:
        P("### %s missing" % nm)

for o in list(bpy.data.objects):
    if o.name.startswith(("HUD_", "P_")):
        move(o, hudc)

P("### saving")
bpy.ops.wm.save_mainfile()
P("### saved %s" % bpy.data.filepath)

"""Import the Boy character (rig + meshes) from the source .blend into the live scene.

Runs inside the current Blender session (via the MCP bridge) or in background.
Idempotent: skips if already imported.
"""
import bpy

SRC = "E:/Reality/ECO/People/body/Boy - A Rigged Character.blend"
CHAR_OBJS = [
    'Boy_RIG', 'body', 'hair', 'shirt', 'shorts',
    'boot.L', 'boot.R', 'boot_laces.L', 'boot_laces.R',
    'boot_heel_mesh_deformer.L', 'boot_heel_mesh_deformer.R',
    'boot_laces_mesh_deformer.L', 'boot_laces_mesh_deformer.R',
    'eyeball.L', 'eyeball.R', 'eye_optic.L', 'eye_optic.R',
    'lashes.L', 'lashes.R', 'teeth_upper', 'teeth_lower', 'tongue',
]
DEFORMER = [n for n in CHAR_OBJS if 'mesh_deformer' in n]


def srgb_safe_link(coll, ob):
    if ob.name not in coll.objects:
        coll.objects.link(ob)


def main():
    if 'Boy_RIG' in bpy.data.objects:
        print("IMPORT: Boy_RIG already present, skipping import")
    else:
        lib = bpy.data.libraries.load(SRC, link=False)
        df, dt = lib.__enter__()
        dt.objects = CHAR_OBJS
        dt.materials = None
        lib.__exit__(None, None, None)
        loaded = [o for o in dt.objects if o is not None]
        print("IMPORT: loaded %d objects" % len(loaded))
        coll = bpy.data.collections.get('Boy_character')
        if coll is None:
            coll = bpy.data.collections.new('Boy_character')
            bpy.context.scene.collection.children.link(coll)
        for ob in loaded:
            srgb_safe_link(coll, ob)

    arm = bpy.data.objects['Boy_RIG']
    print("IMPORT: armature loc=%s scale=%s" % (tuple(round(v, 4) for v in arm.location),
                                                tuple(round(v, 4) for v in arm.scale)))

    # report modifier stack + build-modifier ranges + visibility
    print("--- modifiers ---")
    for ob in bpy.data.objects:
        if ob.parent is not arm or ob.type != 'MESH':
            continue
        mods = []
        for m in ob.modifiers:
            extra = ''
            if m.type == 'SUBSURF':
                extra = ' lvl=%d/%d' % (m.levels, m.render_levels)
            if m.type == 'BUILD':
                extra = ' start=%s dur=%s end=%s' % (getattr(m, 'frame_start', '?'),
                                                    getattr(m, 'frame_duration', '?'),
                                                    getattr(m, 'frame_end', '?'))
            mods.append('%s[%s]%s' % (m.type, m.name, extra))
        print("MOD|%s|%d verts|%s|vgroups=%d|vis=%s" % (
            ob.name, len(ob.data.vertices), ' + '.join(mods), len(ob.vertex_groups), ob.visible_get()))

    # vertex-group usage: which bone names do the meshes actually weight?
    groups = {}
    for ob in bpy.data.objects:
        if ob.parent is arm and ob.type == 'MESH':
            for g in ob.vertex_groups:
                groups.setdefault(g.name, []).append(ob.name)
    prefixes = {}
    for name in groups:
        prefixes[name.split('.')[0]] = prefixes.get(name.split('.')[0], 0) + 1
    print("VGROUP_PREFIXES", dict(sorted(prefixes.items(), key=lambda kv: -kv[1])))
    print("VGROUP_COUNT", len(groups))
    print("DEFORMER_OBJS", DEFORMER)
    print("IMPORT DONE")


main()

"""Helpers for posing the imported Boy rig (Rigify-style, 1037 bones).

The rig exposes IK targets for both legs (default) and both arms (FK by default,
switchable through custom properties on the Root bone). Everything here works in
*character local* space = the rig's own 12-unit scale, so callers can think in the
same numbers as the source file: feet at z~0, hips 6.9, head top 12.0.
"""
import bpy
from mathutils import Vector, Matrix, Euler
import math

MODE_PROPS = ('arm_L_FK_IK', 'arm_R_FK_IK', 'fingers_L_FK_IK', 'fingers_R_FK_IK',
              'leg_L_FK_IK', 'leg_R_FK_IK', 'leg_L_IK_stretch', 'leg_R_IK_stretch')


def arm(name='Boy1_RIG'):
    return bpy.data.objects[name]


def root(a):
    return a.pose.bones['Root']


def upd():
    bpy.context.view_layer.update()


def w2a(a, p):
    """world point -> armature space"""
    return a.matrix_world.inverted() @ Vector(p)


def a2w(a, p):
    return a.matrix_world @ Vector(p)


def set_modes(a, arms_ik=True, legs_ik=True, stretch=False):
    r = root(a)
    for s in ('L', 'R'):
        r['arm_%s_FK_IK' % s] = 1.0 if arms_ik else 0.0
        r['fingers_%s_FK_IK' % s] = 1.0 if arms_ik else 0.0
        r['leg_%s_FK_IK' % s] = 1.0 if legs_ik else 0.0
        r['leg_%s_IK_stretch' % s] = 1.0 if stretch else 0.0
    upd()


def key_modes(a, frame):
    r = root(a)
    for k in MODE_PROPS:
        r.keyframe_insert('["%s"]' % k, frame=frame)


def bone_world_head(a, name):
    return a.matrix_world @ a.pose.bones[name].head


def bone_world_tail(a, name):
    return a.matrix_world @ a.pose.bones[name].tail


def move_to(a, name, world_pos, keep_rot=True):
    """move a pose bone so its HEAD sits at world_pos (armature-space aware)"""
    pb = a.pose.bones[name]
    M = pb.matrix.copy()
    M.translation = w2a(a, world_pos)
    pb.matrix = M
    upd()
    return pb


def aim(a, name, direction, up=(0, 0, 1)):
    """point a bone's local +Y (its length) along a world direction, keep the head"""
    pb = a.pose.bones[name]
    M = pb.matrix.copy()
    loc = M.translation.copy()
    d = Vector(direction).normalized()
    quat = d.to_track_quat('Y', 'Z')
    R = quat.to_matrix().to_4x4()
    R.translation = loc
    pb.matrix = R
    upd()
    return pb


def rotate_local(a, name, euler_deg):
    """add a rotation (degrees, bone local axes) on top of the bone's rest orientation"""
    pb = a.pose.bones[name]
    rest = a.data.bones[name].matrix_local.to_3x3()
    parent = pb.parent
    base = pb.matrix.to_3x3()
    e = Euler([math.radians(v) for v in euler_deg], 'XYZ').to_matrix()
    M = pb.matrix.copy()
    M_new = (base @ e).to_4x4()
    M_new.translation = M.translation
    pb.matrix = M_new
    upd()
    return pb


def set_root(a, world_loc=None, yaw_deg=None, pitch_deg=None):
    r = a.pose.bones['Root']
    r.rotation_mode = 'XYZ'
    if world_loc is not None:
        r.location = w2a(a, world_loc) - w2a(a, (0, 0, 0))
    if yaw_deg is not None or pitch_deg is not None:
        r.rotation_euler = (math.radians(pitch_deg or 0.0), 0.0, math.radians(yaw_deg or 0.0))
    upd()
    return r


def key_bone(a, name, frame, loc=True, rot=True, scale=False):
    pb = a.pose.bones[name]
    if pb.rotation_mode in ('QUATERNION',):
        pass
    if loc:
        pb.keyframe_insert('location', frame=frame)
    if rot:
        pb.keyframe_insert('rotation_quaternion' if pb.rotation_mode == 'QUATERNION' else 'rotation_euler', frame=frame)
    if scale:
        pb.keyframe_insert('scale', frame=frame)


def key_bones(a, names, frame, loc=True, rot=True, scale=False):
    for n in names:
        if n in a.pose.bones:
            key_bone(a, n, frame, loc, rot, scale)


def rest_pose(a):
    """clear every posed bone back to rest and drop constraints for a clean slate"""
    for pb in a.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_mode = pb.rotation_mode if pb.rotation_mode == 'QUATERNION' else 'XYZ'
        pb.rotation_euler = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.scale = (1, 1, 1)
    upd()

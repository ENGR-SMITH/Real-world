"""Animation helpers for the boy rig: pose in armature space, record, bake.

All numbers are in the rig's own units (12.03 tall, sole z~0, hips 6.9, facing -Y,
the character's left = +X). Clips are authored "in place": the game moves the
character through the world, the clip only moves its limbs.

Authoring is done with the action detached, recording bone channel values per
frame, then the fcurves are written directly - that avoids the animation system
overwriting the pose we are building, which is the usual trap with this kind of
script.
"""
import bpy
import math
from mathutils import Vector, Matrix

FPS = 24
ANKLE_Z = 0.527
FOOT_X = {'L': 0.638, 'R': -0.638}
V = Vector

MODE_PROPS = ('arm_L_FK_IK', 'arm_R_FK_IK', 'fingers_L_FK_IK', 'fingers_R_FK_IK',
              'leg_L_FK_IK', 'leg_R_FK_IK', 'leg_L_IK_stretch', 'leg_R_IK_stretch',
              'arm_L_IK_elbow_follow', 'arm_R_IK_elbow_follow')

CONTROLS = ['Root', 'tweak.pelvis', 'pelvis', 'spine_01', 'spine_02', 'chest', 'chest.parent',
            'neck_01', 'neck_02', 'head', 'head.parent',
            'IK.foot.L', 'IK.foot.R', 'IK.foot_roll.L', 'IK.foot_roll.R',
            'IK.hand.L', 'IK.hand.R', 'IK.leg.pole.L', 'IK.leg.pole.R',
            'FK.upper_arm.L', 'FK.upper_arm.R', 'FK.lower_arm.L', 'FK.lower_arm.R',
            'FK.hand.L', 'FK.hand.R', 'FK.thigh.L', 'FK.thigh.R', 'FK.shin.L', 'FK.shin.R',
            'FK.foot.L', 'FK.foot.R', 'jaw', 'eyes_panel.parent-head',
            'shape_IK.IK.foot.L']


def upd():
    bpy.context.view_layer.update()


def rest_matrix(a, name):
    return a.data.bones[name].matrix_local


def set_modes(a, arms_ik=True, legs_ik=True, stretch=False):
    r = a.pose.bones['Root']
    for s in ('L', 'R'):
        r['arm_%s_FK_IK' % s] = 1.0 if arms_ik else 0.0
        r['fingers_%s_FK_IK' % s] = 1.0 if arms_ik else 0.0
        r['leg_%s_FK_IK' % s] = 1.0 if legs_ik else 0.0
        r['leg_%s_IK_stretch' % s] = 1.0 if stretch else 0.0
        r['arm_%s_IK_elbow_follow' % s] = 1.0
    upd()


def set_ik(a, name, pos, pitch=0.0, yaw=0.0, roll=0.0):
    pb = a.pose.bones[name]
    R = rest_matrix(a, name).to_3x3()
    if yaw:
        R = Matrix.Rotation(math.radians(yaw), 3, 'Z') @ R
    if pitch:
        R = Matrix.Rotation(math.radians(pitch), 3, 'X') @ R
    if roll:
        R = Matrix.Rotation(math.radians(roll), 3, 'Y') @ R
    M = R.to_4x4()
    M.translation = V(pos)
    pb.matrix = M
    upd()
    return pb


def aim_ik(a, name, pos, direction):
    """place an IK control pointing its length along `direction` (armature space)"""
    pb = a.pose.bones[name]
    M = Vector(direction).normalized().to_track_quat('Y', 'Z').to_matrix().to_4x4()
    M.translation = V(pos)
    pb.matrix = M
    upd()
    return pb


def arm_hang(a, side, y, z=6.05, x=1.72, out=0.20, fore=0.55):
    """relaxed arm at the side; y = fore/aft offset of the hand"""
    s = 1.0 if side == 'L' else -1.0
    dy = y - 0.35
    return aim_ik(a, 'IK.hand.%s' % side, (s * x, y, z),
                  (s * out, -fore * dy, -1.0))


def foot(a, side, y, z, pitch=0.0, yaw=0.0):
    return set_ik(a, 'IK.foot.%s' % side, (FOOT_X[side], y, z), pitch=pitch, yaw=yaw)


def hand(a, side, pos, pitch=0.0, yaw=0.0):
    return set_ik(a, 'IK.hand.%s' % side, pos, pitch=pitch, yaw=yaw)


def rot(a, name, x=0.0, y=0.0, z=0.0):
    pb = a.pose.bones.get(name)
    if pb is None:
        return None
    M = pb.matrix.copy()
    R = M.to_3x3()
    if z:
        R = Matrix.Rotation(math.radians(z), 3, 'Z') @ R
    if x:
        R = Matrix.Rotation(math.radians(x), 3, 'X') @ R
    if y:
        R = Matrix.Rotation(math.radians(y), 3, 'Y') @ R
    M2 = R.to_4x4()
    M2.translation = M.translation
    pb.matrix = M2
    upd()
    return pb


def root_offset(a, off):
    """shift the whole character; `off` is in rig-local units like every other number"""
    pb = a.pose.bones['Root']
    base = rest_matrix(a, 'Root').translation
    w = a.matrix_world @ (V(base) + V(off))
    M = pb.matrix.to_3x3().to_4x4()
    M.translation = a.matrix_world.inverted() @ w
    pb.matrix = M
    upd()
    return pb


def clear_pose(a):
    for pb in a.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.scale = (1, 1, 1)
    upd()


def apply_pose(a, p):
    for k, v in p.get('foot', {}).items():
        foot(a, k, v[0], v[1], v[2] if len(v) > 2 else 0.0, v[3] if len(v) > 3 else 0.0)
    for k, v in p.get('hand', {}).items():
        hand(a, k, v[:3], v[3] if len(v) > 3 else 0.0, v[4] if len(v) > 4 else 0.0)
    for k, v in p.get('rot', {}).items():
        rot(a, k, *(list(v) + [0.0] * (3 - len(v))))
    if 'root' in p:
        root_offset(a, p['root'])


# ------------------------------------------------------------------ record + fcurves
def _chan(pb):
    if pb.rotation_mode == 'QUATERNION':
        return [('rotation_quaternion', 4, tuple(pb.rotation_quaternion))]
    return [('rotation_euler', 3, tuple(pb.rotation_euler))]


def record(a, rec, frame, bones=None):
    for n in (bones or CONTROLS):
        pb = a.pose.bones.get(n)
        if pb is None:
            continue
        vals = [('location', 3, tuple(pb.location))] + _chan(pb) + [('scale', 3, tuple(pb.scale))]
        for path, ncomp, vals_ in vals:
            for i in range(ncomp):
                rec.setdefault((n, path, i), {})[frame] = vals_[i]
    r = a.pose.bones['Root']
    for k in MODE_PROPS:
        rec.setdefault(('Root', '["%s"]' % k, 0), {})[frame] = r[k]


def write_action(a, name, rec):
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    for (bone, path, idx), frames in rec.items():
        if path.startswith('['):
            dp = 'pose.bones["%s"]%s' % (bone, path)
        else:
            dp = 'pose.bones["%s"].%s' % (bone, path)
        fc = act.fcurves.new(dp, index=idx, action_group=bone)
        for f in sorted(frames):
            kp = fc.keyframe_points.insert(f, frames[f], options={'FAST'})
            kp.interpolation = 'LINEAR'
        fc.update()
    if a.animation_data is None:
        a.animation_data_create()
    a.animation_data.action = act
    return act


def author_clip(a, name, pose_fn, frames, **kw):
    """pose_fn(i, frames, **kw) applies a pose for frame i (0-based)"""
    sc = bpy.context.scene
    if a.animation_data is None:
        a.animation_data_create()
    a.animation_data.action = None
    for t in a.animation_data.nla_tracks:      # the source file's stashed face actions
        t.mute = True
    rec = {}
    for i in range(frames + 1):
        f = 1 + i
        sc.frame_set(f)
        clear_pose(a)
        set_modes(a, arms_ik=True, legs_ik=True)
        pose_fn(i if i < frames else 0, frames, **kw)
        upd()
        record(a, rec, f)
    return write_action(a, name + '_src', rec)


def bake_clip(a, name, frames):
    """visual bake of every bone so the pose survives without the rig's constraints"""
    sc = bpy.context.scene
    src = a.animation_data.action
    sc.frame_start, sc.frame_end = 1, 1 + frames
    sc.frame_set(1)
    bpy.context.view_layer.objects.active = a
    for o in bpy.data.objects:
        o.select_set(False)
    a.select_set(True)
    bpy.ops.object.mode_set(mode='POSE')
    bpy.ops.pose.select_all(action='SELECT')
    bpy.ops.nla.bake(frame_start=1, frame_end=1 + frames, step=1, only_selected=False,
                     visual_keying=True, clear_constraints=False, clear_parents=False,
                     use_current_action=False, bake_types={'POSE'})
    baked = a.animation_data.action
    baked.name = name
    baked.use_fake_user = True
    bpy.ops.object.mode_set(mode='OBJECT')
    if src and src.users == 0:
        bpy.data.actions.remove(src)
    return baked


def mute_constraints(a, mute=True):
    n = 0
    for pb in a.pose.bones:
        for c in pb.constraints:
            if c.mute != mute:
                c.mute = mute
                n += 1
    print("  constraints set mute=%s: %d" % (mute, n))
    upd()
    return n


# ------------------------------------------------------------------ the clips
def walk_pose(i, frames, step=2.2, lift=0.85, bob=0.30, lean=3.0, arm_swing=22.0, sway=4.0):
    """treadmill walk in place; left foot contacts the ground at t=0"""
    t = i / float(frames)
    for side, phase in (('L', t % 1.0), ('R', (t + 0.5) % 1.0)):
        STANCE = 0.58
        if phase < STANCE:
            u = phase / STANCE
            y = -step + 2.0 * step * u
            z = ANKLE_Z + (0.12 * ((u - 0.8) / 0.2) ** 2 if u > 0.8 else 0.0)
            pitch = -14.0 * ((u - 0.8) / 0.2) if u > 0.8 else 0.0
        else:
            u = (phase - STANCE) / (1.0 - STANCE)
            y = step - 2.0 * step * u
            z = ANKLE_Z + lift * math.sin(math.pi * u) ** 0.8
            pitch = 12.0 * math.sin(math.pi * u)
        foot(a, side, y, z, pitch)
    swing = math.sin(2.0 * math.pi * t)
    # pelvis is lowest at foot contact (t = 0, 0.5) and highest at mid-stance
    root_offset(a, (0.0, 0.0, bob * (abs(math.cos(2.0 * math.pi * t)) - 0.5)))
    rot(a, 'spine_01', lean, 0.0, -sway * swing)
    rot(a, 'spine_02', lean * 0.5, 0.0, -sway * 0.5 * swing)
    rot(a, 'chest', 0.0, 0.0, sway * swing)
    rot(a, 'neck_01', -lean * 0.6, 0.0, 0.0)
    rot(a, 'head', -lean * 0.4, 0.0, sway * 0.5 * swing)
    # arms counter-swing: the hand travels fore/aft while staying beside the body
    arm_hang(a, 'L', 0.35 - 1.45 * swing, z=6.05 + 0.10 * abs(swing))
    arm_hang(a, 'R', 0.35 + 1.45 * swing, z=6.05 + 0.10 * abs(swing))


def idle_pose(i, frames, amp=1.0):
    """breathing idle: chest rises, weight shifts, arms relaxed at the sides"""
    t = i / float(frames)
    s = math.sin(2.0 * math.pi * t)
    foot(a, 'L', 0.53, ANKLE_Z, 0.0)
    foot(a, 'R', 0.53, ANKLE_Z, 0.0)
    root_offset(a, (0.0, 0.0, 0.10 * amp * s))
    rot(a, 'spine_01', 2.2 * amp + 0.8 * s, 0.0, -1.2 * amp * s)
    rot(a, 'chest', -1.5 * amp * s, 0.0, 0.0)
    rot(a, 'neck_01', -1.6, 0.0, 0.0)
    rot(a, 'head', 0.0, 0.0, 1.5 * amp * s)
    # relaxed arms hanging beside the body
    arm_hang(a, 'L', 0.45 - 0.06 * s, z=6.00 + 0.05 * s, x=1.70)
    arm_hang(a, 'R', 0.45 + 0.06 * s, z=6.00 - 0.05 * s, x=1.70)


def _smooth(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3.0 - 2.0 * u)


def reach_pose(i, frames, target=(0.95, -2.75, 7.9), side='L'):
    """one-shot: lean in, take something off a shelf in front, hold it, step back"""
    t = i / float(frames)
    if t < 0.30:
        w = _smooth(t / 0.30)
    elif t < 0.55:
        w = 1.0
    elif t < 0.85:
        w = 1.0 - _smooth((t - 0.55) / 0.30)
    else:
        w = 0.0
    foot(a, 'L', 0.75, ANKLE_Z, 0.0)
    foot(a, 'R', 0.40, ANKLE_Z, 0.0)
    root_offset(a, (0.0, -0.45 * w, -0.06 * w))
    rot(a, 'spine_01', 13.0 * w, 0.0, 3.0 * w)
    rot(a, 'spine_02', 6.0 * w, 0.0, 2.0 * w)
    rot(a, 'chest', 3.0 * w, 0.0, -4.0 * w)
    rot(a, 'neck_01', -9.0 * w, 0.0, 0.0)
    rot(a, 'head', -5.0 * w, 0.0, 4.0 * w)
    s = 1.0 if side == 'L' else -1.0
    aim_ik(a, 'IK.hand.%s' % side,
           (target[0] * s, target[1], target[2]),
           (0.10 * s, -1.0, -0.25))
    arm_hang(a, 'R', 0.45 + 0.9 * w, z=6.05)


def sit_pose(i, frames, hip=5.30, foot_y=-3.05, foot_z=1.95, wheel_y=-3.9,
             wheel_z=8.15, hand_x=0.62, s0=0.0):
    """seated driving pose: legs forward in the footwell, hands on the wheel"""
    t = i / float(frames)
    s = math.sin(2.0 * math.pi * t)
    foot(a, 'L', foot_y + 0.55, foot_z, 26.0, 6.0)
    foot(a, 'R', foot_y + 0.55, foot_z, 26.0, -6.0)
    root_offset(a, (0.0, 0.55, hip - 6.904))
    rot(a, 'spine_01', 6.0, 0.0, 0.8 * s)
    rot(a, 'spine_02', 3.0, 0.0, 0.6 * s)
    rot(a, 'chest', -1.0, 0.0, -1.2 * s)
    rot(a, 'neck_01', -2.0, 0.0, 0.0)
    rot(a, 'head', -1.0, 0.0, 0.8 * s)
    for side, sgn in (('L', 1.0), ('R', -1.0)):
        aim_ik(a, 'IK.hand.%s' % side,
               (hand_x * sgn, wheel_y, wheel_z),
               (0.05 * sgn, -0.9, -0.35))


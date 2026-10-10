"""game.py -- playable third-person scene for Shop_with_people.blend (UPBGE 0.50 / Blender 5.0).

Open Shop_with_people.blend in UPBGE and press P, or run
    blenderplayer.exe Shop_with_people.blend

Controls
    W A S D     walk, relative to the camera
    SHIFT       hurry
    E           context action -- open/close the shop door, take the item you are
                looking at, drop one, signal the vehicle to stop, open its door,
                get in, get out
    TAB         swap between the two boys
    ESC         quit

The scene drives itself through a Python main loop (the scene's "__main__" property
points at this text block), so nothing depends on logic bricks.

Structure
    * the world model (regions / blockers / collision) is plain arithmetic at the
      top so it can also be exercised outside the engine
    * everything below `# ===== engine =====` needs bge
"""

import math
import os
import sys
import time

# >>> WORLD_DATA
WORLD = {
    'regions': [['door', -4.3, -2.95, -4.05, -1.05, 0.05], ['shop', -4.05, -10.65, 7.725, 7.37, 0.046], ['pave', -6.48, -19.98, -4.3, 19.98, 0.06], ['road', -13.48, -19.98, -6.52, 19.98, -0.08]],
    'wall': [-4.3, -4.05],
    'doorway': [-2.95, -1.05],
    'blockers': [[-13.077, 15.201, -10.433, 19.529], [-12.864, 18.311, -10.641, 18.95], [-12.864, 18.821, -10.641, 19.212], [-12.22, 15.87, -11.3, 16.693], [-12.088, 16.694, -11.416, 17.344], [-12.077, 17.179, -11.427, 17.422], [-11.862, 15.682, -11.629, 15.936], [-4.383, -10.769, -3.745, -10.131], [-4.383, 6.803, -3.745, 7.441], [-3.94, -11.491, 6.646, -9.526], [-3.719, -10.519, 6.637, -10.38], [-2.878, -2.229, -2.756, 3.783], [-2.856, -2.267, -0.471, 3.837], [-2.819, 3.103, -2.64, 3.42], [-2.774, 1.766, -2.457, 1.945], [-2.774, 1.953, -2.457, 2.132], [-2.774, 2.147, -2.457, 2.326], [-2.774, 2.334, -2.457, 2.513], [-2.774, 2.514, -2.457, 2.693], [-2.773, -0.009, -2.531, 0.216], [-2.773, 0.23, -2.531, 0.455], [-2.773, 0.485, -2.531, 0.71], [-2.773, 0.724, -2.531, 0.948], [-2.773, 0.957, -2.531, 1.182], [-2.773, 1.191, -2.531, 1.416], [-2.773, 1.433, -2.531, 1.657], [-2.773, 1.673, -2.531, 1.898], [-2.773, 2.139, -2.531, 2.364], [-2.773, 2.372, -2.531, 2.597], [-2.773, 2.607, -2.531, 2.831], [-2.773, 2.848, -2.531, 3.073], [-2.773, 3.088, -2.531, 3.313], [-2.754, -2.167, -2.212, -1.605], [-2.75, 2.908, -2.433, 3.087], [-2.74, 2.715, -2.423, 2.894], [-2.733, 2.514, -2.416, 2.693], [-2.729, 3.344, -2.417, 3.486], [-2.69, -1.511, -2.42, -1.059], [-2.69, -1.033, -2.42, -0.58], [-2.69, -0.552, -2.42, -0.099], [-2.681, -1.511, -2.411, -1.058], [-2.681, -1.039, -2.411, -0.586], [-2.681, -0.555, -2.411, -0.102], [-2.677, -0.552, -2.407, -0.099], [-2.673, 0.687, -2.366, 1.011], [-2.673, 1.03, -2.366, 1.354], [-2.673, 1.375, -2.366, 1.699], [-2.668, -2.204, -2.529, -1.891], [-2.668, -1.875, -2.529, -1.563], [-2.668, -1.867, -2.529, -1.555], [-2.663, -0.086, -2.427, 0.164], [-2.663, 0.175, -2.427, 0.425], [-2.663, 0.435, -2.427, 0.685], [-2.66, 3.513, -2.347, 3.655], [-2.636, -2.081, -2.324, -1.942], [-2.636, -1.946, -2.324, -1.808], [-2.622, 3.115, -2.443, 3.433], [-2.556, 1.898, -2.314, 2.123], [-2.507, -2.204, -2.369, -1.891], [-2.507, -1.875, -2.369, -1.563], [-2.436, 3.547, -2.094, 3.801], [-2.388, -1.511, -2.117, -1.058], [-2.388, -1.034, -2.117, -0.581], [-2.388, -0.552, -2.117, -0.099], [-2.386, -1.511, -2.116, -1.058], [-2.386, -1.041, -2.116, -0.588], [-2.355, 3.294, -2.043, 3.433], [-2.35, -2.204, -2.211, -1.891], [-2.35, -1.875, -2.211, -1.563], [-2.346, 3.513, -2.034, 3.655], [-2.105, -2.205, -1.792, -2.066], [-2.105, -2.044, -1.792, -1.906], [-2.105, -1.887, -1.792, -1.748], [-2.105, -1.748, -1.792, -1.61], [-2.103, -2.213, -1.562, -1.651], [-2.084, -1.645, -1.294, 3.07], [-1.992, 3.194, -1.45, 3.756], [-1.957, 3.156, -1.645, 3.294], [-1.957, 3.237, -1.645, 3.376], [-1.957, 3.294, -1.645, 3.433], [-1.957, 3.376, -1.645, 3.514], [-1.957, 3.452, -1.645, 3.59], [-1.957, 3.533, -1.645, 3.671], [-1.957, 3.612, -1.645, 3.751], [-1.781, -2.205, -1.468, -2.066], [-1.781, -2.126, -1.468, -1.987], [-1.781, -2.044, -1.468, -1.906], [-1.781, -1.968, -1.468, -1.83], [-1.781, -1.887, -1.468, -1.748], [-1.781, -1.83, -1.468, -1.691], [-1.781, -1.748, -1.468, -1.61], [-1.633, 3.156, -1.321, 3.294], [-1.633, 3.294, -1.321, 3.433], [-1.633, 3.452, -1.321, 3.59], [-1.633, 3.612, -1.321, 3.751], [-1.486, -2.161, -1.174, -2.019], [-1.402, 3.234, -0.86, 3.796], [-1.383, -1.887, -1.07, -1.748], [-1.346, -1.811, -1.104, -1.587], [-1.331, -2.256, -0.99, -2.001], [-1.217, 2.6, -0.947, 3.053], [-1.216, 2.123, -0.946, 2.576], [-1.216, 2.6, -0.946, 3.053], [-1.214, 3.109, -1.076, 3.421], [-1.214, 3.437, -1.076, 3.75], [-1.172, -2.161, -0.86, -2.019], [-1.103, -1.779, -0.791, -1.637], [-1.102, 3.354, -0.79, 3.492], [-1.102, 3.488, -0.79, 3.627], [-1.067, -0.483, -0.825, -0.258], [-1.057, 3.109, -0.919, 3.421], [-1.057, 3.437, -0.919, 3.75], [-1.054, -0.265, -0.748, 0.059], [-1.054, 0.079, -0.748, 0.403], [-1.054, 0.424, -0.748, 0.748], [-1.0, -1.0, 1.0, 1.0], [-0.98, 0.779, -0.744, 1.029], [-0.98, 1.039, -0.744, 1.289], [-0.98, 1.3, -0.744, 1.55], [-0.963, -1.354, -0.646, -1.175], [-0.956, -1.555, -0.639, -1.376], [-0.953, -0.953, 0.953, 0.953], [-0.945, -1.748, -0.628, -1.569], [-0.935, -2.093, -0.756, -1.776], [-0.926, 1.641, -0.656, 2.093], [-0.923, 1.644, -0.652, 2.097], [-0.923, 2.127, -0.652, 2.58], [-0.923, 2.6, -0.652, 3.053], [-0.922, -1.354, -0.605, -1.175], [-0.922, -1.174, -0.605, -0.995], [-0.922, -0.987, -0.605, -0.808], [-0.922, -0.793, -0.605, -0.614], [-0.922, -0.606, -0.605, -0.427], [-0.913, 1.641, -0.643, 2.093], [-0.913, 2.122, -0.643, 2.575], [-0.913, 2.6, -0.643, 3.053], [-0.896, 3.1, -0.758, 3.413], [-0.896, 3.109, -0.758, 3.421], [-0.896, 3.437, -0.758, 3.75], [-0.85, -1.673, -0.608, -1.448], [-0.85, -1.432, -0.608, -1.207], [-0.85, -1.191, -0.608, -0.966], [-0.85, -0.957, -0.608, -0.732], [-0.85, -0.723, -0.608, -0.498], [-0.85, -0.257, -0.608, -0.033], [-0.85, -0.017, -0.608, 0.208], [-0.85, 0.224, -0.608, 0.449], [-0.85, 0.459, -0.608, 0.683], [-0.85, 0.692, -0.608, 0.917], [-0.85, 0.931, -0.608, 1.155], [-0.85, 1.186, -0.608, 1.41], [-0.85, 1.425, -0.608, 1.649], [-0.76, -5.19, 1.282, -2.677], [-0.739, -2.081, -0.56, -1.764], [-0.657, -5.108, 1.244, -2.954], [-0.625, -5.153, 1.277, -3.009], [-0.613, -2.229, -0.491, 3.783], [-0.577, -5.134, 1.268, -3.113], [-0.543, -5.093, 1.153, -2.955], [-0.404, -3.847, -0.009, -3.478], [-0.342, -4.634, 0.991, -3.564], [-0.202, -4.176, 0.037, -3.898], [-0.147, -3.734, 0.512, -3.139], [-0.043, -4.632, 0.343, -4.275], [0.048, -4.9, 0.293, -4.655], [0.086, -4.293, 0.232, -3.963], [0.179, -3.852, 0.4, -3.625], [0.261, -4.064, 0.625, -3.753], [0.328, -10.539, 2.677, -10.4], [0.382, -4.381, 0.521, -4.069], [0.414, -4.775, 0.684, -4.505], [0.511, -3.696, 0.72, -3.501], [0.546, -4.291, 0.799, -3.949], [0.607, -9.038, 5.595, -2.96], [0.719, -4.611, 0.989, -4.341], [1.777, -8.287, 1.806, -3.848], [1.78, -7.294, 3.303, -5.826], [2.054, -8.399, 4.116, -8.37], [2.062, -3.628, 4.125, -3.599], [2.812, -7.028, 3.238, -4.722], [3.04, -1.494, 4.788, 4.326], [4.308, -7.243, 4.47, -6.374], [4.308, -5.931, 4.47, -5.063], [4.909, -10.205, 6.648, -8.103], [5.633, -9.716, 6.01, -8.611], [6.639, -10.769, 7.277, -10.131]],
    'clips': {'walk': [1, 23], 'idle': [1, 65], 'reach': [1, 37], 'sit': [1, 49]},
    'props': {'Prop_Item_1': {'stand': [-1.027, -3.791], 'yaw': 1.5708}, 'Prop_Item_2': {'stand': [-1.033, -4.165], 'yaw': 1.5708}, 'Prop_Item_3': {'stand': [-1.1, -4.582], 'yaw': 1.5708}, 'Prop_Item_4': {'stand': [0.873, -3.78], 'yaw': -1.5708}},
    'vehicles': {'SUV_root': {'yaw': -3.1416, 'lane': -8.26, 'cruise': 6.0, 'road': [-12.154, -7.846], 'wrap': [-19.0, 19.0], 'width': 2.353, 'length': 5.148, 'body_fwd': 1.554, 'reach': 4.03, 'getout_side': -1.0, 'tuktuk': False, 'door_angle': 48.0, 'door': 'SUV_Door_FR', 'seat': [2.004, -0.376, 0.472]}, 'TukTuk_root': {'yaw': 0.0, 'lane': -11.262, 'cruise': 4.2, 'road': [-12.008, -7.992], 'wrap': [-19.0, 19.0], 'width': 2.645, 'length': 4.444, 'body_fwd': -1.657, 'reach': 3.64, 'getout_side': 1.0, 'tuktuk': True, 'door_angle': 48.0, 'door': None, 'seat': [-1.657, 0.423, -0.325]}},
    'shop_doors': [['Shop_Door_L', -1.0], ['Shop_Door_R', 1.0]],
    'shop_door_angle': 96.0,
    'shop_door_centre': [-4.15, -2.0],
}
# <<< WORLD_DATA

# ---------------------------------------------------------------- tuning
WALK_SPEED = 1.28          # m/s at 1x playback of the walk clip (clip is 1.00 m/s)
RUN_SPEED = 1.95
TURN_RATE = 7.0            # rad/s
PLAYER_R = 0.20            # collision radius
REACH_TIME = 1.35          # seconds of the reach clip before the item is in hand
TAKE_RANGE = 1.70          # how far the boy can reach for a shelf item
FACE_CONE = 0.52           # ~30 deg -- standing in this cone makes an item "the" item
CAM_BACK = 3.35
CAM_UP = 1.90
CAM_LOOK_UP = 1.20
CAM_LAG = 8.0
CHASE_BACK = 7.6
CHASE_UP = 3.4

CAR_MAX_FWD = 13.0
CAR_MAX_REV = 5.0
CAR_ACC = 5.5
CAR_BRAKE = 9.0
CAR_COAST = 1.4
CAR_STEER = 1.15
CAR_CRUISE = 6.0
CAR_SEES_PLAYER = 6.5      # metres ahead in its lane where the bus brakes for you

DRIVE_EXIT = 1.9           # how far beside the car you climb out

LOG_PATH = os.environ.get("BOYLOG")
_T0 = time.time()


def L(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    if LOG_PATH:
        try:
            with open(LOG_PATH, "a") as f:
                f.write("%7.3f %s\n" % (time.time() - _T0, s))
        except Exception:
            pass


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


# ================================================================== world model
REGIONS = WORLD["regions"]
BLOCKERS = WORLD["blockers"]
WALL = WORLD["wall"]                 # [x0, x1] of the shop's storefront band
DOORWAY = WORLD["doorway"]           # [y0, y1] of the opening in that band
CLIPS = WORLD["clips"]
PROP_SPOTS = WORLD["props"]
VEHICLES = WORLD["vehicles"]


def region_at(x, y):
    for r in REGIONS:
        if r[1] <= x <= r[3] and r[2] <= y <= r[4]:
            return r
    return None


def ground_z(x, y):
    r = region_at(x, y)
    return None if r is None else r[5]


def blocked(x, y, r):
    for b in BLOCKERS:
        if b[0] - r < x < b[2] + r and b[1] - r < y < b[3] + r:
            return True
    return False


def can_stand(x, y, r=PLAYER_R, doors_open=True):
    if ground_z(x, y) is None:
        return False
    if blocked(x, y, r):
        return False
    if WALL[0] - r < x < WALL[1] + r:
        if not (doors_open and DOORWAY[0] + r * 0.5 <= y <= DOORWAY[1] - r * 0.5):
            return False
    return True


# ================================================================== engine
import bge
from mathutils import Vector, Matrix, Euler


def key_held(code):
    return bge.logic.keyboard.inputs[code].status != bge.logic.KX_INPUT_NONE


def key_hit(code):
    return bge.logic.keyboard.inputs[code].status == bge.logic.KX_INPUT_JUST_ACTIVATED


def clampv(v, r=PLAYER_R):
    """the collider is a sphere of radius r, but the walls are axis aligned so a
    rectangular probe is a better fit -- walk along whichever axis still fits"""
    return v


def scene_objects(sc):
    """KX_Scene.objects is an EXP_ListValue in this build, not a mapping"""
    try:
        return list(sc.objects.values())
    except AttributeError:
        return list(sc.objects)


def set_local_z_rot(obj, base_euler, deg):
    e = base_euler.copy()
    e.z = base_euler.z + math.radians(deg)
    obj.localOrientation = e.to_matrix()


class Animator(object):
    """thin wrapper over playAction.

    playAction restarts the action, so it is only issued when the clip or its
    playback speed actually changes -- otherwise the walk cycle would be reset
    every single frame.
    """

    def __init__(self, obj):
        self.obj = obj
        self.clip = None
        self.speed = None
        self.until = 0.0
        self.one_shot = False

    def play(self, clip, speed=1.0, one_shot=False, now=0.0, blend=0.18):
        if clip is None or clip not in CLIPS:
            return
        rng = CLIPS[clip]
        if self.clip == clip and not one_shot and self.speed is not None \
                and abs(self.speed - speed) < 0.01:
            return
        mode = bge.logic.KX_ACTION_MODE_PLAY if one_shot else bge.logic.KX_ACTION_MODE_LOOP
        try:
            self.obj.playAction(clip, rng[0], rng[1], 0, 0.0, blendin=blend,
                                play_mode=mode, speed=speed)
        except TypeError:
            try:
                self.obj.playAction(clip, rng[0], rng[1], 0, 0.0)
            except Exception:
                pass
        except Exception as exc:
            L("## anim error", clip, exc)
        self.clip = clip
        self.speed = speed
        self.one_shot = one_shot
        if one_shot:
            self.until = now + (rng[1] - rng[0]) / 24.0 / max(speed, 0.01)

    def finished(self, now):
        return self.one_shot and now >= self.until


class Actor(object):
    """one of the two boys"""

    def __init__(self, rig, title):
        self.rig = rig
        self.title = title
        self.anim = Animator(rig)
        self.pos = Vector(rig.worldPosition)
        self.yaw = 0.0
        self.carrying = None
        self.vehicle = None
        self.busy_until = 0.0
        self.pending_pickup = None

    def face(self, yaw):
        self.yaw = yaw
        self.rig.worldOrientation = Euler((0.0, 0.0, yaw)).to_matrix()

    def place(self, x, y, z=None):
        if z is None:
            z = ground_z(x, y)
        self.pos = Vector((x, y, z if z is not None else 0.06))
        self.rig.worldPosition = self.pos


class Vehicle(object):
    def __init__(self, root, data, scene):
        self.root = root
        self.data = data
        self.seat = data["seat"]
        self.yaw = data["yaw"]
        self.home_yaw = data["yaw"]
        self.pos = Vector(root.worldPosition)
        self.speed = 0.0
        self.driver = None
        self.door = None
        self.door_base = None
        self.door_frac = 0.0
        self.hailed = False
        if data.get("door"):
            self.door = scene.objects.get(data["door"])
            if self.door is not None:
                self.door_base = self.door.localOrientation.to_euler()
            else:
                L("## missing vehicle door", data["door"])

    # ---------- placement
    def apply(self):
        self.root.worldPosition = self.pos
        self.root.worldOrientation = Euler((0.0, 0.0, self.yaw)).to_matrix()
        if self.door is not None:
            set_local_z_rot(self.door, self.door_base, self.data["door_angle"] * self.door_frac)

    def forward(self):
        return Vector((math.sin(self.yaw), -math.cos(self.yaw), 0.0))

    def cabin(self, offset):
        """a world point expressed in metres relative to the vehicle's origin"""
        f = self.forward()
        right = Vector((math.cos(self.yaw), math.sin(self.yaw), 0.0))
        return self.pos + right * offset[1] + f * offset[0] + Vector((0.0, 0.0, offset[2]))

    def hit_box(self):
        c = self.pos + self.forward() * self.data["body_fwd"]
        f = self.forward()
        right = Vector((math.cos(self.yaw), math.sin(self.yaw), 0.0))
        return c, f, right


class Game(object):
    def __init__(self):
        self.sc = bge.logic.getCurrentScene()
        self.world = WORLD
        self.log = L
        self.frame = 0
        self.notes = []
        self.fails = []
        self.time = 0.0
        self.last = time.time()
        self.speed_hint = None

        bge.logic.setMaxLogicFrame(1)
        bge.logic.setLogicTicRate(60)
        self.t_next = 0.0
        res = os.environ.get("BOYRES", "")
        try:
            bge.render.setFullScreen(False)
        except Exception:
            pass
        if res and "x" in res:
            w, h = res.split("x")
            try:
                bge.render.setWindowSize(int(w), int(h))
                L("## window resized to", res)
            except Exception as exc:
                L("## resize failed", exc)

        self.cam = self.sc.objects["Camera_Game"]
        self.sc.active_camera = self.cam
        self.cam_yaw = 0.0

        self.actors = [Actor(self.sc.objects["Boy1_RIG"], "Boy 1 (blue shirt)"),
                       Actor(self.sc.objects["Boy2_RIG"], "Boy 2 (white shirt)")]
        self.active = 0

        self.props = sorted([o for o in scene_objects(self.sc) if o.name.startswith("Prop_Item_")],
                            key=lambda o: o.name)
        for p in self.props:
            p.visible = True

        self.doors = []
        for nm, sign in WORLD["shop_doors"]:
            o = self.sc.objects.get(nm)
            if o is not None:
                self.doors.append([o, o.localOrientation.to_euler(), sign])
        self.door_open = 0.0            # 0 closed, 1 open
        self.door_target = 0.0

        self.vehs = []
        for nm in ("SUV_root", "TukTuk_root"):
            data = VEHICLES.get(nm)
            if data is None:
                continue
            o = self.sc.objects.get(nm)
            if o is None:
                continue
            v = Vehicle(o, data, self.sc)
            v.apply()
            self.vehs.append(v)

        self.hud = {}
        for o in scene_objects(self.sc):
            if o.name.startswith("HUD_") or o.name.startswith("P_"):
                self.hud[o.name] = o
                o.visible = (o.name == "HUD_Help")
        for nm in ("HUD_Title1", "HUD_Title2"):
            if nm in self.hud:
                self.hud[nm].visible = (nm == "HUD_Title1")

        self.prompt = None
        self.apply_cutaways()
        self.shadow_switch()
        self.scene_ready()

    def apply_cutaways(self):
        """BOYHIDE=boys,hud,cubes,crowd -- a diagnostic switch for profiling the scene"""
        want = [s for s in (os.environ.get("BOYHIDE") or "").split(",") if s]
        if not want:
            return
        for o in scene_objects(self.sc):
            if "boys" in want and o.name.startswith("Boy"):
                o.visible = False
            if "cubes" in want and o.name.startswith("Cube"):
                o.visible = False
            if "crowd" in want and (o.name.startswith(("Plane", "Circle", "dose", "Cylinder"))):
                o.visible = False
        if "hud" in want:
            for o in self.hud.values():
                o.visible = False
        L("## cutaways applied:", want)

    def shadow_switch(self):
        """Every lamp's shadow is off by default: this scene is 750 objects, and
        measuring showed shadow passes were roughly half of the frame cost
        (0.9 fps -> 1.9 fps). BOYNOSHADOW=1 turns them back on."""
        val = os.environ.get("BOYNOSHADOW", "0")
        on = val != "0"
        try:
            import bpy
        except ImportError:
            L("## no bpy in the game session, cannot touch the lights")
            return
        n = 0
        for l in bpy.data.lights:
            try:
                l.use_shadow = on
                n += 1
            except Exception as exc:
                L("## light %s: %r" % (l.name, exc))
        L("## shadows set to %s on %d lamps" % (on, n))

    # ------------------------------------------------------------ helpers
    def note(self, msg):
        self.notes.append(msg)
        L("NOTE", msg)

    def check(self, ok, msg):
        (self.note if ok else self.fail)(("PASS " if ok else "FAIL ") + msg)

    def fail(self, msg):
        self.fails.append(msg)
        L("FAIL", msg)

    def scene_ready(self):
        a = self.actors[0]
        L("## scene", self.sc.name, "objects", len(self.sc.objects))
        L("## regions", len(REGIONS), "blockers", len(BLOCKERS), "props", len(self.props),
          "vehicles", [v.root.name for v in self.vehs])
        L("## clips", CLIPS)
        L("## has channels attr:", hasattr(a.rig, "channels"))
        for v in self.vehs:
            L("## vehicle %s pos=%s seat=%s door=%s" % (
                v.root.name, tuple(round(x, 3) for x in v.pos), v.seat,
                v.door.name if v.door else None))
        # stand the boys on the pavement
        for a in self.actors:
            a.place(a.pos.x, a.pos.y)
            a.face(0.0)
        self.cam_yaw = 0.0
        self.snap_camera()

    # ------------------------------------------------------------ input
    def read_input(self):
        k = bge.events
        mx = (1.0 if key_held(k.DKEY) else 0.0) - (1.0 if key_held(k.AKEY) else 0.0)
        my = (1.0 if key_held(k.WKEY) else 0.0) - (1.0 if key_held(k.SKEY) else 0.0)
        return {
            "mx": mx, "my": my,
            "run": key_held(k.LEFTSHIFTKEY) or key_held(k.RIGHTSHIFTKEY),
            "use": key_hit(k.EKEY),
            "tab": key_hit(k.TABKEY),
            "quit": key_hit(k.ESCKEY),
        }

    # ------------------------------------------------------------ camera
    def snap_camera(self):
        self.cam.worldPosition = Vector((0, 0, 0))
        self.place_camera(1.0)

    def place_camera(self, blend):
        a = self.actors[self.active]
        if a.vehicle is not None:
            v = a.vehicle
            f = v.forward()
            tgt = v.pos + f * v.data["body_fwd"] + Vector((0, 0, 1.0))
            want = tgt - f * CHASE_BACK + Vector((0, 0, CHASE_UP))
            look = tgt + Vector((0, 0, 0.2))
        else:
            f = Vector((math.sin(self.cam_yaw), -math.cos(self.cam_yaw), 0.0))
            tgt = a.pos + Vector((0, 0, CAM_LOOK_UP))
            want = tgt - f * CAM_BACK + Vector((0, 0, CAM_UP - CAM_LOOK_UP))
            want = self.avoid_walls(tgt, want)
            look = tgt
        if blend >= 1.0:
            self.cam.worldPosition = want
        else:
            self.cam.worldPosition = self.cam.worldPosition.lerp(want, blend)
        d = look - self.cam.worldPosition
        if d.length > 0.01:
            self.cam.worldOrientation = d.to_track_quat('-Z', 'Y').to_matrix()

    def avoid_walls(self, target, want):
        """do not let the follow camera sit inside the storefront or a shelf"""
        p = Vector(want)
        for i in range(6):
            if can_stand(p.x, p.y, 0.05, doors_open=(self.door_open > 0.5)):
                return p
            p = p.lerp(target, 0.28)
        return p

    # ------------------------------------------------------------ movement
    def move_actor(self, a, mx, my, run, dt):
        if mx == 0.0 and my == 0.0:
            return 0.0
        cy = self.cam_yaw
        fwd = Vector((math.sin(cy), -math.cos(cy), 0.0))
        right = Vector((math.cos(cy), math.sin(cy), 0.0))
        d = fwd * my + right * mx
        if d.length < 1e-6:
            return 0.0
        d.normalize()
        want_yaw = math.atan2(d.x, -d.y)
        diff = (want_yaw - a.yaw + math.pi) % (2.0 * math.pi) - math.pi
        a.yaw += clamp(diff, -TURN_RATE * dt, TURN_RATE * dt)
        a.face(a.yaw)
        speed = RUN_SPEED if run else WALK_SPEED
        f = Vector((math.sin(a.yaw), -math.cos(a.yaw), 0.0))
        step = f * speed * dt
        npos = a.pos + step
        ok = can_stand(npos.x, npos.y, PLAYER_R, self.door_open > 0.5)
        self.speed_hint = 1 if ok else 0
        if ok:
            a.pos = npos
        else:
            p2 = Vector((a.pos.x + step.x, a.pos.y, a.pos.z))
            if can_stand(p2.x, p2.y, PLAYER_R, self.door_open > 0.5):
                a.pos = p2
            else:
                p3 = Vector((a.pos.x, a.pos.y + step.y, a.pos.z))
                if can_stand(p3.x, p3.y, PLAYER_R, self.door_open > 0.5):
                    a.pos = p3
                else:
                    speed = 0.0
        a.pos.z = ground_z(a.pos.x, a.pos.y)
        a.rig.worldPosition = a.pos
        return speed

    # ------------------------------------------------------------ shop doors
    def shop_door_dist(self, a):
        c = WORLD["shop_door_centre"]
        return math.hypot(a.pos.x - c[0], a.pos.y - c[1])

    def update_doors(self, dt):
        self.door_open += clamp(self.door_target - self.door_open, -1.6 * dt, 1.6 * dt)
        for o, base, sign in self.doors:
            set_local_z_rot(o, base, WORLD["shop_door_angle"] * sign * self.door_open)

    # ------------------------------------------------------------ props
    def prop_dist(self, a, p):
        return math.hypot(a.pos.x - p.worldPosition.x, a.pos.y - p.worldPosition.y)

    def facing_angle(self, a, p):
        """radians between the way the boy is looking and the item"""
        dx = p.worldPosition.x - a.pos.x
        dy = p.worldPosition.y - a.pos.y
        d = math.hypot(dx, dy)
        if d < 1e-6:
            return 0.0
        f = Vector((math.sin(a.yaw), -math.cos(a.yaw), 0.0))
        return math.acos(clamp((f.x * dx + f.y * dy) / d, -1.0, 1.0))

    def pick_up(self, a, p):
        a.carrying = p
        a.pending_pickup = p
        a.busy_until = self.time + REACH_TIME
        a.anim.play("reach", one_shot=True, now=self.time)
        self.note("taking %s" % p.name)

    def carry_point(self, a):
        f = Vector((math.sin(a.yaw), -math.cos(a.yaw), 0.0))
        left = Vector((-f.y, f.x, 0.0))
        return a.pos + f * 0.30 + left * 0.17 + Vector((0.0, 0.0, 1.02))

    def update_carry(self, a):
        p = a.carrying
        if p is None:
            return
        if a.pending_pickup is not None and self.time >= a.busy_until - REACH_TIME * 0.45:
            a.pending_pickup = None          # the hand has arrived
        if a.pending_pickup is not None:
            return
        p.worldPosition = self.carry_point(a)
        p.worldOrientation = Euler((0.0, 0.0, a.yaw)).to_matrix()

    def drop(self, a):
        p = a.carrying
        if p is None:
            return
        a.carrying = None
        a.pending_pickup = None
        f = Vector((math.sin(a.yaw), -math.cos(a.yaw), 0.0))
        spot = a.pos + f * 0.55
        z = ground_z(spot.x, spot.y)
        if z is None:
            spot = a.pos
            z = a.pos.z
        p.worldPosition = Vector((spot.x, spot.y, z))
        p.worldOrientation = Euler((0.0, 0.0, a.yaw)).to_matrix()
        self.note("put down %s" % p.name)

    # ------------------------------------------------------------ vehicles
    def near_vehicle(self, a):
        best = None
        for v in self.vehs:
            c = v.pos + v.forward() * v.data["body_fwd"]
            d = math.hypot(a.pos.x - c.x, a.pos.y - c.y)
            if d < v.data["reach"] and (best is None or d < best[1]):
                best = (v, d)
        return best

    def update_vehicles(self, dt):
        for v in self.vehs:
            if v.driver is None:
                self.auto_drive(v, dt)
            v.apply()
            if v.driver is not None:
                self.seat_driver(v)

    def auto_drive(self, v, dt):
        d = v.data
        target = 0.0 if v.hailed else d["cruise"]
        # brake for a player standing in the road ahead
        for a in self.actors:
            if a.vehicle is not None:
                continue
            f = v.forward()
            rel = a.pos - v.pos
            ahead = rel.dot(f)
            lat = rel.dot(Vector((math.cos(v.yaw), math.sin(v.yaw), 0.0)))
            if 0.5 < ahead < CAR_SEES_PLAYER and abs(lat) < d["width"] * 0.6:
                target = 0.0
        v.speed += clamp(target - v.speed, -CAR_BRAKE * dt, 2.5 * dt)
        # steer toward a carrot further along the lane. Correcting the lane offset by
        # nudging the yaw directly has the wrong sign at yaw=pi and the vehicle ends up
        # pinned against a kerb, so aim at a point instead.
        sign = 1.0 if v.forward().y >= 0.0 else -1.0
        to = Vector((d["lane"], v.pos.y + sign * 8.0, 0.0)) - v.pos
        if to.length > 0.01:
            want = math.atan2(to.x, -to.y)
            err = (want - v.yaw + math.pi) % (2.0 * math.pi) - math.pi
            v.yaw += clamp(err, -0.8 * dt, 0.8 * dt)
        v.pos += v.forward() * v.speed * dt
        self.wrap_vehicle(v)

    def wrap_vehicle(self, v):
        d = v.data
        if v.pos.y > d["wrap"][1]:
            v.pos.y -= (d["wrap"][1] - d["wrap"][0])
        elif v.pos.y < d["wrap"][0]:
            v.pos.y += (d["wrap"][1] - d["wrap"][0])
        v.pos.x = clamp(v.pos.x, d["road"][0], d["road"][1])

    def seat_driver(self, v):
        a = v.driver
        a.pos = v.cabin(v.seat)
        a.rig.worldPosition = a.pos
        a.yaw = v.yaw
        a.rig.worldOrientation = Euler((0.0, 0.0, a.yaw)).to_matrix()

    def drive(self, v, mx, my, dt):
        if my > 0.0:  # noqa
            v.speed += CAR_ACC * dt * my
        elif my < 0.0:
            if v.speed > 0.15:
                v.speed -= CAR_BRAKE * dt
            else:
                v.speed -= CAR_ACC * 0.6 * dt
        else:
            v.speed -= clamp(v.speed, -CAR_COAST * dt, CAR_COAST * dt)
        v.speed = clamp(v.speed, -CAR_MAX_REV, CAR_MAX_FWD)
        if abs(v.speed) > 0.2 and mx:
            grip = 1.0 - 0.45 * min(1.0, abs(v.speed) / CAR_MAX_FWD)
            v.yaw += mx * CAR_STEER * dt * grip * (1.0 if v.speed >= 0 else -1.0)
        f = v.forward()
        npos = v.pos + f * v.speed * dt
        d = v.data
        inside = (d["road"][0] <= npos.x <= d["road"][1] and
                  d["wrap"][0] + 0.4 <= npos.y <= d["wrap"][1] - 0.4)
        if inside:
            v.pos = npos
        else:
            v.speed *= 0.25
        if not inside:
            # keep it inside the kerbs rather than in the wall
            v.pos.x = clamp(v.pos.x, d["road"][0], d["road"][1])
            v.pos.y = clamp(v.pos.y, d["wrap"][0] + 0.4, d["wrap"][1] - 0.4)

    def enter_vehicle(self, v, a):
        v.driver = a
        a.vehicle = v
        v.speed = 0.0
        v.hailed = True
        v.door_frac = 0.0
        a.carrying = None
        a.pending_pickup = None
        a.anim.play("sit")
        self.note("entered %s" % v.root.name)

    def leave_vehicle(self, v, a):
        v.driver = None
        v.speed = 0.0
        v.hailed = True
        a.vehicle = None
        right = Vector((math.cos(v.yaw), math.sin(v.yaw), 0.0))
        f = v.forward()
        side = v.data["getout_side"]
        centre = v.pos + f * v.data["body_fwd"]
        # the first spot beside the door is the natural one, but near the end of the
        # road it lands outside the walkable strip, so try a ring of candidates
        cands = []
        for dist in (v.data["width"] * 0.5 + 0.8, v.data["width"] * 0.5 + 1.3, 2.8):
            for s in (side, -side):
                spot = centre + right * dist * s
                cands.append(spot)
                cands.append(spot + f * 2.2)
                cands.append(spot - f * 2.2)
        spot = None
        for cand in cands:
            if can_stand(cand.x, cand.y, PLAYER_R, self.door_open > 0.5):
                spot = cand
                break
        if spot is None:
            spot = centre
        a.place(spot.x, spot.y)
        a.face(v.yaw)
        a.anim.play("idle")
        self.note("left %s at (%.2f, %.2f) %s" % (
            v.root.name, a.pos.x, a.pos.y,
            "" if can_stand(a.pos.x, a.pos.y, PLAYER_R, True) else "(WARNING: outside the walkable area)"))

    # ------------------------------------------------------------ interactions
    def interaction(self, a):
        """(kind, distance, payload) for the best thing the active boy can use"""
        cands = []
        if a.carrying is not None:
            cands.append(("drop", 0.0, None))
        # shelf items: everything within reach is a candidate, but the one the boy
        # is looking at wins -- otherwise the nearest item always shadows the rest
        # and the shops four display pieces can only ever be taken in one order
        reach = []
        for p in self.props:
            if p is a.carrying:
                continue
            d = self.prop_dist(a, p)
            if d < TAKE_RANGE:
                reach.append((self.facing_angle(a, p), d, p))
        if reach:
            faced = [c for c in reach if c[0] < FACE_CONE]
            pick = min(faced, key=lambda c: c[0]) if faced else min(reach, key=lambda c: c[1])
            cands.append(("take", pick[1], pick[2]))
        nv = self.near_vehicle(a)
        if nv is not None:
            v, d = nv
            if v.driver is not None:
                pass
            elif v.door is not None and v.door_frac > 0.8:
                cands.append(("enter", 0.4, v))
            elif abs(v.speed) > 0.35:
                cands.append(("stop", d, v))
            elif v.door is not None:
                cands.append(("vehdoor", d, v))
            else:
                cands.append(("enter", d, v))
        if self.shop_door_dist(a) < 2.3:
            if self.door_target > 0.5:
                cands.append(("doorclose", self.shop_door_dist(a), None))
            else:
                cands.append(("dooropen", self.shop_door_dist(a), None))
        if not cands:
            return None
        cands.sort(key=lambda c: c[1])
        return cands[0]

    def do_interaction(self, a, it):
        kind, dist, payload = it
        if kind == "drop":
            self.drop(a)
        elif kind == "take":
            self.pick_up(a, payload)
        elif kind == "dooropen":
            self.door_target = 1.0
            self.note("shop door opening")
        elif kind == "doorclose":
            self.door_target = 0.0
            self.note("shop door closing")
        elif kind == "stop":
            payload.speed = 0.0
            payload.hailed = True
            self.note("signalled %s to stop" % payload.root.name)
        elif kind == "vehdoor":
            payload.door_frac = 1.0
            self.note("opened %s door" % payload.root.name)
        elif kind == "enter":
            if payload.driver is not None:
                return
            self.enter_vehicle(payload, a)

    # ------------------------------------------------------------ hud
    def update_hud(self, it):
        want = [("HUD_Help", True)]
        if self.active == 0:
            want += [("HUD_Title1", True)]
        else:
            want += [("HUD_Title2", True)]
        a = self.actors[self.active]
        if a.carrying is not None:
            want.append(("HUD_Carry", True))
        if a.vehicle is not None:
            want.append(("P_Drive", True))
        elif it is not None:
            m = {"dooropen": "P_DoorOpen", "doorclose": "P_DoorClose", "take": "P_Take",
                 "drop": "P_Drop", "stop": "P_BusStop", "vehdoor": "P_VehDoor",
                 "enter": "P_VehEnter"}
            nm = m.get(it[0])
            if nm == "P_VehEnter" and getattr(it[2], "data", {}).get("tuktuk"):
                nm = "P_TukEnter"
            if nm:
                want.append((nm, True))
        on = set(n for n, v in want if v)
        for name, o in self.hud.items():
            o.visible = name in on

    # ------------------------------------------------------------ main step
    def step(self, inp, dt):
        self.frame += 1
        self.time += dt
        a = self.actors[self.active]

        if inp.get("quit"):
            return False
        if inp.get("tab") and a.vehicle is None and self.actors[1 - self.active].vehicle is None:
            a.anim.play("idle")
            self.active = 1 - self.active
            self.cam_yaw = self.actors[self.active].yaw
            a = self.actors[self.active]
            self.note("switched to %s" % a.title)

        if a.vehicle is not None:
            self.drive(a.vehicle, inp["mx"], inp["my"], dt)
            if self.time >= a.busy_until:
                speed = 0.0
        else:
            busy = self.time < a.busy_until
            speed = 0.0 if busy else self.move_actor(a, inp["mx"], inp["my"], inp["run"], dt)
            if not busy:
                if speed > 0.05:
                    a.anim.play("walk", speed=(speed / 1.002))
                else:
                    a.anim.play("idle")
            elif a.anim.finished(self.time):
                a.busy_until = 0.0

        self.update_doors(dt)
        self.update_vehicles(dt)
        for act in self.actors:
            self.update_carry(act)

        it = None if a.vehicle is not None else self.interaction(a)
        if it is not None and inp.get("use"):
            self.do_interaction(a, it)
        elif inp.get("use") and a.vehicle is not None:
            self.leave_vehicle(a.vehicle, a)
            a.busy_until = self.time + 0.4

        if a.vehicle is None:
            # smooth third person: the camera swings behind the way we are walking
            target_yaw = a.yaw
            diff = (target_yaw - self.cam_yaw + math.pi) % (2.0 * math.pi) - math.pi
            if speed > 0.05:
                self.cam_yaw += diff * min(1.0, 6.0 * dt)
        self.place_camera(min(1.0, CAM_LAG * dt))
        self.update_hud(it)
        if self.frame % 120 == 0:
            L("## frame %d  fps=%.1f  frame_time=%.3f  engine_tick=%.3f" % (
                self.frame, bge.logic.getAverageFrameRate(), bge.logic.getFrameTime(), self.t_next))
        return True


# ================================================================== autopilot
def load_scenario(path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("scenario", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    g = Game()
    scen_path = os.environ.get("BOYSCEN", "")
    scen = load_scenario(scen_path) if scen_path else None
    if scen is not None:
        scen.setup(g)
    max_frames = int(os.environ.get("BOYFRAMES", "3600")) if scen else 0
    dt_max = float(os.environ.get("BOYDT", "0.05"))

    while True:
        now = time.time()
        dt = clamp(now - g.last, 0.0005, dt_max)
        g.last = now
        if scen is not None:
            inp = scen.step(g, g.frame, dt)
        else:
            inp = g.read_input()
        t0 = time.time()
        cont = g.step(inp, dt)
        t1 = time.time()
        g.t_next = t1 - t0
        if not cont:
            break
        plan = getattr(scen, "PLAN", None) if scen is not None else None
        if plan is not None and g.auto["i"] >= len(plan):
            L("## scenario complete after", g.frame, "frames")
            break
        if scen is not None and g.frame >= max_frames:
            L("## hit frame limit", max_frames)
            break
        bge.logic.NextFrame()

    if scen is not None:
        scen.finish(g)
        L("## notes:", len(g.notes), "failures:", len(g.fails))
        for f in g.fails:
            L("##   FAILED:", f)
        L("## RESULT", "PASS" if not g.fails else "FAIL")
    L("## frames", g.frame)


main()

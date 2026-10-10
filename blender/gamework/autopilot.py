"""autopilot.py -- a scripted playthrough of the shop game, run inside the real engine.

The game only takes input from the keyboard, so a scenario like this is the only way
to drive it end to end without a human at the keys. Every stage states what it
expects to be true when it is done, and the game records PASS/FAIL for each.

    BOYLOG=... BOYSCEN=.../autopilot.py blenderplayer.exe Shop_with_people.blend
"""

import math
import os

SHOTS = "E:/UPBGE/shots"
DOOR_FRONT = (-5.0, -2.0)
OLD_SHELF_1 = (-0.637, -3.791)      # replaced in setup() by the measured stand spot
SHELF_1 = OLD_SHELF_1
ROADSIDE = (-6.70, 4.00)


LOOK_TIME = 0.5              # seconds spent turning to look at an item before E


def neutral():
    return {"mx": 0.0, "my": 0.0, "run": False, "use": False, "tab": False}


def actor(g):
    return g.actors[g.active]


def suv(g):
    for v in g.vehs:
        if v.root.name == "SUV_root":
            return v
    return g.vehs[0]


def steer(g, target):
    a = actor(g)
    d = (target[0] - a.pos.x, target[1] - a.pos.y)
    ln = math.hypot(d[0], d[1])
    inp = neutral()
    if ln < 1e-6:
        return inp
    d = (d[0] / ln, d[1] / ln)
    cy = g.cam_yaw
    fwd = (math.sin(cy), -math.cos(cy))
    right = (math.cos(cy), math.sin(cy))
    inp["my"] = d[0] * fwd[0] + d[1] * fwd[1]
    inp["mx"] = d[0] * right[0] + d[1] * right[1]
    return inp


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def car_near_player(g):
    v = suv(g)
    c = v.pos + v.forward() * v.data["body_fwd"]
    a = actor(g)
    return math.hypot(c.x - a.pos.x, c.y - a.pos.y)


def prop(g, name):
    for p in g.props:
        if p.name == name:
            return p
    return None


# the shop's four display items all stand on the same counter, so the easy item
# shadows its neighbours unless the boy takes the one he is looking at: this
# sweep walks up to each item, looks at it, presses E, and checks WHICH item
# ended up in his hands.
SWEEP_ITEMS = ("Prop_Item_2", "Prop_Item_3", "Prop_Item_4")
DROP_SPOT = (-3.60, -2.60)   # open floor by the shop's west aisle, inside the door
TAKE_RANGE = 1.70            # must match game.py's TAKE_RANGE


def make_sweep(g):
    """one look-and-take pass per shelf item, dropped clear of the shelf again

    Run before the generic take stage: while four items share one counter, the
    boy always picks the one he is looking at, so a sweep has to name its item
    and check the name that ends up in his hands.
    """
    out = []
    for name in SWEEP_ITEMS:
        p = prop(g, name)
        if p is None:
            g.note("sweep: %s is missing from the scene" % name)
            continue
        here = (p.worldPosition.x, p.worldPosition.y)

        def walked(g, n=name):
            d = g.prop_dist(actor(g), prop(g, n))
            return d < TAKE_RANGE, "%s is %.2f m away" % (n, d)

        def holding(g, n=name):
            c = actor(g).carrying
            return (c is not None and c.name == n,
                    "carrying %s" % (c.name if c else "nothing"))

        out.append({"label": "walk up to %s on the shelf" % name,
                    "goto": [here], "tol": 1.60, "check": walked})
        out.append({"label": "look at %s and take it" % name,
                    "use": True, "face": here, "after": 0.8, "retry": 4, "check": holding})
        out.append({"label": "carry %s clear of the shelf and put it down" % name,
                    "goto": [DROP_SPOT], "tol": 0.40, "use": True, "after": 0.5,
                    "check": lambda g: (actor(g).carrying is None, "hands empty again")})
    out.append({"label": "walk back to the shelf",
                "goto": [DROP_SPOT, SHELF_1], "tol": 0.32,
                "check": lambda g: (actor(g).pos.x > SHELF_1[0] - 0.33,
                                    "back at the shelf (%.2f, %.2f)" % (actor(g).pos.x,
                                                                        actor(g).pos.y))})
    return out


# ------------------------------------------------------------------ the plan
PLAN = [
    {"label": "walk south along the pavement to the shop door",
     "goto": [(-5.0, 4.0), (-5.0, 1.0), DOOR_FRONT], "tol": 0.35,
     "check": lambda g: (actor(g).pos.y < -1.4, "reached y=%.2f" % actor(g).pos.y)},

    {"label": "open the shop door",
     "use": True, "after": 2.2, "shot": "01_shop_door_open.png",
     "check": lambda g: (g.door_open > 0.9, "door_open=%.2f" % g.door_open)},

    {"label": "walk through the doorway into the shop",
     "goto": [(-4.70, -2.0), (-4.15, -2.0), (-3.60, -2.60), SHELF_1], "tol": 0.32,
     # the tolerance above lets the walk stop up to 0.32 m short of the shelf, so
     # the check has to allow the same slack or it fails on a 2 cm miss
     "check": lambda g: (actor(g).pos.x > SHELF_1[0] - 0.33,
                         "inside the shop at (%.2f, %.2f)" % (actor(g).pos.x, actor(g).pos.y))},

    {"label": "take an item off the shelf",
     "use": True, "after": 0.8, "shot": "02_taking_item.png",
     "check": lambda g: (actor(g).carrying is not None,
                         "carrying %s" % (actor(g).carrying.name if actor(g).carrying else "nothing"))},

    {"label": "put it back down",
     "use": True, "after": 0.5,
     "check": lambda g: (actor(g).carrying is None, "hands empty again")},

    {"label": "pick it up once more so we can see it carried",
     "use": True, "after": 0.8, "shot": "03_carrying.png",
     "check": lambda g: (actor(g).carrying is not None, "carrying again")},

    {"label": "walk back out onto the pavement",
     "goto": [(-3.60, -2.60), (-4.15, -2.0), (-4.70, -2.0), (-5.20, 0.60)], "tol": 0.35,
     "check": lambda g: (actor(g).pos.x < -4.5, "back outside at x=%.2f" % actor(g).pos.x)},

    {"label": "put the item down outside",
     "use": True, "after": 0.5,
     "check": lambda g: (actor(g).carrying is None, "item left on the pavement")},

    {"label": "walk round onto the road, beside the bus lane",
     "goto": [(-5.60, 3.20), ROADSIDE], "tol": 0.35,
     "check": lambda g: (actor(g).pos.x < -6.4,
                         "standing on the roadside at (%.2f, %.2f)" % (actor(g).pos.x, actor(g).pos.y))},

    {"label": "wait for the bus to come down the road",
     "poll": 60.0, "shot": "04_bus_approaching.png",
     "trace": lambda g: "bus at (%.2f, %.2f) speed %.2f yaw %.2f | player (%.2f, %.2f)" % (
         suv(g).pos.x, suv(g).pos.y, suv(g).speed, suv(g).yaw,
         actor(g).pos.x, actor(g).pos.y),
     "check": lambda g: (car_near_player(g) < 4.0,
                         "bus is %.1f m away" % car_near_player(g))},

    # the bus covers 1.2 m per simulated step at BOYDT=0.2, so its reach window is
    # only a few frames wide: press again almost every frame until it takes. Holding
    # E down instead would cascade stop -> open -> enter -> leave, so keep the
    # presses one frame long and lean on the retries.
    {"label": "signal the bus to stop",
     "use": True, "after": 0.0, "poll": 0.2, "retry": 12, "shot": "05_bus_stopped.png",
     "check": lambda g: (abs(suv(g).speed) < 0.05, "bus speed %.2f m/s" % suv(g).speed)},

    {"label": "open the vehicle door",
     "use": True, "after": 0.8, "poll": 0.3, "retry": 6, "shot": "06_vehicle_door_open.png",
     "check": lambda g: (suv(g).door_frac > 0.8, "door open fraction %.2f" % suv(g).door_frac)},

    {"label": "get in and take the wheel",
     "use": True, "after": 0.6, "poll": 0.3, "retry": 4, "shot": "07_seated_in_car.png",
     "check": lambda g: (actor(g).vehicle is not None, "seated in the vehicle")},

    {"label": "drive it down the road",
     "on_enter": lambda g: setattr(suv(g), "_y0", suv(g).pos.y),
     "hold": {"mx": 0.0, "my": 1.0}, "after": 3.5, "shot": "08_driving.png",
     "check": lambda g: (actor(g).vehicle is not None and
                         abs(suv(g).pos.y - suv(g)._y0) > 4.0,
                         "drove %.1f m" % abs(suv(g).pos.y - suv(g)._y0))},

    {"label": "get out again",
     "use": True, "after": 1.0, "retry": 3, "shot": "09_got_out.png",
     "check": lambda g: (actor(g).vehicle is None and car_near_player(g) < 8.0,
                         "on foot %.1f m from the car at (%.2f, %.2f)" % (
                             car_near_player(g), actor(g).pos.x, actor(g).pos.y))},

    {"label": "swap to the second boy",
     "tab": True, "after": 0.4, "retry": 3, "shot": "10_second_boy.png",
     "check": lambda g: (g.active == 1, "now playing %s" % g.actors[g.active].title)},
]


def setup(g):
    global SHELF_1
    # the stand spot is measured by the build script -- never hard code it twice
    spot = (g.world.get("props") or {}).get("Prop_Item_1", {}).get("stand")
    if spot:
        SHELF_1 = tuple(spot)
        for st in PLAN:
            if st.get("goto"):
                st["goto"] = [SHELF_1 if tuple(p) == OLD_SHELF_1 else p for p in st["goto"]]
    sweep = make_sweep(g)
    if sweep:
        # slot the sweep in while all four items are still on the counter, before
        # the generic take stage that only checks that SOMETHING was picked up
        cut = next((k for k, st in enumerate(PLAN)
                    if st["label"].startswith("take an item off the shelf")), len(PLAN))
        PLAN[cut:cut] = sweep

    os.makedirs(SHOTS, exist_ok=True)
    g.note("shelf stand spot %s" % (SHELF_1,))
    g.auto = {"i": 0, "phase": "goto", "act": "goto", "wp": 0, "t": 0.0,
              "tries": 0, "shot_n": 0}
    for v in g.vehs:
        v._y0 = v.pos.y
    g.note("autopilot: %d stages" % len(PLAN))


def action_phase(stage):
    """the phase that actually does something, so a stage can retry itself"""
    if stage.get("goto"):
        return "goto"
    if stage.get("use"):
        return "use"
    if stage.get("tab"):
        return "tab"
    if stage.get("after"):
        return "after"
    return "check"


def _advance(g):
    st = g.auto
    st["i"] += 1
    st["phase"] = "goto"
    st["wp"] = 0
    st["t"] = 0.0
    st["act"] = action_phase(PLAN[st["i"]]) if st["i"] < len(PLAN) else "check"
    st["tries"] = 0
    st["shot_done"] = False
    if st["i"] < len(PLAN):
        hook = PLAN[st["i"]].get("on_enter")
        if hook:
            hook(g)


def step(g, frame, dt):
    st = g.auto
    if st["i"] >= len(PLAN):
        return neutral()
    stage = PLAN[st["i"]]
    inp = neutral()

    if st["phase"] == "goto":
        pts = stage.get("goto")
        if not pts:
            st["phase"] = "use" if stage.get("use") else ("tab" if stage.get("tab") else
                                                          ("after" if stage.get("after") else "check"))
            st["act"] = st["phase"]
            st["t"] = 0.0
        else:
            tgt = pts[st["wp"]]
            a = actor(g)
            st["t"] += dt
            if st["t"] - st.get("trace", -99.0) > 4.0:
                st["trace"] = st["t"]
                g.note("  goto %s: at (%.2f, %.2f) yaw=%.2f cam=%.2f block=%d" % (
                    tgt, a.pos.x, a.pos.y, a.yaw, g.cam_yaw,
                    g.speed_hint if g.speed_hint is not None else -1))
            if dist((a.pos.x, a.pos.y), tgt) < stage.get("tol", 0.32):
                st["wp"] += 1
                st["t"] = 0.0
                if st["wp"] >= len(pts):
                    st["phase"] = "use" if stage.get("use") else ("after" if stage.get("after")
                                                                  else "check")
                    st["act"] = "use" if stage.get("use") else "after"
                    st["t"] = 0.0
            elif st["t"] > stage.get("timeout", 30.0):
                g.check(False, "%s -- stuck at (%.2f, %.2f) heading for %s" % (
                    stage["label"], a.pos.x, a.pos.y, tgt))
                _advance(g)
            else:
                inp = steer(g, tgt)
                inp["run"] = False

    elif st["phase"] == "use":
        st["t"] += dt
        face = stage.get("face")
        if face and st["t"] < LOOK_TIME:
            # a player would turn to look at the thing before pressing E: several
            # items on one counter are only separable by which way the boy faces
            inp = steer(g, face)
        else:
            inp = neutral()
            inp["use"] = True
            if st["t"] >= stage.get("use_hold", 0.0) + (LOOK_TIME if face else 0.0):
                st["phase"] = "after" if stage.get("after") else "check"
                st["t"] = 0.0

    elif st["phase"] == "tab":
        inp = neutral()
        inp["tab"] = True
        st["phase"] = "after" if stage.get("after") else "check"
        st["t"] = 0.0

    elif st["phase"] == "after":
        st["t"] += dt
        hold = stage.get("hold")
        if hold:
            inp = dict(neutral())
            inp.update(hold)
        if st["t"] >= stage.get("after", 0.0):
            if stage.get("shot") and not st.get("shot_done"):
                _shot(g, stage["shot"])
                st["shot_done"] = True
            st["phase"] = "check"
            st["t"] = 0.0

    elif st["phase"] == "check":
        chk = stage.get("check")
        if chk is None:
            g.note("done: %s" % stage["label"])
            _advance(g)
        else:
            ok, msg = chk(g)
            if ok:
                g.check(True, "%s -- %s" % (stage["label"], msg))
                _advance(g)
            else:
                st["t"] += dt
                if stage.get("trace") and st["t"] - st.get("trace_at", -99.0) > 5.0:
                    st["trace_at"] = st["t"]
                    g.note("  " + stage["trace"](g))
                if st["t"] >= stage.get("poll", 0.7):
                    tries = st.get("tries", 0)
                    if tries < stage.get("retry", 0):
                        st["tries"] = tries + 1
                        g.note("  retry %d of %s: %s" % (tries + 1, stage.get("retry", 0),
                                                          stage["label"]))
                        st["phase"] = st.get("act", "use")
                        st["wp"] = 0
                        st["t"] = 0.0
                    else:
                        if stage.get("shot") and not st.get("shot_done"):
                            _shot(g, stage["shot"])
                            st["shot_done"] = True
                        g.check(False, "%s -- %s" % (stage["label"], msg))
                        _advance(g)
    return inp


def _shot(g, name):
    try:
        import bge
        n = g.auto["shot_n"]
        g.auto["shot_n"] = n + 1
        bge.render.makeScreenshot("%s/%02d_%s" % (SHOTS, n, name))
        g.note("screenshot %02d_%s" % (n, name))
    except Exception as exc:
        g.note("screenshot failed: %r" % (exc,))


def finish(g):
    done = g.auto["i"]
    g.note("autopilot finished %d of %d stages, %d failures" % (done, len(PLAN), len(g.fails)))
    for i, st in enumerate(PLAN):
        if i >= done:
            g.note("  not reached: %s" % st["label"])

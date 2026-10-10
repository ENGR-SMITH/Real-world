### probe_api.py -- run the real scene's main loop and dump the runtime API facts we need.
import bge, os, sys, time

LOG = r"E:/Reality/blender/gamework/probe_api.log"
try:
    os.remove(LOG)
except Exception:
    pass


def L(*a):
    with open(LOG, "a") as f:
        f.write(" ".join(str(x) for x in a) + "\n")
    print(*a)
    sys.stdout.flush()


L("### bge", getattr(bge, "version", None))
sc = bge.logic.getCurrentScene()
L("### scene", sc.name, "objects", len(sc.objects), "cameras", [c.name for c in sc.cameras])
L("### active_camera", sc.active_camera.name if sc.active_camera else None)

for nm in ("Boy1_RIG", "Boy2_RIG", "Camera_Game", "HUD_Prompt", "Shop_Door_L", "Shop_Door_R",
           "SUV_root", "SUV_Door_FR", "TukTuk_root", "Prop_Item_1", "Prop_Item_2",
           "Prop_Item_3", "Prop_Item_4", "Street_Road", "Street_Pavement"):
    o = sc.objects.get(nm)
    if o is None:
        L("### %-14s MISSING" % nm)
        continue
    try:
        wp = tuple(round(v, 3) for v in o.worldPosition)
    except Exception as e:
        wp = "ERR %r" % (e,)
    try:
        dim = tuple(round(v, 3) for v in o.dimensions)
    except Exception as e:
        dim = "ERR %r" % (e,)
    L("### %-14s wp=%s dim=%s" % (nm, wp, dim))

rig = sc.objects["Boy1_RIG"]
L("### rig type", type(rig))
L("### rig anim attrs:", sorted([d for d in dir(rig) if "ction" in d or "nim" in d]))
L("### playAction doc:", repr(getattr(rig.playAction, "__doc__", None)))
L("### getActionFrame?", hasattr(rig, "getActionFrame"), "isPlayingAction?", hasattr(rig, "isPlayingAction"))
L("### channels?", hasattr(rig, "channels"))
try:
    ch = rig.channels
    L("### channels type", type(ch), "len", len(ch))
    for k in ("DEF.hand.L", "DEF.hand.R", "Root", "chest"):
        try:
            L("###   channels[%s] = %r" % (k, ch[k]))
        except Exception as e:
            L("###   channels[%s] ERR %r" % (k, e))
except Exception as e:
    L("### channels ERR %r" % (e,))

hud = sc.objects.get("HUD_Prompt")
if hud is not None:
    L("### HUD type", type(hud), "isFont", isinstance(hud, bge.types.KX_FontObject) if hasattr(bge.types, "KX_FontObject") else "?")
    L("### HUD text attr:", hasattr(hud, "text"), getattr(hud, "text", None))
    try:
        hud.text = "PROBE OK"
        L("### HUD text set ->", hud.text, "colour attr?", hasattr(hud, "color"))
    except Exception as e:
        L("### HUD text ERR %r" % (e,))

p = sc.objects.get("Prop_Item_1")
if p is not None:
    L("### prop keys:", list(p.getPropertyNames().__iter__()) if hasattr(p, "getPropertyNames") else "?")
    for k in ("stand_x", "stand_y", "yaw_deg", "on_shelf"):
        L("###   prop[%s] = %r" % (k, p.get(k, "<none>")))

L("### scene props keys:", list(sc.getPropertyNames()) if hasattr(sc, "getPropertyNames") else "?")
L("### texts in blend:", [t for t in bpy_texts()] if False else "n/a")

# can we play an action?
L("### --- playAction tests")
for kw in ({}, {"blendin": 0.2}, {"blendin": 0.2, "play_mode": bge.logic.KX_ACTION_MODE_LOOP},
           {"layer": 0, "blendin": 0.2, "play_mode": bge.logic.KX_ACTION_MODE_LOOP}):
    try:
        rig.playAction("walk", 1.0, 33.0, **kw)
        L("###   playAction(walk,1,33,%r) OK  -> action=%r frame=%r" % (
            kw, getattr(rig, "getActionName", lambda: "?")() if hasattr(rig, "getActionName") else "?",
            getattr(rig, "getActionFrame", lambda: "?")() if hasattr(rig, "getActionFrame") else "?"))
        break
    except Exception as e:
        L("###   playAction(walk,1,33,%r) ERR %r" % (kw, e))

# step a few frames and see whether the rig animates
try:
    pos0 = tuple(rig.worldPosition)
    f0 = rig.getActionFrame() if hasattr(rig, "getActionFrame") else None
    for i in range(10):
        bge.logic.NextFrame()
    f1 = rig.getActionFrame() if hasattr(rig, "getActionFrame") else None
    L("### after 10 frames action frame %r -> %r  pos %s -> %s" % (f0, f1, pos0, tuple(round(v, 3) for v in rig.worldPosition)))
except Exception as e:
    L("### stepping ERR %r" % (e,))

L("### PROBE OK")

import bge, os, sys, time

LOG = r"E:/Reality/blender/gamework/mainloop.log"

def _log(msg):
    with open(LOG, "a") as f:
        f.write(msg + "\n")

def _names(o):
    return sorted([d for d in dir(o) if not d.startswith("_")])

_log("=== EXEC %s" % time.strftime("%H:%M:%S"))
_log("bge: " + repr(_names(bge)))
_log("bge.logic: " + repr(_names(bge.logic)))
_log("bge.render: " + repr(_names(bge.render)))
_log("bge.events: " + repr(_names(bge.events))[:1500])
sc = bge.logic.getCurrentScene()
_log("KX_Scene: " + repr(_names(sc)))
_log("KX_Scene.loop-ish: " + repr([d for d in _names(sc) if any(k in d.lower() for k in
      ("update", "render", "frame", "step", "advance", "draw", "pre", "post", "add"))]))
_log("bge.logic.loop-ish: " + repr([d for d in _names(bge.logic) if any(k in d.lower() for k in
      ("frame", "step", "update", "render", "draw", "exit", "end", "time", "next", "pause", "restart"))]))
_log("bge.render.loop-ish: " + repr([d for d in _names(bge.render) if any(k in d.lower() for k in
      ("frame", "draw", "update", "show", "set", "get", "make", "swap"))]))
try:
    _log("types: " + repr([d for d in _names(bge.types) if "Engine" in d or "Ketsji" in d]))
except Exception as e:
    _log("types ERR %r" % (e,))
try:
    _log("KX_KetsjiEngine: " + repr(_names(bge.types.KX_KetsjiEngine)))
except Exception as e:
    _log("KX_KetsjiEngine ERR %r" % (e,))
_log("scene objs: " + repr(sorted(sc.objects.keys())))
_log("camera: %r" % (sc.active_camera,))
_log("keyboard: %r" % (bge.logic.keyboard,))
try:
    _log("keyboard.inputs: %r" % (list(bge.logic.keyboard.inputs[:4]),))
except Exception as e:
    _log("keyboard.inputs ERR %r" % (e,))
try:
    _log("mouse: %r" % (bge.logic.mouse,))
except Exception as e:
    _log("mouse ERR %r" % (e,))
_log("DONE")

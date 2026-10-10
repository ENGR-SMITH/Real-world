### test main loop: proves NextFrame-based looping, screenshots and clean exit work.
import bge, os, time

LOG = r"E:/Reality/blender/gamework/loop.log"
SHOTS = r"E:/UPBGE/shots"
os.makedirs(SHOTS, exist_ok=True)

def _log(m):
    with open(LOG, "a") as f:
        f.write(m + "\n")

sc = bge.logic.getCurrentScene()
cube = sc.objects["TestCube"]
_log("=== start scene=%s objs=%d" % (sc.name, len(sc.objects)))

t0 = time.time()
N = 40
for i in range(N):
    # spin + bob the cube so consecutive shots differ
    ang = i * 0.08
    cube.worldOrientation = (ang, ang * 0.5, 0.0)
    cube.worldPosition = (0.0, 0.0, 1.0 + 0.4 * (i % 20) / 20.0)

    if i in (5, 20, 39):
        p = os.path.join(SHOTS, "loop_%02d.png" % i)
        try:
            bge.render.makeScreenshot(p)
            _log("shot %d -> %s exists=%s" % (i, p, os.path.exists(p)))
        except Exception as e:
            _log("shot %d ERR %r" % (i, e))

    bge.logic.NextFrame()

el = time.time() - t0
_log("### ran %d frames in %.2fs (%.1f fps)" % (N, el, N / max(el, 1e-6)))
_log("### cube z=%.3f" % cube.worldPosition.z)
_log("### fps=%.1f realtime=%.2f" % (bge.logic.getAverageFrameRate(), bge.logic.getRealTime()))
_log("LOOP OK")

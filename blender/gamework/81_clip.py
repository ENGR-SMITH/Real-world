import bpy
S="E:/Reality/ECO/Bussiness/Mall/MiniMarket/Shop_with_people.blend"
bpy.ops.wm.open_mainfile(filepath=S)
for c in bpy.data.objects:
    if c.type=='CAMERA':
        d=c.data
        print("CAM %-18s clip_start=%.4f clip_end=%.2f lens=%.2f ortho=%s sens=%.2f shift=(%.3f,%.3f)" % (
            c.name, d.clip_start, d.clip_end, d.lens, d.type, d.sensor_width, d.shift_x, d.shift_y))
        print("     game_culling=%s show_limits=%s" % (getattr(d,"use_game_culling",None), d.show_limits))
sc=bpy.context.scene
print("SCENE camera =", sc.camera.name if sc.camera else None)
print("near/far props:", [ (o.name,o.type) for o in sc.objects if o.type=='CAMERA'])

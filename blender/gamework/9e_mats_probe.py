"""9e_mats_probe.py -- what do the blend's materials and lights actually contain?

    blender.exe -b --factory-startup --python 9e_mats_probe.py

Prints, per material: the Principled inputs the glTF exporter reads (base colour,
metallic, roughness) and whether an image texture is linked to base colour.
Also lists the scene's lights and world, since the export carried no lights at all.
"""
import bpy

BLEND = "E:/Reality/ECO/Bussiness/Mall/MiniMarket/Shop_with_people.blend"


def P(*a):
    print("###", *a)
    try:
        import sys
        sys.stdout.flush()
    except Exception:
        pass


bpy.ops.wm.open_mainfile(filepath=BLEND)
P("opened", BLEND)

# ---- lights -----------------------------------------------------------------
lights = [o for o in bpy.data.objects if o.type == "LIGHT"]
P("lights in scene:", len(lights))
for o in lights[:20]:
    d = o.data
    P("   LIGHT", o.name, d.type, "energy=%.1f" % d.energy,
      "colour=(%.3f,%.3f,%.3f)" % tuple(d.color),
      "rot=(%.2f,%.2f,%.2f)" % tuple(o.rotation_euler),
      "loc=(%.1f,%.1f,%.1f)" % tuple(o.location),
      "shadow=%s" % getattr(d, "use_shadow", "?"))
P("worlds:", len(bpy.data.worlds))
for w in bpy.data.worlds:
    P("   WORLD", w.name, "use_nodes=%s" % w.use_nodes,
      "colour=(%.3f,%.3f,%.3f)" % tuple(w.color), "strength=%s" % getattr(w, "strength", "?"))
    if w.use_nodes:
        for n in w.node_tree.nodes:
            P("      wnode", n.type, getattr(n, "inputs", None) and [i.name for i in n.inputs])

# ---- materials --------------------------------------------------------------
P("materials:", len(bpy.data.materials))
has_principled = 0
has_tex = 0
rows = []
for m in bpy.data.materials:
    if not m.use_nodes:
        rows.append((m.name, "no-nodes", "-", "-", "-"))
        continue
    nodes = list(m.node_tree.nodes)
    prin = [n for n in nodes if n.type == "BSDF_PRINCIPLED"]
    tex = [n for n in nodes if n.type == "TEX_IMAGE" and n.image]
    if prin:
        has_principled += 1
        p = prin[0]
        base = p.inputs.get("Base Color")
        met = p.inputs.get("Metallic")
        rough = p.inputs.get("Roughness")
        linked = bool(base and base.is_linked)
        src = "-"
        if linked:
            frm = base.links[0].from_node
            src = frm.type + (":" + (frm.image.name if getattr(frm, "image", None) else "") if frm.type == "TEX_IMAGE" else "")
        def val(s):
            try:
                return "%.3f" % s.default_value
            except Exception:
                try:
                    return "(%.3f,%.3f,%.3f)" % tuple(s.default_value)
                except Exception:
                    return "?"
        rows.append((m.name, "principled", val(base), val(met), val(rough)))
        if linked:
            has_tex += 1
    else:
        kinds = ",".join(sorted({n.type for n in nodes})) or "empty"
        rows.append((m.name, "NO-PRINCIPLED", kinds, "tex:%d" % len(tex), len(nodes)))

P("materials with Principled BSDF:", has_principled, " of", len(bpy.data.materials))
P("materials with an image linked to Base Color:", has_tex)
P("--- all materials (name, kind, base, metallic, roughness) ---")
for r in sorted(rows):
    P("   ", " | ".join(str(x) for x in r))

# a couple of node dumps so we can see what a B4W material looks like inside
P("--- node dumps for 3 materials ---")
for name in ("B4W_carpaint", "Marken", "chrom.001"):
    m = bpy.data.materials.get(name)
    if not m or not m.use_nodes:
        P("   ", name, "missing/no-nodes")
        continue
    P("   MATERIAL", name, "blend_method=%s" % getattr(m, "blend_method", "?"),
      "diffuse=(%.3f,%.3f,%.3f)" % tuple(m.diffuse_color),
      "metal=%.3f rough=%.3f" % (m.metallic, m.roughness))
    for n in m.node_tree.nodes:
        ins = []
        for i in n.inputs:
            if i.is_linked:
                ins.append("%s<-%s" % (i.name, i.links[0].from_node.type))
            else:
                try:
                    ins.append("%s=%.3f" % (i.name, i.default_value))
                except Exception:
                    try:
                        ins.append("%s=(%.2f,%.2f,%.2f)" % ((i.name,) + tuple(i.default_value)))
                    except Exception:
                        ins.append(i.name)
        P("      node", n.type, n.name, "|", ", ".join(ins[:8]))

P("done")

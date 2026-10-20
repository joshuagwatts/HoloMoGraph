"""HoloMoGraph torture suite - adversarial tests: mode-swap loops, add/remove
churn, parent toggling, big counts, dangling refs, renames, duplicates.
Run: blender -b --python tests/test_torture.py
(Undo/redo is NOT covered: its operators need a window context headless lacks.)
"""
import bpy, sys, time, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import holomograph
holomograph.register()
from holomograph.core.cloner import build_chain, new_cloner_object
from holomograph.core import handlers

def clean():
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)
    for ng in list(bpy.data.node_groups):
        if ng.name.startswith("HMG"):
            bpy.data.node_groups.remove(ng)

def ninst(cube):
    if cube is None or cube.name not in bpy.data.objects:
        return -1
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get(); deps.update()
    return sum(1 for i in deps.object_instances
               if i.is_instance and i.object is not None and i.object.original == cube)

def base_scene():
    clean()
    bpy.ops.mesh.primitive_cube_add(size=1.0); cube = bpy.context.active_object
    cl = new_cloner_object(bpy.context, "C")
    cl.hmg_cloner.instance_object = cube; cl.hmg_cloner.mode = "LINEAR"
    cl.hmg_cloner.count = 5; cl.hmg_cloner.step_position = (2.0, 0, 0)
    build_chain(cl)
    return cube, cl

# T1: mode-swap loop with effectors attached
try:
    cube, cl = base_scene()
    bpy.context.view_layer.objects.active = cl
    bpy.ops.hmg.add_effector(eff_type="RANDOM")
    bpy.ops.hmg.add_effector(eff_type="PLAIN")
    bpy.ops.mesh.primitive_ico_sphere_add(radius=4.0); dist = bpy.context.active_object
    cu = bpy.data.curves.new("P", 'CURVE'); cu.dimensions = '3D'
    spl = cu.splines.new('BEZIER'); spl.bezier_points.add(1)
    spl.bezier_points[0].co = (0,0,0); spl.bezier_points[1].co = (8,0,2)
    for bp in spl.bezier_points: bp.handle_left_type='AUTO'; bp.handle_right_type='AUTO'
    path = bpy.data.objects.new("P", cu); bpy.context.collection.objects.link(path)
    cl.hmg_cloner.dist_object = dist; cl.hmg_cloner.spline_object = path
    modes = ["LINEAR", "GRID", "RADIAL", "HONEYCOMB", "OBJECT", "SPLINE"]
    ok = True
    for r in range(3):
        for m in modes:
            cl.hmg_cloner.mode = m
            n = ninst(cube)
            if n <= 0: ok = False; print(f"  round {r} mode {m}: {n} instances BAD")
    print(f"T1 mode-swap x18 with 2 effectors: {'OK' if ok else 'BROKEN'}")
except Exception as e:
    print(f"T1 EXCEPTION {type(e).__name__}: {str(e)[:100]}")

# T2: add/remove churn
try:
    cube, cl = base_scene()
    bpy.context.view_layer.objects.active = cl
    for t in ["PLAIN", "RANDOM", "STEP", "FORMULA", "TIME"]:
        bpy.ops.hmg.add_effector(eff_type=t)
    effs = [o for o in bpy.data.objects if getattr(o, 'hmg_type', '') == 'EFFECTOR']
    # remove from the middle, then the rest
    for eff in list(effs):
        bpy.context.view_layer.objects.active = eff
        bpy.ops.hmg.remove()
    left = [o for o in bpy.data.objects if getattr(o, 'hmg_type', '') == 'EFFECTOR']
    n = ninst(cube)
    print(f"T2 churn: 5 added, all removed (left={len(left)}), instances={n} {'OK' if len(left)==0 and n==5 else 'BROKEN'}")
except Exception as e:
    print(f"T2 EXCEPTION {type(e).__name__}: {str(e)[:100]}")

# T4: rapid parent/unparent x10 (handler path)
try:
    clean()
    bpy.ops.hmg.add_cloner()
    cl = [o for o in bpy.data.objects if getattr(o, 'hmg_type', '') == 'CLONER'][0]
    bpy.ops.mesh.primitive_cube_add(size=1.0); cube = bpy.context.active_object
    for i in range(10):
        cube.parent = cl if i % 2 == 0 else None
        bpy.context.view_layer.update()
        handlers._rebuild_dirty()
    n = ninst(cube)
    print(f"T4 parent toggling x10: final instances={n} {'OK' if n == 0 else 'BROKEN'}")
except Exception as e:
    print(f"T4 EXCEPTION {type(e).__name__}: {str(e)[:100]}")

# T5: big counts
try:
    cube, cl = base_scene()
    t0 = time.time()
    cl.hmg_cloner.count = 1000
    n = ninst(cube)
    dt = time.time() - t0
    print(f"T5 LINEAR count=1000: instances={n} in {dt:.1f}s {'OK' if n == 1000 else 'BROKEN'}")
except Exception as e:
    print(f"T5 EXCEPTION {type(e).__name__}: {str(e)[:100]}")

# T6: delete the source cube (dangling instance_object)
try:
    cube, cl = base_scene()
    bpy.data.objects.remove(cube, do_unlink=True)
    build_chain(cl)
    bpy.context.view_layer.update()
    print("T6 source deleted + rebuild: no crash OK")
except Exception as e:
    print(f"T6 EXCEPTION {type(e).__name__}: {str(e)[:100]}")

# T7: rename effector -> do its sliders stay live?
try:
    cube, cl = base_scene()
    bpy.context.view_layer.objects.active = cl
    bpy.ops.hmg.add_effector(eff_type="PLAIN")
    eff = [o for o in bpy.data.objects if getattr(o, 'hmg_type', '') == 'EFFECTOR'][-1]
    eff.name = "My Renamed Effector"
    def zmax():
        bpy.context.view_layer.update()
        deps = bpy.context.evaluated_depsgraph_get(); deps.update()
        return max(i.matrix_world.translation.z for i in deps.object_instances
                   if i.is_instance and i.object is not None and i.object.original == cube)
    z0 = zmax()
    eff.hmg_effector.position = (0, 0, 9.0)   # live sync only, no rebuild
    z1 = zmax()
    print(f"T7 rename effector, slider live: z {z0:.1f} -> {z1:.1f} {'OK' if z1 == 9.0 else 'DEAD (sync lost after rename)'}")
except Exception as e:
    print(f"T7 EXCEPTION {type(e).__name__}: {str(e)[:100]}")

# T8: duplicate the cloner (Ctrl+D style via copy)
try:
    cube, cl = base_scene()
    cl2 = cl.copy()
    bpy.context.collection.objects.link(cl2)
    build_chain(cl2)
    n = ninst(cube)
    print(f"T8 duplicated cloner: total instances of cube={n} {'OK' if n == 10 else 'BROKEN'}")
except Exception as e:
    print(f"T8 EXCEPTION {type(e).__name__}: {str(e)[:100]}")
print("TORTURE DONE")

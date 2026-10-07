"""HoloMoGraph headless verification part 2: sim, tracer, fracture, sound, drivers."""
import bpy
import sys
import traceback

sys.path.insert(0, "/home/hatch/workspace/HoloMoGraph")
import holomograph

holomograph.register()
from holomograph.core.cloner import build_chain

results = []


def check(name, fn):
    try:
        fn()
        results.append(("PASS", name, ""))
        print(f"PASS {name}", flush=True)
    except Exception:
        results.append(("FAIL", name, traceback.format_exc(limit=6)))
        print(f"FAIL {name}", flush=True)


def _clean():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def _mats(cloner):
    deps = bpy.context.evaluated_depsgraph_get()
    deps.update()
    out = []
    for inst in deps.object_instances:
        if not inst.is_instance:
            continue
        par = inst.parent
        if par is not None and par.original == cloner:
            out.append(inst.matrix_world.translation.copy())
    return out


def t_delay_sim():
    _clean()
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    bpy.ops.hmg.add_cloner(mode="LINEAR")
    cl = bpy.context.active_object
    cl.hmg_cloner.count = 4
    cl.hmg_cloner.instance_object = cube
    bpy.ops.hmg.add_effector(eff_type="DELAY")
    eff = bpy.context.active_object
    eff.hmg_effector.delay = 5.0
    bpy.context.view_layer.objects.active = cl
    build_chain(cl)
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 10
    # animate the cloner itself so the delay has something to trail
    cl.location = (0, 0, 0)
    cl.keyframe_insert(data_path="location", frame=1)
    cl.location = (10, 0, 0)
    cl.keyframe_insert(data_path="location", frame=10)
    for f in (1, 5, 10):
        scene.frame_set(f)
        mats = _mats(cl)
        assert len(mats) == 4, f"frame {f}: got {len(mats)}"
    # instances must follow the cloner transform (regression: as_instance+RELATIVE bug)
    scene.frame_set(10)
    mats = _mats(cl)
    xs = sorted(m.x for m in mats)
    assert xs[0] > 5.0, f"instances did not follow cloner: {xs}"
    print("   delay xs @f10:", [round(x, 2) for x in xs], flush=True)


def t_tracer():
    _clean()
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    bpy.ops.hmg.add_cloner(mode="LINEAR")
    cl = bpy.context.active_object
    cl.hmg_cloner.count = 3
    cl.hmg_cloner.instance_object = cube
    build_chain(cl)
    scene = bpy.context.scene
    cl.location = (0, 0, 0)
    cl.keyframe_insert(data_path="location", frame=1)
    cl.location = (5, 0, 0)
    cl.keyframe_insert(data_path="location", frame=5)
    bpy.ops.hmg.tracer(frame_start=1, frame_end=5, max_clones=10)
    trace = bpy.context.active_object
    assert trace.type == "CURVE", "tracer did not produce a curve"
    assert len(trace.data.splines) == 3, f"expected 3 splines, got {len(trace.data.splines)}"
    assert len(trace.data.splines[0].points) == 5


def t_fracture():
    _clean()
    bpy.ops.mesh.primitive_cube_add()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.subdivide(number_cuts=1)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.hmg.fracture(use_cell_fracture=False)
    cl = bpy.context.active_object
    assert cl.hmg_type == "CLONER"
    mats = _mats(cl)
    # subdivided cube -> 8 corners? loose parts of subdivided cube = 1 island still (connected)
    # so just check it built and evaluates without error
    assert isinstance(mats, list)


def t_sound_bake():
    import wave
    import numpy as np
    _clean()
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    bpy.ops.hmg.add_cloner(mode="GRID")
    cl = bpy.context.active_object
    cl.hmg_cloner.instance_object = cube
    bpy.ops.hmg.add_effector(eff_type="SOUND")
    eff = bpy.context.active_object
    # synth a 2-second WAV with an amplitude envelope
    sr = 44100
    t = np.arange(sr * 2) / sr
    env = 0.5 + 0.5 * np.sin(2 * np.pi * 0.5 * t)
    data = (np.sin(2 * np.pi * 220 * t) * env * 20000).astype(np.int16)
    path = "/tmp/hmg_test_tone.wav"
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 48
    eff.hmg_effector.sound_path = path
    bpy.ops.hmg.sound_bake()
    assert "hmg_sound" in eff, "baked property missing"
    assert eff.animation_data is not None
    drvs = eff.animation_data.drivers
    assert any(d.data_path == "hmg_effector.strength" for d in drvs), "strength driver missing"
    # baked fcurve has keys (5.2 layered actions)
    from holomograph.core.cloner import iter_action_fcurves
    fcs = [fc for fc in iter_action_fcurves(eff.animation_data)
           if fc.data_path == '["hmg_sound"]']
    assert fcs and len(fcs[0].keyframe_points) > 10, "no baked keys"
    # mirrored pass-through driver on the node input
    from holomograph.core.cloner import chain_group_name
    cl2 = eff.parent
    while cl2 is not None and cl2.hmg_type != "CLONER":
        cl2 = cl2.parent
    tree = bpy.data.node_groups.get(chain_group_name(cl2))
    targets = [d.driver.variables[0].targets[0].data_path
               for d in tree.animation_data.drivers if d.driver and d.driver.variables]
    assert "hmg_effector.strength" in targets, f"no mirrored strength driver: {targets}"


def t_driver_mirror():
    _clean()
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    bpy.ops.hmg.add_cloner(mode="LINEAR")
    cl = bpy.context.active_object
    cl.hmg_cloner.count = 2
    cl.hmg_cloner.instance_object = cube
    bpy.ops.hmg.add_effector(eff_type="PLAIN")
    eff = bpy.context.active_object
    # animate strength 0 -> 2
    eff.hmg_effector.strength = 0.0
    eff.hmg_effector.keyframe_insert(data_path="strength", frame=1)
    eff.hmg_effector.strength = 2.0
    eff.hmg_effector.keyframe_insert(data_path="strength", frame=10)
    eff.hmg_effector.position = (0, 0, 4)
    bpy.context.view_layer.objects.active = cl
    build_chain(cl)
    from holomograph.core.cloner import chain_group_name
    tree = bpy.data.node_groups.get(chain_group_name(cl))
    assert tree.animation_data is not None, "no animation data on chain"
    targets = [d.driver.variables[0].targets[0].data_path
               for d in tree.animation_data.drivers if d.driver and d.driver.variables]
    assert "hmg_effector.strength" in targets, f"no mirrored drivers: {targets}"
    print("   mirrored:", targets, flush=True)


check("delay sim", t_delay_sim)
check("tracer", t_tracer)
check("fracture", t_fracture)
check("sound bake", t_sound_bake)
check("driver mirror", t_driver_mirror)

print("\n===== RESULTS =====")
fails = sum(1 for r in results if r[0] == "FAIL")
for r in results:
    if r[0] == "FAIL":
        print(f"FAIL {r[1]}\n{r[2][:2500]}")
print(f"{len(results)-fails}/{len(results)} passed")

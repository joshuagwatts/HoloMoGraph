"""HoloMoGraph headless verification. Run: blender -b --python hmg_test.py"""
import bpy
import sys
import traceback

sys.path.insert(0, "/home/hatch/workspace/HoloMoGraph")

results = []


def check(name, fn):
    try:
        fn()
        results.append(("PASS", name, ""))
        print(f"PASS {name}", flush=True)
    except Exception:
        results.append(("FAIL", name, traceback.format_exc(limit=5)))
        print(f"FAIL {name}", flush=True)


NODE_IDS = [
    "GeometryNodeGroup", "NodeGroupInput", "NodeGroupOutput",
    "ShaderNodeMath", "ShaderNodeVectorMath", "ShaderNodeCombineXYZ",
    "ShaderNodeSeparateXYZ", "FunctionNodeInputColor",
    "FunctionNodeCompare", "FunctionNodeBooleanMath",
    "GeometryNodeSwitch", "GeometryNodeIndexSwitch",
    "ShaderNodeMix", "ShaderNodeValue", "ShaderNodeMapRange",
    "GeometryNodePoints", "GeometryNodeMeshLine", "GeometryNodeMeshGrid",
    "GeometryNodeMeshToPoints", "GeometryNodeDistributePointsOnFaces",
    "GeometryNodeResampleCurve", "GeometryNodeSampleCurve",
    "GeometryNodeSampleNearest", "GeometryNodeSetPosition",
    "GeometryNodeStoreNamedAttribute", "GeometryNodeInputNamedAttribute",
    "GeometryNodeInputIndex", "GeometryNodeInputPosition",
    "GeometryNodeInputSceneTime", "GeometryNodeObjectInfo",
    "GeometryNodeInstanceOnPoints", "GeometryNodeDeleteGeometry",
    "GeometryNodeCollectionInfo", "GeometryNodeImageTexture",
    "GeometryNodeSimulationInput", "GeometryNodeSimulationOutput",
    "FunctionNodeRandomValue", "FunctionNodeAlignEulerToVector",
    "FunctionNodeEulerToRotation", "FunctionNodeRotationToEuler",
    "FunctionNodeMatrixMultiply", "FunctionNodeInvertMatrix",
    "FunctionNodeTransformPoint", "FunctionNodeTransformDirection",
    "ShaderNodeTexWhiteNoise", "ShaderNodeFloatCurve",
]


def t_node_ids():
    ng = bpy.data.node_groups.new("HMG_IDTEST", "GeometryNodeTree")
    bad = []
    for i in NODE_IDS:
        try:
            ng.nodes.new(i)
        except Exception:
            bad.append(i)
    bpy.data.node_groups.remove(ng)
    assert not bad, "unknown node ids: " + ", ".join(bad)


def t_sim_pair():
    ng = bpy.data.node_groups.new("HMG_SIMTEST", "GeometryNodeTree")
    a = ng.nodes.new("GeometryNodeSimulationInput")
    b = ng.nodes.new("GeometryNodeSimulationOutput")
    a.pair_with_output(b)
    bpy.data.node_groups.remove(ng)


def t_index_switch_items():
    ng = bpy.data.node_groups.new("HMG_SWTEST", "GeometryNodeTree")
    n = ng.nodes.new("GeometryNodeIndexSwitch")
    n.index_switch_items.clear()
    for _ in range(9):
        n.index_switch_items.new()
    assert len(n.inputs) >= 10, f"only {len(n.inputs)} inputs"
    bpy.data.node_groups.remove(ng)


def t_register():
    import holomograph
    holomograph.register()


def _clean():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)



def _collect(cloner, want_parent=True, leaf_of=None):
    """Single-pass instance collection (Blender 5.x invalidates stored instances)."""
    deps = bpy.context.evaluated_depsgraph_get()
    deps.update()
    mats = []
    parents = set()
    for inst in deps.object_instances:
        if not inst.is_instance:
            continue
        par = inst.parent
        if want_parent and not (par is not None and par.original == cloner):
            continue
        if leaf_of is not None and not (inst.object is not None and inst.object.original == leaf_of):
            continue
        mats.append(inst.matrix_world.translation.copy())
        if par is not None:
            parents.add(par.original.name)
    return mats, parents

def t_falloff():
    from holomograph.core.falloff import build_falloff_group
    g = build_falloff_group()
    assert len(g.nodes) > 20


def t_modes():
    from holomograph.core.cloner import build_chain
    for mode in ["LINEAR", "RADIAL", "GRID", "HONEYCOMB", "OBJECT", "SPLINE"]:
        _clean()
        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.active_object
        bpy.ops.hmg.add_cloner(mode=mode)
        cl = bpy.context.active_object
        assert cl.hmg_type == "CLONER", "cloner type not set"
        if mode == "OBJECT":
            cl.hmg_cloner.dist_object = cube
        if mode == "SPLINE":
            bpy.ops.curve.primitive_bezier_curve_add()
            cur = bpy.context.active_object
            bpy.context.view_layer.objects.active = cl
            cl.hmg_cloner.spline_object = cur
        cl.hmg_cloner.instance_object = cube
        build_chain(cl)  # must not raise
        assert cl.modifiers.get("HoloMoGraph") is not None


def t_effectors():
    from holomograph.core.cloner import build_chain
    for et in ["PLAIN", "RANDOM", "STEP", "FORMULA", "SHADER", "SOUND",
               "DELAY", "PUSH_APART", "TARGET", "SPLINE", "TIME"]:
        _clean()
        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.active_object
        bpy.ops.hmg.add_cloner(mode="GRID")
        cl = bpy.context.active_object
        cl.hmg_cloner.instance_object = cube
        bpy.ops.hmg.add_effector(eff_type=et)
        eff = bpy.context.active_object
        if et == "TARGET":
            eff.hmg_effector.target_object = cube
        if et == "SPLINE":
            bpy.ops.curve.primitive_bezier_curve_add()
            cur = bpy.context.active_object
            bpy.context.view_layer.objects.active = eff
            eff.hmg_effector.spline_object = cur
        bpy.context.view_layer.objects.active = cl
        build_chain(cl)  # must not raise


def t_eval_instances():
    _clean()
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    bpy.ops.hmg.add_cloner(mode="GRID")
    cl = bpy.context.active_object
    cl.hmg_cloner.count_x = 3
    cl.hmg_cloner.count_y = 2
    cl.hmg_cloner.count_z = 1
    cl.hmg_cloner.instance_object = cube
    from holomograph.core.cloner import build_chain
    build_chain(cl)
    mats, parents = _collect(cl)
    assert len(mats) == 6, f"expected 6 instances, got {len(mats)}"
    assert cl.name in parents, f"tracer parent match failed: {parents}"


def t_eval_effector_plain():
    _clean()
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    bpy.ops.hmg.add_cloner(mode="LINEAR")
    cl = bpy.context.active_object
    cl.hmg_cloner.count = 4
    cl.hmg_cloner.instance_object = cube
    bpy.ops.hmg.add_effector(eff_type="PLAIN")
    eff = bpy.context.active_object
    eff.hmg_effector.position = (0, 0, 5)
    bpy.context.view_layer.objects.active = cl
    from holomograph.core.cloner import build_chain
    build_chain(cl)
    mats, _ = _collect(cl)
    assert len(mats) == 4, f"expected 4, got {len(mats)}"
    pairs = sorted((round(m.x, 3), round(m.z, 3)) for m in mats)
    # linear x = 0,2,4,6; default INFINITE falloff -> uniform z+5
    assert pairs == [(0.0, 5.0), (2.0, 5.0), (4.0, 5.0), (6.0, 5.0)], \
        f"plain+falloff wrong: {pairs}"


def t_eval_random_falloff():
    _clean()
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    bpy.ops.hmg.add_cloner(mode="LINEAR")
    cl = bpy.context.active_object
    cl.hmg_cloner.count = 8
    cl.hmg_cloner.instance_object = cube
    bpy.ops.hmg.add_effector(eff_type="RANDOM")
    eff = bpy.context.active_object
    eff.hmg_effector.position_amt = (2, 0, 0)
    fo = eff.hmg_effector.falloff
    fo.hmg_falloff.shape = "SPHERE"
    fo.location = (4, 0, 0)  # center of the line
    bpy.context.view_layer.objects.active = cl
    from holomograph.core.cloner import build_chain
    build_chain(cl)
    mats, _ = _collect(cl)
    assert len(mats) == 8, f"expected 8, got {len(mats)}"


def t_nested():
    _clean()
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    bpy.ops.hmg.add_cloner(mode="GRID")
    child = bpy.context.active_object
    child.name = "ChildCloner"
    child.hmg_cloner.count_x = 2
    child.hmg_cloner.count_y = 2
    child.hmg_cloner.instance_object = cube
    bpy.ops.hmg.add_cloner(mode="LINEAR")
    parent = bpy.context.active_object
    parent.name = "ParentCloner"
    parent.hmg_cloner.count = 3
    parent.hmg_cloner.instance_object = child  # nested!
    from holomograph.core.cloner import build_chain
    build_chain(parent)
    mats, _ = _collect(parent, leaf_of=cube)
    assert len(mats) == 12, f"expected 12 nested leaf instances, got {len(mats)}"


def t_motext():
    _clean()
    bpy.ops.hmg.motext(text="AB", size=1.0, extrude=0.0, bevel_depth=0.0)
    cl = bpy.context.active_object
    assert cl.hmg_type == "CLONER"
    mats, _ = _collect(cl)
    assert len(mats) == 2, f"expected 2 char instances, got {len(mats)}"


check("node ids", t_node_ids)
check("sim pair api", t_sim_pair)
check("index switch items", t_index_switch_items)
check("register", t_register)
check("falloff group", t_falloff)
check("cloner modes", t_modes)
check("effector builds", t_effectors)
check("eval instances", t_eval_instances)
check("eval plain effector", t_eval_effector_plain)
check("eval random+falloff", t_eval_random_falloff)
check("nested cloners", t_nested)
check("motext", t_motext)

print("\n===== RESULTS =====")
fails = 0
for r in results:
    if r[0] == "PASS":
        print(f"PASS  {r[1]}")
    else:
        fails += 1
        print(f"FAIL  {r[1]}\n{r[2][:2000]}")
print(f"\n{len(results)-fails}/{len(results)} passed")

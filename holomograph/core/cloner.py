"""HoloMoGraph - Cloner core.

Mode point-generators + the chain assembler.

A "Cloner" object carries a Geometry Nodes modifier whose tree is rebuilt
from its properties:

    [mode points] -> [effector 1] -> ... -> [effector N]
        -> apply hmg_poff -> cull by hmg_alpha -> instance -> output

Nested cloners (cloner-in-cloner, the C4D way): if a cloner's Instance
Object is itself a cloner, the child pipeline is inlined recursively and
the parent's effectors stack on top. Depth is capped to keep trees sane.
"""
from __future__ import annotations
import re
import bpy
from .nodes import (
    ng_new, ng_get, add_node, link, group_node, iface_in, iface_out, io_nodes,
    math, vmath, combine_xyz, separate_xyz, compare, switch, value,
    store_attr, named_attr, object_info, euler_to_rotation, index_switch,
)
from . import effectors as FX

# Cycle protection for nested cloners lives in _check_cycle (build-time walk).

A_POFF = FX.A_POFF
A_ROFF = FX.A_ROFF
A_SMUL = FX.A_SMUL
A_COL = FX.A_COL
A_TIME = FX.A_TIME
A_ALPHA = FX.A_ALPHA


def sanitize(name: str) -> str:
    return re.sub(r"\W", "_", name)


def chain_group_name(obj) -> str:
    return f"HMG_Chain_{sanitize(obj.name)}"


# ---------------------------------------------------------------------------
# attribute init shared by every mode
# ---------------------------------------------------------------------------

def _init_attrs(tree, geo, x, roff=None, smul=None):
    sg = geo
    sg = store_attr(tree, sg, A_POFF,
                    combine_xyz(tree, value(tree, 0.0).outputs[0],
                                value(tree, 0.0).outputs[0],
                                value(tree, 0.0).outputs[0], (x, 0)).outputs["Vector"],
                    "FLOAT_VECTOR", location=(x + 150, 0)).outputs["Geometry"]
    sg = store_attr(tree, sg, A_ROFF,
                    roff if roff is not None else
                    combine_xyz(tree, value(tree, 0.0).outputs[0],
                                value(tree, 0.0).outputs[0],
                                value(tree, 0.0).outputs[0]).outputs["Vector"],
                    "FLOAT_VECTOR", location=(x + 150, -120)).outputs["Geometry"]
    sg = store_attr(tree, sg, A_SMUL,
                    smul if smul is not None else
                    combine_xyz(tree, value(tree, 1.0).outputs[0],
                                value(tree, 1.0).outputs[0],
                                value(tree, 1.0).outputs[0]).outputs["Vector"],
                    "FLOAT_VECTOR", location=(x + 150, -240)).outputs["Geometry"]
    col = add_node(tree, "FunctionNodeInputColor", (x, -360))
    sg = store_attr(tree, sg, A_COL, col.outputs["Color"], "FLOAT_COLOR",
                    location=(x + 150, -360)).outputs["Geometry"]
    sg = store_attr(tree, sg, A_TIME, value(tree, 0.0, (x, -480)).outputs[0],
                    "FLOAT", location=(x + 150, -480)).outputs["Geometry"]
    sg = store_attr(tree, sg, A_ALPHA, value(tree, 1.0, (x, -600)).outputs[0],
                    "FLOAT", location=(x + 150, -600)).outputs["Geometry"]
    return sg


def _step_transforms(tree, gin, x):
    """Per-step euler rotation * index and scale-step ^ index (C4D-style).

    C4D's scale step is exponential: clone i has scale = step ^ i.
    Negative steps alternate sign (mirror): (-2)^0=1, (-2)^1=-2, (-2)^2=4.
    Zero step: 0^0=1, 0^n=0 for n>0 (first clone normal, rest collapsed).
    """
    idx = add_node(tree, "GeometryNodeInputIndex", (x, -750))
    idxf = math(tree, "ADD", idx.outputs["Index"], value(tree, 0.0).outputs[0],
                location=(x + 150, -750))
    roff = vmath(tree, "SCALE", gin.outputs["RStep"], None, None, idxf.outputs[0],
                 location=(x + 300, -750)).outputs["Vector"]
    s = separate_xyz(tree, gin.outputs["SStep"], (x + 150, -900))

    def _pow_axis(axis_out, loc):
        # magnitude = |base| ^ index
        mag = math(tree, "POWER",
                   math(tree, "ABSOLUTE", axis_out,
                        location=(loc[0], loc[1] - 50)).outputs[0],
                   idxf.outputs[0], location=loc).outputs[0]
        # sign: 1 if base >= 0; else (-1)^index (alternates for mirrors)
        is_neg = compare(tree, axis_out,
                         value(tree, 0.0).outputs[0],
                         operation="LESS_THAN",
                         location=(loc[0], loc[1] - 150)).outputs[0]
        is_odd = compare(tree,
                         math(tree, "MODULO", idxf.outputs[0],
                              value(tree, 2.0).outputs[0],
                              location=(loc[0], loc[1] - 250)).outputs[0],
                         value(tree, 0.5).outputs[0],
                         operation="GREATER_THAN",
                         location=(loc[0], loc[1] - 350)).outputs[0]
        neg_sign = switch(tree, is_odd,
                          value(tree, 1.0).outputs[0],
                          value(tree, -1.0).outputs[0],
                          location=(loc[0], loc[1] - 450)).outputs[0]
        sign = switch(tree, is_neg,
                      value(tree, 1.0).outputs[0],
                      neg_sign,
                      location=(loc[0], loc[1] - 550)).outputs[0]
        return math(tree, "MULTIPLY", mag, sign,
                    location=(loc[0], loc[1] - 650)).outputs[0]

    pw = combine_xyz(tree,
                     _pow_axis(s.outputs["X"], (x + 300, -900)),
                     _pow_axis(s.outputs["Y"], (x + 450, -900)),
                     _pow_axis(s.outputs["Z"], (x + 600, -900)),
                     location=(x + 750, -900)).outputs["Vector"]
    return roff, pw


def _mode_iface(tree):
    iface_in(tree, "Count", "INT", default=10, min_value=1)
    iface_in(tree, "PStep", "VECTOR", default=(0, 0, 0))
    iface_in(tree, "RStep", "VECTOR", default=(0, 0, 0))
    iface_in(tree, "SStep", "VECTOR", default=(1, 1, 1))
    iface_out(tree, "Geometry", "GEOMETRY")
    iface_out(tree, "Count", "INT")


# ---------------------------------------------------------------------------
# mode groups
# ---------------------------------------------------------------------------

def build_mode_linear():
    tree = ng_new("HMG_Mode_Linear")
    _mode_iface(tree)
    gin, gou = io_nodes(tree)
    pts = add_node(tree, "GeometryNodePoints", (-200, 0))
    link(tree, gin.outputs["Count"], pts.inputs["Count"])
    idx = add_node(tree, "GeometryNodeInputIndex", (-200, -200))
    idxf = math(tree, "ADD", idx.outputs["Index"], value(tree, 0.0).outputs[0],
                location=(0, -200))
    # Use PStep (per-step position) for the linear offset — C4D-style.
    off = vmath(tree, "SCALE", gin.outputs["PStep"], None, None, idxf.outputs[0],
                location=(200, 0))
    sp = add_node(tree, "GeometryNodeSetPosition", (400, 0))
    link(tree, pts.outputs["Points"], sp.inputs["Geometry"])
    link(tree, off.outputs["Vector"], sp.inputs["Offset"])
    roff, smul = _step_transforms(tree, gin, 400)
    geo = _init_attrs(tree, sp.outputs["Geometry"], 600, roff, smul)
    link(tree, geo, gou.inputs["Geometry"])
    link(tree, gin.outputs["Count"], gou.inputs["Count"])
    return tree


def build_mode_radial():
    tree = ng_new("HMG_Mode_Radial")
    _mode_iface(tree)
    iface_in(tree, "Radius", "FLOAT", default=5.0, min_value=0.01)
    iface_in(tree, "Arc", "FLOAT", default=360.0, min_value=0.0, max_value=360.0)
    iface_in(tree, "Plane", "INT", default=1, min_value=0, max_value=2,
             description="0 XY 1 XZ 2 YZ")
    gin, gou = io_nodes(tree)
    pts = add_node(tree, "GeometryNodePoints", (-200, 0))
    link(tree, gin.outputs["Count"], pts.inputs["Count"])
    idx = add_node(tree, "GeometryNodeInputIndex", (-200, -200))
    closed = compare(tree, gin.outputs["Arc"], value(tree, 359.9).outputs[0],
                     operation="GREATER_THAN", location=(0, -300))
    denom = switch(tree, closed.outputs[0],
                   math(tree, "SUBTRACT", gin.outputs["Count"],
                        value(tree, 1.0).outputs[0]).outputs[0],
                   gin.outputs["Count"], input_type="INT", location=(150, -300)).outputs[0]
    denomf = math(tree, "MAXIMUM",
                  math(tree, "ADD", denom, value(tree, 0.0).outputs[0]).outputs[0],
                  value(tree, 1.0).outputs[0], location=(300, -300))
    ang = math(tree, "MULTIPLY",
               math(tree, "DIVIDE",
                    math(tree, "ADD", idx.outputs["Index"],
                         value(tree, 0.0).outputs[0]).outputs[0],
                    denomf.outputs[0]).outputs[0],
               math(tree, "MULTIPLY",
                    math(tree, "RADIANS", gin.outputs["Arc"]).outputs[0],
                    value(tree, 1.0).outputs[0]).outputs[0], location=(450, -200))
    cx = math(tree, "MULTIPLY", math(tree, "COSINE", ang.outputs[0]).outputs[0],
              gin.outputs["Radius"])
    sx = math(tree, "MULTIPLY", math(tree, "SINE", ang.outputs[0]).outputs[0],
              gin.outputs["Radius"])
    zero = value(tree, 0.0)
    # plane select: 0 XY -> (cx, sx, 0); 1 XZ -> (cx, 0, sx); 2 YZ -> (0, cx, sx)
    from .nodes import index_switch
    px = index_switch(tree, gin.outputs["Plane"],
                      [cx.outputs[0], cx.outputs[0], zero.outputs[0]]).outputs[0]
    py = index_switch(tree, gin.outputs["Plane"],
                      [sx.outputs[0], zero.outputs[0], cx.outputs[0]]).outputs[0]
    pz = index_switch(tree, gin.outputs["Plane"],
                      [zero.outputs[0], sx.outputs[0], sx.outputs[0]]).outputs[0]
    sp = add_node(tree, "GeometryNodeSetPosition", (900, 0))
    link(tree, pts.outputs["Points"], sp.inputs["Geometry"])
    link(tree, combine_xyz(tree, px, py, pz, (750, 0)).outputs["Vector"],
         sp.inputs["Position"])
    roff, smul = _step_transforms(tree, gin, 900)
    geo = _init_attrs(tree, sp.outputs["Geometry"], 1100, roff, smul)
    link(tree, geo, gou.inputs["Geometry"])
    link(tree, gin.outputs["Count"], gou.inputs["Count"])
    return tree


def _grid_index(tree, gin, nx, ny, x):
    idx = add_node(tree, "GeometryNodeInputIndex", (x, -200))
    ix = math(tree, "MODULO", idx.outputs["Index"], nx, location=(x + 150, -200))
    iy = math(tree, "MODULO",
              math(tree, "FLOOR", math(tree, "DIVIDE", idx.outputs["Index"], nx,
                                       location=(x + 150, -320)).outputs[0],
                   location=(x + 300, -320)).outputs[0], ny, location=(x + 450, -260))
    iz = math(tree, "FLOOR",
              math(tree, "DIVIDE", idx.outputs["Index"],
                   math(tree, "MULTIPLY", nx, ny, location=(x + 150, -440)).outputs[0],
                   location=(x + 300, -440)).outputs[0], location=(x + 450, -440))
    return ix.outputs[0], iy.outputs[0], iz.outputs[0]


def build_mode_grid():
    tree = ng_new("HMG_Mode_Grid")
    _mode_iface(tree)
    iface_in(tree, "Count X", "INT", default=5, min_value=1)
    iface_in(tree, "Count Y", "INT", default=5, min_value=1)
    iface_in(tree, "Count Z", "INT", default=1, min_value=1)
    iface_in(tree, "Spacing", "VECTOR", default=(2.0, 2.0, 2.0))
    gin, gou = io_nodes(tree)
    nx, ny, nz = gin.outputs["Count X"], gin.outputs["Count Y"], gin.outputs["Count Z"]
    total = math(tree, "MULTIPLY", math(tree, "MULTIPLY", nx, ny).outputs[0], nz)
    pts = add_node(tree, "GeometryNodePoints", (150, 0))
    link(tree, total.outputs[0], pts.inputs["Count"])
    ix, iy, iz = _grid_index(tree, gin, nx, ny, 150)
    spc = separate_xyz(tree, gin.outputs["Spacing"], (450, -600))
    ox = math(tree, "MULTIPLY",
              math(tree, "SUBTRACT", math(tree, "ADD", ix, value(tree, 0.0).outputs[0]).outputs[0],
                   math(tree, "DIVIDE", math(tree, "SUBTRACT", nx, value(tree, 1.0).outputs[0]).outputs[0],
                        value(tree, 2.0).outputs[0]).outputs[0]).outputs[0],
              spc.outputs["X"])
    oy = math(tree, "MULTIPLY",
              math(tree, "SUBTRACT", math(tree, "ADD", iy, value(tree, 0.0).outputs[0]).outputs[0],
                   math(tree, "DIVIDE", math(tree, "SUBTRACT", ny, value(tree, 1.0).outputs[0]).outputs[0],
                        value(tree, 2.0).outputs[0]).outputs[0]).outputs[0],
              spc.outputs["Y"])
    oz = math(tree, "MULTIPLY",
              math(tree, "SUBTRACT", math(tree, "ADD", iz, value(tree, 0.0).outputs[0]).outputs[0],
                   math(tree, "DIVIDE", math(tree, "SUBTRACT", nz, value(tree, 1.0).outputs[0]).outputs[0],
                        value(tree, 2.0).outputs[0]).outputs[0]).outputs[0],
              spc.outputs["Z"])
    sp = add_node(tree, "GeometryNodeSetPosition", (900, 0))
    link(tree, pts.outputs["Points"], sp.inputs["Geometry"])
    link(tree, combine_xyz(tree, ox.outputs[0], oy.outputs[0], oz.outputs[0],
                           (750, 0)).outputs["Vector"], sp.inputs["Position"])
    roff, smul = _step_transforms(tree, gin, 900)
    geo = _init_attrs(tree, sp.outputs["Geometry"], 1100, roff, smul)
    link(tree, geo, gou.inputs["Geometry"])
    link(tree, total.outputs[0], gou.inputs["Count"])
    return tree


def build_mode_honeycomb():
    tree = ng_new("HMG_Mode_Honeycomb")
    _mode_iface(tree)
    iface_in(tree, "Columns", "INT", default=6, min_value=1)
    iface_in(tree, "Rows", "INT", default=6, min_value=1)
    iface_in(tree, "Spacing", "FLOAT", default=2.0, min_value=0.01)
    gin, gou = io_nodes(tree)
    nx, ny = gin.outputs["Columns"], gin.outputs["Rows"]
    total = math(tree, "MULTIPLY", nx, ny, location=(0, -100))
    pts = add_node(tree, "GeometryNodePoints", (150, 0))
    link(tree, total.outputs[0], pts.inputs["Count"])
    ix, iy, _ = _grid_index(tree, gin, nx, ny, 150)
    odd = math(tree, "MODULO", math(tree, "ADD", iy, value(tree, 0.0).outputs[0]).outputs[0],
               value(tree, 2.0).outputs[0], location=(600, -300))
    fx = math(tree, "ADD", math(tree, "ADD", ix, value(tree, 0.0).outputs[0]).outputs[0],
              math(tree, "MULTIPLY", odd.outputs[0], value(tree, 0.5).outputs[0],
                   location=(600, -420)).outputs[0], location=(750, -350))
    fy = math(tree, "MULTIPLY", math(tree, "ADD", iy, value(tree, 0.0).outputs[0]).outputs[0],
              value(tree, 0.8660254).outputs[0], location=(750, -500))
    s = gin.outputs["Spacing"]
    ox = math(tree, "MULTIPLY",
              math(tree, "SUBTRACT", fx.outputs[0],
                   math(tree, "DIVIDE", math(tree, "SUBTRACT", nx,
                                             value(tree, 1.0).outputs[0]).outputs[0],
                        value(tree, 2.0).outputs[0]).outputs[0]).outputs[0], s,
              location=(900, -350))
    oy = math(tree, "MULTIPLY",
              math(tree, "SUBTRACT", fy.outputs[0],
                   math(tree, "MULTIPLY", value(tree, 0.8660254).outputs[0],
                        math(tree, "DIVIDE", math(tree, "SUBTRACT", ny,
                                                  value(tree, 1.0).outputs[0]).outputs[0],
                             value(tree, 2.0).outputs[0]).outputs[0],
                        location=(900, -620)).outputs[0]).outputs[0], s,
              location=(1050, -500))
    sp = add_node(tree, "GeometryNodeSetPosition", (1200, 0))
    link(tree, pts.outputs["Points"], sp.inputs["Geometry"])
    link(tree, combine_xyz(tree, ox.outputs[0], oy.outputs[0],
                           value(tree, 0.0).outputs[0], (1050, -350)).outputs["Vector"],
         sp.inputs["Position"])
    roff, smul = _step_transforms(tree, gin, 1200)
    geo = _init_attrs(tree, sp.outputs["Geometry"], 1400, roff, smul)
    link(tree, geo, gou.inputs["Geometry"])
    link(tree, total.outputs[0], gou.inputs["Count"])
    return tree


def build_mode_object():
    tree = ng_new("HMG_Mode_Object")
    _mode_iface(tree)
    iface_in(tree, "Target", "OBJECT")
    iface_in(tree, "Dist Mode", "INT", default=0, min_value=0, max_value=3,
             description="0 Vertex 1 Edge 2 Face 3 Surface")
    iface_in(tree, "Density", "FLOAT", default=10.0, min_value=0.01)
    iface_in(tree, "Seed", "INT", default=0)
    gin, gou = io_nodes(tree)
    tinfo = object_info(tree, None, (-100, 200))
    link(tree, gin.outputs["Target"], tinfo.inputs["Object"])
    mesh = tinfo.outputs["Geometry"]
    # vertex / edge / face -> Mesh to Points; surface -> distribute
    from .nodes import index_switch
    mp = add_node(tree, "GeometryNodeMeshToPoints", (150, 250))
    link(tree, mesh, mp.inputs["Mesh"])
    # domain cycles with dist mode for 0..2; surface handled by switch below
    dp = add_node(tree, "GeometryNodeDistributePointsOnFaces", (150, 50))
    link(tree, mesh, dp.inputs["Mesh"])
    link(tree, gin.outputs["Density"], dp.inputs["Density"])
    link(tree, gin.outputs["Seed"], dp.inputs["Seed"])
    use_surf = compare(tree, gin.outputs["Dist Mode"], value(tree, 3.0).outputs[0],
                       operation="EQUAL", data_type="INT", location=(150, -150))
    pts_geo = switch(tree, use_surf.outputs[0], mp.outputs["Points"],
                     dp.outputs["Points"], input_type="GEOMETRY",
                     location=(350, 150)).outputs[0]
    # domain for mesh-to-points follows dist mode (vertex/edge/face)
    # (set at build time from props; default vertex)
    geo = _init_attrs(tree, pts_geo, 550)
    link(tree, geo, gou.inputs["Geometry"])
    link(tree, gin.outputs["Count"], gou.inputs["Count"])
    return tree


def build_mode_spline():
    tree = ng_new("HMG_Mode_Spline")
    _mode_iface(tree)
    iface_in(tree, "Spline", "OBJECT")
    iface_in(tree, "Align", "BOOLEAN", default=True)
    gin, gou = io_nodes(tree)
    sinfo = object_info(tree, None, (-100, 200))
    link(tree, gin.outputs["Spline"], sinfo.inputs["Object"])
    res = add_node(tree, "GeometryNodeResampleCurve", (100, 200))
    res.inputs["Mode"].default_value = "Count"
    link(tree, sinfo.outputs["Geometry"], res.inputs["Curve"])
    link(tree, gin.outputs["Count"], res.inputs["Count"])
    pts = add_node(tree, "GeometryNodePoints", (100, -100))
    link(tree, gin.outputs["Count"], pts.inputs["Count"])
    idx = add_node(tree, "GeometryNodeInputIndex", (100, -250))
    denom = math(tree, "MAXIMUM",
                 math(tree, "SUBTRACT", gin.outputs["Count"],
                      value(tree, 1.0).outputs[0]).outputs[0],
                 value(tree, 1.0).outputs[0])
    factor = math(tree, "DIVIDE",
                  math(tree, "ADD", idx.outputs["Index"], value(tree, 0.0).outputs[0]).outputs[0],
                  denom.outputs[0])
    samp = add_node(tree, "GeometryNodeSampleCurve", (450, 0))
    samp.mode = "FACTOR"
    link(tree, res.outputs["Curve"], samp.inputs["Curves"])
    link(tree, factor.outputs[0], samp.inputs["Factor"])
    sp = add_node(tree, "GeometryNodeSetPosition", (650, 0))
    link(tree, pts.outputs["Points"], sp.inputs["Geometry"])
    link(tree, samp.outputs["Position"], sp.inputs["Position"])
    roff, smul = _step_transforms(tree, gin, 650)
    # optional tangent align overrides per-step rotation
    zero_e = euler_to_rotation(tree,
                               combine_xyz(tree, value(tree, 0.0).outputs[0],
                                           value(tree, 0.0).outputs[0],
                                           value(tree, 0.0).outputs[0]).outputs["Vector"])
    from .nodes import align_to_vector as _a2v, rotation_to_euler as _r2e
    aimed = _a2v(tree, zero_e.outputs["Rotation"], samp.outputs["Tangent"], axis="Z")
    aimed_e = _r2e(tree, aimed.outputs["Rotation"])
    do_align = switch(tree, gin.outputs["Align"], roff, aimed_e.outputs["Euler"],
                      input_type="VECTOR").outputs[0]
    geo = _init_attrs(tree, sp.outputs["Geometry"], 900, do_align, smul)
    link(tree, geo, gou.inputs["Geometry"])
    link(tree, gin.outputs["Count"], gou.inputs["Count"])
    return tree


MODE_BUILDERS = {
    "LINEAR": ("HMG_Mode_Linear", build_mode_linear),
    "RADIAL": ("HMG_Mode_Radial", build_mode_radial),
    "GRID": ("HMG_Mode_Grid", build_mode_grid),
    "HONEYCOMB": ("HMG_Mode_Honeycomb", build_mode_honeycomb),
    "OBJECT": ("HMG_Mode_Object", build_mode_object),
    "SPLINE": ("HMG_Mode_Spline", build_mode_spline),
}


def ensure_mode_groups():
    for _name, (_gname, builder) in MODE_BUILDERS.items():
        if ng_get(_gname) is None:
            builder()


# ---------------------------------------------------------------------------
# chain assembly
# ---------------------------------------------------------------------------

def _fx_params(eff) -> dict:
    """Effector prop values -> builder param dict."""
    p = eff.hmg_effector
    t = p.eff_type
    d: dict = {}
    if t in ("PLAIN", "SOUND"):
        d.update(position=tuple(p.position), rotation=tuple(p.rotation),
                 scale=tuple(p.scale), color=tuple(p.color),
                 visibility=p.visibility, time_offset=p.time_offset)
    elif t == "RANDOM":
        d.update(seed=p.seed, position_amt=tuple(p.position_amt),
                 rotation_amt=tuple(p.rotation_amt), scale_amt=tuple(p.scale_amt),
                 color_a=tuple(p.color_a), color_b=tuple(p.color_b),
                 use_color=p.use_color)
    elif t == "STEP":
        d.update(steps=p.steps, position=tuple(p.position),
                 rotation=tuple(p.rotation), scale=tuple(p.scale))
    elif t == "FORMULA":
        d.update(formula_mode=["SINE", "COSINE", "LINEAR", "NOISE"].index(p.formula_mode),
                 amplitude=p.amplitude, frequency=p.frequency, phase=p.phase,
                 speed=p.speed,
                 target=["POSITION", "ROTATION", "SCALE", "COLOR"].index(p.target),
                 axis=tuple(p.axis))
    elif t == "SHADER":
        d.update(image_name=p.image.name if p.image else "",
                 uv_scale=tuple(p.uv_scale), uv_offset=tuple(p.uv_offset),
                 position_amt=p.shader_pos_amt, scale_amt=p.shader_scl_amt,
                 use_color=p.shader_use_color)
    elif t == "DELAY":
        d.update(delay=p.delay, stiffness=p.stiffness, damping=p.damping,
                 delay_mode=["SMOOTH", "SPRING"].index(p.delay_mode))
    elif t == "PUSH_APART":
        d.update(radius=p.pa_radius)
    elif t == "TIME":
        d.update(offset=p.time_offset, stagger=p.time_stagger)
    elif t == "SPLINE":
        d.update(amount=p.spline_amount, align=p.spline_align)
    # Built-in proximity falloff (C4D-style)
    d.update(use_builtin_falloff=p.use_builtin_falloff,
             prox_shape=["INFINITE", "LINEAR", "BOX", "SPHERE", "CAPSULE",
                         "CYLINDER", "TUBE", "CONE", "TORUS"].index(p.prox_shape),
             prox_size=tuple(p.prox_size), prox_inner=p.prox_inner,
             prox_curve=p.prox_curve, prox_invert=p.prox_invert)
    # Built-in time animation
    d.update(use_time_anim=p.use_time_anim,
             time_speed=p.time_speed, time_phase=p.time_phase)
    return d


def _falloff_of(eff):
    p = eff.hmg_effector
    fo = p.falloff
    if fo is None:
        for ch in eff.children:
            if ch.hmg_type == "FALLOFF":
                fo = ch
                break
    return fo


def _effectors_of(cloner_obj):
    effs = [c for c in cloner_obj.children if c.hmg_type == "EFFECTOR"]
    effs.sort(key=lambda o: (o.hmg_effector.order, o.name))
    return effs


def iter_action_fcurves(anim_data):
    """Version-proof fcurve iteration (Blender 5.x layered actions)."""
    if anim_data is None or anim_data.action is None:
        return []
    act = anim_data.action
    if hasattr(act, "fcurves"):
        try:
            return list(act.fcurves)
        except Exception:
            pass
    out = []
    try:
        layers = act.layers
    except Exception:
        return out
    for lay in layers:
        for st in lay.strips:
            try:
                cb = st.channelbag(anim_data.action_slot)
            except Exception:
                continue
            try:
                out.extend(cb.fcurves)
            except Exception:
                pass
    return out


def _mirror_drivers(chain_tree, items):
    """Mirror animated object props onto group-node inputs.

    For every prop that carries animation (f-curve or driver), create a
    pass-through driver on the node input whose variable reads the prop.
    The prop's own animation then drives the node graph live, with no
    rebuilds needed while scrubbing the timeline.
    items: (src_obj, src_rna_path, group_node, input_name)
    """
    if chain_tree.animation_data is None:
        chain_tree.animation_data_create()
    for src_obj, src_path, gnode, iname in items:
        ad = getattr(src_obj, "animation_data", None)
        if not ad:
            continue
        animated = False
        if ad.drivers:
            animated = any(d.data_path == src_path for d in ad.drivers)
        if not animated:
            animated = any(fc.data_path == src_path
                           for fc in iter_action_fcurves(ad))
        if not animated:
            continue
        try:
            inp = gnode.inputs[iname]
        except KeyError:
            continue
        idx = list(gnode.inputs).index(inp)
        dv = inp.default_value
        is_array = hasattr(dv, "__len__") and not isinstance(dv, (str, float, int, bool))
        ncomp = len(dv) if is_array else 1
        for ci in range(ncomp):
            tpath = f'nodes["{gnode.name}"].inputs[{idx}].default_value'
            for dd in list(chain_tree.animation_data.drivers):
                if dd.data_path == tpath and dd.array_index == ci:
                    chain_tree.animation_data.drivers.remove(dd)
            try:
                if is_array:
                    nd = inp.driver_add("default_value", ci).driver
                else:
                    nd = inp.driver_add("default_value").driver
            except Exception:
                continue
            try:
                nd.type = "AVERAGE"
                var = nd.variables.new()
                var.name = "hmg"
                var.type = "SINGLE_PROP"
                var.targets[0].id = src_obj
                var.targets[0].data_path = f"{src_path}[{ci}]" if is_array else src_path
            except Exception:
                pass


def _nested_child(cloner_obj):
    """The cloner nested under this one: explicit instance_object wins,
    otherwise the first parented child cloner (C4D-style hierarchy)."""
    inst = cloner_obj.hmg_cloner.instance_object
    if inst is not None and getattr(inst, "hmg_type", "") == "CLONER":
        return inst
    for child in cloner_obj.children:
        if getattr(child, "hmg_type", "") == "CLONER":
            return child
    return None


def _hierarchy_instance_source(cloner_obj):
    """C4D-style: a regular object parented under the cloner becomes the
    object being cloned. Explicit instance_object wins; child cloners are
    handled by _nested_child; effectors/falloffs are skipped."""
    inst = cloner_obj.hmg_cloner.instance_object
    if inst is not None:
        return inst
    nested = _nested_child(cloner_obj)
    if nested is not None:
        return nested
    for child in cloner_obj.children:
        t = getattr(child, "hmg_type", "")
        if t not in ("CLONER", "EFFECTOR", "FALLOFF"):
            return child
    return None


def _check_cycle(cloner_obj):
    """C4D forbids cloner cycles (A instances B instances A); catch at build."""
    seen = set()
    cur = cloner_obj
    while cur is not None:
        if cur in seen:
            raise RuntimeError("HoloMoGraph: cloner nesting cycle detected")
        seen.add(cur)
        cur = _nested_child(cur) if cur.hmg_type == "CLONER" else None


def _define_master_inputs(tree, cp):
    """Define all cloner params as master group inputs (modifier tab, live)."""
    from .nodes import iface_in as _ii
    _ii(tree, "Mode", "INT", default={"LINEAR": 0, "RADIAL": 1, "GRID": 2,
                                      "HONEYCOMB": 3, "OBJECT": 4,
                                      "SPLINE": 5}[cp.mode],
        min_value=0, max_value=5)
    _ii(tree, "Count", "INT", default=cp.count, min_value=1)
    for name, vec in (("PStep", cp.step_position), ("RStep", cp.step_rotation),
                      ("SStep", cp.step_scale), ("Spacing", cp.spacing)):
        _ii(tree, name, "VECTOR", default=tuple(vec))
    _ii(tree, "Radius", "FLOAT", default=cp.radius, min_value=0.01)
    _ii(tree, "Arc", "FLOAT", default=cp.arc)
    _ii(tree, "Plane", "INT", default={"XY": 0, "XZ": 1, "YZ": 2}[cp.plane],
        min_value=0, max_value=2)
    _ii(tree, "Count X", "INT", default=cp.count_x, min_value=1)
    _ii(tree, "Count Y", "INT", default=cp.count_y, min_value=1)
    _ii(tree, "Count Z", "INT", default=cp.count_z, min_value=1)
    _ii(tree, "Columns", "INT", default=cp.count_x, min_value=1)
    _ii(tree, "Rows", "INT", default=cp.count_y, min_value=1)
    _ii(tree, "Target", "OBJECT", default=cp.dist_object)
    _ii(tree, "Dist Mode", "INT", default={"VERTEX": 0, "EDGE": 1, "FACE": 2,
                                           "SURFACE": 3}[cp.dist_mode],
        min_value=0, max_value=3)
    _ii(tree, "Density", "FLOAT", default=cp.density, min_value=0.01)
    _ii(tree, "Seed", "INT", default=cp.seed)
    _ii(tree, "Spline", "OBJECT", default=cp.spline_object)
    _ii(tree, "Align", "BOOLEAN", default=cp.align_to_spline)


def _wire_mode_inputs(tree, mg, master_gin):
    """Wire master group inputs to a mode group node's matching inputs."""
    for inp in mg.inputs:
        try:
            src = master_gin.outputs[inp.name]
            tree.links.new(src, inp)
        except Exception:
            pass


def _append_pipeline(tree, cloner_obj, x):
    """Append mode points + effector chain for cloner_obj into tree.

    v2: All 6 mode generators are instantiated and an Index Switch on the
    "Mode" input selects the active one — changing modes is a live input
    change, no rebuild. All mode params are master inputs (visible in the
    modifier tab).

    Returns (geo_socket, count_socket, new_x, drv_items).

    Nested cloners (C4D-style cloner-in-cloner): the parent generates its own
    points and instances the *whole child cloner object* (Object Info as
    instance), so each parent clone carries the child's full arrangement.
    Set child.group_nested=False to flatten (parent effectors affect each
    nested clone individually).

    """
    _check_cycle(cloner_obj)
    cp = cloner_obj.hmg_cloner
    ensure_mode_groups()

    # Define all master inputs (modifier tab, live updates).
    _define_master_inputs(tree, cp)

    # Find the Group Input node for wiring.
    gin = None
    for n in tree.nodes:
        if n.bl_idname == "NodeGroupInput":
            gin = n
            break

    # Instantiate all 6 mode groups; wire master inputs through; select via switch.
    # Changing "Mode" is now a live input change — no rebuild.
    mode_geos = []
    mode_counts = []
    my = x
    for mode_key in ("LINEAR", "RADIAL", "GRID", "HONEYCOMB", "OBJECT", "SPLINE"):
        gname, _ = MODE_BUILDERS[mode_key]
        mg = group_node(tree, ng_get(gname), (x, my), f"Mode: {mode_key}")
        my -= 320
        _wire_mode_inputs(tree, mg, gin)
        mode_geos.append(mg.outputs["Geometry"])
        mode_counts.append(mg.outputs["Count"])
    sw_geo = index_switch(tree, gin.outputs["Mode"], mode_geos,
                          location=(x + 300, 0), data_type="GEOMETRY")
    sw_cnt = index_switch(tree, gin.outputs["Mode"], mode_counts,
                          location=(x + 300, -200))
    geo = sw_geo.outputs[0]
    count = sw_cnt.outputs[0]
    x += 560

    drv_items = []
    for eff in _effectors_of(cloner_obj):
        ep = eff.hmg_effector
        builder = FX.BUILDERS.get(ep.eff_type)
        if builder is None:
            continue
        fo = _falloff_of(eff)
        gname_fx = f"HMG_FX_{ep.eff_type}_{sanitize(eff.name)}"
        fxg = builder(gname_fx, _fx_params(eff), fo)
        fn = group_node(tree, fxg, (x, 0), f"FX: {eff.name}")
        x += 300
        link(tree, geo, fn.inputs["Geometry"])
        fn.inputs["Cloner"].default_value = cloner_obj
        if fo is not None:
            fn.inputs["Falloff"].default_value = fo
        fn.inputs["Strength"].default_value = ep.strength
        link(tree, count, fn.inputs["Count"])
        fn.inputs["Weight Attr"].default_value = f"hmg_w_{sanitize(eff.name)}"
        _set_fx_params(fn, eff, fo)
        drv_items.append((eff, "hmg_effector.strength", fn, "Strength"))
        # per-type driver mirrors for the headline params
        for prop_path, input_name in _fx_driver_map(ep.eff_type):
            drv_items.append((eff, f"hmg_effector.{prop_path}", fn, input_name))
        geo = fn.outputs["Geometry"]

    # also mirror cloner headline params
    return geo, count, x, drv_items


def _fx_driver_map(eff_type):
    base = []
    if eff_type in ("PLAIN", "SOUND", "STEP"):
        base += [("position", "Position"), ("rotation", "Rotation"), ("scale", "Scale")]
    if eff_type == "RANDOM":
        base += [("position_amt", "Position Amt"), ("rotation_amt", "Rotation Amt"),
                 ("scale_amt", "Scale Amt")]
    if eff_type == "FORMULA":
        base += [("amplitude", "Amplitude"), ("frequency", "Frequency"),
                 ("phase", "Phase"), ("speed", "Speed")]
    if eff_type == "DELAY":
        base += [("delay", "Delay"), ("stiffness", "Stiffness"), ("damping", "Damping")]
    if eff_type == "TIME":
        base += [("time_offset", "Offset"), ("time_stagger", "Stagger")]
    # Built-in proximity and time anim (all effectors)
    base += [("use_builtin_falloff", "Use Prox Falloff"),
             ("prox_size", "Prox Size"),
             ("prox_inner", "Prox Inner"),
             ("prox_curve", "Prox Curve"),
             ("prox_invert", "Prox Invert"),
             ("use_time_anim", "Use Time Anim"),
             ("time_speed", "Time Speed"),
             ("time_phase", "Time Phase")]
    return base


def _set_mode_params(mg, cp, cloner_obj):
    def put(name, val):
        try:
            mg.inputs[name].default_value = val
        except Exception:
            pass
    put("Count", cp.count)
    put("PStep", tuple(cp.step_position))
    put("RStep", tuple(cp.step_rotation))
    put("SStep", tuple(cp.step_scale))
    put("Offset", tuple(cp.lin_offset))
    put("Radius", cp.radius)
    put("Arc", cp.arc)
    put("Plane", {"XY": 0, "XZ": 1, "YZ": 2}[cp.plane])
    put("Count X", cp.count_x)
    put("Count Y", cp.count_y)
    put("Count Z", cp.count_z)
    put("Spacing", tuple(cp.spacing))
    put("Columns", cp.count_x)
    put("Rows", cp.count_y)
    put("Target", cp.dist_object)
    put("Dist Mode", {"VERTEX": 0, "EDGE": 1, "FACE": 2, "SURFACE": 3}[cp.dist_mode])
    put("Density", cp.density)
    put("Seed", cp.seed)
    put("Spline", cp.spline_object)
    put("Align", cp.align_to_spline)
    # object-mode domain follows dist mode for vertex/edge/face
    try:
        for n in mg.node_tree.nodes:
            if n.bl_idname == "GeometryNodeMeshToPoints":
                n.mode = {"VERTEX": "VERTICES", "EDGE": "EDGES",
                          "FACE": "FACES", "SURFACE": "VERTICES"}[cp.dist_mode]
    except Exception:
        pass


def _set_fx_params(fn, eff, fo):
    ep = eff.hmg_effector
    def put(name, val):
        try:
            fn.inputs[name].default_value = val
        except Exception:
            pass
    t = ep.eff_type
    if t in ("PLAIN", "SOUND", "STEP"):
        put("Position", tuple(ep.position)); put("Rotation", tuple(ep.rotation))
        put("Scale", tuple(ep.scale))
    if t in ("PLAIN", "SOUND"):
        put("Color", tuple(ep.color)); put("Visibility", ep.visibility)
        put("Time Offset", ep.time_offset)
    if t == "RANDOM":
        put("Seed", ep.seed); put("Position Amt", tuple(ep.position_amt))
        put("Rotation Amt", tuple(ep.rotation_amt)); put("Scale Amt", tuple(ep.scale_amt))
        put("Color A", tuple(ep.color_a)); put("Color B", tuple(ep.color_b))
        put("Use Color", ep.use_color)
    if t == "STEP":
        put("Steps", ep.steps)
    if t == "FORMULA":
        put("Mode", ["SINE", "COSINE", "LINEAR", "NOISE"].index(ep.formula_mode))
        put("Amplitude", ep.amplitude); put("Frequency", ep.frequency)
        put("Phase", ep.phase); put("Speed", ep.speed)
        put("Target", ["POSITION", "ROTATION", "SCALE", "COLOR"].index(ep.target))
        put("Axis", tuple(ep.axis))
    if t == "SHADER":
        put("Image Name", ep.image.name if ep.image else "")
        put("UV Scale", tuple(ep.uv_scale)); put("UV Offset", tuple(ep.uv_offset))
        put("Position Amt", ep.shader_pos_amt); put("Scale Amt", ep.shader_scl_amt)
        put("Use Color", ep.shader_use_color)
    if t == "DELAY":
        put("Delay", ep.delay); put("Stiffness", ep.stiffness)
        put("Damping", ep.damping)
        put("Mode", ["SMOOTH", "SPRING"].index(ep.delay_mode))
    if t == "PUSH_APART":
        put("Radius", ep.pa_radius); put("Push Object", ep.push_object)
        put("Use Object", ep.pa_use_object)
    if t == "TARGET":
        put("Target", ep.target_object)
    if t == "SPLINE":
        put("Spline", ep.spline_object); put("Amount", ep.spline_amount)
        put("Align", ep.spline_align)
    if t == "TIME":
        put("Offset", ep.time_offset); put("Stagger", ep.time_stagger)
    # Built-in proximity falloff (C4D-style)
    put("Use Prox Falloff", ep.use_builtin_falloff)
    put("Prox Shape", ["INFINITE", "LINEAR", "BOX", "SPHERE", "CAPSULE",
                       "CYLINDER", "TUBE", "CONE", "TORUS"].index(ep.prox_shape))
    put("Prox Size", tuple(ep.prox_size)); put("Prox Inner", ep.prox_inner)
    put("Prox Curve", ep.prox_curve); put("Prox Invert", ep.prox_invert)
    # Built-in time animation
    put("Use Time Anim", ep.use_time_anim)
    put("Time Speed", ep.time_speed); put("Time Phase", ep.time_phase)
    if fo is not None:
        fp = fo.hmg_falloff
        put("Shape", ["INFINITE", "LINEAR", "BOX", "SPHERE", "CAPSULE",
                      "CYLINDER", "TUBE", "CONE", "TORUS"].index(fp.shape))
        put("Size", tuple(fp.size)); put("Inner", fp.inner)
        put("Curve", fp.curve); put("Invert", fp.invert)


def build_chain(cloner_obj):
    """(Re)build the full node tree for a cloner object."""
    from .nodes import ng_new as _new
    tree = _new(chain_group_name(cloner_obj))
    iface_out(tree, "Geometry", "GEOMETRY")
    gin, gou = io_nodes(tree)

    geo, count, x, drv_items = _append_pipeline(tree, cloner_obj, -400)

    # apply accumulated position offset
    poff = named_attr(tree, A_POFF, "FLOAT_VECTOR", (x, 100))
    sp = add_node(tree, "GeometryNodeSetPosition", (x + 150, 100))
    link(tree, geo, sp.inputs["Geometry"])
    link(tree, poff.outputs["Attribute"], sp.inputs["Offset"])
    geo = sp.outputs["Geometry"]
    x += 300

    # cull invisible
    alpha = named_attr(tree, A_ALPHA, "FLOAT", (x, -100))
    cull = compare(tree, alpha.outputs["Attribute"], value(tree, 0.5).outputs[0],
                   operation="LESS_THAN", location=(x + 150, -100))
    dg = add_node(tree, "GeometryNodeDeleteGeometry", (x + 300, 0))
    try:
        dg.domain = "POINT"
        dg.mode = "ALL"
    except Exception:
        pass
    link(tree, geo, dg.inputs["Geometry"])
    link(tree, cull.outputs[0], dg.inputs["Selection"])
    geo = dg.outputs["Geometry"]
    x += 450

    instance_obj = _hierarchy_instance_source(cloner_obj)
    if instance_obj is not None:
        # Make sure the nested cloner's own chain is built.
        if getattr(instance_obj, "hmg_type", "") == "CLONER":
            try:
                build_chain(instance_obj)
            except Exception:
                pass
        # Nested cloner: instance the whole child cloner object (its evaluated
        # instances) at each of this cloner's points - C4D-style nesting.
        # The child is treated as one grouped unit; parent effectors transform
        # each child instance as a whole. (Flattened mode coming soon.)
        iinfo = object_info(tree, instance_obj, (x, 200), as_instance=True,
                            transform_space="ORIGINAL")
        roff = named_attr(tree, A_ROFF, "FLOAT_VECTOR", (x, 0))
        rot = euler_to_rotation(tree, roff.outputs["Attribute"], (x + 150, 0))
        smul = named_attr(tree, A_SMUL, "FLOAT_VECTOR", (x, -150))
        iop = add_node(tree, "GeometryNodeInstanceOnPoints", (x + 300, 100))
        link(tree, geo, iop.inputs["Points"])
        link(tree, iinfo.outputs["Geometry"], iop.inputs["Instance"])
        link(tree, rot.outputs["Rotation"], iop.inputs["Rotation"])
        link(tree, smul.outputs["Attribute"], iop.inputs["Scale"])
        geo = iop.outputs["Instances"]
    elif cloner_obj.hmg_cloner.instance_collection is not None:
        cp = cloner_obj.hmg_cloner
        cinfo = add_node(tree, "GeometryNodeCollectionInfo", (x, 200))
        cinfo.inputs["Collection"].default_value = cp.instance_collection
        try:
            cinfo.inputs["Separate Children"].default_value = True
            cinfo.inputs["Reset Children"].default_value = True
        except Exception:
            pass
        roff = named_attr(tree, A_ROFF, "FLOAT_VECTOR", (x, 0))
        rot = euler_to_rotation(tree, roff.outputs["Attribute"], (x + 150, 0))
        smul = named_attr(tree, A_SMUL, "FLOAT_VECTOR", (x, -150))
        iop = add_node(tree, "GeometryNodeInstanceOnPoints", (x + 300, 100))
        link(tree, geo, iop.inputs["Points"])
        link(tree, cinfo.outputs["Instances"], iop.inputs["Instance"])
        link(tree, rot.outputs["Rotation"], iop.inputs["Rotation"])
        link(tree, smul.outputs["Attribute"], iop.inputs["Scale"])
        try:
            iop.inputs["Pick Instance"].default_value = cp.pick_instance
        except Exception:
            pass
        idx = add_node(tree, "GeometryNodeInputIndex", (x, -300))
        iidx = math(tree, "ADD", idx.outputs["Index"],
                    value(tree, float(cp.instance_index_offset)).outputs[0],
                    location=(x + 150, -300))
        try:
            link(tree, iidx.outputs[0], iop.inputs["Instance Index"])
        except Exception:
            pass
        geo = iop.outputs["Instances"]

    link(tree, geo, gou.inputs["Geometry"])
    _mirror_drivers(tree, drv_items)
    ensure_modifier(cloner_obj, tree)
    # Reset modifier inputs from props (modifiers keep stale values across
    # rebuilds when identifiers match; vectors especially).
    _reset_modifier_inputs(cloner_obj)
    return tree


def _reset_modifier_inputs(cloner_obj):
    """Set all modifier inputs from current props (fresh rebuild)."""
    mod = cloner_obj.modifiers.get("HoloMoGraph")
    if mod is None or mod.node_group is None:
        return
    tree = mod.node_group
    cp = cloner_obj.hmg_cloner
    # Scalars via sync (live-safe)
    sync_cloner_inputs(cloner_obj)
    # Vectors: set directly (fresh build, no live-update needed)
    for name, vec in (("PStep", cp.step_position), ("RStep", cp.step_rotation),
                      ("SStep", cp.step_scale), ("Spacing", cp.spacing)):
        ident = _mod_input_id(tree, name)
        if ident is None:
            continue
        try:
            if bpy.app.version >= (5, 2, 0):
                getattr(mod.properties.inputs, ident).value = tuple(vec)
            else:
                mod[ident] = tuple(vec)
        except Exception:
            pass
    try:
        mod.id_data.update_tag()
    except Exception:
        pass


def new_cloner_object(context, name):
    """Create the cloner object. A wireframe octahedron mesh (not an empty)
    because Blender 5.0 cannot put modifiers on empties. The modifier output
    replaces the mesh entirely, so the gizmo never renders — it's just a
    visible, selectable handle in the viewport, like a C4D cloner icon."""
    me = bpy.data.meshes.new(f"{name} Mesh")
    # Octahedron: 6 verts, 8 triangular faces (wireframe gizmo)
    verts = [(0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)]
    faces = [(0, 2, 4), (0, 4, 3), (0, 3, 5), (0, 5, 2),
             (1, 4, 2), (1, 3, 4), (1, 5, 3), (1, 2, 5)]
    me.from_pydata(verts, [], faces)
    me.update()
    obj = bpy.data.objects.new(name, me)
    obj.display_type = "WIRE"
    context.scene.collection.objects.link(obj)
    context.view_layer.objects.active = obj
    obj.select_set(True)
    obj.hmg_type = "CLONER"
    return obj


def ensure_modifier(cloner_obj, tree=None):
    mod = cloner_obj.modifiers.get("HoloMoGraph")
    if mod is None:
        try:
            mod = cloner_obj.modifiers.new("HoloMoGraph", "NODES")
        except Exception:
            mod = None
    if mod is None:
        raise RuntimeError(
            f"HoloMoGraph: cannot add a Geometry Nodes modifier to "
            f"'{cloner_obj.name}' ({cloner_obj.type}). "
            f"Blender 5.0 cannot put modifiers on empties — use a mesh object.")
    if tree is None:
        tree = ng_get(chain_group_name(cloner_obj))
    if tree is not None:
        mod.node_group = tree
    return mod


def _mod_input_id(tree, name):
    """Get the modifier input identifier for a named group input."""
    try:
        for item in tree.interface.items_tree:
            if getattr(item, "name", "") == name:
                return item.identifier
    except Exception:
        pass
    return None


def _set_mod_input(mod, identifier, value):
    """Version-gated modifier input setter (5.2+ uses RNA, older uses ID props)."""
    try:
        if bpy.app.version >= (5, 2, 0):
            entry = getattr(mod.properties.inputs, identifier)
            entry.type = "VALUE"
            entry.value = value
        else:
            mod[identifier] = value
        mod.id_data.update_tag()
    except Exception:
        pass


def sync_cloner_inputs(cloner_obj):
    """Sync cloner props to master group modifier inputs (live, no rebuild).

    Note: Vector props (PStep etc.) use _upd_vec which rebuilds, because
    Blender's Python API doesn't propagate vector modifier-input changes.
    Only scalars are synced here.
    """
    mod = cloner_obj.modifiers.get("HoloMoGraph")
    if mod is None or mod.node_group is None:
        return
    tree = mod.node_group
    cp = cloner_obj.hmg_cloner
    vals = {
        "Mode": {"LINEAR": 0, "RADIAL": 1, "GRID": 2,
                 "HONEYCOMB": 3, "OBJECT": 4, "SPLINE": 5}[cp.mode],
        "Count": cp.count,
        "Radius": cp.radius,
        "Arc": cp.arc,
        "Plane": {"XY": 0, "XZ": 1, "YZ": 2}[cp.plane],
        "Count X": cp.count_x, "Count Y": cp.count_y, "Count Z": cp.count_z,
        "Columns": cp.count_x, "Rows": cp.count_y,
        "Target": cp.dist_object,
        "Dist Mode": {"VERTEX": 0, "EDGE": 1, "FACE": 2, "SURFACE": 3}[cp.dist_mode],
        "Density": cp.density, "Seed": cp.seed,
        "Spline": cp.spline_object, "Align": cp.align_to_spline,
    }
    for name, val in vals.items():
        ident = _mod_input_id(tree, name)
        if ident is None:
            continue
        _set_mod_input(mod, ident, val)


def sync_from_any(obj):
    """Sync inputs (live) for a prop change on obj — no structural rebuild."""
    if obj is None:
        return
    t = getattr(obj, "hmg_type", "")
    if t == "CLONER":
        # If master doesn't exist yet, build it.
        mod = obj.modifiers.get("HoloMoGraph")
        if mod is None or mod.node_group is None:
            build_chain(obj)
        else:
            sync_cloner_inputs(obj)
    elif t in ("EFFECTOR", "FALLOFF"):
        # Effector param change: sync the FX node inputs in parent chain.
        # (Structural add/remove still uses build_chain via ops.)
        parent = obj.parent
        if t == "FALLOFF":
            parent = parent.parent if parent else None
        while parent is not None and getattr(parent, "hmg_type", "") != "CLONER":
            parent = parent.parent
        if parent is not None:
            _sync_effector_node(parent, obj if t == "EFFECTOR" else obj.parent)


def _sync_effector_node(cloner_obj, eff_obj):
    """Copy effector props to its node inputs in the cloner master (live)."""
    mod = cloner_obj.modifiers.get("HoloMoGraph")
    if mod is None or mod.node_group is None:
        return
    tree = mod.node_group
    ep = eff_obj.hmg_effector
    # Find the FX group node for this effector
    target = None
    for node in tree.nodes:
        if node.bl_idname == "GeometryNodeGroup" and node.node_tree:
            if sanitize(eff_obj.name) in node.node_tree.name:
                target = node
                break
    if target is None:
        return
    # Reuse the same param-setting logic as the initial build.
    fo = _falloff_of(eff_obj)
    _set_fx_params(target, eff_obj, fo)
    try:
        target.inputs["Strength"].default_value = ep.strength
    except Exception:
        pass


def refresh_from_any(obj):
    """Rebuild whichever cloner is affected by a change on obj."""
    if obj is None:
        return
    t = getattr(obj, "hmg_type", "")
    if t == "CLONER":
        build_chain(obj)
    elif t == "EFFECTOR":
        parent = obj.parent
        while parent is not None and parent.hmg_type != "CLONER":
            parent = parent.parent
        if parent is not None:
            build_chain(parent)
    elif t == "FALLOFF":
        eff = obj.parent
        if eff is not None:
            refresh_from_any(eff)

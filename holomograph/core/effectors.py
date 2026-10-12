"""HoloMoGraph - Effectors.

Each effector is a node group `HMG_FX_<Type>_<name>` built per effector object.
Effectors accumulate into per-point attributes (C4D-style parameter pipeline):

    hmg_poff  vector  position offset          (init 0)
    hmg_roff  vector  euler rotation offset    (init 0, radians)
    hmg_smul  vector  scale multiplier         (init 1)
    hmg_col   color   tint                     (init white)
    hmg_time  float   time offset (frames)     (init 0)
    hmg_alpha float   visibility               (init 1)

Every effector first evaluates its own falloff (HMG_Falloff) into a private
weight attribute, then applies:  effective = falloff_weight * Strength.
"""
from __future__ import annotations
import math as _math
import bpy
from .nodes import (
    ng_new, add_node, link, group_node, iface_in, iface_out, io_nodes,
    math, vmath, combine_xyz, separate_xyz, compare, switch, value,
    boolean_math, mix_float, store_attr, named_attr, random_value,
    object_info, euler_to_rotation, rotation_to_euler, align_to_vector,
    index_switch,
)
from .falloff import build_falloff_group, GROUP_NAME as FALLOFF_GROUP
from .nodes import ng_get as _ng_get

# attribute names
A_POFF = "hmg_poff"
A_ROFF = "hmg_roff"
A_SMUL = "hmg_smul"
A_COL = "hmg_col"
A_TIME = "hmg_time"
A_ALPHA = "hmg_alpha"


def _ensure_falloff():
    g = _ng_get(FALLOFF_GROUP)
    if g is None:
        g = build_falloff_group()
    return g


def _base(name, falloff_obj, cloner_obj):
    """Create group + standard interface. Returns dict of handles."""
    tree = ng_new(name)
    iface_in(tree, "Geometry", "GEOMETRY")
    iface_in(tree, "Cloner", "OBJECT")
    iface_in(tree, "Falloff", "OBJECT")
    iface_in(tree, "Strength", "FLOAT", default=1.0, min_value=-4.0, max_value=4.0)
    iface_in(tree, "Count", "INT", default=100, min_value=1)
    iface_in(tree, "Weight Attr", "STRING", default="hmg_w")
    iface_out(tree, "Geometry", "GEOMETRY")
    gin, gou = io_nodes(tree)
    h = {"tree": tree, "gin": gin, "gou": gou, "geo": gin.outputs["Geometry"]}
    return h


def _apply_falloff(h, falloff_obj):
    """Run the falloff subgroup; return effective weight socket."""
    tree, gin = h["tree"], h["gin"]
    if falloff_obj is None:
        return gin.outputs["Strength"]
    fg = group_node(tree, _ensure_falloff(), location=(200, 200))
    link(tree, h["geo"], fg.inputs["Geometry"])
    link(tree, gin.outputs["Cloner"], fg.inputs["Cloner"])
    link(tree, gin.outputs["Falloff"], fg.inputs["Falloff"])
    for pname in ("Shape", "Size", "Inner", "Curve", "Invert"):
        src = fg.inputs[pname]
        try:
            link(tree, gin.outputs[pname], src)
        except Exception:
            pass
    link(tree, gin.outputs["Weight Attr"], fg.inputs["Weight Attr"])
    h["geo"] = fg.outputs["Geometry"]
    w = named_attr(tree, "hmg_w", location=(450, 200))
    link(tree, gin.outputs["Weight Attr"], w.inputs["Name"])
    return math(tree, "MULTIPLY", w.outputs["Attribute"],
                gin.outputs["Strength"], location=(600, 200)).outputs[0]


def _finish(h, w):
    """Pass geometry through to output (attributes already stored)."""
    link(h["tree"], h["geo"], h["gou"].inputs["Geometry"])
    return h["tree"]


def _idx_norm(h):
    """index / max(count-1,1) -> 0..1"""
    tree, gin = h["tree"], h["gin"]
    idx = add_node(tree, "GeometryNodeInputIndex", (200, -200))
    cnt = math(tree, "MAXIMUM",
               math(tree, "SUBTRACT", gin.outputs["Count"],
                    value(tree, 1.0, (200, -320)).outputs[0], location=(350, -260)).outputs[0],
               value(tree, 1.0, (350, -340)).outputs[0], location=(500, -280))
    return math(tree, "DIVIDE", idx.outputs["Index"], cnt.outputs[0],
                location=(650, -280)).outputs[0]


# ---------------------------------------------------------------------------
# Shared "transform applier": apply P/R/S/Color/Alpha/Visibility/Time
# ---------------------------------------------------------------------------

def _apply_transforms(h, w, P, R, S, C=None, V=None, T=None):
    """P/R/S are offset sockets (already scaled as desired); w = weight.
    Adds P to hmg_poff, R to hmg_roff, multiplies hmg_smul by S-factor etc."""
    tree = h["tree"]
    geo = h["geo"]
    x = 800

    if P is not None:
        cur = named_attr(tree, A_POFF, "FLOAT_VECTOR", (x, 300))
        new = vmath(tree, "ADD", cur.outputs["Attribute"],
                    vmath(tree, "MULTIPLY", P, _to_vec(tree, w, (x, 150)),
                          location=(x + 150, 300)).outputs["Vector"],
                    location=(x + 300, 300))
        geo = store_attr(tree, geo, A_POFF, new.outputs["Vector"], "FLOAT_VECTOR",
                         location=(x + 450, 300)).outputs["Geometry"]
    if R is not None:
        cur = named_attr(tree, A_ROFF, "FLOAT_VECTOR", (x, 100))
        new = vmath(tree, "ADD", cur.outputs["Attribute"],
                    vmath(tree, "MULTIPLY", R, _to_vec(tree, w, (x, -50)),
                          location=(x + 150, 100)).outputs["Vector"],
                    location=(x + 300, 100))
        geo = store_attr(tree, geo, A_ROFF, new.outputs["Vector"], "FLOAT_VECTOR",
                         location=(x + 450, 100)).outputs["Geometry"]
    if S is not None:
        # S here is a per-component FACTOR (1 = no change)
        cur = named_attr(tree, A_SMUL, "FLOAT_VECTOR", (x, -100))
        fac = vmath(tree, "ADD",
                    combine_xyz(tree, value(tree, 1.0, (x, -250)).outputs[0],
                                value(tree, 1.0, (x, -290)).outputs[0],
                                value(tree, 1.0, (x, -330)).outputs[0], (x + 150, -250)).outputs["Vector"],
                    vmath(tree, "MULTIPLY",
                          vmath(tree, "SUBTRACT", S,
                                combine_xyz(tree, value(tree, 1.0).outputs[0],
                                            value(tree, 1.0).outputs[0],
                                            value(tree, 1.0).outputs[0]).outputs["Vector"],
                                location=(x + 150, -150)).outputs["Vector"],
                          _to_vec(tree, w, (x, -50)), location=(x + 300, -150)).outputs["Vector"],
                    location=(x + 450, -100))
        new = vmath(tree, "MULTIPLY", cur.outputs["Attribute"], fac.outputs["Vector"],
                    location=(x + 600, -100))
        geo = store_attr(tree, geo, A_SMUL, new.outputs["Vector"], "FLOAT_VECTOR",
                         location=(x + 750, -100)).outputs["Geometry"]
    if C is not None:
        cur = named_attr(tree, A_COL, "FLOAT_COLOR", (x, -400))
        n = add_node(tree, "ShaderNodeMix", (x + 300, -400))
        n.data_type = "RGBA"
        link(tree, w, n.inputs["Factor"])
        link(tree, cur.outputs["Attribute"], n.inputs["A"])
        link(tree, C, n.inputs["B"])
        geo = store_attr(tree, geo, A_COL, n.outputs["Result"], "FLOAT_COLOR",
                         location=(x + 450, -400)).outputs["Geometry"]
    if V is not None:
        cur = named_attr(tree, A_ALPHA, "FLOAT", (x, -550))
        new = math(tree, "MULTIPLY", cur.outputs["Attribute"],
                   mix_float(tree, w, value(tree, 1.0, (x, -700)).outputs[0], V,
                             location=(x + 150, -550)).outputs[0],
                   location=(x + 300, -550))
        geo = store_attr(tree, geo, A_ALPHA, new.outputs[0], "FLOAT",
                         location=(x + 450, -550)).outputs["Geometry"]
    if T is not None:
        cur = named_attr(tree, A_TIME, "FLOAT", (x, -700))
        new = math(tree, "ADD", cur.outputs["Attribute"],
                   math(tree, "MULTIPLY", T, w, location=(x + 150, -700)).outputs[0],
                   location=(x + 300, -700))
        geo = store_attr(tree, geo, A_TIME, new.outputs[0], "FLOAT",
                         location=(x + 450, -700)).outputs["Geometry"]
    h["geo"] = geo


def _to_vec(tree, float_sock, location):
    """Broadcast float socket to a vector."""
    return combine_xyz(tree, float_sock, float_sock, float_sock, location).outputs["Vector"]


# ---------------------------------------------------------------------------
# Effector builders. Each returns the node group.
# `P` = dict of parameter defaults; `falloff_obj`/`cloner_obj` baked as
# group-input defaults by the chain builder.
# ---------------------------------------------------------------------------

def build_plain(name, P, falloff_obj):
    h = _base(name, falloff_obj, None)
    tree, gin = h["tree"], h["gin"]
    iface_in(tree, "Position", "VECTOR", default=P.get("position", (0, 0, 0)))
    iface_in(tree, "Rotation", "VECTOR", default=P.get("rotation", (0, 0, 0)),
             description="Euler radians")
    iface_in(tree, "Scale", "VECTOR", default=P.get("scale", (1, 1, 1)))
    iface_in(tree, "Color", "RGBA", default=P.get("color", (1, 1, 1, 1)))
    iface_in(tree, "Visibility", "FLOAT", default=P.get("visibility", 1.0),
             min_value=0.0, max_value=1.0)
    iface_in(tree, "Time Offset", "FLOAT", default=P.get("time_offset", 0.0))
    # falloff params live on the group so drivers can reach them
    for pname, stype, default in (("Shape", "INT", 3), ("Size", "VECTOR", (2, 2, 2)),
                                  ("Inner", "FLOAT", 0.0), ("Curve", "FLOAT", 0.0),
                                  ("Invert", "BOOLEAN", False)):
        iface_in(tree, pname, stype, default=default)
    w = _apply_falloff(h, falloff_obj)
    _apply_transforms(h, w, gin.outputs["Position"], gin.outputs["Rotation"],
                      gin.outputs["Scale"], gin.outputs["Color"],
                      gin.outputs["Visibility"], gin.outputs["Time Offset"])
    return _finish(h, w)


def build_random(name, P, falloff_obj):
    h = _base(name, falloff_obj, None)
    tree, gin = h["tree"], h["gin"]
    iface_in(tree, "Seed", "INT", default=P.get("seed", 0))
    iface_in(tree, "Position Amt", "VECTOR", default=P.get("position_amt", (1, 1, 1)))
    iface_in(tree, "Rotation Amt", "VECTOR", default=P.get("rotation_amt", (0.5, 0.5, 0.5)))
    iface_in(tree, "Scale Amt", "VECTOR", default=P.get("scale_amt", (0.3, 0.3, 0.3)))
    iface_in(tree, "Color A", "RGBA", default=P.get("color_a", (1, 1, 1, 1)))
    iface_in(tree, "Color B", "RGBA", default=P.get("color_b", (1, 0.4, 0.1, 1)))
    iface_in(tree, "Use Color", "BOOLEAN", default=P.get("use_color", False))
    for pname, stype, default in (("Shape", "INT", 3), ("Size", "VECTOR", (2, 2, 2)),
                                  ("Inner", "FLOAT", 0.0), ("Curve", "FLOAT", 0.0),
                                  ("Invert", "BOOLEAN", False)):
        iface_in(tree, pname, stype, default=default)
    w = _apply_falloff(h, falloff_obj)

    idx = add_node(tree, "GeometryNodeInputIndex", (200, -300))
    seed_id = math(tree, "ADD",
                   math(tree, "MULTIPLY", idx.outputs["Index"],
                        value(tree, 15731.0, (200, -420)).outputs[0], location=(350, -360)).outputs[0],
                   gin.outputs["Seed"], location=(500, -360)).outputs[0]
    one_v = combine_xyz(tree, value(tree, 1.0).outputs[0], value(tree, 1.0).outputs[0],
                        value(tree, 1.0).outputs[0]).outputs["Vector"]
    neg_one_v = combine_xyz(tree, value(tree, -1.0).outputs[0], value(tree, -1.0).outputs[0],
                            value(tree, -1.0).outputs[0]).outputs["Vector"]

    r_pos = random_value(tree, "FLOAT_VECTOR", neg_one_v, one_v, seed_id, (650, 200))
    r_rot = random_value(tree, "FLOAT_VECTOR", neg_one_v, one_v,
                         math(tree, "ADD", seed_id, value(tree, 101.0).outputs[0]).outputs[0],
                         (650, 0))
    r_scl = random_value(tree, "FLOAT_VECTOR", neg_one_v, one_v,
                         math(tree, "ADD", seed_id, value(tree, 202.0).outputs[0]).outputs[0],
                         (650, -200))
    r_col = random_value(tree, "FLOAT", value(tree, 0.0).outputs[0], value(tree, 1.0).outputs[0],
                         math(tree, "ADD", seed_id, value(tree, 303.0).outputs[0]).outputs[0],
                         (650, -400))

    P_off = vmath(tree, "MULTIPLY", r_pos.outputs[0], gin.outputs["Position Amt"],
                  location=(800, 200)).outputs["Vector"]
    R_off = vmath(tree, "MULTIPLY", r_rot.outputs[0], gin.outputs["Rotation Amt"],
                  location=(800, 0)).outputs["Vector"]
    S_fac = vmath(tree, "ADD", one_v,
                  vmath(tree, "MULTIPLY", r_scl.outputs[0], gin.outputs["Scale Amt"],
                        location=(800, -200)).outputs["Vector"], location=(950, -200)).outputs["Vector"]
    col_mix = add_node(tree, "ShaderNodeMix", (950, -400))
    col_mix.data_type = "RGBA"
    link(tree, r_col.outputs[0], col_mix.inputs["Factor"])
    link(tree, gin.outputs["Color A"], col_mix.inputs["A"])
    link(tree, gin.outputs["Color B"], col_mix.inputs["B"])
    C = switch(tree, gin.outputs["Use Color"],
               combine_xyz(tree, value(tree, 1.0).outputs[0], value(tree, 1.0).outputs[0],
                           value(tree, 1.0).outputs[0]).outputs["Vector"],
               col_mix.outputs["Result"], input_type="RGBA", location=(1100, -400)).outputs[0]
    _apply_transforms(h, w, P_off, R_off, S_fac, C, None, None)
    return _finish(h, w)


def build_step(name, P, falloff_obj):
    h = _base(name, falloff_obj, None)
    tree, gin = h["tree"], h["gin"]
    iface_in(tree, "Steps", "INT", default=P.get("steps", 5), min_value=2)
    iface_in(tree, "Position", "VECTOR", default=P.get("position", (0, 0, 3)))
    iface_in(tree, "Rotation", "VECTOR", default=P.get("rotation", (0, 0, 0)))
    iface_in(tree, "Scale", "VECTOR", default=P.get("scale", (1, 1, 1)))
    for pname, stype, default in (("Shape", "INT", 3), ("Size", "VECTOR", (2, 2, 2)),
                                  ("Inner", "FLOAT", 0.0), ("Curve", "FLOAT", 0.0),
                                  ("Invert", "BOOLEAN", False)):
        iface_in(tree, pname, stype, default=default)
    w = _apply_falloff(h, falloff_obj)
    t = _idx_norm(h)
    steps = gin.outputs["Steps"]
    stepped = math(tree, "DIVIDE",
                   math(tree, "FLOOR",
                        math(tree, "MULTIPLY", t, steps, location=(800, -300)).outputs[0],
                        location=(950, -300)).outputs[0],
                   steps, location=(1100, -300)).outputs[0]
    w2 = math(tree, "MULTIPLY", w, stepped, location=(1250, -200)).outputs[0]
    _apply_transforms(h, w2, gin.outputs["Position"], gin.outputs["Rotation"],
                      gin.outputs["Scale"], None, None, None)
    return _finish(h, w2)


def build_formula(name, P, falloff_obj):
    h = _base(name, falloff_obj, None)
    tree, gin = h["tree"], h["gin"]
    iface_in(tree, "Mode", "INT", default=P.get("formula_mode", 0),
             min_value=0, max_value=3,
             description="0 Sine 1 Cosine 2 Linear 3 Noise")
    iface_in(tree, "Amplitude", "FLOAT", default=P.get("amplitude", 1.0))
    iface_in(tree, "Frequency", "FLOAT", default=P.get("frequency", 1.0))
    iface_in(tree, "Phase", "FLOAT", default=P.get("phase", 0.0))
    iface_in(tree, "Speed", "FLOAT", default=P.get("speed", 1.0))
    iface_in(tree, "Target", "INT", default=P.get("target", 0), min_value=0, max_value=3,
             description="0 Position 1 Rotation 2 Scale 3 Color")
    iface_in(tree, "Axis", "VECTOR", default=P.get("axis", (0, 0, 1)))
    for pname, stype, default in (("Shape", "INT", 3), ("Size", "VECTOR", (2, 2, 2)),
                                  ("Inner", "FLOAT", 0.0), ("Curve", "FLOAT", 0.0),
                                  ("Invert", "BOOLEAN", False)):
        iface_in(tree, pname, stype, default=default)
    w = _apply_falloff(h, falloff_obj)

    t = _idx_norm(h)
    stime = add_node(tree, "GeometryNodeInputSceneTime", (200, -500))
    phase = math(tree, "ADD",
                 math(tree, "ADD",
                      math(tree, "MULTIPLY", t, gin.outputs["Frequency"],
                           location=(800, -300)).outputs[0],
                      gin.outputs["Phase"], location=(950, -300)).outputs[0],
                 math(tree, "MULTIPLY", stime.outputs["Seconds"], gin.outputs["Speed"],
                      location=(950, -420)).outputs[0], location=(1100, -350))
    s_sin = math(tree, "SINE", phase.outputs[0], location=(1250, -200))
    s_cos = math(tree, "COSINE", phase.outputs[0], location=(1250, -350))
    # noise: white noise on index
    wn = add_node(tree, "ShaderNodeTexWhiteNoise", (1250, -500))
    link(tree, _to_vec(tree, t, (1100, -550)), wn.inputs["Vector"])
    s_lin = t
    val = index_switch(tree, gin.outputs["Mode"],
                       [s_sin.outputs[0], s_cos.outputs[0], s_lin, wn.outputs["Value"]],
                       location=(1400, -300)).outputs[0]
    val = math(tree, "MULTIPLY", val, gin.outputs["Amplitude"], location=(1550, -300)).outputs[0]
    vec = vmath(tree, "MULTIPLY", _to_vec(tree, val, (1550, -450)), gin.outputs["Axis"],
                location=(1700, -350)).outputs["Vector"]

    P_o = switch(tree, compare(tree, gin.outputs["Target"], value(tree, 0.0).outputs[0],
                               operation="EQUAL", data_type="INT", location=(1700, -100)).outputs[0],
                 combine_xyz(tree, value(tree, 0.0).outputs[0], value(tree, 0.0).outputs[0],
                             value(tree, 0.0).outputs[0]).outputs["Vector"],
                 vec, input_type="VECTOR", location=(1850, -100)).outputs[0]
    R_o = switch(tree, compare(tree, gin.outputs["Target"], value(tree, 1.0).outputs[0],
                               operation="EQUAL", data_type="INT").outputs[0],
                 combine_xyz(tree, value(tree, 0.0).outputs[0], value(tree, 0.0).outputs[0],
                             value(tree, 0.0).outputs[0]).outputs["Vector"],
                 vec, input_type="VECTOR").outputs[0]
    one_v = combine_xyz(tree, value(tree, 1.0).outputs[0], value(tree, 1.0).outputs[0],
                        value(tree, 1.0).outputs[0]).outputs["Vector"]
    S_o = switch(tree, compare(tree, gin.outputs["Target"], value(tree, 2.0).outputs[0],
                               operation="EQUAL", data_type="INT").outputs[0],
                 one_v, vmath(tree, "ADD", one_v, vec, location=(1850, -500)).outputs["Vector"],
                 input_type="VECTOR").outputs[0]
    C_o = switch(tree, compare(tree, gin.outputs["Target"], value(tree, 3.0).outputs[0],
                               operation="EQUAL", data_type="INT").outputs[0],
                 combine_xyz(tree, value(tree, 1.0).outputs[0], value(tree, 1.0).outputs[0],
                             value(tree, 1.0).outputs[0]).outputs["Vector"],
                 _to_vec(tree, math(tree, "ADD", val,
                                    value(tree, 0.5).outputs[0]).outputs[0],
                         (1850, -650)), input_type="VECTOR").outputs[0]
    _apply_transforms(h, w, P_o, R_o, S_o, C_o, None, None)
    return _finish(h, w)


def build_shader(name, P, falloff_obj):
    h = _base(name, falloff_obj, None)
    tree, gin = h["tree"], h["gin"]
    # NOTE: the image is baked onto the texture node at build time
    # (GeometryNodeImageTexture has no image *input* socket).
    iface_in(tree, "Image Name", "STRING", default=P.get("image_name", ""))
    iface_in(tree, "UV Scale", "VECTOR", default=P.get("uv_scale", (0.2, 0.2, 0.2)))
    iface_in(tree, "UV Offset", "VECTOR", default=P.get("uv_offset", (0, 0, 0)))
    iface_in(tree, "Position Amt", "FLOAT", default=P.get("position_amt", 2.0))
    iface_in(tree, "Scale Amt", "FLOAT", default=P.get("scale_amt", 1.0))
    iface_in(tree, "Use Color", "BOOLEAN", default=P.get("use_color", True))
    for pname, stype, default in (("Shape", "INT", 3), ("Size", "VECTOR", (2, 2, 2)),
                                  ("Inner", "FLOAT", 0.0), ("Curve", "FLOAT", 0.0),
                                  ("Invert", "BOOLEAN", False)):
        iface_in(tree, pname, stype, default=default)
    w = _apply_falloff(h, falloff_obj)

    pos = add_node(tree, "GeometryNodeInputPosition", (200, -300))
    uv = vmath(tree, "ADD",
               vmath(tree, "MULTIPLY", pos.outputs["Position"], gin.outputs["UV Scale"],
                     location=(350, -300)).outputs["Vector"],
               gin.outputs["UV Offset"], location=(500, -300))
    tex = add_node(tree, "GeometryNodeImageTexture", (650, -300))
    link(tree, uv.outputs["Vector"], tex.inputs["Vector"])
    img = bpy.data.images.get(P.get("image_name", ""))
    if img is not None:
        try:
            tex.image = img
        except Exception:
            pass
    col = tex.outputs["Color"]
    sep = separate_xyz(tree, col, (800, -300))
    lum = math(tree, "ADD", math(tree, "ADD", sep.outputs["X"], sep.outputs["Y"],
                                 location=(950, -250)).outputs[0], sep.outputs["Z"],
               location=(1100, -250)).outputs[0]
    lum = math(tree, "DIVIDE", lum, value(tree, 3.0).outputs[0],
               location=(1250, -250)).outputs[0]
    P_off = vmath(tree, "MULTIPLY",
                  vmath(tree, "SUBTRACT", _to_vec(tree, lum, (1250, -400)),
                        _to_vec(tree, value(tree, 0.5).outputs[0], (1250, -460)),
                        location=(1400, -400)).outputs["Vector"],
                  _to_vec(tree, math(tree, "MULTIPLY", gin.outputs["Position Amt"],
                                     value(tree, 2.0).outputs[0]).outputs[0],
                          (1400, -520)), location=(1550, -400)).outputs["Vector"]
    one_v = combine_xyz(tree, value(tree, 1.0).outputs[0], value(tree, 1.0).outputs[0],
                        value(tree, 1.0).outputs[0]).outputs["Vector"]
    S_fac = vmath(tree, "ADD", one_v,
                  vmath(tree, "MULTIPLY",
                        _to_vec(tree, math(tree, "SUBTRACT", lum,
                                           value(tree, 0.5).outputs[0]).outputs[0],
                                (1400, -650)),
                        _to_vec(tree, gin.outputs["Scale Amt"], (1400, -710)),
                        location=(1550, -650)).outputs["Vector"],
                  location=(1700, -650)).outputs["Vector"]
    C = switch(tree, gin.outputs["Use Color"], one_v, col, input_type="RGBA",
               location=(1700, -800)).outputs[0]
    _apply_transforms(h, w, P_off, None, S_fac,
                      C, None, None)
    return _finish(h, w)


def build_delay(name, P, falloff_obj):
    """Spring/smooth delay via a simulation zone. State persists in named attrs."""
    h = _base(name, falloff_obj, None)
    tree, gin = h["tree"], h["gin"]
    iface_in(tree, "Delay", "FLOAT", default=P.get("delay", 10.0), min_value=0.0)
    iface_in(tree, "Stiffness", "FLOAT", default=P.get("stiffness", 1.5),
             min_value=0.01, max_value=10.0)
    iface_in(tree, "Damping", "FLOAT", default=P.get("damping", 0.85),
             min_value=0.0, max_value=0.999)
    iface_in(tree, "Mode", "INT", default=P.get("delay_mode", 1), min_value=0, max_value=1,
             description="0 Smooth 1 Spring")
    for pname, stype, default in (("Shape", "INT", 3), ("Size", "VECTOR", (2, 2, 2)),
                                  ("Inner", "FLOAT", 0.0), ("Curve", "FLOAT", 0.0),
                                  ("Invert", "BOOLEAN", False)):
        iface_in(tree, pname, stype, default=default)
    w = _apply_falloff(h, falloff_obj)
    geo = h["geo"]

    sim_in = add_node(tree, "GeometryNodeSimulationInput", (900, 200))
    sim_out = add_node(tree, "GeometryNodeSimulationOutput", (2100, 200))
    # Blender 5.x: pair on the INPUT node; geometry sockets appear after pairing
    try:
        sim_in.pair_with_output(sim_out)
    except Exception:
        pass
    try:
        link(tree, geo, sim_in.inputs["Geometry"])
    except Exception:
        pass
    prev_geo = sim_in.outputs["Geometry"]

    def _spring_attr(attr_name, dtype, target_sock, loc_y):
        nonlocal prev_geo
        prev = named_attr(tree, "hmg_d_" + attr_name, dtype, (1050, loc_y))
        init = named_attr(tree, "hmg_d_init", "FLOAT", (1050, loc_y - 120))
        is_init = compare(tree, init.outputs["Attribute"], value(tree, 0.5).outputs[0],
                          operation="GREATER_THAN", location=(1200, loc_y - 120))
        eff_prev = switch(tree, is_init.outputs[0], target_sock, prev.outputs["Attribute"],
                          input_type="VECTOR" if dtype == "FLOAT_VECTOR" else "FLOAT",
                          location=(1350, loc_y)).outputs[0]
        k = math(tree, "DIVIDE", value(tree, 1.0, (1200, loc_y - 260)).outputs[0],
                 math(tree, "ADD", value(tree, 1.0, (1200, loc_y - 320)).outputs[0],
                      math(tree, "MULTIPLY", gin.outputs["Delay"], w,
                           location=(1350, loc_y - 320)).outputs[0],
                      location=(1500, loc_y - 300)).outputs[0],
                 location=(1500, loc_y - 200))
        if dtype == "FLOAT_VECTOR":
            _mixn = add_node(tree, "ShaderNodeMix", (1650, loc_y))
            _mixn.data_type = "VECTOR"
            link(tree, k.outputs[0], _mixn.inputs["Factor"])
            link(tree, eff_prev, _mixn.inputs["A"])
            link(tree, target_sock, _mixn.inputs["B"])
            smooth_out = _mixn.outputs["Result"]
        else:
            smooth_out = mix_float(tree, k.outputs[0], eff_prev, target_sock,
                                   location=(1650, loc_y)).outputs[0]
        # spring
        vel = named_attr(tree, "hmg_d_" + attr_name + "_v", dtype, (1200, loc_y + 160))
        acc = vmath(tree, "MULTIPLY",
                    vmath(tree, "SUBTRACT", target_sock, eff_prev,
                          location=(1500, loc_y + 160)).outputs["Vector"],
                    _to_vec(tree, math(tree, "MULTIPLY", gin.outputs["Stiffness"],
                                       value(tree, 0.2).outputs[0]).outputs[0],
                            (1500, loc_y + 60)), location=(1650, loc_y + 160)).outputs["Vector"] \
            if dtype == "FLOAT_VECTOR" else None
        if dtype == "FLOAT_VECTOR":
            new_vel = vmath(tree, "MULTIPLY",
                            vmath(tree, "ADD", vel.outputs["Attribute"], acc,
                                  location=(1800, loc_y + 160)).outputs["Vector"],
                            _to_vec(tree, gin.outputs["Damping"], (1800, loc_y + 60)),
                            location=(1950, loc_y + 160)).outputs["Vector"]
            spring = vmath(tree, "ADD", eff_prev, new_vel, location=(2100, loc_y + 160)).outputs["Vector"]
            new_val = switch(tree, compare(tree, gin.outputs["Mode"],
                                           value(tree, 0.5).outputs[0],
                                           operation="GREATER_THAN").outputs[0],
                             smooth_out, spring, input_type="VECTOR",
                             location=(2250, loc_y)).outputs[0]
        else:
            new_val = smooth_out
        return new_val, vel.outputs["Attribute"] if dtype == "FLOAT_VECTOR" else None, \
            (new_vel if dtype == "FLOAT_VECTOR" else None)

    # delay position / rotation / scale accumulators
    t_poff = named_attr(tree, A_POFF, "FLOAT_VECTOR", (900, -200))
    t_roff = named_attr(tree, A_ROFF, "FLOAT_VECTOR", (900, -350))
    t_smul = named_attr(tree, A_SMUL, "FLOAT_VECTOR", (900, -500))

    new_p, _, new_pv = _spring_attr("p", "FLOAT_VECTOR", t_poff.outputs["Attribute"], 200)
    new_r, _, new_rv = _spring_attr("r", "FLOAT_VECTOR", t_roff.outputs["Attribute"], -100)
    new_s, _, new_sv = _spring_attr("s", "FLOAT_VECTOR", t_smul.outputs["Attribute"], -400)

    sg = prev_geo
    sg = store_attr(tree, sg, "hmg_d_p", new_p, "FLOAT_VECTOR", location=(2400, 200)).outputs["Geometry"]
    sg = store_attr(tree, sg, "hmg_d_r", new_r, "FLOAT_VECTOR", location=(2550, 200)).outputs["Geometry"]
    sg = store_attr(tree, sg, "hmg_d_s", new_s, "FLOAT_VECTOR", location=(2700, 200)).outputs["Geometry"]
    sg = store_attr(tree, sg, "hmg_d_p_v", new_pv, "FLOAT_VECTOR", location=(2400, 350)).outputs["Geometry"]
    sg = store_attr(tree, sg, "hmg_d_r_v", new_rv, "FLOAT_VECTOR", location=(2550, 350)).outputs["Geometry"]
    sg = store_attr(tree, sg, "hmg_d_s_v", new_sv, "FLOAT_VECTOR", location=(2700, 350)).outputs["Geometry"]
    sg = store_attr(tree, sg, "hmg_d_init", value(tree, 1.0).outputs[0], "FLOAT",
                    location=(2850, 200)).outputs["Geometry"]
    link(tree, sg, sim_out.inputs["Geometry"])

    geo = store_attr(tree, geo, A_POFF, new_p, "FLOAT_VECTOR", location=(2400, -200)).outputs["Geometry"]
    geo = store_attr(tree, geo, A_ROFF, new_r, "FLOAT_VECTOR", location=(2550, -200)).outputs["Geometry"]
    geo = store_attr(tree, geo, A_SMUL, new_s, "FLOAT_VECTOR", location=(2700, -200)).outputs["Geometry"]
    h["geo"] = geo
    return _finish(h, w)


def build_push_apart(name, P, falloff_obj):
    """Radial push-apart (from cloner center or an object), evaluated in
    cloner-local space. Pairwise N-body is prohibitively expensive in a node
    graph; radial covers the classic C4D look."""
    h = _base(name, falloff_obj, None)
    tree, gin = h["tree"], h["gin"]
    iface_in(tree, "Radius", "FLOAT", default=P.get("radius", 3.0), min_value=0.01)
    iface_in(tree, "Push Object", "OBJECT")
    iface_in(tree, "Use Object", "BOOLEAN", default=P.get("use_object", False))
    for pname, stype, default in (("Shape", "INT", 3), ("Size", "VECTOR", (2, 2, 2)),
                                  ("Inner", "FLOAT", 0.0), ("Curve", "FLOAT", 0.0),
                                  ("Invert", "BOOLEAN", False)):
        iface_in(tree, pname, stype, default=default)
    w = _apply_falloff(h, falloff_obj)

    pos = add_node(tree, "GeometryNodeInputPosition", (700, 200))
    oinfo = object_info(tree, None, (850, 200))  # RELATIVE: cloner-space
    link(tree, gin.outputs["Push Object"], oinfo.inputs["Object"])
    center = switch(tree, gin.outputs["Use Object"],
                    combine_xyz(tree, value(tree, 0.0).outputs[0],
                                value(tree, 0.0).outputs[0],
                                value(tree, 0.0).outputs[0]).outputs["Vector"],
                    oinfo.outputs["Location"],
                    input_type="VECTOR", location=(1050, 150)).outputs[0]
    to_clone = vmath(tree, "SUBTRACT", pos.outputs["Position"], center, location=(1200, 150))
    dist = vmath(tree, "LENGTH", to_clone.outputs["Vector"], location=(1350, 150))
    dir_l = vmath(tree, "NORMALIZE", to_clone.outputs["Vector"], location=(1350, 300))
    push = math(tree, "MULTIPLY",
                math(tree, "SUBTRACT", value(tree, 1.0).outputs[0],
                     math(tree, "MINIMUM",
                          math(tree, "DIVIDE", dist.outputs["Value"], gin.outputs["Radius"],
                               location=(1500, 150)).outputs[0],
                          value(tree, 1.0).outputs[0], location=(1650, 150)).outputs[0],
                     location=(1800, 150)).outputs[0],
                w, location=(1950, 100))
    off = vmath(tree, "MULTIPLY", dir_l.outputs["Vector"],
                _to_vec(tree, push.outputs[0], (1950, 200)), location=(2100, 200))
    _apply_transforms(h, w, off.outputs["Vector"], None, None, None, None, None)
    return _finish(h, w)


def build_target(name, P, falloff_obj):
    h = _base(name, falloff_obj, None)
    tree, gin = h["tree"], h["gin"]
    iface_in(tree, "Target", "OBJECT")
    iface_in(tree, "Axis", "STRING", default=P.get("axis", "Z"))
    iface_in(tree, "Up Axis", "STRING", default=P.get("up_axis", "Y"))
    for pname, stype, default in (("Shape", "INT", 3), ("Size", "VECTOR", (2, 2, 2)),
                                  ("Inner", "FLOAT", 0.0), ("Curve", "FLOAT", 0.0),
                                  ("Invert", "BOOLEAN", False)):
        iface_in(tree, pname, stype, default=default)
    w = _apply_falloff(h, falloff_obj)

    pos = add_node(tree, "GeometryNodeInputPosition", (700, 200))
    # Object Info with RELATIVE space gives the target in cloner-local space,
    # so no matrix juggling is needed.
    tinfo = object_info(tree, None, (850, 200))
    link(tree, gin.outputs["Target"], tinfo.inputs["Object"])
    dir_l = vmath(tree, "NORMALIZE",
                  vmath(tree, "SUBTRACT", tinfo.outputs["Location"],
                        pos.outputs["Position"], location=(1050, 150)).outputs["Vector"],
                  location=(1200, 150))
    cur = named_attr(tree, A_ROFF, "FLOAT_VECTOR", (1200, -50))
    cur_rot = euler_to_rotation(tree, cur.outputs["Attribute"], (1350, -50))
    aimed = align_to_vector(tree, cur_rot.outputs["Rotation"], dir_l.outputs["Vector"],
                            axis="Z", location=(1500, -50))
    aimed_e = rotation_to_euler(tree, aimed.outputs["Rotation"], (1650, -50))
    blended = vmath(tree, "ADD", cur.outputs["Attribute"],
                    vmath(tree, "MULTIPLY",
                          vmath(tree, "SUBTRACT", aimed_e.outputs["Euler"],
                                cur.outputs["Attribute"], location=(1800, -50)).outputs["Vector"],
                          _to_vec(tree, w, (1800, -200)), location=(1950, -50)).outputs["Vector"],
                    location=(2100, -50))
    geo = store_attr(tree, h["geo"], A_ROFF, blended.outputs["Vector"], "FLOAT_VECTOR",
                     location=(2250, -50)).outputs["Geometry"]
    h["geo"] = geo
    return _finish(h, w)


def build_spline(name, P, falloff_obj):
    h = _base(name, falloff_obj, None)
    tree, gin = h["tree"], h["gin"]
    iface_in(tree, "Spline", "OBJECT")
    iface_in(tree, "Amount", "FLOAT", default=P.get("amount", 1.0))
    iface_in(tree, "Align", "BOOLEAN", default=P.get("align", True))
    for pname, stype, default in (("Shape", "INT", 3), ("Size", "VECTOR", (2, 2, 2)),
                                  ("Inner", "FLOAT", 0.0), ("Curve", "FLOAT", 0.0),
                                  ("Invert", "BOOLEAN", False)):
        iface_in(tree, pname, stype, default=default)
    w = _apply_falloff(h, falloff_obj)

    # RELATIVE object info: spline geometry arrives in cloner-local space,
    # so clone positions compare directly with no matrix juggling.
    sinfo = object_info(tree, None, (700, 200))
    link(tree, gin.outputs["Spline"], sinfo.inputs["Object"])
    res = add_node(tree, "GeometryNodeResampleCurve", (850, 200))
    res.inputs["Mode"].default_value = "Count"
    link(tree, sinfo.outputs["Geometry"], res.inputs["Curve"])
    res.inputs["Count"].default_value = 128
    pos = add_node(tree, "GeometryNodeInputPosition", (700, -100))
    nearest = add_node(tree, "GeometryNodeSampleNearest", (1050, 0))
    link(tree, res.outputs["Curve"], nearest.inputs["Geometry"])
    link(tree, pos.outputs["Position"], nearest.inputs["Sample Position"])
    factor = math(tree, "DIVIDE", nearest.outputs["Index"],
                  value(tree, 127.0).outputs[0], location=(1200, 0))
    samp = add_node(tree, "GeometryNodeSampleCurve", (1350, 0))
    samp.mode = "FACTOR"
    link(tree, res.outputs["Curve"], samp.inputs["Curves"])
    link(tree, factor.outputs[0], samp.inputs["Factor"])
    off = vmath(tree, "MULTIPLY", samp.outputs["Tangent"],
                _to_vec(tree, math(tree, "MULTIPLY", w, gin.outputs["Amount"],
                                   location=(1500, -100)).outputs[0], (1500, -200)),
                location=(1650, -100))
    geo = h["geo"]
    cur = named_attr(tree, A_POFF, "FLOAT_VECTOR", (1650, -250))
    newp = vmath(tree, "ADD", cur.outputs["Attribute"], off.outputs["Vector"],
                 location=(1800, -200))
    geo = store_attr(tree, geo, A_POFF, newp.outputs["Vector"], "FLOAT_VECTOR",
                     location=(1950, -200)).outputs["Geometry"]
    # align rotation to tangent (already cloner-local)
    cur_r = named_attr(tree, A_ROFF, "FLOAT_VECTOR", (1800, 150))
    cur_rot = euler_to_rotation(tree, cur_r.outputs["Attribute"], (1950, 150))
    aimed = align_to_vector(tree, cur_rot.outputs["Rotation"], samp.outputs["Tangent"],
                            axis="Z", location=(2100, 150))
    aimed_e = rotation_to_euler(tree, aimed.outputs["Rotation"], (2250, 150))
    blended = vmath(tree, "ADD", cur_r.outputs["Attribute"],
                    vmath(tree, "MULTIPLY",
                          vmath(tree, "SUBTRACT", aimed_e.outputs["Euler"],
                                cur_r.outputs["Attribute"], location=(2400, 150)).outputs["Vector"],
                          _to_vec(tree, w, (2400, 50)), location=(2550, 150)).outputs["Vector"],
                    location=(2700, 150))
    do_align = switch(tree, gin.outputs["Align"], cur_r.outputs["Attribute"],
                      blended.outputs["Vector"], input_type="VECTOR",
                      location=(2850, 150)).outputs[0]
    geo = store_attr(tree, geo, A_ROFF, do_align, "FLOAT_VECTOR",
                     location=(3000, 150)).outputs["Geometry"]
    h["geo"] = geo
    return _finish(h, w)


def build_time(name, P, falloff_obj):
    h = _base(name, falloff_obj, None)
    tree, gin = h["tree"], h["gin"]
    iface_in(tree, "Offset", "FLOAT", default=P.get("offset", 0.0))
    iface_in(tree, "Stagger", "FLOAT", default=P.get("stagger", 2.0),
             description="Extra frames per clone index")
    for pname, stype, default in (("Shape", "INT", 3), ("Size", "VECTOR", (2, 2, 2)),
                                  ("Inner", "FLOAT", 0.0), ("Curve", "FLOAT", 0.0),
                                  ("Invert", "BOOLEAN", False)):
        iface_in(tree, pname, stype, default=default)
    w = _apply_falloff(h, falloff_obj)
    idx = add_node(tree, "GeometryNodeInputIndex", (700, -300))
    t = math(tree, "MULTIPLY", w,
             math(tree, "ADD", gin.outputs["Offset"],
                  math(tree, "MULTIPLY", idx.outputs["Index"], gin.outputs["Stagger"],
                       location=(850, -300)).outputs[0], location=(1000, -300)).outputs[0],
             location=(1150, -300)).outputs[0]
    _apply_transforms(h, w, None, None, None, None, None, t)
    return _finish(h, w)


BUILDERS = {
    "PLAIN": build_plain,
    "RANDOM": build_random,
    "STEP": build_step,
    "FORMULA": build_formula,
    "SHADER": build_shader,
    "SOUND": build_plain,      # Sound = Plain + baked-sound driver (ops wire it)
    "DELAY": build_delay,
    "PUSH_APART": build_push_apart,
    "TARGET": build_target,
    "SPLINE": build_spline,
    "TIME": build_time,
}

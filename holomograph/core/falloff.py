"""HoloMoGraph - Falloff field.

Builds the HMG_Falloff node group: samples a per-clone weight (0..1) from a
Falloff object's transform, with Cinema 4D-style shapes:
Infinite, Linear, Box, Sphere, Capsule, Cylinder, Tube, Cone, Torus.

The weight is stored to a named point attribute so each effector can carry
its own falloff.
"""
from __future__ import annotations
from .nodes import (
    ng_new, add_node, link, group_node, iface_in, iface_out, io_nodes,
    math, vmath, combine_xyz, separate_xyz, compare, switch, value,
    index_switch, store_attr, named_attr, object_info,
)

GROUP_NAME = "HMG_Falloff"

SHAPES = [
    ("INFINITE", "Infinite"),
    ("LINEAR", "Linear"),
    ("BOX", "Box"),
    ("SPHERE", "Sphere"),
    ("CAPSULE", "Capsule"),
    ("CYLINDER", "Cylinder"),
    ("TUBE", "Tube"),
    ("CONE", "Cone"),
    ("TORUS", "Torus"),
]


def _matrix_multiply(tree, a, b, location):
    n = add_node(tree, "FunctionNodeMatrixMultiply", location)
    link(tree, a, n.inputs[0])
    link(tree, b, n.inputs[1])
    return n


def _matrix_invert(tree, a, location):
    n = add_node(tree, "FunctionNodeInvertMatrix", location)
    link(tree, a, n.inputs[0])
    return n


def _transform_point(tree, matrix, point, location):
    n = add_node(tree, "FunctionNodeTransformPoint", location)
    link(tree, matrix, n.inputs["Transform"])
    link(tree, point, n.inputs["Vector"])
    return n


def _transform_direction(tree, matrix, direction, location):
    n = add_node(tree, "FunctionNodeTransformDirection", location)
    link(tree, matrix, n.inputs["Transform"])
    link(tree, direction, n.inputs["Direction"])
    return n


def build_falloff_group():
    """(Re)build the shared HMG_Falloff node group."""
    tree = ng_new(GROUP_NAME)

    iface_in(tree, "Geometry", "GEOMETRY")
    iface_in(tree, "Cloner", "OBJECT", description="Cloner object (space owner)")
    iface_in(tree, "Falloff", "OBJECT", description="Falloff object (field source)")
    iface_in(tree, "Shape", "INT", default=3, min_value=0, max_value=8)
    iface_in(tree, "Size", "VECTOR", default=(2.0, 2.0, 2.0),
             description="Half-extents / radius in falloff local space")
    iface_in(tree, "Inner", "FLOAT", default=0.0, min_value=0.0, max_value=0.99,
             description="Inner offset: weight stays 1 up to this fraction")
    iface_in(tree, "Curve", "FLOAT", default=0.0, min_value=-0.9, max_value=3.0,
             description="Falloff curve shaping (exponent)")
    iface_in(tree, "Invert", "BOOLEAN", default=False)
    iface_in(tree, "Weight Attr", "STRING", default="hmg_w")
    iface_out(tree, "Geometry", "GEOMETRY")

    gin, gou = io_nodes(tree)
    geo = gin.outputs["Geometry"]

    # --- falloff-local point -------------------------------------------
    # p_fall = Inverse(Inverse(M_cloner) * M_fall) * p_cloner
    info_c = object_info(tree, None, (-500, 300))
    link(tree, gin.outputs["Cloner"], info_c.inputs["Object"])
    info_f = object_info(tree, None, (-500, 100))
    link(tree, gin.outputs["Falloff"], info_f.inputs["Object"])

    m_rel = _matrix_multiply(tree,
                             _matrix_invert(tree, info_c.outputs["Transform"], (-300, 300)).outputs[0],
                             info_f.outputs["Transform"], (-100, 200))
    m_rel_inv = _matrix_invert(tree, m_rel.outputs[0], (100, 200))
    pos = add_node(tree, "GeometryNodeInputPosition", (100, 0))
    p_fall = _transform_point(tree, m_rel_inv.outputs[0], pos.outputs["Position"], (300, 100))

    # q = p_fall / max(Size, eps)
    size = gin.outputs["Size"]
    eps_v = combine_xyz(tree, value(tree, 1e-4, (300, -100)).outputs[0],
                        value(tree, 1e-4, (300, -140)).outputs[0],
                        value(tree, 1e-4, (300, -180)).outputs[0], (450, -140))
    safe_size = vmath(tree, "MAXIMUM", size, eps_v.outputs["Vector"], location=(600, -100))
    q = vmath(tree, "DIVIDE", p_fall.outputs["Vector"], safe_size.outputs["Vector"],
              location=(750, 100))
    qv = q.outputs["Vector"]
    qx = separate_xyz(tree, qv, (900, 100))
    ax = vmath(tree, "ABSOLUTE", qv, location=(900, -100)).outputs["Vector"]

    def _len2(v):
        return vmath(tree, "LENGTH", v, location=(0, 0)).outputs["Value"]

    # --- per-shape weights ----------------------------------------------
    one = value(tree, 1.0)
    zero = value(tree, 0.0)

    # 0 Infinite
    w_inf = one.outputs[0]
    # 1 Linear: full at -Z, zero at +Z
    w_lin = math(tree, "SUBTRACT", value(tree, 0.5).outputs[0],
                 math(tree, "MULTIPLY", qx.outputs["Z"], value(tree, 0.5).outputs[0]).outputs[0],
                 location=(1100, 500))
    w_lin = math(tree, "MINIMUM", math(tree, "MAXIMUM", w_lin.outputs[0], zero.outputs[0]).outputs[0],
                 one.outputs[0], location=(1250, 500)).outputs[0]

    # helper: clamp01(x)
    def clamp01(x, loc):
        return math(tree, "MINIMUM",
                    math(tree, "MAXIMUM", x, zero.outputs[0], location=(loc[0]-140, loc[1])).outputs[0],
                    one.outputs[0], location=loc).outputs[0]

    abs_q = vmath(tree, "ABSOLUTE", qv, location=(1050, 200))
    aq = separate_xyz(tree, abs_q.outputs["Vector"], (1200, 200))
    max_xy = math(tree, "MAXIMUM", aq.outputs["X"], aq.outputs["Y"], location=(1350, 250))
    max_xyz = math(tree, "MAXIMUM", max_xy.outputs[0], aq.outputs["Z"], location=(1500, 250))
    w_box = math(tree, "SUBTRACT", one.outputs[0], clamp01(max_xyz.outputs[0], (1650, 250)),
                 location=(1800, 250)).outputs[0]

    # 3 Sphere
    len_q = vmath(tree, "LENGTH", qv, location=(1350, 100))
    w_sph = math(tree, "SUBTRACT", one.outputs[0], clamp01(len_q.outputs["Value"], (1500, 100)),
                 location=(1650, 100)).outputs[0]

    # 4 Capsule (axis Z, straight section |z| <= 1)
    len_xy = vmath(tree, "LENGTH", combine_xyz(tree, qx.outputs["X"], qx.outputs["Y"],
                                               location=(1350, -50)).outputs["Vector"],
                   location=(1500, -50))
    over = math(tree, "MAXIMUM",
                math(tree, "SUBTRACT", aq.outputs["Z"], one.outputs[0], location=(1350, -150)).outputs[0],
                zero.outputs[0], location=(1500, -150))
    cap_d = vmath(tree, "LENGTH",
                  combine_xyz(tree, len_xy.outputs["Value"], over.outputs[0],
                              location=(1650, -100)).outputs["Vector"],
                  location=(1800, -100))
    w_cap = math(tree, "SUBTRACT", one.outputs[0], clamp01(cap_d.outputs["Value"], (1950, -100)),
                 location=(2100, -100)).outputs[0]

    # 5 Cylinder
    w_cyl = math(tree, "MULTIPLY",
                 math(tree, "SUBTRACT", one.outputs[0], clamp01(len_xy.outputs["Value"], (1650, -250)),
                      location=(1800, -250)).outputs[0],
                 math(tree, "SUBTRACT", one.outputs[0], clamp01(aq.outputs["Z"], (1650, -350)),
                      location=(1800, -350)).outputs[0],
                 location=(1950, -300)).outputs[0]

    # 6 Tube: ring radius 0.65, half-thickness 0.35
    ring = math(tree, "DIVIDE",
                math(tree, "ABSOLUTE",
                     math(tree, "SUBTRACT", len_xy.outputs["Value"], value(tree, 0.65).outputs[0],
                          location=(1650, -500)).outputs[0], location=(1800, -500)).outputs[0],
                value(tree, 0.35).outputs[0], location=(1950, -500))
    w_tube = math(tree, "MULTIPLY",
                  math(tree, "SUBTRACT", one.outputs[0], clamp01(ring.outputs[0], (2100, -500)),
                       location=(2250, -500)).outputs[0],
                  math(tree, "SUBTRACT", one.outputs[0], clamp01(aq.outputs["Z"], (2100, -600)),
                       location=(2250, -600)).outputs[0],
                  location=(2400, -550)).outputs[0]

    # 7 Cone: radius 1 at z=-1, 0 at z=+1
    cone_r = math(tree, "MAXIMUM",
                  math(tree, "MULTIPLY", value(tree, 0.5).outputs[0],
                       math(tree, "SUBTRACT", one.outputs[0], qx.outputs["Z"],
                            location=(1650, -750)).outputs[0], location=(1800, -750)).outputs[0],
                  value(tree, 1e-4).outputs[0], location=(1950, -750))
    cone_d = math(tree, "DIVIDE", len_xy.outputs["Value"], cone_r.outputs[0], location=(2100, -750))
    w_cone = math(tree, "MULTIPLY",
                  math(tree, "SUBTRACT", one.outputs[0], clamp01(cone_d.outputs[0], (2250, -750)),
                       location=(2400, -750)).outputs[0],
                  math(tree, "SUBTRACT", one.outputs[0], clamp01(aq.outputs["Z"], (2250, -850)),
                       location=(2400, -850)).outputs[0],
                  location=(2550, -800)).outputs[0]

    # 8 Torus: ring radius 0.6, tube 0.4
    tor_d = math(tree, "DIVIDE",
                 vmath(tree, "LENGTH",
                       combine_xyz(tree,
                                   math(tree, "SUBTRACT", len_xy.outputs["Value"],
                                        value(tree, 0.6).outputs[0], location=(1650, -1000)).outputs[0],
                                   qx.outputs["Z"], location=(1800, -1000)).outputs["Vector"],
                       location=(1950, -1000)).outputs["Value"],
                 value(tree, 0.4).outputs[0], location=(2100, -1000))
    w_tor = math(tree, "SUBTRACT", one.outputs[0], clamp01(tor_d.outputs[0], (2250, -1000)),
                 location=(2400, -1000)).outputs[0]

    w_shape = index_switch(tree, gin.outputs["Shape"],
                           [w_inf, w_lin, w_box, w_sph, w_cap, w_cyl, w_tube, w_cone, w_tor],
                           location=(2700, 0)).outputs[0]

    # --- shaping: inner offset, curve exponent, invert -------------------
    inner = gin.outputs["Inner"]
    shaped = math(tree, "DIVIDE",
                  math(tree, "SUBTRACT", w_shape, inner, location=(2850, 0)).outputs[0],
                  math(tree, "MAXIMUM",
                       math(tree, "SUBTRACT", one.outputs[0], inner, location=(2850, -120)).outputs[0],
                       value(tree, 1e-4).outputs[0], location=(3000, -120)).outputs[0],
                  location=(3000, 0))
    shaped = clamp01(shaped.outputs[0], (3150, 0))
    curved = math(tree, "POWER", shaped,
                  math(tree, "ADD", one.outputs[0], gin.outputs["Curve"],
                       location=(3150, -150)).outputs[0],
                  location=(3300, 0)).outputs[0]
    final = switch(tree, gin.outputs["Invert"],
                   curved, math(tree, "SUBTRACT", one.outputs[0], curved,
                                location=(3300, 150)).outputs[0],
                   location=(3450, 50)).outputs[0]

    out = store_attr(tree, geo, "__WEIGHT__", final, data_type="FLOAT",
                     location=(3600, 0))
    # rename attribute input via reroute of the string socket
    link(tree, gin.outputs["Weight Attr"], out.inputs["Name"])
    link(tree, out.outputs["Geometry"], gou.inputs["Geometry"])
    return tree

"""HoloMoGraph - RNA properties.

Cloner / Effector / Falloff settings live on the objects themselves so they
are animatable, drivable, and survive file save/load. Any change triggers a
chain rebuild (fast: it only rewrites the node tree, never the scene).
"""
from __future__ import annotations
import bpy


def _refresh_cloner_of(prop_self):
    """Sync the owning cloner chain inputs when a prop changes (live, no rebuild)."""
    try:
        from .core.cloner import sync_from_any
        obj = prop_self.id_data
        sync_from_any(obj)
    except Exception:
        pass


def _upd(self, context):
    _refresh_cloner_of(self)


def _upd_vec(self, context):
    """Vector props rebuild (Blender's Python API doesn't propagate vector
    modifier-input changes live; scalars do). Rebuild is fast (<1s)."""
    try:
        from .core.cloner import build_chain
        obj = self.id_data
        if obj is not None and getattr(obj, "hmg_type", "") == "CLONER":
            build_chain(obj)
    except Exception:
        pass


CLONER_MODES = [
    ("LINEAR", "Linear", "Clones along a line", 0),
    ("RADIAL", "Radial", "Clones on a circle / arc", 1),
    ("GRID", "Grid Array", "3D grid of clones", 2),
    ("HONEYCOMB", "Honeycomb", "Hexagonal lattice", 3),
    ("OBJECT", "Object", "Clones on another object's geometry", 4),
    ("SPLINE", "Spline", "Clones along a curve", 5),
]

EFFECTOR_TYPES = [
    ("PLAIN", "Plain", "Direct transform offsets", 0),
    ("RANDOM", "Random", "Seeded random transforms", 1),
    ("STEP", "Step", "Stepped interpolation across clones", 2),
    ("FORMULA", "Formula", "Wave / math driven offsets", 3),
    ("SHADER", "Shader", "Sample an image like a shader", 4),
    ("SOUND", "Sound", "Driven by baked audio (like Plain + driver)", 5),
    ("DELAY", "Delay", "Spring / smooth follow", 6),
    ("PUSH_APART", "Push Apart", "Radial separation", 7),
    ("TARGET", "Target", "Aim clones at an object", 8),
    ("SPLINE", "Spline", "Deform along a spline", 9),
    ("TIME", "Time", "Per-clone time offset", 10),
]

FALLOFF_SHAPES = [
    ("INFINITE", "Infinite", "", 0),
    ("LINEAR", "Linear", "", 1),
    ("BOX", "Box", "", 2),
    ("SPHERE", "Sphere", "", 3),
    ("CAPSULE", "Capsule", "", 4),
    ("CYLINDER", "Cylinder", "", 5),
    ("TUBE", "Tube", "", 6),
    ("CONE", "Cone", "", 7),
    ("TORUS", "Torus", "", 8),
]


class HMG_ClonerProps(bpy.types.PropertyGroup):
    mode: bpy.props.EnumProperty(name="Mode", items=CLONER_MODES,
                                 default="GRID", update=_upd)
    # counts
    count: bpy.props.IntProperty(name="Count", default=10, min=1, soft_max=1000,
                                 update=_upd)
    count_x: bpy.props.IntProperty(name="Count X", default=5, min=1, update=_upd)
    count_y: bpy.props.IntProperty(name="Count Y", default=5, min=1, update=_upd)
    count_z: bpy.props.IntProperty(name="Count Z", default=1, min=1, update=_upd)
    # linear
    lin_offset: bpy.props.FloatVectorProperty(name="Offset", default=(2.0, 0, 0),
                                              subtype="TRANSLATION", update=_upd_vec)
    # radial
    radius: bpy.props.FloatProperty(name="Radius", default=5.0, min=0.01, update=_upd)
    arc: bpy.props.FloatProperty(name="Arc", default=360.0, min=0.0, max=360.0,
                                 subtype="ANGLE", unit="ROTATION", update=_upd)
    plane: bpy.props.EnumProperty(name="Plane",
                                  items=[("XY", "XY", ""), ("XZ", "XZ", ""), ("YZ", "YZ", "")],
                                  default="XZ", update=_upd)
    # grid
    spacing: bpy.props.FloatVectorProperty(name="Spacing", default=(2.0, 2.0, 2.0),
                                           subtype="TRANSLATION", update=_upd_vec)
    # object mode
    dist_object: bpy.props.PointerProperty(name="Distribution Object",
                                           type=bpy.types.Object, update=_upd)
    dist_mode: bpy.props.EnumProperty(name="Distribution",
                                      items=[("VERTEX", "Vertex", ""),
                                             ("EDGE", "Edge", ""),
                                             ("FACE", "Face", ""),
                                             ("SURFACE", "Surface", "")],
                                      default="VERTEX", update=_upd)
    density: bpy.props.FloatProperty(name="Density", default=10.0, min=0.01, update=_upd)
    seed: bpy.props.IntProperty(name="Seed", default=0, update=_upd)
    # spline mode
    spline_object: bpy.props.PointerProperty(name="Spline", type=bpy.types.Object,
                                             update=_upd)
    align_to_spline: bpy.props.BoolProperty(name="Align to Spline", default=True,
                                            update=_upd)
    # Nested cloner behavior: when this cloner is nested inside another,
    # "Grouped" (default, C4D-style) instances the whole arrangement as one unit.
    # Parent effectors transform each nested instance as a whole.
    group_nested: bpy.props.BoolProperty(
        name="Group Nested Cloner", default=True, update=_upd,
        description="When nested: ON treats the whole arrangement as one grouped "
                    "unit (C4D-style, parent effectors transform each instance as "
                    "a whole). OFF (flattened, coming soon) will let parent "
                    "effectors affect each nested clone individually.")
    # per-step transforms (the C4D P/R/S per clone step)
    step_position: bpy.props.FloatVectorProperty(name="P", default=(2.0, 0, 0),
                                                 subtype="TRANSLATION", update=_upd_vec)
    step_rotation: bpy.props.FloatVectorProperty(name="R", default=(0, 0, 0),
                                                 subtype="EULER", unit="ROTATION", update=_upd_vec)
    step_scale: bpy.props.FloatVectorProperty(name="S", default=(1, 1, 1),
                                              subtype="XYZ", update=_upd_vec)
    # instance source
    instance_object: bpy.props.PointerProperty(name="Instance Object",
                                               type=bpy.types.Object, update=_upd)
    instance_collection: bpy.props.PointerProperty(name="Instance Collection",
                                                   type=bpy.types.Collection, update=_upd)
    pick_instance: bpy.props.BoolProperty(name="Pick Instance", default=False,
                                          description="Pick a different collection child "
                                          "per clone index (MoText / Fracture style)",
                                          update=_upd)
    instance_index_offset: bpy.props.IntProperty(name="Index Offset", default=0,
                                                 update=_upd)
    use_vertex_weights: bpy.props.BoolProperty(name="Vertex Weights", default=False,
                                               description="Modulate effectors by the "
                                               "distribution object's active vertex group",
                                               update=_upd)


class HMG_EffectorProps(bpy.types.PropertyGroup):
    eff_type: bpy.props.EnumProperty(name="Type", items=EFFECTOR_TYPES,
                                     default="PLAIN", update=_upd)
    strength: bpy.props.FloatProperty(name="Strength", default=1.0,
                                      soft_min=-2.0, soft_max=2.0, update=_upd)
    order: bpy.props.IntProperty(name="Order", default=0, update=_upd)
    falloff: bpy.props.PointerProperty(name="Falloff", type=bpy.types.Object,
                                       update=_upd)
    # Built-in proximity/falloff (C4D-style, no separate object needed).
    # If an external Falloff object is linked above, it wins.
    use_builtin_falloff: bpy.props.BoolProperty(
        name="Use Proximity Falloff", default=False, update=_upd,
        description="Enable built-in distance-based falloff (proximity)")
    prox_shape: bpy.props.EnumProperty(name="Shape", items=FALLOFF_SHAPES,
                                       default="SPHERE", update=_upd)
    prox_size: bpy.props.FloatVectorProperty(name="Size", default=(2.0, 2.0, 2.0),
                                             subtype="XYZ", update=_upd)
    prox_inner: bpy.props.FloatProperty(name="Inner", default=0.0,
                                        min=0.0, max=0.99, update=_upd)
    prox_curve: bpy.props.FloatProperty(name="Curve", default=0.0,
                                        min=-0.9, max=3.0, update=_upd)
    prox_invert: bpy.props.BoolProperty(name="Invert", default=False, update=_upd)
    # Built-in time animation (C4D-style: every effector animatable over time)
    use_time_anim: bpy.props.BoolProperty(
        name="Animate Over Time", default=False, update=_upd,
        description="Modulate strength automatically over time")
    time_speed: bpy.props.FloatProperty(name="Speed", default=1.0, update=_upd,
                                        description="Oscillations per second")
    time_phase: bpy.props.FloatProperty(name="Phase", default=0.0, update=_upd,
                                        description="Phase offset in cycles")
    # plain / sound
    position: bpy.props.FloatVectorProperty(name="Position", default=(0, 0, 0),
                                            subtype="TRANSLATION", update=_upd)
    rotation: bpy.props.FloatVectorProperty(name="Rotation", default=(0, 0, 0),
                                            subtype="EULER", unit="ROTATION", update=_upd)
    scale: bpy.props.FloatVectorProperty(name="Scale", default=(1, 1, 1),
                                         subtype="XYZ", update=_upd)
    color: bpy.props.FloatVectorProperty(name="Color", default=(1, 1, 1, 1),
                                         size=4, subtype="COLOR", update=_upd)
    visibility: bpy.props.FloatProperty(name="Visibility", default=1.0,
                                        min=0.0, max=1.0, update=_upd)
    time_offset: bpy.props.FloatProperty(name="Time Offset", default=0.0, update=_upd)
    # random
    seed: bpy.props.IntProperty(name="Seed", default=0, update=_upd)
    position_amt: bpy.props.FloatVectorProperty(name="Position Amt", default=(1, 1, 1),
                                                subtype="TRANSLATION", update=_upd)
    rotation_amt: bpy.props.FloatVectorProperty(name="Rotation Amt", default=(0.5, 0.5, 0.5),
                                                subtype="EULER", unit="ROTATION", update=_upd)
    scale_amt: bpy.props.FloatVectorProperty(name="Scale Amt", default=(0.3, 0.3, 0.3),
                                             subtype="XYZ", update=_upd)
    color_a: bpy.props.FloatVectorProperty(name="Color A", default=(1, 1, 1, 1),
                                           size=4, subtype="COLOR", update=_upd)
    color_b: bpy.props.FloatVectorProperty(name="Color B", default=(1, 0.4, 0.1, 1),
                                           size=4, subtype="COLOR", update=_upd)
    use_color: bpy.props.BoolProperty(name="Randomize Color", default=False, update=_upd)
    # step
    steps: bpy.props.IntProperty(name="Steps", default=5, min=2, update=_upd)
    # formula
    formula_mode: bpy.props.EnumProperty(name="Function",
                                         items=[("SINE", "Sine", ""), ("COSINE", "Cosine", ""),
                                                ("LINEAR", "Linear", ""), ("NOISE", "Noise", "")],
                                         default="SINE", update=_upd)
    amplitude: bpy.props.FloatProperty(name="Amplitude", default=1.0, update=_upd)
    frequency: bpy.props.FloatProperty(name="Frequency", default=1.0, update=_upd)
    phase: bpy.props.FloatProperty(name="Phase", default=0.0, update=_upd)
    speed: bpy.props.FloatProperty(name="Speed", default=1.0, update=_upd)
    target: bpy.props.EnumProperty(name="Target",
                                   items=[("POSITION", "Position", ""), ("ROTATION", "Rotation", ""),
                                          ("SCALE", "Scale", ""), ("COLOR", "Color", "")],
                                   default="POSITION", update=_upd)
    axis: bpy.props.FloatVectorProperty(name="Axis", default=(0, 0, 1),
                                        subtype="DIRECTION", update=_upd)
    # shader
    image: bpy.props.PointerProperty(name="Image", type=bpy.types.Image, update=_upd)
    uv_scale: bpy.props.FloatVectorProperty(name="UV Scale", default=(0.2, 0.2, 0.2),
                                            subtype="XYZ", update=_upd)
    uv_offset: bpy.props.FloatVectorProperty(name="UV Offset", default=(0, 0, 0),
                                             subtype="TRANSLATION", update=_upd)
    shader_pos_amt: bpy.props.FloatProperty(name="Position Amount", default=2.0, update=_upd)
    shader_scl_amt: bpy.props.FloatProperty(name="Scale Amount", default=1.0, update=_upd)
    shader_use_color: bpy.props.BoolProperty(name="Use as Color", default=True, update=_upd)
    # delay
    delay: bpy.props.FloatProperty(name="Delay", default=10.0, min=0.0, update=_upd)
    stiffness: bpy.props.FloatProperty(name="Stiffness", default=1.5,
                                       min=0.01, max=10.0, update=_upd)
    damping: bpy.props.FloatProperty(name="Damping", default=0.85,
                                     min=0.0, max=0.999, update=_upd)
    delay_mode: bpy.props.EnumProperty(name="Mode",
                                       items=[("SMOOTH", "Smooth", ""), ("SPRING", "Spring", "")],
                                       default="SPRING", update=_upd)
    # push apart
    pa_radius: bpy.props.FloatProperty(name="Radius", default=3.0, min=0.01, update=_upd)
    push_object: bpy.props.PointerProperty(name="Push Object", type=bpy.types.Object,
                                           update=_upd)
    pa_use_object: bpy.props.BoolProperty(name="Use Object", default=False, update=_upd)
    # target
    target_object: bpy.props.PointerProperty(name="Target", type=bpy.types.Object,
                                             update=_upd)
    # spline
    spline_object: bpy.props.PointerProperty(name="Spline", type=bpy.types.Object,
                                             update=_upd)
    spline_amount: bpy.props.FloatProperty(name="Amount", default=1.0, update=_upd)
    spline_align: bpy.props.BoolProperty(name="Align", default=True, update=_upd)
    # time
    time_stagger: bpy.props.FloatProperty(name="Stagger", default=2.0,
                                          description="Frames per clone index", update=_upd)
    # sound
    sound_path: bpy.props.StringProperty(name="Sound File", subtype="FILE_PATH", update=_upd)
    sound_baked_prop: bpy.props.StringProperty(name="Baked Property", default="")


class HMG_FalloffProps(bpy.types.PropertyGroup):
    shape: bpy.props.EnumProperty(name="Shape", items=FALLOFF_SHAPES,
                                  default="INFINITE", update=_upd)
    size: bpy.props.FloatVectorProperty(name="Size", default=(2.0, 2.0, 2.0),
                                        subtype="XYZ", update=_upd)
    inner: bpy.props.FloatProperty(name="Inner Offset", default=0.0,
                                   min=0.0, max=0.99, update=_upd)
    curve: bpy.props.FloatProperty(name="Curve", default=0.0,
                                   min=-0.9, max=3.0, update=_upd)
    invert: bpy.props.BoolProperty(name="Invert", default=False, update=_upd)


class HMG_MocapProps(bpy.types.PropertyGroup):
    bvh_path: bpy.props.StringProperty(name="BVH File", subtype="FILE_PATH")
    target_rig: bpy.props.PointerProperty(name="Target Rig", type=bpy.types.Object)
    crowd_count: bpy.props.IntProperty(name="Crowd Count", default=12, min=1, max=500)
    crowd_mode: bpy.props.EnumProperty(name="Time Offset",
                                       items=[("RANDOM", "Random", ""), ("STEP", "Step", "")],
                                       default="RANDOM")
    crowd_min: bpy.props.FloatProperty(name="Min Frames", default=0.0)
    crowd_max: bpy.props.FloatProperty(name="Max Frames", default=60.0)
    crowd_step: bpy.props.FloatProperty(name="Step Frames", default=5.0)


CLASSES = (HMG_ClonerProps, HMG_EffectorProps, HMG_FalloffProps, HMG_MocapProps)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Object.hmg_type = bpy.props.StringProperty(name="HMG Type", default="")
    bpy.types.Object.hmg_cloner = bpy.props.PointerProperty(type=HMG_ClonerProps)
    bpy.types.Object.hmg_effector = bpy.props.PointerProperty(type=HMG_EffectorProps)
    bpy.types.Object.hmg_falloff = bpy.props.PointerProperty(type=HMG_FalloffProps)
    bpy.types.Scene.hmg_mocap = bpy.props.PointerProperty(type=HMG_MocapProps)


def unregister():
    del bpy.types.Scene.hmg_mocap
    del bpy.types.Object.hmg_falloff
    del bpy.types.Object.hmg_effector
    del bpy.types.Object.hmg_cloner
    del bpy.types.Object.hmg_type
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)

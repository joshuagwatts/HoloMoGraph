"""HoloMoGraph - low-level Geometry Nodes construction helpers.

Everything the addon builds is a real Geometry Nodes tree, so clones are
true instances (fast, animatable, renderable) instead of duplicated objects.
These helpers keep the tree-building code terse and consistent.
"""
from __future__ import annotations
import bpy

# ---------------------------------------------------------------------------
# Node-group management
# ---------------------------------------------------------------------------

def ng_new(name: str) -> bpy.types.GeometryNodeTree:
    """Create a fresh geometry node group, deleting any stale one first."""
    old = bpy.data.node_groups.get(name)
    if old is not None:
        bpy.data.node_groups.remove(old)
    return bpy.data.node_groups.new(name, "GeometryNodeTree")


def ng_get(name: str):
    return bpy.data.node_groups.get(name)


def add_node(tree, bl_idname: str, location=(0, 0), label: str | None = None):
    n = tree.nodes.new(bl_idname)
    n.location = location
    if label:
        n.label = label
    return n


def link(tree, from_sock, to_sock):
    tree.links.new(from_sock, to_sock)


def group_node(tree, group: bpy.types.GeometryNodeTree, location=(0, 0), label=None):
    n = add_node(tree, "GeometryNodeGroup", location, label or group.name)
    n.node_tree = group
    return n


# Blender 5.x interface socket identifiers (full type names)
SOCKET_TYPES = {
    "FLOAT": "NodeSocketFloat",
    "INT": "NodeSocketInt",
    "BOOLEAN": "NodeSocketBool",
    "VECTOR": "NodeSocketVector",
    "RGBA": "NodeSocketColor",
    "ROTATION": "NodeSocketRotation",
    "MATRIX": "NodeSocketMatrix",
    "STRING": "NodeSocketString",
    "GEOMETRY": "NodeSocketGeometry",
    "OBJECT": "NodeSocketObject",
    "IMAGE": "NodeSocketImage",
    "COLLECTION": "NodeSocketCollection",
    "MATERIAL": "NodeSocketMaterial",
    "MENU": "NodeSocketMenu",
}


def _resolve_socket_type(socket_type: str) -> str:
    return SOCKET_TYPES.get(socket_type, socket_type)

def iface_in(tree, name: str, socket_type: str, default=None,
             min_value=None, max_value=None, description: str = ""):
    s = tree.interface.new_socket(name, in_out="INPUT", socket_type=_resolve_socket_type(socket_type))
    if description:
        s.description = description
    if default is not None:
        try:
            s.default_value = default
        except Exception:
            pass
    for attr, val in (("min_value", min_value), ("max_value", max_value)):
        if val is not None:
            try:
                setattr(s, attr, val)
            except Exception:
                pass
    return s


def iface_out(tree, name: str, socket_type: str, description: str = ""):
    s = tree.interface.new_socket(name, in_out="OUTPUT", socket_type=_resolve_socket_type(socket_type))
    if description:
        s.description = description
    return s


def io_nodes(tree):
    """Return (group_input, group_output), creating them if missing."""
    gin = gou = None
    for n in tree.nodes:
        if n.bl_idname == "NodeGroupInput":
            gin = n
        elif n.bl_idname == "NodeGroupOutput":
            gou = n
    if gin is None:
        gin = add_node(tree, "NodeGroupInput", (-600, 0))
    if gou is None:
        gou = add_node(tree, "NodeGroupOutput", (900, 0))
    return gin, gou


# ---------------------------------------------------------------------------
# Common math nodes
# ---------------------------------------------------------------------------

def math(tree, operation: str, a=None, b=None, c=None, location=(0, 0), label=None,
         clamp=False):
    n = add_node(tree, "ShaderNodeMath", location, label or operation)
    n.operation = operation
    n.use_clamp = clamp
    if a is not None:
        link(tree, a, n.inputs[0])
    if b is not None:
        link(tree, b, n.inputs[1])
    if c is not None:
        link(tree, c, n.inputs[2])
    return n


def vmath(tree, operation: str, a=None, b=None, c=None, d=None, location=(0, 0),
          label=None):
    n = add_node(tree, "ShaderNodeVectorMath", location, label or operation)
    n.operation = operation
    if a is not None:
        link(tree, a, n.inputs[0])
    if b is not None:
        link(tree, b, n.inputs[1])
    if c is not None:
        link(tree, c, n.inputs[2])
    if d is not None:
        link(tree, d, n.inputs[3])
    return n


def combine_xyz(tree, x=None, y=None, z=None, location=(0, 0)):
    n = add_node(tree, "ShaderNodeCombineXYZ", location)
    if x is not None:
        link(tree, x, n.inputs["X"])
    if y is not None:
        link(tree, y, n.inputs["Y"])
    if z is not None:
        link(tree, z, n.inputs["Z"])
    return n


def separate_xyz(tree, vec=None, location=(0, 0)):
    n = add_node(tree, "ShaderNodeSeparateXYZ", location)
    if vec is not None:
        link(tree, vec, n.inputs["Vector"])
    return n


def compare(tree, a=None, b=None, operation="GREATER_THAN", data_type="FLOAT",
            location=(0, 0), c=None):
    n = add_node(tree, "FunctionNodeCompare", location)
    n.operation = operation
    n.data_type = data_type
    if a is not None:
        link(tree, a, n.inputs["A"])
    if b is not None:
        link(tree, b, n.inputs["B"])
    if c is not None:
        link(tree, c, n.inputs["C"])
    return n


def switch(tree, condition, false_val, true_val, input_type="FLOAT", location=(0, 0)):
    n = add_node(tree, "GeometryNodeSwitch", location)
    n.input_type = input_type
    link(tree, condition, n.inputs["Switch"])
    link(tree, false_val, n.inputs["False"])
    link(tree, true_val, n.inputs["True"])
    return n


def mix_float(tree, factor, a, b, location=(0, 0)):
    n = add_node(tree, "ShaderNodeMix", location)
    n.data_type = "FLOAT"
    try:
        n.clamp_factor = True
    except Exception:
        pass
    link(tree, factor, n.inputs["Factor"])
    link(tree, a, n.inputs["A"])
    link(tree, b, n.inputs["B"])
    return n


def value(tree, v: float, location=(0, 0)):
    n = add_node(tree, "ShaderNodeValue", location)
    n.outputs[0].default_value = v
    return n


def boolean_math(tree, operation, a, b, location=(0, 0)):
    n = add_node(tree, "FunctionNodeBooleanMath", location)
    n.operation = operation
    link(tree, a, n.inputs[0])
    link(tree, b, n.inputs[1])
    return n


def index_switch(tree, index_sock, values, location=(0, 0), data_type="FLOAT"):
    """Index Switch node with `values` list of output sockets."""
    n = add_node(tree, "GeometryNodeIndexSwitch", location)
    # Blender 5.0 defaults items to GEOMETRY; set the data type explicitly
    # (5.2 infers from links, but explicit works on both).
    try:
        n.data_type = data_type
    except Exception:
        pass
    try:
        n.index_switch_items.clear()
        for _ in values:
            n.index_switch_items.new()
    except Exception:
        pass
    link(tree, index_sock, n.inputs["Index"])
    for i, v in enumerate(values):
        try:
            link(tree, v, n.inputs[i + 1])
        except Exception:
            pass
    return n


def store_attr(tree, geometry, name: str, value_sock, data_type="FLOAT",
               domain="POINT", location=(0, 0), selection=None):
    n = add_node(tree, "GeometryNodeStoreNamedAttribute", location)
    n.data_type = data_type
    n.domain = domain
    link(tree, geometry, n.inputs["Geometry"])
    if selection is not None:
        link(tree, selection, n.inputs["Selection"])
    n.inputs["Name"].default_value = name
    link(tree, value_sock, n.inputs["Value"])
    return n


def named_attr(tree, name: str, data_type="FLOAT", location=(0, 0)):
    n = add_node(tree, "GeometryNodeInputNamedAttribute", location)
    n.data_type = data_type
    n.inputs["Name"].default_value = name
    return n


def random_value(tree, data_type: str, min_sock, max_sock, id_sock, location=(0, 0)):
    n = add_node(tree, "FunctionNodeRandomValue", location)
    n.data_type = data_type
    link(tree, min_sock, n.inputs["Min"])
    link(tree, max_sock, n.inputs["Max"])
    link(tree, id_sock, n.inputs["ID"])
    return n


def object_info(tree, obj, location=(0, 0), as_instance=False,
                 transform_space="RELATIVE"):
    n = add_node(tree, "GeometryNodeObjectInfo", location)
    n.inputs["Object"].default_value = obj
    try:
        n.transform_space = transform_space
    except Exception:
        pass
    if as_instance:
        try:
            n.inputs["As Instance"].default_value = True
        except Exception:
            pass
    return n


def euler_to_rotation(tree, euler_sock, location=(0, 0)):
    n = add_node(tree, "FunctionNodeEulerToRotation", location)
    link(tree, euler_sock, n.inputs["Euler"])
    return n


def rotation_to_euler(tree, rot_sock, location=(0, 0)):
    n = add_node(tree, "FunctionNodeRotationToEuler", location)
    link(tree, rot_sock, n.inputs["Rotation"])
    return n


def align_to_vector(tree, rotation_sock, vector_sock, axis="Z", factor=None,
                    location=(0, 0)):
    n = add_node(tree, "FunctionNodeAlignEulerToVector", location)
    n.axis = axis
    link(tree, rotation_sock, n.inputs["Rotation"])
    link(tree, vector_sock, n.inputs["Vector"])
    if factor is not None:
        link(tree, factor, n.inputs["Factor"])
    return n

"""HoloMoGraph - Cinema 4D-style MoGraph for Blender.

Cloner (Linear / Radial / Grid / Honeycomb / Object / Spline, nestable),
11 effectors (Plain, Random, Step, Formula, Shader, Sound, Delay,
Push Apart, Target, Spline, Time) with real 3D falloff fields, MoText,
Fracture, Tracer, and mocap tools (BVH import, retarget, crowds).

Everything is built on Geometry Nodes, so clones are true instances.
"""
bl_info = {
    "name": "HoloMoGraph",
    "author": "Holowatts",
    "version": (1, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > HoloMoGraph",
    "description": "C4D-style MoGraph: Cloner, Effectors, Falloffs, MoText, "
                   "Fracture, Tracer + mocap crowd tools",
    "category": "Object",
}

from . import props
from .ops import cloner_ops, tools_ops, mocap_ops
from .ui import panels


def register():
    props.register()
    cloner_ops.register()
    tools_ops.register()
    mocap_ops.register()
    panels.register()


def unregister():
    panels.unregister()
    mocap_ops.unregister()
    tools_ops.unregister()
    cloner_ops.unregister()
    props.unregister()


if __name__ == "__main__":
    register()

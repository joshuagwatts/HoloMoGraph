# Changelog

## v1.0.0 — 2026-10-07

First release. The whole thing, done right.

**Cloner**
- 6 modes: Linear, Radial, Grid, Honeycomb, Object, Spline
- Per-step position / rotation / scale offsets
- Instance object or collection
- Nested cloner-in-cloner (parent instances the full child arrangement, C4D-style), with build-time cycle detection

**Effectors (11)**
- Plain, Random, Step, Formula, Shader, Sound, Delay, Push Apart, Target, Spline, Time
- Every effector carries its own falloff object (9 shapes)
- Keyframable/driven strength + params, mirrored as live drivers onto the node graph
- Delay uses a real simulation zone (smooth + spring modes)

**Tools**
- MoText, Fracture, Tracer, Sound Bake (WAV → f-curves)

**Mocap**
- BVH import (hierarchy + quaternion-correct rotations)
- Constraint retarget with auto bone-name matching, baked to action
- Crowd builder with staggered time offsets

**Verified** — 23/23 headless checks on Blender 5.2.2 LTS.

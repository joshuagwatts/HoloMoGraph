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

## v1.0.1 — 2026-10-08

Blender 5.0 compatibility fixes (reported by Joshua — thank you for the screenshot):
- Cloner object is now a single-vertex mesh instead of an empty: Blender 5.0
  cannot put modifiers on empties at all (`modifiers.new()` returns None).
  The modifier output replaces the vertex, so it never renders.
- Index Switch node: set `data_type` explicitly — 5.0 defaults items to
  GEOMETRY, which broke all falloff shapes (constant 0.5 weights).
- `ensure_modifier` now raises a clear error instead of `AttributeError: NoneType`.

## v1.0.2 — 2026-10-08

C4D-style hierarchy nesting:
- Parenting a cloner under another cloner (Blender object hierarchy, like dragging
  in C4D's Object Manager) now nests it — the parent clones the child's full
  arrangement. The sidebar shows which cloners are nested and offers a rebuild.
- Explicit Instance Object still wins if both are set.
- Build-time cycle detection covers hierarchy + instance_object chains.

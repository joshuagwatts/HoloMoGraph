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

## v1.1.0 — 2026-10-08

Live-update architecture (no more rebuilds):
- Cloner is now a visible wireframe octahedron gizmo (selectable in viewport).
- All 6 modes live in one static node tree with an Index Switch — changing the
  Mode is a live input change, no rebuild.
- Every cloner param is a modifier input (Properties > Modifiers tab) — tweak
  live, C4D-style. Sidebar props sync to the modifier.
- Effector param changes sync live to node inputs (no rebuild). Structural
  changes (add/remove/reorder effectors) still rebuild.
- Blender 5.2 modifier input API fix (mod.properties.inputs.<id>.value).

## v1.2.0 — 2026-10-08

C4D-style workflow:
- ONE "Add HoloCloner" button (was six per-mode buttons). Add it, parent
  objects under it, change mode in the Modifiers tab.
- Parenting is LIVE: drag an object under the cloner and it clones instantly —
  no more manual Rebuild button. A depsgraph handler watches for hierarchy
  changes and rebuilds automatically.

## v1.2.1 — 2026-10-08

Bug fixes:
- Plain effector default falloff is now INFINITE (was SPHERE) — position/rotation
  apply uniformly instead of a confusing gradient. C4D-style.
- Linear cloner mode now uses PStep (per-step position) — was using a separate
  "Offset" and PStep did nothing. PStep defaults to (2,0,0).

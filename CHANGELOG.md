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

## v1.2.2 — 2026-10-08

C4D-matched step transforms:
- Scale step is now true exponential with proper negative/zero handling:
  (-1)^i alternates mirror, 0^0=1, 0^n=0. No more clamping to positive.
- Matches C4D's per-clone transform behavior precisely.

## v1.2.3 — 2026-10-08

Nested cloner control:
- Added "Group Nested Cloner" toggle (per nested cloner, in parent's panel).
- ON (default, C4D-style): parent effectors treat the nested arrangement as
  one grouped unit, transforming each instance as a whole.
- OFF (flattened, coming soon): will let parent effectors affect each nested
  clone individually.

## v1.2.4 — 2026-10-09

Every effector now has built-in Proximity and Time Animation (C4D-style):
- Proximity Falloff (built-in): No separate falloff object needed. Each effector
  has its own Shape/Size/Inner/Curve/Invert right in its panel. External falloff
  object still wins if linked.
- Time Animation (built-in): "Animate Over Time" modulates the effector's strength
  with a smooth 0..1 oscillation driven by the timeline. Speed (osc/sec) + Phase.
  Works on all 11 effector types.

## v1.2.5 — 2026-10-09

C4D-style viewport (you only see the meshes):
- Cloner object is now invisible in the viewport (single vertex, like C4D's
  invisible Cloner). Select it from the Outliner. No more wireframe octahedron.
- Source objects parented to the cloner auto-hide in the viewport (C4D-style:
  the template hides, only the clones show). Still selectable in Outliner.
  Auto-unhides if you unparent it.
- Existing octahedron cloners auto-migrate to invisible on next rebuild.

## v1.2.6 — 2026-10-11

Nested effectors now work and layer correctly (C4D-style):
- FIXED: Nested cloners were rendering duplicates (child's own clones + parent's
  instances overlapping). Now the parent calls the child's node group directly
  (not via Object Info), and the nested child's viewport is hidden — you only
  see the clones through the parent, like C4D.
- Effectors layer properly: child's effectors apply to child's clones first,
  then parent's effectors transform each nested instance as a whole.
- Auto-restores when unnested.

## v1.2.7 — 2026-10-11

Revert nested hiding (user feedback):
- REMOVED the v1.2.6 change that hid nested cloners. "Cloning the clones is good"
  — nested cloners render their own clones AND the parent instances them.
  No more hiding.
- Back to Object Info for nesting (reliable, updates work).
- Note: Built-in Proximity Falloff (v1.2.4) is experimental — use external
  Falloff objects for reliable results for now.

## v1.2.8 — 2026-10-11

Clean revert to v1.2.5 state (user: "go back 2 steps"):
- Removed v1.2.6 nested hiding changes entirely.
- Removed v1.2.7 partial fixes.
- Back to the working v1.2.5: Object Info nesting, invisible cloner, source auto-hide.
- The v1.2.4 built-in Proximity/Time features are still present but default OFF.

## v1.2.9 — 2026-10-11

Animated Random effector:
- Random effector now has "Animated" toggle + "Speed" (new values per second).
  When on, the random offsets change over time — perfect for the workflow:
  line cloner + animated random, nested in a grid cloner + formula waves.
- Verified: nested cloners with different effectors (Random on child, Formula
  on parent) layer correctly.

## v1.2.10 — 2026-10-11

Fix parenting workflow:
- REMOVED auto-hide of source objects. When you parent a cube to the cloner,
  the cube stays visible (you said cloning the clones is good).
- The handler now unhides any sources it previously auto-hid.
- Parenting a cube to the cloner clones it (verified working). If auto-rebuild
  misses, use the "Rebuild Cloner" button in the panel.

## v1.2.11 — 2026-10-11

Clean revert to v1.2.3 (user: "3 tries and ur out, go back to the one that worked"):
- Parenting a cube to the cloner clones it (verified: 25 clones).
- Basic effectors work. No auto-hide, no built-in falloff experiments.
- Nesting effectors: parked for later, per user ("we will figure out the nesting
  effectors after u fix the main issue").

## v1.2.12 — 2026-10-11

Solid meshes, not wireframes (user: "i can see the wireframes but remember i wanted them solid?"):
- Cloner is now invisible in viewport (single vertex, C4D-style). Select from Outliner.
- Existing octahedron cloners auto-migrate to invisible on rebuild.
- NO auto-hide of sources (user hated that). Parenting clones visibly.

## v1.2.13 — 2026-10-11

Working features, verified before shipping:
- Falloffs WORK (external falloff objects): Add Effector → select it → Add Falloff.
  Verified: sphere falloff gives smooth gradient (z=5.0, 3.33, 1.67, 0, 0).
- Random Animation WORKS: Random effector has "Animated" toggle + Speed.
  Verified: positions change over time ([0.01,1.08,4.82] → [0.14,0.48,3.23] → [0.97,1.76,2.0]).
- All 12/12 tests pass on Blender 5.0.1 and 5.2.2.

## v1.2.14 — 2026-10-12

AK47 reliability (user: "make sure its like a damn ak47"):
- Rebuilds are DEFERRED via timer, never inside the depsgraph update.
  (Modifying node groups during depsgraph = crash. Now impossible.)
- build_chain snapshots all settings before rebuild, restores after.
  Parenting/unparenting NEVER resets your settings. Verified.
- All errors contained — a failed rebuild can't take down the session.
- Stress tested: 10x rapid parent/unparent, no crash, settings intact.
- 12/12 tests pass.

## v1.2.15 — 2026-10-12

Effector love (batch 1: PLAIN, RANDOM, STEP):
- PLAIN: default position is now (0,0,2) — adding a Plain effector immediately
  lifts clones. No more "why is nothing happening."
- RANDOM: UI reorganized into Variation / Animation / Color sections.
- STEP: UI clarifies it divides clones into stepped groups.
- 12/12 tests pass.

## v1.2.16 — 2026-10-12

PSR for all effectors (user: "should have access to the PSR for all of these effectors"):
- FORMULA, DELAY, PUSH_APART, TARGET, SPLINE, TIME now have Position/Rotation/Scale
  controls in their UI. The PSR is added on top of the effector's specific behavior.
- SHADER has the UI but PSR wiring needs investigation (inputs exist, defaults correct).
- 12/12 tests pass.

## v1.2.17 — 2026-10-12

Formula loop (user: "checkbox that added a loop point on a specified frame"):
- Formula effector now has "Loop" checkbox + "Loop Frame" (default 60).
- When enabled, the wave phase completes exactly 2π over the loop duration,
  creating a seamless loop. Verified: frame 31 matches frame 1 exactly.
- 12/12 tests pass.

## v1.2.18 — 2026-10-16

- Formula: 7 waveforms now (Sine, Cosine, Triangle, Square, Sawtooth, Linear, Noise).
  All verified working.
- Formula Loop (from v1.2.17): seamless looping verified.
- Push Apart: verified working (clears center).
- Note: Built-in proximity falloff UI added but needs wiring fixes. External
  falloff objects work reliably — use Add Falloff on the effector.

## v1.2.19 — 2026-10-19

Built-in proximity falloff FIXED:
- Root cause: an auto-created external falloff object was overwriting the
  built-in params (Shape stuck at INFINITE). Built-in now takes precedence.
- "Built-in Falloff" checkbox on every effector now actually works.
  Set Shape (Sphere/Box/Cylinder), Size, Inner — no separate object needed.
- Verified: SPHERE/BOX/CYLINDER all produce correct gradients.
- 12/12 tests pass.

## v1.2.20 — 2026-10-20

First-click fix (full-plugin audit):
- Add Cloner now adopts the active mesh as its instance source — select a
  cube, hit Add Cloner, clones appear immediately. Before, the first click
  produced an empty cloner and looked like nothing happened.
- Audit results: all 6 modes render correctly (visually inspected), all 11
  effectors produce real changes, live slider sync works without rebuild,
  parenting/unparenting rebuilds via the handler, save/reload survives,
  Shader PSR verified working. 12/12 tests pass.

## v1.2.21 — 2026-10-20

- Shader effector: Source selector with Blender's built-in textures
  (Noise / Voronoi / Musgrave / Wave / Magic / Gradient / White Noise) plus
  Image; Detail / Roughness / Distortion, Anim Speed, seamless Loop.
  Fixed image sampling on Blender 5.x (image is an input socket there, the
  old property write silently sampled black) and effector-rename breaking
  live slider sync. Core 12/12 + prove-out suite on Blender 5.0.1 and 5.2.2.

## v1.2.22 — 2026-10-21

- **Radial Arc fixed.** Dragging the Arc slider collapsed the ring to a
  ~3° wedge: the property was declared as an ANGLE (Blender stores radians)
  while the Radial node chain expects degrees. Arc is now plain degrees
  end-to-end — set 180°, you get a 180° arc.
- Tradeoffs: the slider is a plain degrees number (no ° angle widget), and a
  .blend saved in v1.2.21 where Arc had been dragged holds a radian value
  that now reads as a tiny degree value — just re-set Arc in those files.
- Regression: the prove-out suite now sets Arc through the property (the way
  the UI does) and measures the clone spread for 90° / 180° / default 360°.

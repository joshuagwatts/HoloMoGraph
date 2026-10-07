# HoloMoGraph

**Cinema 4D-style MoGraph for Blender — done right.**

Cloner (all 6 modes, nested cloner-in-cloner), 11 effectors with per-effector falloffs, and a mocap toolkit — all built on real Geometry Nodes, so everything is true instancing, fully animatable, and renders in Eevee/Cycles.

## Install

1. Download `HoloMoGraph.zip` from [Releases](https://github.com/joshuagwatts/HoloMoGraph/releases).
2. Blender → **Edit → Preferences → Add-ons → Install from Disk**, pick the zip.
3. Enable **HoloMoGraph**. A **MoGraph** tab appears in the 3D Viewport sidebar (N-panel).

Requires Blender 4.2+ (verified on 5.2 LTS).

## Cloner

**Add → MoGraph → Cloner**, or the sidebar button. Six modes:

| Mode | What it does |
|---|---|
| Linear | Copies along an axis with per-step position / rotation / scale |
| Radial | Ring / arc placement with angular steps |
| Grid | 3D grid with per-axis counts and spacing |
| Honeycomb | Hex-packed grid (C4D's honeycomb) |
| Object | Scatter on a target mesh (verts / edges / faces) |
| Spline | Distribute along a curve, optional tangent alignment |

Set the **Instance Object** (or Collection) to clone. **Cloner-in-cloner nesting works** — drop another cloner in as the instance object and each parent clone carries the full child arrangement. Cycles are caught at build time.

## Effectors

Select a cloner → **Add Effector**. Every effector gets its own **falloff object** (9 shapes: infinite, sphere, box, capsule, cone, torus, linear, radial, spline) and a **strength** that can be keyframed or driven — animated props are mirrored onto the node graph as live drivers, no rebuilds while scrubbing.

| Effector | C4D equivalent |
|---|---|
| Plain | Offset / rotate / scale / color / visibility / time |
| Random | Per-clone seeded randomization |
| Step | Stepped interpolation between two states |
| Formula | Expression-driven (per-clone index spline) |
| Shader | Image-texture-driven offsets |
| Sound | Audio amplitude → effector (bake a WAV to f-curves) |
| Delay | Spring / smooth trailing via simulation zone |
| Push Apart | Clone separation |
| Target | Aim clones at an object |
| Spline | Offset along a spline |
| Time | Time offset per clone |

## Tools

- **MoText** — text objects as cloners, per-letter control
- **Fracture** — smash a mesh into a cloner (cell fracture if the addon is enabled)
- **Tracer** — bake clone trajectories to curves over a frame range
- **Sound Bake** — bake WAV amplitude to an effector's strength

## Mocap

- **Import BVH** — proper hierarchy + quaternion-correct rotation import
- **Retarget** — constraint-based bone mapping with auto name matching, baked to action
- **Crowd Builder** — duplicate a baked rig into N staggered crowd members

## How it works

Everything is generated Geometry Nodes — no fake parenting tricks. Each cloner builds a node chain: **mode points → per-step transforms → effector stack → instancing**. Effectors accumulate into per-point attributes, so they layer exactly like C4D. The Delay effector uses a real simulation zone; nested cloners instance the child's evaluated result.

## Verified

23 automated headless checks on Blender 5.2.2 LTS — all cloner modes, falloff weights, effector builds, instance evaluation, nested cloners, delay trailing, driver mirroring, sound bake, tracer, fracture, BVH import, retarget, crowd. See `tests/`.

## License

MIT — do whatever you want with it.

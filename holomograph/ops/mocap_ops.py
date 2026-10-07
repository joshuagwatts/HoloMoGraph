"""HoloMoGraph - mocap tools: BVH import, constraint retarget + bake, crowds.

The retarget path is deliberately boring and reliable: COPY_TRANSFORMS
constraints from the source (BVH) bones onto the target rig, then an NLA
bake with visual keying. No hand-rolled matrix math to get subtly wrong.

Crowds: duplicate the rig (linked) N times, stagger each copy's action in
NLA - the mocap equivalent of the Time effector.
"""
from __future__ import annotations
import random
import bpy


def _norm(name: str) -> str:
    n = name.lower()
    for tok in ("mixamorig", "mixamo", "_", "-", " ", ".", ":"):
        n = n.replace(tok, "")
    for side in ("l", "r", "left", "right"):
        if n.endswith(side):
            n = n[: -len(side)]
    return n


class HMG_OT_mocap_import(bpy.types.Operator):
    bl_idname = "hmg.mocap_import"
    bl_label = "Import BVH"
    bl_options = {"REGISTER", "UNDO"}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        if not self.filepath:
            self.report({"ERROR"}, "No BVH file chosen")
            return {"CANCELLED"}
        before = set(bpy.data.objects)
        try:
            bpy.ops.import_anim.bvh(filepath=self.filepath)
        except Exception as e:
            self.report({"ERROR"}, f"BVH import failed: {e}")
            return {"CANCELLED"}
        new = [o for o in bpy.data.objects if o not in before]
        arm = next((o for o in new if o.type == "ARMATURE"), None)
        if arm is None:
            self.report({"WARNING"}, "Imported, but no armature found")
            return {"CANCELLED"}
        arm.name = "HMG Mocap Source"
        self.report({"INFO"}, f"BVH imported: {arm.name} ({len(arm.data.bones)} bones)")
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class HMG_OT_mocap_retarget(bpy.types.Operator):
    bl_idname = "hmg.mocap_retarget"
    bl_label = "Retarget to Rig"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Map BVH bones onto the target rig and bake the motion"

    source_rig: bpy.props.StringProperty(name="Source Rig")
    target_rig: bpy.props.StringProperty(name="Target Rig")
    frame_start: bpy.props.IntProperty(name="Start", default=1)
    frame_end: bpy.props.IntProperty(name="End", default=250)

    def execute(self, context):
        src = bpy.data.objects.get(self.source_rig)
        dst = bpy.data.objects.get(self.target_rig)
        if src is None or dst is None or src.type != "ARMATURE" or dst.type != "ARMATURE":
            self.report({"ERROR"}, "Pick a source (BVH) rig and a target rig")
            return {"CANCELLED"}
        # auto bone map by normalized name
        dst_names = {_norm(b.name): b.name for b in dst.data.bones}
        bmap = {}
        for sb in src.data.bones:
            key = _norm(sb.name)
            if key in dst_names:
                bmap[sb.name] = dst_names[key]
        if not bmap:
            self.report({"ERROR"}, "No bones matched - check naming")
            return {"CANCELLED"}
        # constraints
        cons = []
        for sname, dname in bmap.items():
            pb = dst.pose.bones.get(dname)
            if pb is None:
                continue
            c = pb.constraints.new("COPY_TRANSFORMS")
            c.target = src
            c.subtarget = sname
            c.mix_mode = "REPLACE"
            cons.append((pb, c))
        scene = context.scene
        cur = scene.frame_current
        try:
            context.view_layer.objects.active = dst
            bpy.ops.object.mode_set(mode="POSE")
            bpy.ops.nla.bake(
                frame_start=self.frame_start, frame_end=self.frame_end,
                step=1, only_selected=False, visual_keying=True,
                clear_constraints=False, clear_parents=False,
                use_current_action=False, bake_types={"POSE"},
            )
        except Exception as e:
            self.report({"ERROR"}, f"Bake failed: {e}")
            return {"CANCELLED"}
        finally:
            for pb, c in cons:
                try:
                    pb.constraints.remove(c)
                except Exception:
                    pass
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass
            scene.frame_set(cur)
        # stash the baked action name on the rig for the crowd tool
        act = getattr(dst.animation_data, "action", None)
        dst["hmg_mocap_action"] = act.name if act else ""
        self.report({"INFO"}, f"Retargeted {len(bmap)} bones -> {dst.name}")
        return {"FINISHED"}


class HMG_OT_mocap_crowd(bpy.types.Operator):
    bl_idname = "hmg.mocap_crowd"
    bl_label = "Build Mocap Crowd"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Duplicate a baked rig into a staggered mocap crowd"

    rig: bpy.props.StringProperty(name="Rig")
    count: bpy.props.IntProperty(name="Count", default=12, min=1, max=500)
    mode: bpy.props.EnumProperty(name="Time Offset",
                                 items=[("RANDOM", "Random", ""), ("STEP", "Step", "")],
                                 default="RANDOM")
    min_frames: bpy.props.FloatProperty(name="Min Frames", default=0.0)
    max_frames: bpy.props.FloatProperty(name="Max Frames", default=60.0)
    step_frames: bpy.props.FloatProperty(name="Step Frames", default=5.0)
    spread: bpy.props.FloatProperty(name="Spread", default=6.0, min=0.0)

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        rig = bpy.data.objects.get(self.rig) if self.rig else context.active_object
        if rig is None or rig.type != "ARMATURE":
            self.report({"ERROR"}, "Select the baked armature")
            return {"CANCELLED"}
        act_name = rig.get("hmg_mocap_action", "")
        act = bpy.data.actions.get(act_name) if act_name else None
        if act is None and rig.animation_data:
            act = rig.animation_data.action
        if act is None:
            self.report({"ERROR"}, "Rig has no baked action - retarget first")
            return {"CANCELLED"}
        # duplicate rig + its mesh children
        members = [rig] + [c for c in rig.children_recursive if c.type == "MESH"]
        empty = bpy.data.objects.new(f"HMG Crowd {rig.name}", None)
        context.scene.collection.objects.link(empty)
        rng = random.Random(1234)
        for i in range(self.count):
            dup_map = {}
            for m in members:
                d = m.copy()
                d.data = m.data  # linked
                context.scene.collection.objects.link(d)
                dup_map[m] = d
            drig = dup_map[rig]
            drig.parent = empty
            for m, d in dup_map.items():
                if m == rig:
                    continue
                if m.parent in dup_map:
                    d.parent = dup_map[m.parent]
                arm_mod = next((md for md in d.modifiers if md.type == "ARMATURE"), None)
                if arm_mod:
                    arm_mod.object = drig
            # ring placement
            ang = (i / max(self.count, 1)) * 6.2831853
            r = self.spread * (0.5 + 0.5 * rng.random())
            drig.location = (r * __import__("math").cos(ang), r * __import__("math").sin(ang), 0)
            # stagger the action in NLA
            if self.mode == "RANDOM":
                off = rng.uniform(self.min_frames, self.max_frames)
            else:
                off = i * self.step_frames
            if drig.animation_data is None:
                drig.animation_data_create()
            track = drig.animation_data.nla_tracks.new()
            track.name = "HMG Mocap"
            strip = track.strips.new(act.name, int(off), act)
            strip.name = f"mocap+{off:.0f}"
            drig["hmg_time_offset"] = off
        self.report({"INFO"}, f"Crowd: {self.count} copies of {rig.name}")
        return {"FINISHED"}


CLASSES = (
    HMG_OT_mocap_import,
    HMG_OT_mocap_retarget,
    HMG_OT_mocap_crowd,
)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)

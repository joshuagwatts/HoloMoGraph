"""HoloMoGraph - N-panel UI."""
from __future__ import annotations
import bpy


class HMG_PT_main(bpy.types.Panel):
    bl_label = "HoloMoGraph"
    bl_idname = "HMG_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "HoloMoGraph"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.label(text="Cloners")
        row = col.row(align=True)
        for mode, label in (("GRID", "Grid"), ("LINEAR", "Linear"), ("RADIAL", "Radial")):
            op = row.operator("hmg.add_cloner", text=label)
            op.mode = mode
        row = col.row(align=True)
        for mode, label in (("HONEYCOMB", "Honey"), ("OBJECT", "Object"), ("SPLINE", "Spline")):
            op = row.operator("hmg.add_cloner", text=label)
            op.mode = mode
        col.separator()
        col.label(text="Tools")
        col.operator("hmg.motext", text="MoText")
        col.operator("hmg.fracture", text="Fracture")
        col.operator("hmg.tracer", text="Tracer")


class HMG_PT_cloner(bpy.types.Panel):
    bl_label = "Cloner"
    bl_idname = "HMG_PT_cloner"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "HoloMoGraph"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.hmg_type == "CLONER"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        cp = obj.hmg_cloner
        layout.prop(cp, "mode", text="Mode")
        box = layout.box()
        if cp.mode in ("LINEAR", "RADIAL", "SPLINE"):
            box.prop(cp, "count")
        if cp.mode == "LINEAR":
            box.prop(cp, "lin_offset")
        elif cp.mode == "RADIAL":
            box.prop(cp, "radius")
            box.prop(cp, "arc")
            box.prop(cp, "plane")
        elif cp.mode in ("GRID", "HONEYCOMB"):
            row = box.row(align=True)
            row.prop(cp, "count_x")
            row.prop(cp, "count_y")
            if cp.mode == "GRID":
                row.prop(cp, "count_z")
            box.prop(cp, "spacing")
        elif cp.mode == "OBJECT":
            box.prop(cp, "dist_object")
            box.prop(cp, "dist_mode")
            if cp.dist_mode == "SURFACE":
                box.prop(cp, "density")
                box.prop(cp, "seed")
        elif cp.mode == "SPLINE":
            box.prop(cp, "spline_object")
            box.prop(cp, "align_to_spline")
        box.separator()
        box.label(text="Per-Step Transform")
        box.prop(cp, "step_position")
        box.prop(cp, "step_rotation")
        box.prop(cp, "step_scale")
        layout.separator()
        layout.label(text="Instance Source")
        layout.prop(cp, "instance_object")
        layout.prop(cp, "instance_collection")
        if cp.instance_collection:
            layout.prop(cp, "pick_instance")
            layout.prop(cp, "instance_index_offset")
        # C4D-style hierarchy nesting hint
        nested = [c for c in obj.children if getattr(c, "hmg_type", "") == "CLONER"]
        if nested:
            layout.label(text=f"Nesting: {', '.join(c.name for c in nested)}",
                         icon="LINKED")
        else:
            layout.label(text="Tip: parent a cloner under this one (C4D-style)",
                         icon="INFO")
        layout.separator()
        layout.label(text="Effectors")
        effs = sorted([c for c in obj.children if c.hmg_type == "EFFECTOR"],
                      key=lambda o: (o.hmg_effector.order, o.name))
        for e in effs:
            row = layout.row(align=True)
            row.label(text=f"{e.hmg_effector.order}: {e.name}")
            op = row.operator("hmg.effector_move", text="^")
            op.direction = -1
            op = row.operator("hmg.effector_move", text="v")
            op.direction = 1
        row = layout.row(align=True)
        op = row.operator("hmg.add_effector", text="Plain")
        op.eff_type = "PLAIN"
        op = row.operator("hmg.add_effector", text="Random")
        op.eff_type = "RANDOM"
        row = layout.row(align=True)
        op = row.operator("hmg.add_effector", text="Delay")
        op.eff_type = "DELAY"
        op = row.operator("hmg.add_effector", text="Formula")
        op.eff_type = "FORMULA"
        row = layout.row(align=True)
        op = row.operator("hmg.add_effector", text="Target")
        op.eff_type = "TARGET"
        op = row.operator("hmg.add_effector", text="Spline")
        op.eff_type = "SPLINE"
        row = layout.row(align=True)
        op = row.operator("hmg.add_effector", text="Shader")
        op.eff_type = "SHADER"
        op = row.operator("hmg.add_effector", text="Sound")
        op.eff_type = "SOUND"
        row = layout.row(align=True)
        op = row.operator("hmg.add_effector", text="Step")
        op.eff_type = "STEP"
        op = row.operator("hmg.add_effector", text="Time")
        op.eff_type = "TIME"
        row = layout.row(align=True)
        op = row.operator("hmg.add_effector", text="Push Apart")
        op.eff_type = "PUSH_APART"
        layout.separator()
        layout.operator("hmg.refresh", text="Rebuild Cloner")


class HMG_PT_effector(bpy.types.Panel):
    bl_label = "Effector"
    bl_idname = "HMG_PT_effector"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "HoloMoGraph"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.hmg_type == "EFFECTOR"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        ep = obj.hmg_effector
        layout.prop(ep, "eff_type", text="Type")
        layout.prop(ep, "strength")
        layout.prop(ep, "order")
        layout.prop(ep, "falloff")
        t = ep.eff_type
        box = layout.box()
        if t in ("PLAIN", "SOUND", "STEP"):
            box.prop(ep, "position")
            box.prop(ep, "rotation")
            box.prop(ep, "scale")
        if t in ("PLAIN", "SOUND"):
            box.prop(ep, "color")
            box.prop(ep, "visibility")
            box.prop(ep, "time_offset")
        if t == "RANDOM":
            box.prop(ep, "seed")
            box.prop(ep, "position_amt")
            box.prop(ep, "rotation_amt")
            box.prop(ep, "scale_amt")
            box.prop(ep, "use_color")
            if ep.use_color:
                box.prop(ep, "color_a")
                box.prop(ep, "color_b")
        if t == "STEP":
            box.prop(ep, "steps")
        if t == "FORMULA":
            box.prop(ep, "formula_mode")
            box.prop(ep, "target")
            box.prop(ep, "axis")
            box.prop(ep, "amplitude")
            box.prop(ep, "frequency")
            box.prop(ep, "phase")
            box.prop(ep, "speed")
        if t == "SHADER":
            box.prop(ep, "image")
            box.prop(ep, "uv_scale")
            box.prop(ep, "uv_offset")
            box.prop(ep, "shader_pos_amt")
            box.prop(ep, "shader_scl_amt")
            box.prop(ep, "shader_use_color")
        if t == "DELAY":
            box.prop(ep, "delay_mode")
            box.prop(ep, "delay")
            box.prop(ep, "stiffness")
            box.prop(ep, "damping")
        if t == "PUSH_APART":
            box.prop(ep, "pa_use_object")
            if ep.pa_use_object:
                box.prop(ep, "push_object")
            box.prop(ep, "pa_radius")
        if t == "TARGET":
            box.prop(ep, "target_object")
        if t == "SPLINE":
            box.prop(ep, "spline_object")
            box.prop(ep, "spline_amount")
            box.prop(ep, "spline_align")
        if t == "TIME":
            box.prop(ep, "time_offset")
            box.prop(ep, "time_stagger")
        if t == "SOUND":
            box.prop(ep, "sound_path")
            box.operator("hmg.sound_bake", text="Bake Sound")
        layout.separator()
        row = layout.row(align=True)
        row.operator("hmg.add_falloff", text="Add Falloff")
        row.operator("hmg.remove", text="Delete Effector")


class HMG_PT_falloff(bpy.types.Panel):
    bl_label = "Falloff"
    bl_idname = "HMG_PT_falloff"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "HoloMoGraph"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.hmg_type == "FALLOFF"

    def draw(self, context):
        layout = self.layout
        fp = context.active_object.hmg_falloff
        layout.prop(fp, "shape")
        layout.prop(fp, "size")
        layout.prop(fp, "inner")
        layout.prop(fp, "curve")
        layout.prop(fp, "invert")
        layout.separator()
        layout.operator("hmg.remove", text="Delete Falloff")


class HMG_PT_mocap(bpy.types.Panel):
    bl_label = "Mocap"
    bl_idname = "HMG_PT_mocap"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "HoloMoGraph"

    def draw(self, context):
        layout = self.layout
        mp = context.scene.hmg_mocap
        layout.operator("hmg.mocap_import", text="Import BVH")
        layout.separator()
        layout.label(text="Retarget")
        layout.prop(mp, "target_rig")
        row = layout.row(align=True)
        op = row.operator("hmg.mocap_retarget", text="Retarget to Rig")
        op.target_rig = mp.target_rig.name if mp.target_rig else ""
        layout.separator()
        layout.label(text="Crowd")
        layout.prop(mp, "crowd_count")
        layout.prop(mp, "crowd_mode")
        if mp.crowd_mode == "RANDOM":
            layout.prop(mp, "crowd_min")
            layout.prop(mp, "crowd_max")
        else:
            layout.prop(mp, "crowd_step")
        row = layout.row(align=True)
        op = row.operator("hmg.mocap_crowd", text="Build Crowd")
        op.rig = (bpy.context.active_object.name
                  if bpy.context.active_object and bpy.context.active_object.type == "ARMATURE"
                  else "")
        op.count = mp.crowd_count
        op.mode = mp.crowd_mode
        op.min_frames = mp.crowd_min
        op.max_frames = mp.crowd_max
        op.step_frames = mp.crowd_step


CLASSES = (
    HMG_PT_main,
    HMG_PT_cloner,
    HMG_PT_effector,
    HMG_PT_falloff,
    HMG_PT_mocap,
)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)

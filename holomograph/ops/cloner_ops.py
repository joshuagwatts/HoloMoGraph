"""HoloMoGraph - operators: cloners, effectors, falloffs."""
from __future__ import annotations
import bpy
from ..props import CLONER_MODES, EFFECTOR_TYPES


def _active_cloner(context):
    obj = context.active_object
    if obj is None:
        return None
    if obj.hmg_type == "CLONER":
        return obj
    p = obj.parent
    while p is not None:
        if p.hmg_type == "CLONER":
            return p
        p = p.parent
    return None


class HMG_OT_add_cloner(bpy.types.Operator):
    bl_idname = "hmg.add_cloner"
    bl_label = "Add Cloner"
    bl_options = {"REGISTER", "UNDO"}

    mode: bpy.props.EnumProperty(name="Mode", items=CLONER_MODES, default="GRID")

    def execute(self, context):
        from ..core.cloner import build_chain, new_cloner_object
        obj = new_cloner_object(context, "HMG Cloner")
        obj.hmg_cloner.mode = self.mode
        build_chain(obj)
        return {"FINISHED"}

    def invoke(self, context, event):
        return self.execute(context)


class HMG_OT_add_effector(bpy.types.Operator):
    bl_idname = "hmg.add_effector"
    bl_label = "Add Effector"
    bl_options = {"REGISTER", "UNDO"}

    eff_type: bpy.props.EnumProperty(name="Type", items=EFFECTOR_TYPES, default="PLAIN")

    @classmethod
    def poll(cls, context):
        return _active_cloner(context) is not None

    def execute(self, context):
        from ..core.cloner import build_chain
        cloner = _active_cloner(context)
        bpy.ops.object.empty_add(type="SPHERE")
        obj = context.active_object
        obj.name = f"HMG {self.eff_type.title()} Effector"
        obj.hmg_type = "EFFECTOR"
        obj.hmg_effector.eff_type = self.eff_type
        obj.parent = cloner
        existing = [c for c in cloner.children if c.hmg_type == "EFFECTOR"]
        obj.hmg_effector.order = len(existing)
        # every effector gets a falloff child by default (C4D-style)
        bpy.ops.object.empty_add(type="CUBE")
        fo = context.active_object
        fo.name = f"HMG Falloff ({obj.name})"
        fo.hmg_type = "FALLOFF"
        fo.parent = obj
        fo.scale = (2, 2, 2)
        obj.hmg_effector.falloff = fo
        context.view_layer.objects.active = obj
        build_chain(cloner)
        return {"FINISHED"}

    def invoke(self, context, event):
        return self.execute(context)


class HMG_OT_add_falloff(bpy.types.Operator):
    bl_idname = "hmg.add_falloff"
    bl_label = "Add Falloff"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.hmg_type in ("EFFECTOR", "CLONER")

    def execute(self, context):
        from ..core.cloner import build_chain
        obj = context.active_object
        eff = obj if obj.hmg_type == "EFFECTOR" else None
        if eff is None:
            effs = [c for c in obj.children if c.hmg_type == "EFFECTOR"]
            eff = effs[0] if effs else None
        if eff is None:
            self.report({"WARNING"}, "Add an effector first")
            return {"CANCELLED"}
        bpy.ops.object.empty_add(type="CUBE")
        fo = context.active_object
        fo.name = "HMG Falloff"
        fo.hmg_type = "FALLOFF"
        fo.parent = eff
        fo.scale = (2, 2, 2)
        eff.hmg_effector.falloff = fo
        build_chain(_active_cloner(context))
        return {"FINISHED"}


class HMG_OT_refresh(bpy.types.Operator):
    bl_idname = "hmg.refresh"
    bl_label = "Rebuild Cloner"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_cloner(context) is not None

    def execute(self, context):
        from ..core.cloner import build_chain
        build_chain(_active_cloner(context))
        self.report({"INFO"}, "Cloner rebuilt")
        return {"FINISHED"}


class HMG_OT_effector_move(bpy.types.Operator):
    bl_idname = "hmg.effector_move"
    bl_label = "Move Effector"
    bl_options = {"REGISTER", "UNDO"}

    direction: bpy.props.IntProperty(default=1)  # +1 down, -1 up

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.hmg_type == "EFFECTOR"

    def execute(self, context):
        from ..core.cloner import build_chain
        obj = context.active_object
        obj.hmg_effector.order += self.direction
        build_chain(_active_cloner(context))
        return {"FINISHED"}


class HMG_OT_remove_hmg(bpy.types.Operator):
    bl_idname = "hmg.remove"
    bl_label = "Remove"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.hmg_type in ("EFFECTOR", "FALLOFF")

    def execute(self, context):
        from ..core.cloner import build_chain
        obj = context.active_object
        cloner = _active_cloner(context)
        bpy.data.objects.remove(obj, do_unlink=True)
        if cloner:
            build_chain(cloner)
        return {"FINISHED"}


CLASSES = (
    HMG_OT_add_cloner,
    HMG_OT_add_effector,
    HMG_OT_add_falloff,
    HMG_OT_refresh,
    HMG_OT_effector_move,
    HMG_OT_remove_hmg,
)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)

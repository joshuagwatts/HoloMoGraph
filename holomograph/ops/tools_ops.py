"""HoloMoGraph - creative tools: MoText, Fracture, Tracer, Sound bake."""
from __future__ import annotations
import bpy
from mathutils import Vector, Matrix


def _pivot_of(obj) -> Vector:
    ws = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    mn = Vector((min(v.x for v in ws), min(v.y for v in ws), min(v.z for v in ws)))
    mx = Vector((max(v.x for v in ws), max(v.y for v in ws), max(v.z for v in ws)))
    return (mn + mx) * 0.5


def _center_piece_on_pivot(piece, pivot: Vector):
    """Rebase a piece so its local origin sits at its pivot.

    With Collection Info 'Reset Children', the cloner then places each piece
    exactly on its pivot point."""
    me = piece.data
    me.transform(Matrix.Translation(-pivot))
    me.update()
    piece.location = pivot


def _pieces_to_cloner(context, pieces, name: str):
    """Shared MoText/Fracture finish: collection + pivot points + cloner."""
    from ..core.cloner import build_chain
    pieces = sorted(pieces, key=lambda o: (_pivot_of(o).x, _pivot_of(o).y))
    col = bpy.data.collections.new(f"HMG {name} Pieces")
    context.scene.collection.children.link(col)
    pivots = []
    for p in pieces:
        piv = _pivot_of(p)
        _center_piece_on_pivot(p, piv)
        for c in list(p.users_collection):
            c.objects.unlink(p)
        col.objects.link(p)
        pivots.append(piv)
    mesh = bpy.data.meshes.new(f"HMG {name} Pivots")
    mesh.from_pydata([tuple(v) for v in pivots], [], [])
    mesh.update()
    pobj = bpy.data.objects.new(f"HMG {name} Pivots", mesh)
    context.scene.collection.objects.link(pobj)

    bpy.ops.object.empty_add(type="PLAIN_AXES")
    cl = context.active_object
    cl.name = f"HMG {name} Cloner"
    cl.hmg_type = "CLONER"
    cp = cl.hmg_cloner
    cp.mode = "OBJECT"
    cp.dist_object = pobj
    cp.dist_mode = "VERTEX"
    cp.instance_collection = col
    cp.pick_instance = True
    build_chain(cl)
    return cl


class HMG_OT_motext(bpy.types.Operator):
    bl_idname = "hmg.motext"
    bl_label = "MoText from String"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Split text into per-character clones (C4D MoText style)"

    text: bpy.props.StringProperty(name="Text", default="HOLOWATTS")
    size: bpy.props.FloatProperty(name="Size", default=1.0, min=0.01)
    extrude: bpy.props.FloatProperty(name="Extrude", default=0.15, min=0.0)
    bevel_depth: bpy.props.FloatProperty(name="Bevel", default=0.01, min=0.0)

    def execute(self, context):
        bpy.ops.object.text_add()
        tobj = context.active_object
        tcu = tobj.data
        tcu.body = self.text or "A"
        tcu.size = self.size
        tcu.extrude = self.extrude
        tcu.bevel_depth = self.bevel_depth
        bpy.ops.object.convert(target="MESH")
        mobj = context.active_object
        # separate into per-character islands
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.separate(type="LOOSE")
        bpy.ops.object.mode_set(mode="OBJECT")
        pieces = [o for o in context.selected_objects if o.type == "MESH"]
        pieces = [p for p in pieces if len(p.data.vertices) > 0]
        if not pieces:
            self.report({"WARNING"}, "No characters produced geometry")
            return {"CANCELLED"}
        cl = _pieces_to_cloner(context, pieces, f"MoText {self.text[:10]}")
        self.report({"INFO"}, f"MoText: {len(pieces)} characters -> {cl.name}")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class HMG_OT_fracture(bpy.types.Operator):
    bl_idname = "hmg.fracture"
    bl_label = "Fracture to Cloner"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Shatter a mesh into cloner pieces (C4D Fracture style)"

    use_cell_fracture: bpy.props.BoolProperty(
        name="Voronoi (Cell Fracture)", default=True,
        description="Use the Cell Fracture addon when available, else loose parts")

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        src = context.active_object
        # duplicate source
        bpy.ops.object.duplicate()
        dup = context.active_object
        pieces = []
        if self.use_cell_fracture:
            try:
                bpy.ops.object.add_fracture_cell_objects(use_recursive=False)
                pieces = [o for o in context.selected_objects if o != dup]
                bpy.data.objects.remove(dup, do_unlink=True)
            except Exception:
                pieces = []
        if not pieces:
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.mesh.separate(type="LOOSE")
            bpy.ops.object.mode_set(mode="OBJECT")
            pieces = [o for o in context.selected_objects if o.type == "MESH"]
        pieces = [p for p in pieces if len(p.data.vertices) > 0]
        if not pieces:
            self.report({"WARNING"}, "Fracture produced no pieces")
            return {"CANCELLED"}
        cl = _pieces_to_cloner(context, pieces, f"Fracture {src.name}")
        self.report({"INFO"}, f"Fracture: {len(pieces)} pieces -> {cl.name}")
        return {"FINISHED"}


class HMG_OT_tracer(bpy.types.Operator):
    bl_idname = "hmg.tracer"
    bl_label = "Trace Clones (Tracer)"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Bake clone trajectories to curves over the frame range"

    frame_start: bpy.props.IntProperty(name="Start", default=1)
    frame_end: bpy.props.IntProperty(name="End", default=100)
    max_clones: bpy.props.IntProperty(name="Max Clones", default=100, min=1, max=2000)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.hmg_type == "CLONER"

    def execute(self, context):
        cloner = context.active_object
        scene = context.scene
        if self.frame_start == 1 and self.frame_end == 100:
            self.frame_start, self.frame_end = scene.frame_start, scene.frame_end
        deps = context.evaluated_depsgraph_get()
        tracks: list[list[Vector]] = []
        cur_frame = scene.frame_current
        try:
            for f in range(self.frame_start, self.frame_end + 1):
                scene.frame_set(f)
                deps.update()
                mats = []
                for inst in deps.object_instances:
                    if not inst.is_instance:
                        continue
                    par = inst.parent
                    hit = (par is not None and par.original == cloner)
                    if hit:
                        mats.append(inst.matrix_world.translation.copy())
                        if len(mats) >= self.max_clones:
                            break
                while len(tracks) < len(mats):
                    tracks.append([])
                for i, m in enumerate(mats):
                    tracks[i].append(m)
        finally:
            scene.frame_set(cur_frame)

        if not tracks:
            self.report({"WARNING"}, "No clone instances found - is the cloner instancing?")
            return {"CANCELLED"}
        cu = bpy.data.curves.new(f"HMG Trace {cloner.name}", type="CURVE")
        cu.dimensions = "3D"
        ob = bpy.data.objects.new(f"HMG Trace {cloner.name}", cu)
        context.scene.collection.objects.link(ob)
        for track in tracks:
            if len(track) < 2:
                continue
            sp = cu.splines.new("POLY")
            sp.points.add(len(track) - 1)
            for pt, v in zip(sp.points, track):
                pt.co = (v.x, v.y, v.z, 1.0)
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        context.view_layer.objects.active = ob
        self.report({"INFO"}, f"Tracer: {len(tracks)} paths baked")
        return {"FINISHED"}


class HMG_OT_sound_bake(bpy.types.Operator):
    bl_idname = "hmg.sound_bake"
    bl_label = "Bake Sound to Effector"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Analyze audio (WAV) and drive this Sound effector's strength"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.hmg_type == "EFFECTOR"
                and obj.hmg_effector.eff_type == "SOUND")

    def execute(self, context):
        import wave
        import numpy as np
        eff = context.active_object
        p = eff.hmg_effector
        path = bpy.path.abspath(p.sound_path)
        try:
            w = wave.open(path, "rb")
        except Exception as e:
            self.report({"ERROR"}, f"Cannot open WAV: {e}")
            return {"CANCELLED"}
        n = w.getnframes()
        ch = w.getnchannels()
        sr = w.getframerate()
        raw = w.readframes(n)
        w.close()
        if n == 0:
            self.report({"ERROR"}, "Empty audio file")
            return {"CANCELLED"}
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        samples = samples.reshape(-1, ch).mean(axis=1) / 32768.0
        scene = context.scene
        fps = scene.render.fps / max(scene.render.fps_base, 1e-6)
        prop = "hmg_sound"
        eff[prop] = 0.0
        cur = scene.frame_current
        try:
            for f in range(scene.frame_start, scene.frame_end + 1):
                t0 = (f - scene.frame_start) / fps
                i0 = int(t0 * sr)
                i1 = int((t0 + 1.0 / fps) * sr)
                seg = samples[max(i0, 0):max(i1, i0 + 1)]
                rms = float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0
                eff[prop] = rms * 4.0
                eff.keyframe_insert(data_path=f'["{prop}"]', frame=f)
        finally:
            scene.frame_set(cur)
        # drive strength from the baked property
        try:
            eff.hmg_effector.driver_remove("strength")
        except Exception:
            pass
        drv = eff.hmg_effector.driver_add("strength").driver
        drv.type = "AVERAGE"
        var = drv.variables.new()
        var.name = "snd"
        var.type = "SINGLE_PROP"
        var.targets[0].id = eff
        var.targets[0].data_path = f'["{prop}"]'
        from ..core.cloner import build_chain
        par = eff.parent
        while par is not None and par.hmg_type != "CLONER":
            par = par.parent
        if par is not None:
            build_chain(par)  # mirrors the driver onto the node input
        self.report({"INFO"}, f"Sound baked: {path}")
        return {"FINISHED"}


CLASSES = (
    HMG_OT_motext,
    HMG_OT_fracture,
    HMG_OT_tracer,
    HMG_OT_sound_bake,
)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)

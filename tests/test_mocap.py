import bpy, sys, traceback
sys.path.insert(0, "/home/hatch/workspace/HoloMoGraph")
import holomograph
holomograph.register()
from holomograph.core.cloner import build_chain

def _clean():
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)

def _mats(cloner):
    deps = bpy.context.evaluated_depsgraph_get(); deps.update()
    out = []
    for inst in deps.object_instances:
        if not inst.is_instance: continue
        par = inst.parent
        if par is not None and par.original == cloner:
            out.append(inst.matrix_world.translation.copy())
    return out

# 1. delay actually trails an animated plain offset
_clean()
bpy.ops.mesh.primitive_cube_add(); cube = bpy.context.active_object
bpy.ops.hmg.add_cloner(mode="LINEAR")
cl = bpy.context.active_object
cl.hmg_cloner.count = 2; cl.hmg_cloner.instance_object = cube
bpy.ops.hmg.add_effector(eff_type="PLAIN")
plain = bpy.context.active_object
plain.hmg_effector.position = (0, 0, 0)
plain.hmg_effector.keyframe_insert(data_path="position", frame=1)
plain.hmg_effector.position = (0, 0, 10)
plain.hmg_effector.keyframe_insert(data_path="position", frame=10)
bpy.ops.hmg.add_effector(eff_type="DELAY")
delay_eff = bpy.context.active_object
# remove falloff -> infinite, both points get equal delay
bpy.data.objects.remove(delay_eff.hmg_effector.falloff, do_unlink=True)
bpy.context.view_layer.objects.active = cl
build_chain(cl)
sc = bpy.context.scene
sc.frame_set(1); _mats(cl)
sc.frame_set(10)
def _xz(c):
    return sorted((round(m.x,1), round(m.z,2)) for m in _mats(c))
got = _xz(cl)
print("delay trail check f10 (x,z):", got)
# spring tracks targets (10, 5); key check is mid-ramp lag at f5
sc.frame_set(5)
got5 = _xz(cl)
print("delay trail check f5 (x,z):", got5)
# no-delay baseline at f5 would be (0,5.0),(2,2.5); delay must lag behind
assert got5[0][1] < 5.0 and got5[1][1] < 2.5, f"delay not trailing at f5: {got5}"
assert got5[0][1] > 0.5, "delay did not move"
print("PASS delay trails")

# 2. falloff deleted -> infinite falloff, still builds
_clean()
bpy.ops.mesh.primitive_cube_add(); cube = bpy.context.active_object
bpy.ops.hmg.add_cloner(mode="GRID")
cl = bpy.context.active_object
cl.hmg_cloner.count_x = 2; cl.hmg_cloner.count_y = 2
cl.hmg_cloner.instance_object = cube
bpy.ops.hmg.add_effector(eff_type="RANDOM")
eff = bpy.context.active_object
fo = eff.hmg_effector.falloff
bpy.data.objects.remove(fo, do_unlink=True)
bpy.context.view_layer.objects.active = cl
build_chain(cl)
mats = _mats(cl)
assert len(mats) == 4
print("PASS missing falloff")

# 3. mocap: BVH import with a synthetic file
bvh = """HIERARCHY
ROOT Hips
{
 OFFSET 0.00 0.00 0.00
 CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
 JOINT Spine
 {
  OFFSET 0.00 10.00 0.00
  CHANNELS 3 Zrotation Xrotation Yrotation
  End Site
  {
   OFFSET 0.00 10.00 0.00
  }
 }
}
MOTION
Frames: 3
Frame Time: 0.033333
0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
1.0 0.0 0.0 0.0 10.0 0.0 0.0 5.0 0.0
2.0 0.0 0.0 0.0 20.0 0.0 0.0 10.0 0.0
"""
open("/tmp/hmg_test.bvh", "w").write(bvh)
_clean()
bpy.ops.hmg.mocap_import(filepath="/tmp/hmg_test.bvh")
arm = bpy.context.active_object
assert arm.type == "ARMATURE" and len(arm.data.bones) == 2, f"bones: {[b.name for b in arm.data.bones]}"
assert arm.animation_data is not None
print("PASS bvh import:", [b.name for b in arm.data.bones])

# 4. retarget: source -> target with matching names
adata = bpy.data.armatures.new("TargetData")
tgt = bpy.data.objects.new("Target", adata)
bpy.context.scene.collection.objects.link(tgt)
bpy.context.view_layer.objects.active = tgt
bpy.ops.object.mode_set(mode="EDIT")
for b in ["Hips", "Spine"]:
    eb = adata.edit_bones.new(b)
    eb.head = (0, 0, 0); eb.tail = (0, 1, 0)
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.hmg.mocap_retarget(source_rig=arm.name, target_rig=tgt.name)
assert tgt.animation_data is not None
print("PASS retarget")

# 5. crowd builder from the imported action
_clean()
bpy.ops.hmg.mocap_import(filepath="/tmp/hmg_test.bvh")
src = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(); cube = bpy.context.active_object
bpy.context.view_layer.objects.active = src
bpy.ops.hmg.mocap_crowd(rig=src.name, count=4)
crowd = [o for o in bpy.context.scene.objects
         if o.type == "ARMATURE" and o.name.startswith(src.name)]
assert len(crowd) == 5, f"crowd rigs: {len(crowd)}"  # original + 4 dups
dups = [o for o in crowd if o != src]
assert all(o.parent and "Crowd" in o.parent.name for o in dups), "dups not parented"
assert all(o.animation_data and o.animation_data.action for o in dups), "dups lost action"
print("PASS crowd:", len(dups))
print("ALL PASS")

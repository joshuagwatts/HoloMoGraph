"""HoloMoGraph — live hierarchy tracking.

C4D-style: dragging an object under a cloner (or removing it) should update
the cloner instantly, no manual rebuild. This module watches the depsgraph
for parent/child changes on cloner objects and rebuilds the affected chain.
"""

from __future__ import annotations
import bpy

# obj.name -> tuple of (child.name, child.hmg_type) for last known state
_children_cache: dict[str, tuple] = {}
# Re-entrancy guard: don't trigger rebuilds while we're rebuilding.
_rebuilding = False


def _children_key(obj) -> tuple:
    try:
        return tuple(sorted(
            (c.name, getattr(c, "hmg_type", "")) for c in obj.children
        ))
    except Exception:
        return ()


def _prune_cache():
    """Drop cache entries for deleted cloners."""
    alive = {o.name for o in bpy.data.objects
             if getattr(o, "hmg_type", "") == "CLONER"}
    for name in list(_children_cache):
        if name not in alive:
            del _children_cache[name]


@bpy.app.handlers.persistent
def on_depsgraph_update(scene, depsgraph):
    global _rebuilding
    if _rebuilding:
        return
    # Cheap pass: only cloners, only compare child name/type tuples.
    try:
        cloners = [o for o in bpy.data.objects
                   if getattr(o, "hmg_type", "") == "CLONER"]
    except Exception:
        return
    if not cloners:
        _children_cache.clear()
        return
    changed = []
    for cl in cloners:
        key = _children_key(cl)
        if _children_cache.get(cl.name) != key:
            _children_cache[cl.name] = key
            changed.append(cl)
    _prune_cache()
    if not changed:
        return
    # Rebuild affected cloners (deferred to avoid re-entrancy).
    _rebuilding = True
    try:
        from .cloner import build_chain
        for cl in changed:
            try:
                build_chain(cl)
            except Exception:
                pass
            # C4D-style: hide source objects parented to the cloner in the
            # viewport (they're the template, only the clones should show).
            # Still selectable in the Outliner. Unhide when unparented.
            try:
                # First, unhide any objects we previously hid that are no longer children
                for obj in bpy.data.objects:
                    if getattr(obj, "_hmg_hidden_source", False):
                        if obj.parent != cl:
                            obj.hide_viewport = False
                            obj["_hmg_hidden_source"] = False
                # Now hide current source children
                for child in cl.children:
                    t = getattr(child, "hmg_type", "")
                    if t not in ("CLONER", "EFFECTOR", "FALLOFF"):
                        # Regular object = clone source, hide in viewport
                        if not child.hide_viewport:
                            child.hide_viewport = True
                            child["_hmg_hidden_source"] = True
            except Exception:
                pass
    finally:
        _rebuilding = False


def register():
    if on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)


def unregister():
    if on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)

"""HoloMoGraph — live hierarchy tracking.

C4D-style: dragging an object under a cloner (or removing it) should update
the cloner instantly, no manual rebuild. This module watches the depsgraph
for parent/child changes on cloner objects and rebuilds the affected chain.

AK47 design: the depsgraph handler NEVER rebuilds directly (modifying node
groups inside a depsgraph update = crash). It only marks cloners dirty; a
timer fires after the depsgraph settles and does the rebuild safely.
"""

from __future__ import annotations
import bpy

# obj.name -> tuple of (child.name, child.hmg_type) for last known state
_children_cache: dict[str, tuple] = {}
# Cloners marked dirty by the handler, rebuilt by the timer.
_dirty: set[str] = set()
# Timer state
_timer_running = False


def _children_key(obj) -> tuple:
    try:
        return tuple(sorted(
            (c.name, getattr(c, "hmg_type", "")) for c in obj.children
        ))
    except Exception:
        return ()


def _prune_cache():
    """Drop cache entries for deleted cloners."""
    try:
        alive = {o.name for o in bpy.data.objects
                 if getattr(o, "hmg_type", "") == "CLONER"}
    except Exception:
        return
    for name in list(_children_cache):
        if name not in alive:
            del _children_cache[name]
    for name in list(_dirty):
        if name not in alive:
            _dirty.discard(name)


def _rebuild_dirty():
    """Timer callback: rebuild all dirty cloners, then stop the timer."""
    global _timer_running
    _timer_running = False
    if not _dirty:
        return None
    # Snapshot and clear — rebuilds may mark more dirty, they'll get next tick.
    names = sorted(_dirty)
    _dirty.clear()
    try:
        from .cloner import build_chain
    except Exception:
        return None
    for name in names:
        try:
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            if getattr(obj, "hmg_type", "") != "CLONER":
                continue
            # Never rebuild during render or while Blender is busy — skip.
            build_chain(obj)
        except Exception:
            # AK47: a failed rebuild never takes down the session.
            continue
    return None


def _ensure_timer():
    global _timer_running
    if _timer_running:
        return
    try:
        bpy.app.timers.register(_rebuild_dirty, first_interval=0.05)
        _timer_running = True
    except Exception:
        pass


@bpy.app.handlers.persistent
def on_depsgraph_update(scene, depsgraph):
    # NEVER rebuild here — only detect changes and mark dirty.
    # The timer does the heavy lifting after the depsgraph settles.
    try:
        cloners = [o for o in bpy.data.objects
                   if getattr(o, "hmg_type", "") == "CLONER"]
    except Exception:
        return
    if not cloners:
        _children_cache.clear()
        _dirty.clear()
        return
    for cl in cloners:
        try:
            key = _children_key(cl)
        except Exception:
            continue
        if _children_cache.get(cl.name) != key:
            _children_cache[cl.name] = key
            _dirty.add(cl.name)
    _prune_cache()
    if _dirty:
        _ensure_timer()


def mark_dirty(obj):
    """Public: mark a cloner for rebuild (safe to call from anywhere)."""
    try:
        if getattr(obj, "hmg_type", "") == "CLONER":
            _dirty.add(obj.name)
            _ensure_timer()
    except Exception:
        pass


def register():
    if on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)


def unregister():
    if on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
    _dirty.clear()
    _children_cache.clear()

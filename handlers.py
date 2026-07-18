import bpy

from .utils import (
    ILLUMINATED_OBJECT_TYPE_LIST,
    has_shared_linking_collections,
    make_light_linking_single_user,
    process_duplicated_object,
)

_processing = False


def _auto_fix_enabled() -> bool:
    try:
        from . import __package__ as base_package
        return bpy.context.preferences.addons[base_package].preferences.auto_fix_shared_linking
    except (KeyError, AttributeError):
        return False


def _collect_candidate_objects(depsgraph: bpy.types.Depsgraph) -> list[bpy.types.Object]:
    candidates = []
    seen = set()
    for update in depsgraph.updates:
        id_ref = update.id
        if not isinstance(id_ref, bpy.types.Object):
            continue
        if id_ref.is_evaluated:
            id_ref = id_ref.original
            if id_ref is None:
                continue
        if id_ref.name in seen:
            continue
        if id_ref.type not in ILLUMINATED_OBJECT_TYPE_LIST:
            continue
        seen.add(id_ref.name)
        candidates.append(id_ref)
    return candidates


@bpy.app.handlers.persistent
def depsgraph_update_post_handler(_scene, depsgraph: bpy.types.Depsgraph):
    global _processing
    if _processing or not _auto_fix_enabled():
        return

    candidates = _collect_candidate_objects(depsgraph)
    if not candidates:
        return

    _processing = True
    try:
        context = bpy.context
        for obj in candidates:
            if obj.type == 'LIGHT' and has_shared_linking_collections(obj):
                make_light_linking_single_user(obj)
                continue
            process_duplicated_object(obj, context)
    finally:
        _processing = False


def sync_auto_fix_depsgraph_handler(enabled: bool | None = None) -> None:
    if enabled is None:
        enabled = _auto_fix_enabled()
    if enabled:
        if depsgraph_update_post_handler not in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.append(depsgraph_update_post_handler)
    elif depsgraph_update_post_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(depsgraph_update_post_handler)


@bpy.app.handlers.persistent
def invalidate_filter_cache_handler(_scene, _depsgraph):
    from .filter import invalidate_filter_cache
    invalidate_filter_cache()


def ensure_filter_cache_invalidation_handler() -> None:
    """Register cache invalidation only after the filtered list is used."""
    if invalidate_filter_cache_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(invalidate_filter_cache_handler)


def register():
    # Auto-fix is opt-in and never mutates data during registration or file load.
    sync_auto_fix_depsgraph_handler()


def unregister():
    sync_auto_fix_depsgraph_handler(False)
    if invalidate_filter_cache_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(invalidate_filter_cache_handler)

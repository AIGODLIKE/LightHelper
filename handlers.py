import time

import bpy

from .utils import (
    ILLUMINATED_OBJECT_TYPE_LIST,
    has_shared_linking_collections,
    make_light_linking_single_user,
    process_duplicated_object,
)

_processing = False
_FILTER_CACHE_HANDLER_IDLE_SECONDS = 1.0
_filter_cache_last_used = 0.0


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
    if time.monotonic() - _filter_cache_last_used > _FILTER_CACHE_HANDLER_IDLE_SECONDS:
        from .filter import invalidate_filter_cache
        from .utils import invalidate_linking_ui_cache
        invalidate_filter_cache()
        invalidate_linking_ui_cache()
        if invalidate_filter_cache_handler in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(invalidate_filter_cache_handler)
        return
    if not _depsgraph_updates_affect_ui_cache(_depsgraph):
        return
    from .filter import invalidate_filter_cache
    from .utils import invalidate_linking_ui_cache
    invalidate_filter_cache()
    invalidate_linking_ui_cache()


@bpy.app.handlers.persistent
def world_environment_sun_sync_handler(scene, depsgraph):
    """Keep newly added Sun lights from illuminating a managed environment dome."""
    from .utils.world_environment import sync_world_environment_suns_from_depsgraph
    sync_world_environment_suns_from_depsgraph(scene, depsgraph)


def _depsgraph_updates_affect_ui_cache(depsgraph: bpy.types.Depsgraph) -> bool:
    """Ignore transform-only updates that cannot change linking or light-source lists."""
    relevant_types = (
        bpy.types.Collection,
        bpy.types.Material,
        bpy.types.NodeTree,
    )
    for update in depsgraph.updates:
        id_ref = update.id
        if isinstance(id_ref, bpy.types.Object):
            transform_only = (
                bool(getattr(update, "is_updated_transform", False))
                and not bool(getattr(update, "is_updated_geometry", False))
                and not bool(getattr(update, "is_updated_shading", False))
            )
            if not transform_only:
                return True
        elif isinstance(id_ref, relevant_types):
            return True
    return False


def ensure_filter_cache_invalidation_handler() -> None:
    """Keep cache invalidation active only while a filtered list is being drawn."""
    global _filter_cache_last_used
    _filter_cache_last_used = time.monotonic()
    if invalidate_filter_cache_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(invalidate_filter_cache_handler)


def _scene_needs_world_environment_sun_sync(scene: bpy.types.Scene) -> bool:
    from .utils.world_environment import get_world_dome, is_world_dome_owned_by_scene
    dome = get_world_dome(scene)
    return bool(
        dome is not None
        and is_world_dome_owned_by_scene(scene, dome)
    )


def sync_world_environment_sun_handler(enabled: bool | None = None) -> None:
    """Keep Sun synchronization active only while a managed dome exists."""
    if enabled is None:
        try:
            scenes = bpy.data.scenes
        except AttributeError:
            # Extension install/enable runs register() with restricted bpy.data.
            # load_post will perform the check once file data is available.
            return
        enabled = any(
            _scene_needs_world_environment_sun_sync(scene)
            for scene in scenes
        )
    if enabled:
        if world_environment_sun_sync_handler not in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.append(world_environment_sun_sync_handler)
    elif world_environment_sun_sync_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(world_environment_sun_sync_handler)


def ensure_world_environment_sun_handler(scene: bpy.types.Scene) -> None:
    """Enable automatic Sun exclusion after the feature is actively used."""
    if _scene_needs_world_environment_sun_sync(scene):
        sync_world_environment_sun_handler(True)


@bpy.app.handlers.persistent
def light_helper_load_post_handler(_filepath) -> None:
    """Refresh transient caches and handlers after Blender replaces file data."""
    from .filter import invalidate_filter_cache
    from .utils import invalidate_linking_ui_cache
    from .utils.world_environment import clear_world_environment_sync_state
    clear_world_environment_sync_state()
    invalidate_filter_cache()
    invalidate_linking_ui_cache()
    sync_world_environment_sun_handler()


def register():
    from .utils.world_environment import clear_world_environment_sync_state
    clear_world_environment_sync_state()
    if light_helper_load_post_handler not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(light_helper_load_post_handler)
    # Auto-fix is opt-in and never mutates data during registration or file load.
    sync_auto_fix_depsgraph_handler()
    # Manual enable can happen after a file containing a managed dome is open.
    sync_world_environment_sun_handler()


def unregister():
    global _filter_cache_last_used
    from .filter import invalidate_filter_cache
    from .utils import invalidate_linking_ui_cache
    from .utils.world_environment import clear_world_environment_sync_state
    sync_auto_fix_depsgraph_handler(False)
    if light_helper_load_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(light_helper_load_post_handler)
    if invalidate_filter_cache_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(invalidate_filter_cache_handler)
    _filter_cache_last_used = 0.0
    sync_world_environment_sun_handler(False)
    invalidate_filter_cache()
    invalidate_linking_ui_cache()
    clear_world_environment_sync_state()

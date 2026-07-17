import bpy

LIGHT_HELPER_SAFE_KEY = "light_helper_safe"
LIGHT_HELPER_MANAGED_KEY = "light_helper_managed"
LIGHT_HELPER_MIGRATED_KEY = "light_helper_migrated_v047"


def _is_legacy_safe_object(obj: bpy.types.Object) -> bool:
    return bool(obj.get(LIGHT_HELPER_SAFE_KEY))


def _remove_legacy_safe_objects() -> int:
    # Safe placeholders are intentional again; do not strip them on cleanup.
    return 0


def _infer_linking_mode_from_collections(light: bpy.types.Object) -> str | None:
    from .utils import CollectionType, get_linking_coll, StateValue

    states = []
    for coll_type in (CollectionType.RECEIVER, CollectionType.BLOCKER):
        coll = get_linking_coll(light, coll_type)
        if coll is None:
            continue
        for coll_obj in coll.collection_objects:
            states.append(coll_obj.light_linking.link_state)
        for coll_child in coll.collection_children:
            states.append(coll_child.light_linking.link_state)

    if not states:
        return None
    if all(s == StateValue.INCLUDE.value for s in states):
        return StateValue.INCLUDE.value
    if all(s == StateValue.EXCLUDE.value for s in states):
        return StateValue.EXCLUDE.value
    return None


def _scene_has_extension_managed_linking(scene: bpy.types.Scene) -> bool:
    from .utils import CollectionType, get_linking_coll, is_linking_initialized

    for obj in scene.objects:
        if not hasattr(obj, "light_linking"):
            continue
        if not is_linking_initialized(obj):
            continue
        for coll_type in (CollectionType.RECEIVER, CollectionType.BLOCKER):
            coll = get_linking_coll(obj, coll_type)
            if coll is not None and coll.get(LIGHT_HELPER_MANAGED_KEY):
                return True
    return False


def scene_needs_migration(scene: bpy.types.Scene) -> bool:
    if scene.get(LIGHT_HELPER_MIGRATED_KEY):
        return False
    return _scene_has_extension_managed_linking(scene)


def has_legacy_residue() -> bool:
    try:
        scenes = bpy.data.scenes
    except (AttributeError, TypeError):
        return False
    return any(scene_needs_migration(scene) for scene in scenes)


def migrate_scene(scene: bpy.types.Scene) -> bool:
    if scene.get(LIGHT_HELPER_MIGRATED_KEY):
        return False
    if not _scene_has_extension_managed_linking(scene):
        scene[LIGHT_HELPER_MIGRATED_KEY] = True
        return False

    from .utils import (
        CollectionType,
        apply_linking_mode_to_light,
        get_linking_coll,
        is_linking_initialized,
    )

    for obj in scene.objects:
        if not hasattr(obj, "light_linking"):
            continue
        if not is_linking_initialized(obj):
            continue
        managed = any(
            (coll := get_linking_coll(obj, coll_type)) is not None
            and bool(coll.get(LIGHT_HELPER_MANAGED_KEY))
            for coll_type in (CollectionType.RECEIVER, CollectionType.BLOCKER)
        )
        if not managed:
            continue
        mode = _infer_linking_mode_from_collections(obj)
        if mode is not None:
            obj.light_helper_property.linking_mode = mode
            apply_linking_mode_to_light(obj, mode)

    scene[LIGHT_HELPER_MIGRATED_KEY] = True
    return True


def run_legacy_cleanup() -> tuple[int, int]:
    """Remove legacy leftovers and migrate unmigrated scenes.

    Returns (removed_safe_object_count, migrated_scene_count).
    """
    removed = _remove_legacy_safe_objects()
    migrated = 0
    for scene in bpy.data.scenes:
        if migrate_scene(scene):
            migrated += 1
    return removed, migrated

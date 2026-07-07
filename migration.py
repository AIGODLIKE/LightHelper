import bpy

LIGHT_HELPER_SAFE_KEY = "light_helper_safe"
LIGHT_HELPER_MIGRATED_KEY = "light_helper_migrated_v047"
MIGRATION_VERSION = (0, 4, 7)


def _is_legacy_safe_object(obj: bpy.types.Object) -> bool:
    if obj.get(LIGHT_HELPER_SAFE_KEY):
        return True
    return obj.name.startswith("LLP_SAFE_")


def _remove_legacy_safe_objects() -> None:
    to_remove = [obj for obj in bpy.data.objects if _is_legacy_safe_object(obj)]
    for obj in to_remove:
        mesh = obj.data if obj.type == 'MESH' else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def _infer_linking_mode_from_collections(light: bpy.types.Object) -> str:
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
        return StateValue.EXCLUDE.value
    if all(s == StateValue.INCLUDE.value for s in states):
        return StateValue.INCLUDE.value
    return StateValue.EXCLUDE.value


def migrate_scene(scene: bpy.types.Scene) -> None:
    if scene.get(LIGHT_HELPER_MIGRATED_KEY):
        return

    from .utils import apply_linking_mode_to_light, is_linking_initialized

    _remove_legacy_safe_objects()

    for obj in scene.objects:
        if not hasattr(obj, "light_linking"):
            continue
        if not is_linking_initialized(obj):
            continue
        mode = _infer_linking_mode_from_collections(obj)
        obj.light_helper_property.linking_mode = mode
        apply_linking_mode_to_light(obj, mode)

    from .utils import fix_all_shared_light_linking
    fix_all_shared_light_linking(scene)

    scene[LIGHT_HELPER_MIGRATED_KEY] = True


@bpy.app.handlers.persistent
def load_post_handler(_dummy):
    for scene in bpy.data.scenes:
        migrate_scene(scene)


_handlers = (load_post_handler,)


def register():
    for handler in _handlers:
        if handler not in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.append(handler)
    if bpy.context.scene:
        migrate_scene(bpy.context.scene)


def unregister():
    for handler in _handlers:
        if handler in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(handler)

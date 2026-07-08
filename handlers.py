import bpy

from .utils import (
    ILLUMINATED_OBJECT_TYPE_LIST,
    fix_all_shared_light_linking,
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
        return True


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


@bpy.app.handlers.persistent
def load_post_fix_handler(_dummy):
    if not _auto_fix_enabled():
        return
    for scene in bpy.data.scenes:
        fix_all_shared_light_linking(scene)


_handlers = (
    depsgraph_update_post_handler,
    load_post_fix_handler,
)

_handler_lists = (
    bpy.app.handlers.depsgraph_update_post,
    bpy.app.handlers.load_post,
)


def run_fix_for_all_scenes() -> None:
    try:
        scenes = bpy.data.scenes
    except (AttributeError, TypeError):
        return
    for scene in scenes:
        fix_all_shared_light_linking(scene)


def _deferred_fix():
    run_fix_for_all_scenes()
    return None


def register():
    for handler, handler_list in zip(_handlers, _handler_lists):
        if handler not in handler_list:
            handler_list.append(handler)
    if not bpy.app.timers.is_registered(_deferred_fix):
        bpy.app.timers.register(_deferred_fix, first_interval=0.0)


def unregister():
    if bpy.app.timers.is_registered(_deferred_fix):
        bpy.app.timers.unregister(_deferred_fix)
    for handler, handler_list in zip(_handlers, _handler_lists):
        if handler in handler_list:
            handler_list.remove(handler)

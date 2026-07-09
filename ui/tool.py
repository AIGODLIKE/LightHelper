import os

import bpy
from bpy.app.translations import pgettext_iface as p_

TOOL_IDNAME = "light_helper.light_linking"
TOOL_PICK = "object.light_helper_light_linking_pick"
TOOL_HUD_DRAG = "object.light_helper_light_linking_hud_drag"
TOOL_ICON = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "icons",
    "ops.light_helper.light_linking",
)
DEFAULT_FALLBACK_TOOL = "builtin.select_box"

_previous_tool_idname = None
_last_seen_tool_idname = None
_tool_registered = False
_msgbus_owner = object()
_depsgraph_sync_registered = False
_msgbus_subscribed = False
_deferred_session_sync_pending = False
_deferred_selection_sync_pending = False


def _deferred_session_sync():
    """One-shot timer: sync session outside of UI draw / depsgraph."""
    global _deferred_session_sync_pending
    _deferred_session_sync_pending = False
    try:
        context = bpy.context
        if context is None:
            return None
        _track_previous_tool(context)
        if is_light_linking_tool_active(context):
            if not is_session_active(context):
                start_tool_session(context)
        elif is_session_active(context):
            stop_tool_session(context)
    except (AttributeError, ReferenceError, TypeError):
        pass
    return None


def schedule_session_sync():
    """Queue a one-shot session sync (safe from draw_settings)."""
    global _deferred_session_sync_pending
    if _deferred_session_sync_pending:
        return
    if bpy.app.timers.is_registered(_deferred_session_sync):
        return
    _deferred_session_sync_pending = True
    bpy.app.timers.register(_deferred_session_sync, first_interval=0.0)


def _deferred_selection_sync():
    """One-shot timer: sync list (+ tool subject when session is on)."""
    global _deferred_selection_sync_pending
    _deferred_selection_sync_pending = False
    try:
        context = bpy.context
        if context is None:
            return None
        # Sidebar list should follow Outliner/viewport even without the tool session.
        sync_list_from_selection(context)
        if is_session_active(context):
            if not is_light_linking_tool_active(context):
                schedule_session_sync()
            else:
                sync_tool_subject_from_selection(context)
    except (AttributeError, ReferenceError, TypeError):
        pass
    return None


def schedule_selection_sync():
    global _deferred_selection_sync_pending
    if _deferred_selection_sync_pending:
        return
    if bpy.app.timers.is_registered(_deferred_selection_sync):
        return
    _deferred_selection_sync_pending = True
    bpy.app.timers.register(_deferred_selection_sync, first_interval=0.0)


def get_active_tool_idname(context: bpy.types.Context) -> str | None:
    if context is None or context.workspace is None:
        return None
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except (AttributeError, TypeError):
        return None
    if tool is None:
        return None
    return tool.idname


def is_light_linking_tool_active(context: bpy.types.Context) -> bool:
    return get_active_tool_idname(context) == TOOL_IDNAME


def is_session_active(context: bpy.types.Context | None = None) -> bool:
    ctx = context if context is not None else bpy.context
    try:
        return bool(ctx.window_manager.light_helper_property.linking_tool_active)
    except (AttributeError, ReferenceError, TypeError):
        return False


def get_fallback_tool_idname() -> str:
    if _previous_tool_idname and _previous_tool_idname != TOOL_IDNAME:
        return _previous_tool_idname
    return DEFAULT_FALLBACK_TOOL


def activate_tool_by_id(context: bpy.types.Context, tool_idname: str) -> bool:
    if not tool_idname:
        return False
    try:
        bpy.ops.wm.tool_set_by_id(name=tool_idname, space_type='VIEW_3D')
        return True
    except (RuntimeError, AttributeError, TypeError):
        pass
    for window in context.window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for region in area.regions:
                if region.type != 'WINDOW':
                    continue
                try:
                    with context.temp_override(window=window, screen=screen, area=area, region=region):
                        bpy.ops.wm.tool_set_by_id(name=tool_idname, space_type='VIEW_3D')
                    return True
                except (RuntimeError, AttributeError, TypeError):
                    continue
    return False


def exit_to_previous_tool(context: bpy.types.Context) -> str:
    target = get_fallback_tool_idname()
    stop_tool_session(context)
    if not activate_tool_by_id(context, target):
        target = DEFAULT_FALLBACK_TOOL
        activate_tool_by_id(context, target)
    return target


def _track_previous_tool(context: bpy.types.Context) -> None:
    global _previous_tool_idname, _last_seen_tool_idname
    current = get_active_tool_idname(context)
    if current is None:
        return
    if current == TOOL_IDNAME:
        if _last_seen_tool_idname and _last_seen_tool_idname != TOOL_IDNAME:
            _previous_tool_idname = _last_seen_tool_idname
    _last_seen_tool_idname = current


def init_session_light(context: bpy.types.Context) -> bpy.types.Object | None:
    from ..utils import get_filtered_tool_lights, is_tool_light_source, select_tool_light
    obj = context.object
    if obj is not None and is_tool_light_source(obj, context):
        select_tool_light(context, obj)
        return obj
    lights = get_filtered_tool_lights(context)
    if lights:
        select_tool_light(context, lights[0])
        return lights[0]
    return None


def init_session_object(context: bpy.types.Context) -> bpy.types.Object | None:
    from ..utils import get_filtered_tool_objects, is_linkable_object, select_tool_object
    obj = context.object
    if obj is not None and is_linkable_object(obj):
        select_tool_object(context, obj)
        return obj
    objects = get_filtered_tool_objects(context)
    if objects:
        select_tool_object(context, objects[0])
        return objects[0]
    return None


def start_tool_session(context: bpy.types.Context) -> None:
    from ..utils.overlay import refresh_overlay_cache, register_draw_handlers, tag_view3d_redraw
    wm_props = context.window_manager.light_helper_property
    if wm_props.linking_tool_active:
        if wm_props.linking_tool_subject_mode == 'OBJECT':
            if wm_props.linking_tool_object is None:
                wm_props.linking_tool_object = init_session_object(context)
        elif wm_props.linking_tool_light is None:
            wm_props.linking_tool_light = init_session_light(context)
        _subscribe_tool_changes()
        _register_depsgraph_sync()
        register_draw_handlers()
        refresh_overlay_cache(context)
        tag_view3d_redraw(context)
        return
    wm_props.linking_tool_subject_mode = 'LIGHT'
    light = init_session_light(context)
    wm_props.linking_tool_active = True
    wm_props.linking_tool_light = light
    wm_props.linking_tool_object = None
    _subscribe_tool_changes()
    _register_depsgraph_sync()
    register_draw_handlers()
    refresh_overlay_cache(context)
    tag_view3d_redraw(context)


def stop_tool_session(context: bpy.types.Context) -> None:
    from ..utils.overlay import invalidate_overlay_cache, tag_view3d_redraw, unregister_draw_handlers
    wm_props = context.window_manager.light_helper_property
    if not wm_props.linking_tool_active:
        return
    wm_props.linking_tool_active = False
    wm_props.linking_tool_light = None
    wm_props.linking_tool_object = None
    wm_props.linking_tool_subject_mode = 'LIGHT'
    unregister_draw_handlers()
    _unsubscribe_tool_changes()
    _unregister_depsgraph_sync()
    invalidate_overlay_cache()
    tag_view3d_redraw(context)
    if context.window:
        context.window.cursor_set('DEFAULT')


def _tag_sidebar_redraw(context: bpy.types.Context) -> None:
    for window in context.window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


_syncing_list_index = False


def sync_list_from_selection(context: bpy.types.Context) -> bool:
    """Keep sidebar UIList highlight in sync with Outliner/viewport active object."""
    global _syncing_list_index
    from ..utils import resolve_original_id

    obj = resolve_original_id(context.view_layer.objects.active or context.object)
    if obj is None:
        return False

    scene_props = context.scene.light_helper_property
    objects = context.scene.objects
    try:
        index = objects.find(obj.name)
    except (AttributeError, TypeError):
        return False
    if index < 0:
        return False
    if scene_props.active_object_index == index:
        return False

    # Skip update callback to avoid re-selecting / view jumps from Outliner picks.
    _syncing_list_index = True
    try:
        scene_props.active_object_index = index
    finally:
        _syncing_list_index = False
    _tag_sidebar_redraw(context)
    return True


def is_syncing_list_index() -> bool:
    return _syncing_list_index


def sync_tool_subject_from_selection(context: bpy.types.Context) -> bool:
    from ..utils import is_linkable_object, is_tool_light_source, resolve_original_id
    from ..utils.overlay import invalidate_overlay_cache, refresh_overlay_cache, tag_view3d_redraw

    wm_props = context.window_manager.light_helper_property
    if not wm_props.linking_tool_active:
        return False

    obj = resolve_original_id(context.view_layer.objects.active or context.object)
    if obj is None:
        return False

    changed = False
    if wm_props.linking_tool_subject_mode == 'OBJECT':
        if is_linkable_object(obj):
            current = resolve_original_id(wm_props.linking_tool_object)
            if current is None or current.name != obj.name:
                wm_props.linking_tool_object = obj
                changed = True
    elif is_tool_light_source(obj, context):
        current = resolve_original_id(wm_props.linking_tool_light)
        if current is None or current.name != obj.name:
            wm_props.linking_tool_light = obj
            changed = True

    sync_list_from_selection(context)

    if changed:
        invalidate_overlay_cache()
        refresh_overlay_cache(context)
        tag_view3d_redraw(context)
    return changed


def _on_tool_changed(*_args):
    schedule_session_sync()


@bpy.app.handlers.persistent
def _depsgraph_sync_selection(_scene, _depsgraph):
    """Session-only fallback for tool subject; list sync uses always-on msgbus."""
    try:
        context = bpy.context
        if context is None or not is_session_active(context):
            return
        if not is_light_linking_tool_active(context):
            schedule_session_sync()
            return
        schedule_selection_sync()
    except (AttributeError, ReferenceError, TypeError):
        pass


def _register_depsgraph_sync() -> None:
    global _depsgraph_sync_registered
    if _depsgraph_sync_registered:
        return
    if _depsgraph_sync_selection not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_depsgraph_sync_selection)
    _depsgraph_sync_registered = True


def _unregister_depsgraph_sync() -> None:
    global _depsgraph_sync_registered
    if not _depsgraph_sync_registered:
        return
    if _depsgraph_sync_selection in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_sync_selection)
    _depsgraph_sync_registered = False


_active_object_msgbus_owner = object()
_active_object_subscribed = False


def _on_active_object_changed(*_args):
    """Outliner / viewport active object changes."""
    schedule_selection_sync()


def _subscribe_active_object():
    """Always-on: sidebar list follows Outliner selection."""
    global _active_object_subscribed
    if _active_object_subscribed:
        return
    try:
        bpy.msgbus.clear_by_owner(_active_object_msgbus_owner)
        bpy.msgbus.subscribe_rna(
            key=(bpy.types.LayerObjects, "active"),
            owner=_active_object_msgbus_owner,
            args=(),
            notify=_on_active_object_changed,
            options={'PERSISTENT'},
        )
        _active_object_subscribed = True
    except (AttributeError, TypeError, RuntimeError):
        _active_object_subscribed = False


def _unsubscribe_active_object():
    global _active_object_subscribed
    try:
        bpy.msgbus.clear_by_owner(_active_object_msgbus_owner)
    except (AttributeError, TypeError, RuntimeError):
        pass
    _active_object_subscribed = False


def _subscribe_tool_changes():
    global _msgbus_subscribed
    try:
        bpy.msgbus.clear_by_owner(_msgbus_owner)
        bpy.msgbus.subscribe_rna(
            key=(bpy.types.WorkSpace, "tools"),
            owner=_msgbus_owner,
            args=(),
            notify=_on_tool_changed,
            options={'PERSISTENT'},
        )
        _msgbus_subscribed = True
    except (AttributeError, TypeError, RuntimeError):
        _msgbus_subscribed = False


def _unsubscribe_tool_changes():
    global _msgbus_subscribed
    try:
        bpy.msgbus.clear_by_owner(_msgbus_owner)
    except (AttributeError, TypeError, RuntimeError):
        pass
    _msgbus_subscribed = False


class VIEW3D_WT_light_linking(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = TOOL_IDNAME
    bl_label = "Light Linking"
    bl_description = (
        "Interactive light linking tool. "
        "LClick: select/toggle link. "
        "Ctrl+LClick: switch light/object. "
        "Esc: exit tool"
    )
    bl_icon = TOOL_ICON
    bl_widget = None
    bl_operator = ""
    bl_keymap = (
        (TOOL_HUD_DRAG, {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
        (TOOL_PICK, {"type": 'LEFTMOUSE', "value": 'CLICK'}, None),
        ("object.light_helper_light_linking_toggle_light", {"type": 'SPACE', "value": 'PRESS'}, None),
        ("object.light_helper_light_linking_toggle_shadow", {"type": 'D', "value": 'PRESS'}, None),
        ("object.light_helper_light_linking_toggle_mode", {"type": 'A', "value": 'PRESS'}, None),
        ("object.light_helper_light_linking_toggle_overlay", {"type": 'X', "value": 'PRESS'}, None),
        ("object.light_helper_light_linking_exit", {"type": 'ESC', "value": 'PRESS'}, None),
        ("object.light_helper_light_linking_cycle_light", {"type": 'WHEELUPMOUSE', "value": 'PRESS', "ctrl": True},
         {"properties": [("direction", -1)]}),
        ("object.light_helper_light_linking_cycle_light", {"type": 'WHEELDOWNMOUSE', "value": 'PRESS', "ctrl": True},
         {"properties": [("direction", 1)]}),
    )

    @staticmethod
    def _draw_mode_controls(row, wm_props):
        control_row = row.row(align=True)
        control_row.prop(wm_props, "linking_tool_overlay_mode", text="", text_ctxt="light_helper_zh_CN")
        control_row.prop(
            wm_props, "linking_tool_show_hud",
            text=p_("Shortcuts"), toggle=True, text_ctxt="light_helper_zh_CN",
        )
        row.separator(factor=0.8)
        row.prop(wm_props, "linking_tool_subject_mode", expand=True, icon_only=True, text_ctxt="light_helper_zh_CN")

    @staticmethod
    def _draw_subject_status(row, subject_mode, light, obj, link_count):
        from ..utils.icon import get_item_icon, get_light_icon

        if subject_mode == 'OBJECT':
            if obj is not None:
                row.label(text=obj.name, icon='OBJECT_DATA', translate=False)
                row.separator(factor=0.8)
                row.label(text=p_("Linked lights: %d") % link_count)
            else:
                row.label(text=p_("No object selected"), icon='INFO')
        elif light is not None:
            if light.type == 'LIGHT':
                light_icon = get_light_icon(light)
            else:
                light_icon = get_item_icon(light).get('icon', 'OBJECT_DATA')
            row.label(text=light.name, icon=light_icon, translate=False)
            row.separator(factor=0.8)
            row.label(text=p_("Linked items: %d") % link_count)
            row.separator(factor=0.8)
            row.prop(light.light_helper_property, "linking_mode", expand=True, text_ctxt="light_helper_zh_CN")
        else:
            row.label(text=p_("No light selected"), icon='INFO')

    @staticmethod
    def draw_settings(context, layout, tool):
        from ..ui.panel import LLT_PT_light_control_panel
        from ..utils import get_light_link_item_count, get_object_link_light_count
        from ..utils.overlay import get_active_link_count

        if not LLT_PT_light_control_panel.check_support_light_linking(context):
            layout.label(
                text=p_("This rendering engine does not support light linking"),
                icon='ERROR',
            )
            return

        wm_props = context.window_manager.light_helper_property
        # Read-only draw path: never refresh cache here. Defer session start/stop.
        if is_light_linking_tool_active(context) != wm_props.linking_tool_active:
            schedule_session_sync()
        subject_mode = wm_props.linking_tool_subject_mode
        light = wm_props.linking_tool_light
        obj = wm_props.linking_tool_object
        is_header = context.region and context.region.type == 'TOOL_HEADER'
        session_on = wm_props.linking_tool_active

        link_count = 0
        if subject_mode == 'OBJECT':
            if obj is not None:
                link_count = get_active_link_count() if session_on else get_object_link_light_count(obj, context)
        elif light is not None:
            link_count = get_active_link_count() if session_on else get_light_link_item_count(light)

        if is_header:
            row = layout.row(align=True)
            VIEW3D_WT_light_linking._draw_mode_controls(row, wm_props)
            row.separator(factor=1.2)
            VIEW3D_WT_light_linking._draw_subject_status(
                row, subject_mode, light, obj, link_count,
            )
            return

        col = layout.column(align=True)
        row = col.row(align=True)
        VIEW3D_WT_light_linking._draw_mode_controls(row, wm_props)

        col.separator()
        if subject_mode == 'OBJECT':
            if obj is not None:
                col.label(text=obj.name, icon='OBJECT_DATA', translate=False)
                col.label(text=p_("Linked lights: %d") % link_count)
            elif session_on:
                col.label(text=p_("No object selected"), icon='INFO')
        elif light is not None:
            from ..utils.icon import get_item_icon, get_light_icon
            if light.type == 'LIGHT':
                light_icon = get_light_icon(light)
            else:
                light_icon = get_item_icon(light).get('icon', 'OBJECT_DATA')
            col.label(text=light.name, icon=light_icon, translate=False)
            col.label(text=p_("Linked items: %d") % link_count)
            col.row(align=True).prop(
                light.light_helper_property, "linking_mode", expand=True, text_ctxt="light_helper_zh_CN",
            )
        elif session_on:
            col.label(text=p_("No light selected"), icon='INFO')


def register():
    global _tool_registered
    bpy.utils.register_tool(
        VIEW3D_WT_light_linking,
        separator=True,
        group=False,
    )
    _tool_registered = True
    _subscribe_active_object()
    # Tool msgbus / depsgraph attach in start_tool_session only.
    try:
        if bpy.context is not None and is_light_linking_tool_active(bpy.context):
            schedule_session_sync()
        elif bpy.context is not None:
            schedule_selection_sync()
    except (AttributeError, ReferenceError, TypeError):
        pass


def unregister():
    global _tool_registered, _deferred_session_sync_pending, _deferred_selection_sync_pending
    if bpy.app.timers.is_registered(_deferred_session_sync):
        bpy.app.timers.unregister(_deferred_session_sync)
    if bpy.app.timers.is_registered(_deferred_selection_sync):
        bpy.app.timers.unregister(_deferred_selection_sync)
    _deferred_session_sync_pending = False
    _deferred_selection_sync_pending = False
    try:
        if bpy.context is not None:
            stop_tool_session(bpy.context)
    except (AttributeError, ReferenceError, TypeError):
        pass
    _unsubscribe_active_object()
    _unsubscribe_tool_changes()
    _unregister_depsgraph_sync()
    if _tool_registered:
        bpy.utils.unregister_tool(VIEW3D_WT_light_linking)
        _tool_registered = False

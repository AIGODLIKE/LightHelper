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
_session_active = False


def is_light_linking_tool_active(context: bpy.types.Context) -> bool:
    if context is None or context.workspace is None:
        return False
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode)
    except (AttributeError, TypeError):
        return False
    return tool is not None and tool.idname == TOOL_IDNAME


def is_session_active() -> bool:
    return _session_active


def _init_session_light(context: bpy.types.Context) -> bpy.types.Object | None:
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


def _init_session_object(context: bpy.types.Context) -> bpy.types.Object | None:
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
    global _session_active
    from ..utils.overlay import refresh_overlay_cache, register_draw_handlers, tag_view3d_redraw
    wm_props = context.window_manager.light_helper_property
    if _session_active:
        if wm_props.linking_tool_subject_mode == 'OBJECT':
            if wm_props.linking_tool_object is None:
                wm_props.linking_tool_object = _init_session_object(context)
        elif wm_props.linking_tool_light is None:
            wm_props.linking_tool_light = _init_session_light(context)
        refresh_overlay_cache(context)
        tag_view3d_redraw(context)
        return
    wm_props.linking_tool_subject_mode = 'LIGHT'
    light = _init_session_light(context)
    wm_props.linking_tool_active = True
    wm_props.linking_tool_light = light
    wm_props.linking_tool_object = None
    wm_props.linking_tool_overlay_mode = 'SELECTED'
    register_draw_handlers()
    refresh_overlay_cache(context)
    tag_view3d_redraw(context)
    _session_active = True


def stop_tool_session(context: bpy.types.Context) -> None:
    global _session_active
    if not _session_active:
        return
    from ..utils.overlay import invalidate_overlay_cache, tag_view3d_redraw, unregister_draw_handlers
    wm_props = context.window_manager.light_helper_property
    wm_props.linking_tool_active = False
    wm_props.linking_tool_light = None
    wm_props.linking_tool_object = None
    wm_props.linking_tool_subject_mode = 'LIGHT'
    unregister_draw_handlers()
    invalidate_overlay_cache()
    tag_view3d_redraw(context)
    if context.window:
        context.window.cursor_set('DEFAULT')
    _session_active = False


class VIEW3D_WT_light_linking(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = TOOL_IDNAME
    bl_label = "Light Linking"
    bl_description = (
        "Interactive light linking tool\n"
        "LClick: select light or toggle link"
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
        from ..utils.overlay import _cache_needs_refresh, get_active_link_count, refresh_overlay_cache

        if not LLT_PT_light_control_panel.check_support_light_linking(context):
            layout.label(
                text=p_("This rendering engine does not support light linking"),
                icon='ERROR',
            )
            return

        wm_props = context.window_manager.light_helper_property
        subject_mode = wm_props.linking_tool_subject_mode
        light = wm_props.linking_tool_light
        obj = wm_props.linking_tool_object
        is_header = context.region and context.region.type == 'TOOL_HEADER'

        link_count = 0
        if subject_mode == 'OBJECT':
            if obj is not None:
                if _session_active:
                    if _cache_needs_refresh(context):
                        refresh_overlay_cache(context)
                    link_count = get_active_link_count(context)
                else:
                    link_count = get_object_link_light_count(obj, context)
        elif light is not None:
            if _session_active:
                if _cache_needs_refresh(context):
                    refresh_overlay_cache(context)
                link_count = get_active_link_count(context)
            else:
                link_count = get_light_link_item_count(light)

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
            elif wm_props.linking_tool_active:
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
        elif wm_props.linking_tool_active:
            col.label(text=p_("No light selected"), icon='INFO')

_tool_registered = False
_session_timer = None


def _sync_tool_subject_from_selection(context: bpy.types.Context) -> bool:
    from ..utils import is_linkable_object, is_tool_light_source, resolve_original_id
    from ..utils.overlay import invalidate_overlay_cache, refresh_overlay_cache, tag_view3d_redraw

    wm_props = context.window_manager.light_helper_property
    if not wm_props.linking_tool_active:
        return False

    obj = resolve_original_id(context.object)
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

    if changed:
        invalidate_overlay_cache()
        refresh_overlay_cache(context)
        tag_view3d_redraw(context)
    return changed


def _tool_session_poll():
    try:
        context = bpy.context
        if context is None or context.window_manager is None:
            return 0.15
        if is_light_linking_tool_active(context):
            if not _session_active:
                start_tool_session(context)
            else:
                _sync_tool_subject_from_selection(context)
        elif _session_active:
            stop_tool_session(context)
    except Exception:
        pass
    return 0.15


def _start_session_timer():
    global _session_timer
    if _session_timer is None:
        _session_timer = bpy.app.timers.register(_tool_session_poll, first_interval=0.05)


def _stop_session_timer():
    global _session_timer
    if _session_timer is not None:
        bpy.app.timers.unregister(_tool_session_poll)
        _session_timer = None


def register():
    global _tool_registered
    bpy.utils.register_tool(
        VIEW3D_WT_light_linking,
        separator=True,
        group=False,
    )
    _tool_registered = True
    _start_session_timer()


def unregister():
    global _tool_registered
    _stop_session_timer()
    if _tool_registered:
        bpy.utils.unregister_tool(VIEW3D_WT_light_linking)
        _tool_registered = False
    try:
        if bpy.context is not None:
            stop_tool_session(bpy.context)
    except Exception:
        pass

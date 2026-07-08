import bpy
from bpy.app.translations import pgettext_iface as p_

TOOL_IDNAME = "light_helper.light_linking"
TOOL_PICK = "object.light_helper_light_linking_pick"

_TOOL_HELP = p_(
    """Light Linking Tool
LClick: select light or toggle object link.
Space: toggle light channel. D: toggle shadow channel.
A: switch Exclude/Include. X: toggle overlay.
Ctrl+Wheel: previous/next filtered light."""
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
    from ..utils import get_filtered_tool_lights, select_tool_light
    obj = context.object
    if obj is not None and obj.type == 'LIGHT':
        select_tool_light(context, obj)
        return obj
    lights = get_filtered_tool_lights(context)
    if lights:
        select_tool_light(context, lights[0])
        return lights[0]
    return None


def start_tool_session(context: bpy.types.Context) -> None:
    global _session_active
    from ..utils.overlay import refresh_overlay_cache, register_draw_handlers, tag_view3d_redraw
    wm_props = context.window_manager.light_helper_property
    if _session_active:
        if wm_props.linking_tool_light is None:
            wm_props.linking_tool_light = _init_session_light(context)
            refresh_overlay_cache(context, wm_props.linking_tool_light)
            tag_view3d_redraw(context)
        return
    light = _init_session_light(context)
    wm_props.linking_tool_active = True
    wm_props.linking_tool_light = light
    wm_props.show_linking_overlay = True
    register_draw_handlers()
    refresh_overlay_cache(context, light)
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
    bl_icon = "OUTLINER_OB_LIGHT"
    bl_widget = None
    bl_operator = ""
    bl_keymap = (
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
    def draw_settings(context, layout, tool):
        from ..ops import LLP_OT_question
        from ..ui.panel import LLT_PT_light_control_panel
        from ..utils import get_light_link_item_count, get_linking_mode
        from ..utils.overlay import get_overlay_cache, refresh_overlay_cache

        if not LLT_PT_light_control_panel.check_support_light_linking(context):
            layout.label(
                text=p_("This rendering engine does not support light linking"),
                icon='ERROR',
            )
            return

        wm_props = context.window_manager.light_helper_property
        light = wm_props.linking_tool_light
        is_header = context.region and context.region.type == 'TOOL_HEADER'

        link_count = 0
        if light is not None:
            if _session_active:
                cache = get_overlay_cache()
                if cache.invalid or cache.light != light:
                    refresh_overlay_cache(context, light)
                link_count = len(cache.targets)
            else:
                link_count = get_light_link_item_count(light)

        if is_header:
            row = layout.row(align=True)
            row.prop(wm_props, "show_linking_overlay", text=p_("Show Overlay"), toggle=True)
            if light is not None:
                mode = get_linking_mode(light)
                mode_label = p_("Exclude") if mode == "EXCLUDE" else p_("Include")
                row.separator()
                row.label(text=mode_label, icon='LIGHT', translate=False)
                row.separator()
                row.label(text=p_("Linked items: %d") % link_count)
            elif wm_props.linking_tool_active:
                row.separator()
                row.label(text=p_("No light selected"), icon='INFO')
            row.separator()
            tips = row.operator(LLP_OT_question.bl_idname, text="", icon="QUESTION", emboss=False)
            tips.data = _TOOL_HELP
            return

        col = layout.column(align=True)
        row = col.row(align=True)
        row.label(text=p_("Light Linking Tool"), icon='OUTLINER_OB_LIGHT')
        tips = row.operator(LLP_OT_question.bl_idname, text="", icon="QUESTION", emboss=False)
        tips.data = _TOOL_HELP

        if light is not None:
            col.label(text=light.name, icon='LIGHT', translate=False)
            mode = get_linking_mode(light)
            mode_label = p_("Exclude") if mode == "EXCLUDE" else p_("Include")
            col.label(text=f"{p_('Linking Mode')}: {mode_label}")
            col.label(text=p_("Linked items: %d") % link_count)
        elif wm_props.linking_tool_active:
            col.label(text=p_("No light selected"), icon='INFO')

        col.separator()
        col.prop(wm_props, "show_linking_overlay", text=p_("Show Overlay"), toggle=True)

_tool_registered = False
_session_timer = None


def _tool_session_poll():
    try:
        context = bpy.context
        if context is None or context.window_manager is None:
            return 0.15
        if is_light_linking_tool_active(context):
            if not _session_active:
                start_tool_session(context)
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

import bpy
from bpy.app.translations import pgettext_iface as p_

from ..utils import (
    CollectionType,
    apply_linking_mode_to_light,
    cycle_tool_light,
    cycle_tool_object,
    get_linking_mode,
    init_light_linking,
    is_item_in_channel,
    is_linkable_object,
    is_tool_light_source,
    link_item_to_channel,
    resolve_original_id,
    select_tool_light,
    select_tool_object,
    toggle_item_both_channels,
)
from .common import LightHelperOperator


class _LLP_LightLinkingToolPoll:
    @classmethod
    def poll(cls, context):
        from ..ui.panel import LLT_PT_light_control_panel
        from ..ui.tool import is_light_linking_tool_active
        if not is_light_linking_tool_active(context):
            cls.poll_message_set(p_("Light Linking tool is not active"))
            return False
        if not LLT_PT_light_control_panel.check_support_light_linking(context):
            cls.poll_message_set(p_("This rendering engine does not support light linking"))
            return False
        return True


class _LLP_LightLinkingToolInvoke(_LLP_LightLinkingToolPoll):
    """Shared invoke: ensure session, skip when click is on HUD."""

    def invoke_tool(self, context, event, *, skip_hud: bool = True, clear_hud_click: bool = False):
        from ..ui.tool import start_tool_session
        from ..utils.overlay import clear_hud_consumed_click, hud_consumed_click, mouse_over_hud

        start_tool_session(context)
        if clear_hud_click and hud_consumed_click():
            clear_hud_consumed_click()
            return {'CANCELLED'}
        if skip_hud and mouse_over_hud(context, event):
            return {'CANCELLED'}
        return None


class LLP_OT_light_linking_pick(_LLP_LightLinkingToolInvoke, LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_light_linking_pick'
    bl_label = "Light Linking Pick"
    bl_description = "Select subject or toggle light linking"
    bl_options = {'REGISTER', 'UNDO'}

    switch_subject_mode: bpy.props.BoolProperty(
        name="Switch Subject Mode",
        default=False,
        options={'SKIP_SAVE', 'HIDDEN'},
    )

    @staticmethod
    def _pick_target(context, event):
        from ..utils.overlay import pick_object_under_mouse, view3d_window_at_mouse

        area, region = view3d_window_at_mouse(context, event)
        if area is None or region is None:
            return None, None, None
        return area, region, pick_object_under_mouse(context, event)

    @staticmethod
    def _finish_pick(context):
        from ..ui.tool import _tag_sidebar_redraw
        from ..utils.overlay import invalidate_overlay_cache, refresh_overlay_cache, tag_view3d_redraw
        invalidate_overlay_cache()
        refresh_overlay_cache(context)
        tag_view3d_redraw(context)
        _tag_sidebar_redraw(context)

    @staticmethod
    def _set_light(context, light_obj: bpy.types.Object):
        light_obj = resolve_original_id(light_obj)
        wm_props = context.window_manager.light_helper_property
        # Assign subject first, then force mode so RNA update cannot wipe it.
        wm_props.linking_tool_light = light_obj
        wm_props.linking_tool_object = None
        wm_props["linking_tool_subject_mode"] = 0  # LIGHT
        select_tool_light(context, light_obj)
        LLP_OT_light_linking_pick._finish_pick(context)

    @staticmethod
    def _set_object(context, obj: bpy.types.Object):
        obj = resolve_original_id(obj)
        wm_props = context.window_manager.light_helper_property
        # Assign subject first, then force mode so RNA update cannot wipe it.
        wm_props.linking_tool_object = obj
        wm_props.linking_tool_light = None
        wm_props["linking_tool_subject_mode"] = 1  # OBJECT
        select_tool_object(context, obj)
        LLP_OT_light_linking_pick._finish_pick(context)

    @staticmethod
    def perform_ctrl_pick(operator, context, event):
        area, region, obj = LLP_OT_light_linking_pick._pick_target(context, event)
        if area is None:
            operator.report({'WARNING'}, p_("Click in the 3D viewport"))
            return {'CANCELLED'}
        if obj is None:
            operator.report({'WARNING'}, p_("No object under cursor"))
            return {'CANCELLED'}

        obj = resolve_original_id(obj)

        # True lights always switch to light subject mode.
        if obj.type == 'LIGHT':
            LLP_OT_light_linking_pick._set_light(context, obj)
            operator.report({'INFO'}, p_("Light mode: %s") % obj.name)
            return {'FINISHED'}

        # Any linkable mesh/object (including emissive) switches to object mode.
        # Use the hub to stay in light mode when treating an emissive mesh as a light.
        if is_linkable_object(obj):
            LLP_OT_light_linking_pick._set_object(context, obj)
            operator.report({'INFO'}, p_("Object mode: %s") % obj.name)
            return {'FINISHED'}

        operator.report({'WARNING'}, p_("Selected object cannot use light linking"))
        return {'CANCELLED'}

    @staticmethod
    def _toggle_link(operator, context, light, item, toggle_both: bool, coll_type):
        if toggle_both:
            enabled = toggle_item_both_channels(light, item, context)
            action = p_("linked") if enabled else p_("unlinked")
            operator.report({'INFO'}, f"{item.name} {action}")
        elif coll_type is not None:
            in_channel = is_item_in_channel(light, item, coll_type)
            link_item_to_channel(light, item, coll_type, not in_channel, context)
            channel = p_("light") if coll_type == CollectionType.RECEIVER else p_("shadow")
            state = p_("on") if not in_channel else p_("off")
            operator.report({'INFO'}, f"{item.name} {channel} {state}")
        LLP_OT_light_linking_pick._finish_pick(context)
        return {'FINISHED'}

    @staticmethod
    def perform_pick(operator, context, event, toggle_both: bool, coll_type=None):
        wm_props = context.window_manager.light_helper_property
        object_mode = wm_props.linking_tool_subject_mode == 'OBJECT'
        subject = resolve_original_id(
            wm_props.linking_tool_object if object_mode else wm_props.linking_tool_light
        )
        if subject is None:
            operator.report(
                {'WARNING'},
                p_("No object selected") if object_mode else p_("No light selected"),
            )
            return {'CANCELLED'}

        area, region, obj = LLP_OT_light_linking_pick._pick_target(context, event)
        if area is None:
            operator.report({'WARNING'}, p_("Click in the 3D viewport"))
            return {'CANCELLED'}
        if obj is None:
            operator.report({'WARNING'}, p_("No object under cursor"))
            return {'CANCELLED'}

        obj = resolve_original_id(obj)

        if object_mode:
            # True lights toggle linking; any linkable object (incl. emissive) becomes subject.
            if obj.type == 'LIGHT':
                if subject == obj:
                    operator.report({'WARNING'}, p_("Cannot link a light source to itself"))
                    return {'CANCELLED'}
                init_light_linking(obj, context)
                return LLP_OT_light_linking_pick._toggle_link(
                    operator, context, obj, subject, toggle_both, coll_type,
                )
            if is_linkable_object(obj):
                LLP_OT_light_linking_pick._set_object(context, obj)
                operator.report({'INFO'}, p_("Object mode: %s") % obj.name)
                return {'FINISHED'}
            operator.report({'WARNING'}, p_("No light under cursor"))
            return {'CANCELLED'}

        # Light mode
        if is_tool_light_source(obj, context) and subject != obj:
            LLP_OT_light_linking_pick._set_light(context, obj)
            operator.report({'INFO'}, p_("Selected light: %s") % obj.name)
            return {'FINISHED'}

        if not is_linkable_object(obj):
            operator.report({'WARNING'}, p_("Selected object cannot use light linking"))
            return {'CANCELLED'}

        if subject == obj:
            operator.report({'WARNING'}, p_("Cannot link a light source to itself"))
            return {'CANCELLED'}

        return LLP_OT_light_linking_pick._toggle_link(
            operator, context, subject, obj, toggle_both, coll_type,
        )

    def invoke(self, context, event):
        blocked = self.invoke_tool(context, event, skip_hud=True, clear_hud_click=True)
        if blocked is not None:
            return blocked
        if self.switch_subject_mode or event.ctrl:
            return self.perform_ctrl_pick(self, context, event)
        return self.perform_pick(self, context, event, toggle_both=True)


class LLP_OT_light_linking_hud_drag(_LLP_LightLinkingToolPoll, LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_light_linking_hud_drag'
    bl_label = "Move Linking HUD"
    bl_description = "Drag to reposition the linking tool HUD"
    bl_options = {'BLOCKING', 'INTERNAL'}

    _dragging: bool = False

    def invoke(self, context, event):
        from ..ui.tool import start_tool_session
        from ..utils.overlay import mark_hud_consumed_click, mouse_over_hud
        start_tool_session(context)
        if event.value != 'PRESS' or not mouse_over_hud(context, event):
            return {'PASS_THROUGH'}
        wm_props = context.window_manager.light_helper_property
        self._offset_x = event.mouse_region_x - wm_props.linking_tool_hud_x
        self._offset_y = event.mouse_region_y - wm_props.linking_tool_hud_y
        self._dragging = False
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        from ..utils.overlay import mark_hud_consumed_click, tag_view3d_redraw
        region = context.region
        if region is None or region.type != 'WINDOW':
            return {'CANCELLED'}

        wm_props = context.window_manager.light_helper_property
        if event.type == 'MOUSEMOVE':
            self._dragging = True
            max_x = max(0, region.width - 40)
            max_y = max(0, region.height - 20)
            wm_props.linking_tool_hud_x = int(max(0, min(max_x, event.mouse_region_x - self._offset_x)))
            wm_props.linking_tool_hud_y = int(max(0, min(max_y, event.mouse_region_y - self._offset_y)))
            tag_view3d_redraw(context)
            return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if self._dragging:
                mark_hud_consumed_click()
            return {'FINISHED'}

        if event.type in {'RIGHTMOUSE', 'ESC'}:
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}


class LLP_OT_light_linking_toggle_light(_LLP_LightLinkingToolInvoke, LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_light_linking_toggle_light'
    bl_label = "Toggle Light Channel"
    bl_description = "Toggle the light channel for the object under the cursor"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        blocked = self.invoke_tool(context, event)
        if blocked is not None:
            return blocked
        return LLP_OT_light_linking_pick.perform_pick(
            self, context, event, toggle_both=False, coll_type=CollectionType.RECEIVER,
        )


class LLP_OT_light_linking_toggle_shadow(_LLP_LightLinkingToolInvoke, LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_light_linking_toggle_shadow'
    bl_label = "Toggle Shadow Channel"
    bl_description = "Toggle the shadow channel for the object under the cursor"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        blocked = self.invoke_tool(context, event)
        if blocked is not None:
            return blocked
        return LLP_OT_light_linking_pick.perform_pick(
            self, context, event, toggle_both=False, coll_type=CollectionType.BLOCKER,
        )


class LLP_OT_light_linking_toggle_mode(_LLP_LightLinkingToolInvoke, LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_light_linking_toggle_mode'
    bl_label = "Toggle Linking Mode"
    bl_description = "Switch between Exclude and Include mode"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        from ..utils.overlay import invalidate_overlay_cache, refresh_overlay_cache, tag_view3d_redraw

        blocked = self.invoke_tool(context, event, skip_hud=False)
        if blocked is not None:
            return blocked

        wm_props = context.window_manager.light_helper_property
        if wm_props.linking_tool_subject_mode == 'OBJECT':
            _, _, light = LLP_OT_light_linking_pick._pick_target(context, event)
            if light is None or not is_tool_light_source(light, context):
                self.report({'WARNING'}, p_("No light under cursor"))
                return {'CANCELLED'}
        else:
            light = resolve_original_id(wm_props.linking_tool_light)
            if light is None:
                self.report({'WARNING'}, p_("No light selected"))
                return {'CANCELLED'}

        if not hasattr(light, "light_helper_property"):
            self.report({'WARNING'}, p_("No light selected"))
            return {'CANCELLED'}

        mode = get_linking_mode(light)
        new_mode = "INCLUDE" if mode == "EXCLUDE" else "EXCLUDE"
        light.light_helper_property.linking_mode = new_mode
        apply_linking_mode_to_light(light, new_mode)
        invalidate_overlay_cache()
        refresh_overlay_cache(context)
        tag_view3d_redraw(context)
        return {'FINISHED'}


class LLP_OT_light_linking_toggle_overlay(_LLP_LightLinkingToolInvoke, LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_light_linking_toggle_overlay'
    bl_label = "Cycle Overlay"
    bl_description = "Cycle overlay mode: Off, Selected, All"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        from ..utils.overlay import cycle_overlay_mode, invalidate_overlay_cache, refresh_overlay_cache, tag_view3d_redraw

        blocked = self.invoke_tool(context, event, skip_hud=False)
        if blocked is not None:
            return blocked

        wm_props = context.window_manager.light_helper_property
        wm_props.linking_tool_overlay_mode = cycle_overlay_mode(wm_props.linking_tool_overlay_mode)
        invalidate_overlay_cache()
        refresh_overlay_cache(context)
        tag_view3d_redraw(context)
        return {'FINISHED'}


class LLP_OT_light_linking_exit(_LLP_LightLinkingToolPoll, LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_light_linking_exit'
    bl_label = "Exit Tool"
    bl_description = "Exit to the previous tool, or the first tool if none"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        from ..ui.tool import exit_to_previous_tool
        target = exit_to_previous_tool(context)
        self.report({'INFO'}, p_("Switched to tool: %s") % target)
        return {'FINISHED'}


class LLP_OT_light_linking_cycle_light(_LLP_LightLinkingToolInvoke, LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_light_linking_cycle_light'
    bl_label = "Cycle Subject"
    bl_description = "Switch to previous or next filtered light or object"
    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.IntProperty(default=1, options={'SKIP_SAVE'})

    def invoke(self, context, event):
        blocked = self.invoke_tool(context, event, skip_hud=False)
        if blocked is not None:
            return blocked

        wm_props = context.window_manager.light_helper_property
        if wm_props.linking_tool_subject_mode == 'OBJECT':
            obj = cycle_tool_object(context, wm_props.linking_tool_object, self.direction)
            if obj is not None:
                LLP_OT_light_linking_pick._set_object(context, obj)
            else:
                self.report({'WARNING'}, p_("No filtered objects in the list"))
        else:
            light = cycle_tool_light(context, wm_props.linking_tool_light, self.direction)
            if light is not None:
                LLP_OT_light_linking_pick._set_light(context, light)
            else:
                self.report({'WARNING'}, p_("No filtered lights in the list"))
        return {'FINISHED'}

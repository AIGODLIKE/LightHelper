import bpy
from bpy.app.translations import pgettext_iface as p_

from .common import LightHelperOperator, get_light_obj


def _iter_adjustable_lights(context) -> list[bpy.types.Object]:
    lights = [obj for obj in context.selected_objects if obj.type == 'LIGHT' and obj.data is not None]
    if lights:
        return lights
    light = get_light_obj(context)
    if light is not None and light.type == 'LIGHT' and light.data is not None:
        return [light]
    return []


class LLP_OT_adjust_light_ev(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_adjust_light_ev'
    bl_label = "Adjust Light EV"
    bl_description = "Multiply selected light energy by 2^EV"
    bl_options = {'REGISTER', 'UNDO'}

    ev: bpy.props.FloatProperty(
        name="EV",
        default=0.0,
        options={'SKIP_SAVE'},
    )

    @classmethod
    def poll(cls, context):
        if not _iter_adjustable_lights(context):
            cls.poll_message_set(p_("No light selected"))
            return False
        return True

    def execute(self, context):
        lights = _iter_adjustable_lights(context)
        if not lights:
            self.report({'WARNING'}, p_("No light selected"))
            return {'CANCELLED'}
        factor = 2.0 ** self.ev
        for light in lights:
            light.data.energy = max(0.0, light.data.energy * factor)
        return {'FINISHED'}


class LLP_OT_reset_linking_hud(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'wm.light_helper_reset_linking_hud'
    bl_label = "Reset HUD Position"
    bl_description = "Reset the linking tool HUD to the default corner position"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        from .. import __package__ as base_package
        if base_package not in context.preferences.addons:
            cls.poll_message_set(p_("Add-on preferences unavailable"))
            return False
        return True

    def execute(self, context):
        from ..utils import get_pref
        from ..utils.overlay import tag_view3d_redraw
        pref = get_pref(context)
        pref.linking_tool_hud_x = 100
        pref.linking_tool_hud_y = 150
        tag_view3d_redraw(context)
        self.report({'INFO'}, p_("HUD position reset"))
        return {'FINISHED'}


class LLP_OT_solo_light(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_solo_light'
    bl_label = "Solo Light"
    bl_description = "Show only this light; press again to restore"
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty(default=-1, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        obj = getattr(context, "solo_light_object", None)
        if obj is None or obj.type != 'LIGHT':
            cls.poll_message_set(p_("No light selected"))
            return False
        return True

    @staticmethod
    def _clear_legacy_solo_props(context) -> None:
        for obj in context.scene.objects:
            if "lh_solo_prev" not in obj:
                continue
            try:
                del obj["lh_solo_prev"]
            except (KeyError, TypeError):
                pass

    @staticmethod
    def _restore_solo(context) -> None:
        from ..property import restore_solo_visibility
        restore_solo_visibility(context.window_manager)
        LLP_OT_solo_light._clear_legacy_solo_props(context)

    def execute(self, context):
        from ..filter import filter_objects

        target = getattr(context, "solo_light_object", None)
        if target is None:
            self.report({'WARNING'}, p_("No light selected"))
            return {'CANCELLED'}

        wm_props = context.window_manager.light_helper_property
        current = wm_props.solo_light
        if current is not None and current == target:
            self._restore_solo(context)
            self.report({'INFO'}, p_("Solo restored"))
            if self.index != -1:
                context.scene.light_helper_property.active_object_index = self.index
            return {'FINISHED'}

        if current is not None:
            self._restore_solo(context)

        wm_props.solo_visibility.clear()
        for obj in filter_objects(context):
            item = wm_props.solo_visibility.add()
            item.object = obj
            item.was_hide_viewport = bool(obj.hide_viewport)
            item.was_hide_render = bool(obj.hide_render)
            try:
                item.was_hide_local = bool(obj.hide_get())
            except RuntimeError:
                item.was_hide_local = False
            obj.light_helper_property.show_in_view = obj == target

        wm_props.solo_light = target
        self.report({'INFO'}, p_("Solo: %s") % target.name)
        if self.index != -1:
            context.scene.light_helper_property.active_object_index = self.index
        return {'FINISHED'}

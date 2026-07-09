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

    def execute(self, context):
        from ..utils import get_pref
        from ..utils.overlay import tag_view3d_redraw
        pref = get_pref(context)
        pref.linking_tool_hud_x = 16
        pref.linking_tool_hud_y = 16
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
    def _restore_solo(context) -> None:
        wm_props = context.window_manager.light_helper_property
        for obj in context.scene.objects:
            if "lh_solo_prev" not in obj:
                continue
            try:
                obj.light_helper_property.show_in_view = bool(obj["lh_solo_prev"])
            except (AttributeError, ReferenceError, TypeError, KeyError):
                pass
            try:
                del obj["lh_solo_prev"]
            except (KeyError, TypeError):
                pass
        wm_props.solo_light = None

    def execute(self, context):
        from ..filter import filter_objects

        target = getattr(context, "solo_light_object", None)
        if target is None:
            self.report({'WARNING'}, p_("No light selected"))
            return {'CANCELLED'}

        wm_props = context.window_manager.light_helper_property
        current = wm_props.solo_light
        if current is not None and current.name == target.name:
            self._restore_solo(context)
            self.report({'INFO'}, p_("Solo restored"))
            if self.index != -1:
                context.scene.light_helper_property.active_object_index = self.index
            return {'FINISHED'}

        if current is not None:
            self._restore_solo(context)

        for obj in filter_objects(context):
            obj["lh_solo_prev"] = bool(obj.light_helper_property.show_in_view)
            obj.light_helper_property.show_in_view = obj.name == target.name

        wm_props.solo_light = target
        self.report({'INFO'}, p_("Solo: %s") % target.name)
        if self.index != -1:
            context.scene.light_helper_property.active_object_index = self.index
        return {'FINISHED'}

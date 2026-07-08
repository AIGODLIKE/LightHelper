import bpy
from bpy.app.translations import pgettext_iface as p_

from .common import LightHelperOperator


class LLP_OT_switch_filter_show(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_switch_filter_show'
    bl_label = "Switch Filter Show"
    bl_description = "Toggle viewport visibility for all filtered lights in the list"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from ..filter import filter_objects
        if not filter_objects(context):
            cls.poll_message_set(p_("No filtered lights in the list"))
            return False
        return True

    def execute(self, context):
        from ..filter import filter_objects
        _, show = self.get_icon(context)
        for obj in filter_objects(context):
            obj.light_helper_property.show_in_view = not show
        return {"FINISHED"}

    @staticmethod
    def get_icon(context):
        from ..filter import filter_objects
        last_show = None
        for obj in filter_objects(context):
            show = obj.light_helper_property.show_in_view
            if last_show is None:
                last_show = show
            if show != last_show:
                return 'REMOVE', show
            last_show = show

        if last_show is True:
            return 'HIDE_OFF', True
        return 'HIDE_ON', False


class LLP_OT_invert_filter_show(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_invert_filter_show'
    bl_label = "Invert"
    bl_description = "Invert viewport visibility for each filtered light in the list"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from ..filter import filter_objects
        if not filter_objects(context):
            cls.poll_message_set(p_("No filtered lights in the list"))
            return False
        return True

    def execute(self, context):
        from ..filter import filter_objects
        for obj in filter_objects(context):
            obj.light_helper_property.show_in_view = not obj.light_helper_property.show_in_view
        return {"FINISHED"}

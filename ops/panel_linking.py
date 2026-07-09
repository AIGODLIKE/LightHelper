import bpy
from bpy.app.translations import pgettext_iface as p_

from ..utils import (
    CollectionType,
    init_light_linking,
    is_item_in_channel,
    is_linking_initialized,
    link_item_both_channels,
    link_item_to_channel,
    mark_managed_linking_collection,
    restore_light_linking,
)
from .common import LightHelperOperator, enum_coll_type, get_light_obj, operator_tooltip_description


class LLP_OT_remove_light_linking(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_remove_light_linking'
    bl_label = "Remove"
    bl_description = "Remove the object or collection from light linking lists"
    bl_options = {'REGISTER', 'UNDO'}

    coll_type: bpy.props.EnumProperty(
        items=enum_coll_type, options={'SKIP_SAVE'}
    )

    remove_all: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})
    tooltip: bpy.props.StringProperty(default="", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        light = getattr(context, "remove_light_linking_light_obj", None)
        obj = getattr(context, "remove_light_linking_object", None)
        coll = getattr(context, "remove_light_linking_collection", None)
        if light is None:
            cls.poll_message_set(p_("No light selected for removal"))
            return False
        if obj is None and coll is None:
            cls.poll_message_set(p_("No object or collection to remove"))
            return False
        return True

    @classmethod
    def description(cls, context, properties):
        return operator_tooltip_description(properties, cls.bl_description)

    def execute(self, context):
        obj = getattr(context, "remove_light_linking_object", None)
        coll = getattr(context, "remove_light_linking_collection", None)
        light = getattr(context, "remove_light_linking_light_obj", None)

        item = coll if obj is None else obj
        if item is None or light is None:
            self.report({'ERROR'}, p_("No object selected"))
            return {"CANCELLED"}

        if self.remove_all:
            link_item_to_channel(light, item, CollectionType.RECEIVER, False, context)
            link_item_to_channel(light, item, CollectionType.BLOCKER, False, context)
        else:
            coll_type = (CollectionType.RECEIVER if self.coll_type == CollectionType.RECEIVER.value
                         else CollectionType.BLOCKER)
            link_item_to_channel(light, item, coll_type, False, context)

        return {"FINISHED"}


class LLP_OT_clear_light_linking(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_clear_light_linking'
    bl_label = "Clear"
    bl_description = "Clear light linking collections and restore default lighting behavior"
    bl_options = {'REGISTER', 'UNDO'}
    index: bpy.props.IntProperty(default=-1, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        obj = getattr(context, "clear_light_linking_object", None)
        if obj is not None:
            return True
        light = get_light_obj(context)
        if light is None:
            cls.poll_message_set(p_("No light selected"))
            return False
        if not is_linking_initialized(light):
            cls.poll_message_set(p_("Light linking is not initialized"))
            return False
        return True

    def execute(self, context):
        obj = getattr(context, "clear_light_linking_object", None)
        light = obj if obj is not None else get_light_obj(context)
        if light is None:
            self.report({'ERROR'}, p_("No light selected"))
            return {"CANCELLED"}
        restore_light_linking(light, context)
        self.report({'INFO'}, light.name + " " + p_("Restored"))

        if self.index != -1:
            context.scene.light_helper_property.active_object_index = self.index
        return {"FINISHED"}


class LLP_OT_add_light_linking(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_add_light_linking'
    bl_label = "Add"
    bl_description = "Initialize light linking collections for this light"
    bl_options = {'REGISTER', 'UNDO'}

    coll_type: bpy.props.EnumProperty(
        items=enum_coll_type, options={'SKIP_SAVE'}
    )

    init: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    index: bpy.props.IntProperty(default=-1, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        light = getattr(context, "add_light_linking_light_obj", None)
        if light is None:
            cls.poll_message_set(p_("No light selected"))
            return False
        if light.type != 'LIGHT':
            cls.poll_message_set(p_("Selected object cannot use light linking"))
            return False
        return True

    def execute(self, context):
        obj = getattr(context, "add_light_linking_object", None)
        light = getattr(context, "add_light_linking_light_obj", None)
        if not light:
            self.report({'ERROR'}, p_("No light selected"))
            return {"CANCELLED"}
        if self.init:
            init_light_linking(light, context)
        else:
            if not obj or not light:
                return {"CANCELLED"}
            coll_type = (CollectionType.RECEIVER if self.coll_type == CollectionType.RECEIVER.value
                         else CollectionType.BLOCKER)
            if not is_linking_initialized(light):
                init_light_linking(light, context)
            coll = light.light_linking.receiver_collection if coll_type == CollectionType.RECEIVER else light.light_linking.blocker_collection
            if coll is None:
                coll_name = ("Light Linking for " if coll_type == CollectionType.RECEIVER
                             else "Shadow Linking for ") + light.name
                coll = bpy.data.collections.new(coll_name)
                mark_managed_linking_collection(coll)
                if coll_type == CollectionType.RECEIVER:
                    light.light_linking.receiver_collection = coll
                else:
                    light.light_linking.blocker_collection = coll
            link_item_to_channel(light, obj, coll_type, True, context)

        if self.index != -1:
            context.scene.light_helper_property.active_object_index = self.index
        return {"FINISHED"}


class LLP_OT_toggle_light_linking(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_toggle_light_linking'
    bl_label = "Toggle"
    bl_description = "Toggle illumination or shadow channel for this object"
    bl_options = {'REGISTER', 'UNDO'}

    coll_type: bpy.props.EnumProperty(
        items=enum_coll_type, options={'SKIP_SAVE'}
    )
    tooltip: bpy.props.StringProperty(default="", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        light = getattr(context, "toggle_light_linking_light_obj", None)
        obj = getattr(context, "toggle_light_linking_object", None)
        coll = getattr(context, "toggle_light_linking_collection", None)
        if light is None:
            cls.poll_message_set(p_("No light selected"))
            return False
        if obj is None and coll is None:
            cls.poll_message_set(p_("No object or collection to toggle"))
            return False
        return True

    @classmethod
    def description(cls, context, properties):
        if properties.coll_type == CollectionType.RECEIVER.value:
            default = "Toggle Light"
        else:
            default = "Toggle Shadow"
        return operator_tooltip_description(properties, default)

    def execute(self, context):
        light = getattr(context, "toggle_light_linking_light_obj", None)
        obj = getattr(context, "toggle_light_linking_object", None)
        coll = getattr(context, "toggle_light_linking_collection", None)
        if (not obj and not coll) or not light:
            return {"CANCELLED"}

        item = obj if obj else coll
        coll_type = (CollectionType.RECEIVER if self.coll_type == CollectionType.RECEIVER.value
                     else CollectionType.BLOCKER)
        in_channel = is_item_in_channel(light, item, coll_type)
        link_item_to_channel(light, item, coll_type, not in_channel, context)
        return {"FINISHED"}


class LLP_OT_link_selected_objs(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_link_selected_objs'
    bl_label = "Add Selected Objects"
    bl_description = "Add the currently selected objects to the light linking collections"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if getattr(context, "link_light_obj", None) is None:
            cls.poll_message_set(p_("Light linking is not initialized"))
            return False
        return True

    def execute(self, context):
        light = getattr(context, "link_light_obj", None)
        if not light:
            self.report({'ERROR'}, p_("No light selected"))
            return {"CANCELLED"}
        for obj in context.selected_objects:
            if obj == light:
                continue
            link_item_both_channels(light, obj, context)
        return {"FINISHED"}


class LLP_OT_clear_selected_light_linking(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_clear_selected_light_linking'
    bl_label = "Clear Selected Links"
    bl_description = "Clear light linking for all selected lights"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def _iter_targets(cls, context):
        from ..utils import is_linking_initialized, is_tool_light_source
        for obj in context.selected_objects:
            if is_tool_light_source(obj, context) and is_linking_initialized(obj):
                yield obj

    @classmethod
    def poll(cls, context):
        if not any(cls._iter_targets(context)):
            cls.poll_message_set(p_("No selected lights with light linking"))
            return False
        return True

    def execute(self, context):
        from .common import format_lights_report
        lights = list(self._iter_targets(context))
        if not lights:
            self.report({'WARNING'}, p_("No selected lights with light linking"))
            return {"CANCELLED"}
        for light in lights:
            restore_light_linking(light, context)
        self.report(
            {'INFO'},
            format_lights_report(
                lights,
                p_("Cleared light linking for %d light(s): %s"),
                p_("Cleared light linking for %d light(s): %s, and %d more"),
            ),
        )
        return {"FINISHED"}

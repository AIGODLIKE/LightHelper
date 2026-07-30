import bpy
from bpy.app.translations import pgettext_iface as p_

from ..utils import (
    ChannelState,
    CollectionType,
    are_light_linking_collections_editable,
    init_light_linking,
    is_item_in_channel,
    is_light_linking_source_editable,
    is_linking_initialized,
    link_item_both_channels,
    link_item_to_channel,
    restore_light_linking,
    set_item_channel_state,
    set_linking_edit_mode,
)
from .common import COLL_TYPE_ITEMS, LightHelperOperator, get_light_obj, operator_tooltip_description


class LLP_OT_set_linking_edit_mode(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_set_linking_edit_mode'
    bl_label = "Set Linking Edit Mode"
    bl_description = "Switch between Simple and Advanced editing without silently changing native states"
    bl_options = {'REGISTER', 'UNDO'}

    edit_mode: bpy.props.EnumProperty(
        items=[('SIMPLE', "Simple", ""), ('ADVANCED', "Advanced", "")],
        options={'HIDDEN', 'SKIP_SAVE'},
    )
    simple_mode: bpy.props.EnumProperty(
        items=[('INCLUDE', "Include", ""), ('EXCLUDE', "Exclude", "")],
        default='INCLUDE',
        options={'HIDDEN', 'SKIP_SAVE'},
    )

    @classmethod
    def poll(cls, context):
        light = getattr(context, "linking_edit_mode_light", None)
        if light is None:
            cls.poll_message_set(p_("No light selected"))
            return False
        if not is_light_linking_source_editable(light):
            cls.poll_message_set(p_("Light linking data is read-only"))
            return False
        return True

    def execute(self, context):
        light = getattr(context, "linking_edit_mode_light", None)
        if light is None:
            return {'CANCELLED'}
        simple_mode = self.simple_mode if self.edit_mode == 'SIMPLE' else None
        if not set_linking_edit_mode(light, self.edit_mode, simple_mode, context):
            return {'CANCELLED'}
        return {'FINISHED'}


class LLP_OT_set_item_channel_state(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_set_item_channel_state'
    bl_label = "Set Link State"
    bl_description = "Set this target to Off, Include, or Exclude in one native channel"
    bl_options = {'REGISTER', 'UNDO'}

    coll_type: bpy.props.EnumProperty(items=COLL_TYPE_ITEMS, options={'HIDDEN', 'SKIP_SAVE'})
    state: bpy.props.EnumProperty(
        items=[
            ('OFF', "Off", "Remove the direct entry and preserve inherited collection links"),
            ('INCLUDE', "Include", "Add or set a direct Include entry"),
            ('EXCLUDE', "Exclude", "Add or set a direct Exclude entry"),
        ],
        options={'HIDDEN', 'SKIP_SAVE'},
    )

    @classmethod
    def poll(cls, context):
        light = getattr(context, "channel_state_light", None)
        item = getattr(context, "channel_state_item", None)
        if light is None or item is None:
            cls.poll_message_set(p_("No light or target selected"))
            return False
        if not are_light_linking_collections_editable(light):
            cls.poll_message_set(p_("Light linking data is read-only"))
            return False
        return True

    def execute(self, context):
        light = getattr(context, "channel_state_light", None)
        item = getattr(context, "channel_state_item", None)
        if light is None or item is None:
            return {'CANCELLED'}
        coll_type = CollectionType(self.coll_type)
        if not set_item_channel_state(
                light, item, coll_type, ChannelState(self.state), context):
            return {'CANCELLED'}
        return {'FINISHED'}


class LLP_OT_remove_light_linking(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_remove_light_linking'
    bl_label = "Remove"
    bl_description = "Remove the object or collection from light linking lists"
    bl_options = {'REGISTER', 'UNDO'}

    coll_type: bpy.props.EnumProperty(
        items=COLL_TYPE_ITEMS, options={'HIDDEN', 'SKIP_SAVE'}
    )

    # Internal wiring set from the UI; keep these out of the redo panel.
    remove_all: bpy.props.BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})
    restore_default_when_empty: bpy.props.BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})
    tooltip: bpy.props.StringProperty(default="", options={'HIDDEN', 'SKIP_SAVE'})

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
        if not are_light_linking_collections_editable(light):
            cls.poll_message_set(p_("Light linking data is read-only"))
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
        if not are_light_linking_collections_editable(light):
            self.report({'WARNING'}, p_("Light linking data is read-only"))
            return {"CANCELLED"}

        if self.remove_all:
            receiver_changed = link_item_to_channel(
                light, item, CollectionType.RECEIVER, False, context,
                restore_default_when_empty=self.restore_default_when_empty,
            )
            blocker_changed = link_item_to_channel(
                light, item, CollectionType.BLOCKER, False, context,
                restore_default_when_empty=self.restore_default_when_empty,
            )
            changed = receiver_changed or blocker_changed
        else:
            coll_type = (CollectionType.RECEIVER if self.coll_type == CollectionType.RECEIVER.value
                         else CollectionType.BLOCKER)
            changed = link_item_to_channel(
                light, item, coll_type, False, context,
                restore_default_when_empty=self.restore_default_when_empty,
            )

        if not changed:
            self.report({'WARNING'}, p_("Light linking could not be changed"))
            return {"CANCELLED"}

        return {"FINISHED"}


class LLP_OT_clear_light_linking(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_clear_light_linking'
    bl_label = "Clear"
    bl_description = "Clear light linking collections and restore default lighting behavior"
    bl_options = {'REGISTER', 'UNDO'}
    index: bpy.props.IntProperty(default=-1, options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        obj = getattr(context, "clear_light_linking_object", None)
        light = obj if obj is not None else get_light_obj(context)
        if light is None:
            cls.poll_message_set(p_("No light selected"))
            return False
        if not is_light_linking_source_editable(light):
            cls.poll_message_set(p_("Light linking data is read-only"))
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
        if not is_light_linking_source_editable(light):
            self.report({'WARNING'}, p_("Light linking data is read-only"))
            return {"CANCELLED"}
        if not restore_light_linking(light, context):
            self.report({'WARNING'}, p_("Light linking could not be changed"))
            return {"CANCELLED"}
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
        items=COLL_TYPE_ITEMS, options={'HIDDEN', 'SKIP_SAVE'}
    )

    init: bpy.props.BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})

    index: bpy.props.IntProperty(default=-1, options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        from ..utils import is_tool_light_source
        light = getattr(context, "add_light_linking_light_obj", None)
        if light is None:
            cls.poll_message_set(p_("No light selected"))
            return False
        if not is_tool_light_source(light, context):
            cls.poll_message_set(p_("Selected object cannot use light linking"))
            return False
        if not are_light_linking_collections_editable(light):
            cls.poll_message_set(p_("Light linking data is read-only"))
            return False
        return True

    def execute(self, context):
        obj = getattr(context, "add_light_linking_object", None)
        light = getattr(context, "add_light_linking_light_obj", None)
        if not light:
            self.report({'ERROR'}, p_("No light selected"))
            return {"CANCELLED"}
        if not are_light_linking_collections_editable(light):
            self.report({'WARNING'}, p_("Light linking data is read-only"))
            return {"CANCELLED"}
        if self.init:
            changed = init_light_linking(light, context)
        else:
            if not obj or not light:
                return {"CANCELLED"}
            coll_type = (CollectionType.RECEIVER if self.coll_type == CollectionType.RECEIVER.value
                         else CollectionType.BLOCKER)
            changed = link_item_to_channel(light, obj, coll_type, True, context)

        if not changed:
            self.report({'WARNING'}, p_("Light linking could not be changed"))
            return {"CANCELLED"}

        if self.index != -1:
            context.scene.light_helper_property.active_object_index = self.index
        return {"FINISHED"}


class LLP_OT_toggle_light_linking(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_toggle_light_linking'
    bl_label = "Toggle"
    bl_description = "Toggle illumination or shadow channel for this object"
    bl_options = {'REGISTER', 'UNDO'}

    coll_type: bpy.props.EnumProperty(
        items=COLL_TYPE_ITEMS, options={'HIDDEN', 'SKIP_SAVE'}
    )
    restore_default_when_empty: bpy.props.BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})
    tooltip: bpy.props.StringProperty(default="", options={'HIDDEN', 'SKIP_SAVE'})

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
        if not are_light_linking_collections_editable(light):
            cls.poll_message_set(p_("Light linking data is read-only"))
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
        if not are_light_linking_collections_editable(light):
            self.report({'WARNING'}, p_("Light linking data is read-only"))
            return {"CANCELLED"}

        item = obj if obj else coll
        coll_type = (CollectionType.RECEIVER if self.coll_type == CollectionType.RECEIVER.value
                     else CollectionType.BLOCKER)
        in_channel = is_item_in_channel(light, item, coll_type)
        if not link_item_to_channel(
            light, item, coll_type, not in_channel, context,
            restore_default_when_empty=self.restore_default_when_empty,
        ):
            self.report({'WARNING'}, p_("Light linking could not be changed"))
            return {"CANCELLED"}
        return {"FINISHED"}


class LLP_OT_link_selected_objs(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_link_selected_objs'
    bl_label = "Add Selected Objects"
    bl_description = "Add the currently selected objects to the light linking collections"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        light = getattr(context, "link_light_obj", None)
        if light is None:
            cls.poll_message_set(p_("Light linking is not initialized"))
            return False
        if not are_light_linking_collections_editable(light):
            cls.poll_message_set(p_("Light linking data is read-only"))
            return False
        return True

    def execute(self, context):
        from ..utils import is_linkable_object

        light = getattr(context, "link_light_obj", None)
        if not light:
            self.report({'ERROR'}, p_("No light selected"))
            return {"CANCELLED"}
        if not are_light_linking_collections_editable(light):
            self.report({'WARNING'}, p_("Light linking data is read-only"))
            return {"CANCELLED"}
        changed = False
        for obj in context.selected_objects:
            if obj == light or not is_linkable_object(obj):
                continue
            changed = link_item_both_channels(light, obj, context) or changed
        if not changed:
            self.report({'WARNING'}, p_("Light linking could not be changed"))
            return {"CANCELLED"}
        return {"FINISHED"}


class LLP_OT_clear_selected_light_linking(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_clear_selected_light_linking'
    bl_label = "Clear Selected Links"
    bl_description = "Clear light linking for all selected lights"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def _iter_targets(cls, context):
        from ..utils import is_light_linking_source_editable, is_linking_initialized, is_tool_light_source
        for obj in context.selected_objects:
            if (is_tool_light_source(obj, context)
                    and is_light_linking_source_editable(obj)
                    and is_linking_initialized(obj)):
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
        cleared = [
            light for light in lights
            if restore_light_linking(light, context)
        ]
        if not cleared:
            self.report({'WARNING'}, p_("Light linking could not be changed"))
            return {"CANCELLED"}
        self.report(
            {'INFO'},
            format_lights_report(
                cleared,
                p_("Cleared light linking for %d light(s): %s"),
                p_("Cleared light linking for %d light(s): %s, and %d more"),
            ),
        )
        return {"FINISHED"}

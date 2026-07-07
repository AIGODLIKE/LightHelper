import bpy
from bpy.app.translations import pgettext_iface as p_

TCTX = "light_helper_zh_CN"


class LightHelperOperator:
    bl_translation_context = TCTX


from .utils import (
    CollectionType,
    restore_light_linking,
    init_light_linking,
    link_item_both_channels,
    link_item_to_channel,
    is_item_in_channel,
    is_linking_initialized,
    apply_linking_mode_to_light,
    mark_managed_linking_collection,
)


def enum_coll_type(self, context):
    items = []
    for i in CollectionType:
        items.append((i.value, p_(i.value.title()), ''))
    return items


def get_light_obj(context):
    if context.scene.light_helper_property.light_linking_pin:
        light_obj = context.scene.light_helper_property.light_linking_pin_object
    else:
        light_obj = context.object
    return light_obj


def get_area(context, area_type: str):
    areas = []
    for area in context.screen.areas:
        if area.type == area_type:
            areas.append(area)
    if len(areas) > 0:
        area = max(areas, key=lambda area: area.width * area.height)
        return area
    return None


def get_layer_collection_by_coll(context, coll: bpy.types.Collection) -> bpy.types.LayerCollection:
    layer_collection = context.view_layer.layer_collection

    def get_lc(lc: bpy.types.LayerCollection):
        if lc.collection == coll:
            return lc
        for i in lc.children:
            rs = get_lc(i)
            if rs:
                return rs

    return get_lc(layer_collection)


class LLP_OT_question(bpy.types.Operator):
    bl_idname = 'wm.light_helper_question'
    bl_label = ""
    bl_options = {'INTERNAL'}

    data: bpy.props.StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        return properties.data

    def execute(self, context):
        return {"FINISHED"}


class LLP_OT_remove_light_linking(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_remove_light_linking'
    bl_label = "Remove"
    bl_description = "Remove the object or collection from light linking lists"
    bl_options = {'REGISTER', 'UNDO'}

    coll_type: bpy.props.EnumProperty(
        items=enum_coll_type, options={'SKIP_SAVE'}
    )

    remove_all: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

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
        restore_light_linking(light)
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
    add_all: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    index: bpy.props.IntProperty(default=-1, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        light = getattr(context, "add_light_linking_light_obj", None)
        from .utils import ILLUMINATED_OBJECT_TYPE_LIST
        if light is None:
            cls.poll_message_set(p_("No light selected"))
            return False
        if light.type not in ILLUMINATED_OBJECT_TYPE_LIST:
            cls.poll_message_set(p_("Selected object cannot use light linking"))
            return False
        return True

    def execute(self, context):
        obj = getattr(context, "add_light_linking_object", None)
        light = getattr(context, "add_light_linking_light_obj", None)
        if not light:
            self.report({'ERROR'}, p_("No light selected"))
            return {"CANCELLED"}
        if self.init or self.add_all:
            init_light_linking(light, context)
            if self.add_all and obj:
                link_item_both_channels(light, obj, context)
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
            return p_("Toggle Light")
        return p_("Toggle Shadow")

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


class LLP_OT_select_item(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_select_item'
    bl_label = "Select"
    bl_description = "Select the object in the viewport or the collection in the outliner"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = getattr(context, "select_item_object", None)
        coll = getattr(context, "select_item_collection", None)
        if obj is None and coll is None:
            cls.poll_message_set(p_("No object or collection to select"))
            return False
        return True

    def execute(self, context):
        from .utils import view_selected
        obj = getattr(context, "select_item_object", None)
        coll = getattr(context, "select_item_collection", None)
        if not obj and not coll:
            self.report({'ERROR'}, p_("No object or collection selected"))
            return {"CANCELLED"}

        if obj:
            area_3d = get_area(context, 'VIEW_3D')
            if not area_3d:
                return {"CANCELLED"}
            self.select_obj_in_view3d(context, obj)
        elif coll:
            area_outliner = get_area(context, 'OUTLINER')
            if not area_outliner:
                return {"CANCELLED"}

            with context.temp_override(area=area_outliner, id=coll, region=area_outliner.regions[0]):
                self.select_coll_in_outliner(context, coll)
        view_selected(context)
        return {"FINISHED"}

    def select_obj_in_view3d(self, context, obj: bpy.types.Object):
        view_layer = context.view_layer
        for selected_obj in view_layer.objects.selected:
            selected_obj.select_set(False)
        view_layer.objects.active = obj
        obj.select_set(True)

    def select_coll_in_outliner(self, context, coll: bpy.types.Collection):
        view_layer = context.view_layer
        for selected_obj in view_layer.objects.selected:
            selected_obj.select_set(False)
        lc = get_layer_collection_by_coll(context, coll)
        if not lc:
            self.report({'ERROR'}, p_("Collection not in scene found"))
            return
        view_layer.active_layer_collection = lc


class LLP_OT_instances_data(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_instances_data'
    bl_label = "Instances Data"
    bl_description = "Make shared light linking collections single-user for this light"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        light_obj = get_light_obj(context)
        if not light_obj:
            cls.poll_message_set(p_("No light selected"))
            return False
        light = light_obj.light_linking
        receiver = getattr(light, "receiver_collection", None)
        if receiver and receiver.users > 1:
            return True
        blocker = getattr(light, "blocker_collection", None)
        if blocker and blocker.users > 1:
            return True
        cls.poll_message_set(p_("Light linking collections are not shared"))
        return False

    def execute(self, context):
        light_obj = get_light_obj(context)
        if light_obj is None:
            self.report({'ERROR'}, p_("No light selected"))
            return {"CANCELLED"}
        light = light_obj.light_linking
        receiver = getattr(light, "receiver_collection", None)
        if receiver and receiver.users > 1:
            setattr(light, "receiver_collection", receiver.copy())
        blocker = getattr(light, "blocker_collection", None)
        if blocker and blocker.users > 1:
            setattr(light, "blocker_collection", blocker.copy())
        apply_linking_mode_to_light(light_obj)
        return {"FINISHED"}


class LLP_OT_switch_filter_show(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_switch_filter_show'
    bl_label = "Switch Filter Show"
    bl_description = "Toggle viewport visibility for all filtered lights in the list"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from .filter import filter_objects
        if not filter_objects(context):
            cls.poll_message_set(p_("No filtered lights in the list"))
            return False
        return True

    def execute(self, context):
        from .filter import filter_objects
        _, show = self.get_icon(context)
        for obj in filter_objects(context):
            obj.light_helper_property.show_in_view = not show
        return {"FINISHED"}

    @staticmethod
    def get_icon(context):
        from .filter import filter_objects
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


ops_list = [
    LLP_OT_question,
    LLP_OT_remove_light_linking,
    LLP_OT_clear_light_linking,
    LLP_OT_add_light_linking,
    LLP_OT_toggle_light_linking,
    LLP_OT_link_selected_objs,
    LLP_OT_select_item,
    LLP_OT_instances_data,
    LLP_OT_switch_filter_show,
]
register_class, unregister_class = bpy.utils.register_classes_factory(ops_list)


def register():
    register_class()


def unregister():
    unregister_class()

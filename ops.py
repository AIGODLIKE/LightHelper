import bpy
from bpy.app.translations import pgettext_iface as p_

from .utils import get_light_effect_obj_state, get_light_effect_coll_state
from .utils import set_light_effect_obj_state, set_light_effect_coll_state, CollectionType, StateValue, restore_light_linking


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
    # get biggest area
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


class LLP_OT_remove_light_linking(bpy.types.Operator):
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
            cls.poll_message_set("No light selected for removal")
            return False
        if obj is None and coll is None:
            cls.poll_message_set("No object or collection to remove")
            return False
        return True

    def execute(self, context):
        obj = getattr(context, "remove_light_linking_object", None)
        coll = getattr(context, "remove_light_linking_collection", None)
        light = getattr(context, "remove_light_linking_light_obj", None)

        if obj is None:
            item = coll
        else:
            item = obj
        if item is None or light is None:
            self.report({'ERROR'}, "No object selected")
            return {"CANCELLED"}

        def remove_item_from_coll(collection: bpy.types.Collection,
                                  remove_item: bpy.types.Object | bpy.types.Collection):
            if isinstance(remove_item, bpy.types.Object):
                if remove_item.name in collection.objects:
                    collection.objects.unlink(remove_item)
            elif isinstance(remove_item, bpy.types.Collection):
                if remove_item.name in collection.children:
                    collection.children.unlink(remove_item)

        if not self.remove_all:
            if self.coll_type == CollectionType.RECEIVER.value:
                coll = light.light_linking.receiver_collection
            else:
                coll = light.light_linking.blocker_collection
            if not coll: return {"CANCELLED"}
            remove_item_from_coll(coll, item)
        else:
            if coll := light.light_linking.receiver_collection:
                remove_item_from_coll(coll, item)
            if coll := light.light_linking.blocker_collection:
                remove_item_from_coll(coll, item)

        return {"FINISHED"}


class LLP_OT_clear_light_linking(bpy.types.Operator):
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
            cls.poll_message_set("No light selected")
            return False
        linking = light.light_linking
        if linking.receiver_collection is None and linking.blocker_collection is None:
            cls.poll_message_set("Light linking is not initialized")
            return False
        return True

    def execute(self, context):
        obj = getattr(context, "clear_light_linking_object", None)
        light = obj if obj is not None else get_light_obj(context)
        if light is None:
            self.report({'ERROR'}, "No light selected")
            return {"CANCELLED"}
        restore_light_linking(light)
        self.report({'INFO'}, light.name + " " + p_("Restored"))

        if self.index != -1:
            context.scene.light_helper_property.active_object_index = self.index
        return {"FINISHED"}


class LLP_OT_add_light_linking(bpy.types.Operator):
    bl_idname = 'object.light_helper_add_light_linking'
    bl_label = "Add"
    bl_description = "Initialize light linking collections and create a hidden placeholder mesh per light"
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
            cls.poll_message_set("No light selected")
            return False
        if light.type not in ILLUMINATED_OBJECT_TYPE_LIST:
            cls.poll_message_set("Selected object cannot use light linking")
            return False
        return True

    def execute(self, context):
        from .utils import ensure_linking_coll, mark_managed_linking_collection
        obj = getattr(context, "add_light_linking_object", None)
        light = getattr(context, "add_light_linking_light_obj", None)
        if not light:
            self.report({'ERROR'}, "No light selected")
            return {"CANCELLED"}
        if self.init or self.add_all:
            ensure_linking_coll(CollectionType.RECEIVER, light)
            ensure_linking_coll(CollectionType.BLOCKER, light)
            # link to both collections
            if self.add_all:
                coll1 = light.light_linking.receiver_collection
                coll2 = light.light_linking.blocker_collection
                if obj not in coll1.objects:
                    coll1.objects.link(obj)
                if obj not in coll2.objects:
                    coll2.objects.link(obj)
        else:
            if not obj or not light:
                return {"CANCELLED"}
            coll = None
            if self.coll_type == CollectionType.RECEIVER.value:
                coll = light.light_linking.receiver_collection
                if not coll:
                    coll = bpy.data.collections.new("Light Linking for " + light.name)
                    mark_managed_linking_collection(coll)
                    light.light_linking.receiver_collection = coll
            elif self.coll_type == CollectionType.BLOCKER.value:
                coll = light.light_linking.blocker_collection
                if not coll:
                    coll = bpy.data.collections.new("Shadow Linking for " + light.name)
                    mark_managed_linking_collection(coll)
                    light.light_linking.blocker_collection = coll
            if coll and obj:
                coll.objects.link(obj)

        if self.index != -1:
            context.scene.light_helper_property.active_object_index = self.index
        return {"FINISHED"}


class LLP_OT_toggle_light_linking(bpy.types.Operator):
    bl_idname = 'object.light_helper_toggle_light_linking'
    bl_label = "Toggle"
    bl_description = "Toggle include or exclude state for light or shadow linking"
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
            cls.poll_message_set("No light selected")
            return False
        if obj is None and coll is None:
            cls.poll_message_set("No object or collection to toggle")
            return False
        return True

    @classmethod
    def description(cls, context, properties):
        if properties.coll_type == CollectionType.RECEIVER.value:
            return "Toggle Light"
        else:
            return "Toggle Shadow"

    def execute(self, context):
        light = getattr(context, "toggle_light_linking_light_obj", None)
        obj = getattr(context, "toggle_light_linking_object", None)
        coll = getattr(context, "toggle_light_linking_collection", None)
        if (not obj and not coll) or not light:
            return {"CANCELLED"}

        if obj:
            state_get = get_light_effect_obj_state(light, obj)
        elif coll:
            state_get = get_light_effect_coll_state(light, coll)
        # check if state value exists, if is None, means that the object is not in the collection
        # if exists, set the other value of the state value
        coll_type = CollectionType.RECEIVER if self.coll_type == CollectionType.RECEIVER.value else CollectionType.BLOCKER

        if state_value := state_get.get(coll_type):  # exist
            # toggle state value
            if state_value == StateValue.INCLUDE:
                value_set = StateValue.EXCLUDE
            else:
                value_set = StateValue.INCLUDE

            if obj:
                set_light_effect_obj_state(light, obj, (coll_type, value_set))
            elif coll:
                set_light_effect_coll_state(light, coll, (coll_type, value_set))

        return {"FINISHED"}


class LLP_OT_link_selected_objs(bpy.types.Operator):
    bl_idname = 'object.light_helper_link_selected_objs'
    bl_label = "Add Selected Objects"
    bl_description = "Add the currently selected objects to the light linking collections"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if getattr(context, "link_light_obj", None) is None:
            cls.poll_message_set("Light linking is not initialized")
            return False
        return True

    def execute(self, context):
        light = getattr(context, "link_light_obj", None)
        if not light:
            self.report({'ERROR'}, "No light selected")
            return {"CANCELLED"}
        coll1 = light.light_linking.receiver_collection
        coll2 = light.light_linking.blocker_collection
        for obj in context.selected_objects:
            if obj == light:
                continue
            if coll1 and obj.name not in coll1.objects:
                coll1.objects.link(obj)
            if coll2 and obj.name not in coll2.objects:
                coll2.objects.link(obj)
        return {"FINISHED"}


class LLP_OT_select_item(bpy.types.Operator):
    bl_idname = 'object.light_helper_select_item'
    bl_label = "Select"
    bl_description = "Select the object in the viewport or the collection in the outliner"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = getattr(context, "select_item_object", None)
        coll = getattr(context, "select_item_collection", None)
        if obj is None and coll is None:
            cls.poll_message_set("No object or collection to select")
            return False
        return True

    def execute(self, context):
        from .utils import view_selected
        obj = getattr(context, "select_item_object", None)
        coll = getattr(context, "select_item_collection", None)
        if not obj and not coll:
            self.report({'ERROR'}, "No object or collection selected")
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
            self.report({'ERROR'}, "Collection not in scene found")
            return
        view_layer.active_layer_collection = lc


class LLP_OT_instances_data(bpy.types.Operator):
    bl_idname = 'object.light_helper_instances_data'
    bl_label = "Instances Data"
    bl_description = "Make shared light linking collections single-user for this light"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        light_obj = get_light_obj(context)
        if not light_obj:
            cls.poll_message_set("No light selected")
            return False
        light = light_obj.light_linking
        receiver = getattr(light, "receiver_collection", None)
        if receiver and receiver.users > 1:
            return True
        blocker = getattr(light, "blocker_collection", None)
        if blocker and blocker.users > 1:
            return True
        cls.poll_message_set("Light linking collections are not shared")
        return False

    def execute(self, context):
        light_obj = get_light_obj(context)
        if light_obj is None:
            self.report({'ERROR'}, "No light selected")
            return {"CANCELLED"}
        light = light_obj.light_linking
        receiver = getattr(light, "receiver_collection", None)
        if receiver and receiver.users > 1:
            setattr(light, "receiver_collection", receiver.copy())
        blocker = getattr(light, "blocker_collection", None)
        if blocker and blocker.users > 1:
            setattr(light, "blocker_collection", blocker.copy())
        return {"FINISHED"}


class LLP_OT_switch_filter_show(bpy.types.Operator):
    bl_idname = 'object.light_helper_switch_filter_show'
    bl_label = "Switch Filter Show"
    bl_description = "Toggle viewport visibility for all filtered lights in the list"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from .filter import filter_objects
        if not filter_objects(context):
            cls.poll_message_set("No filtered lights in the list")
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
        else:
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

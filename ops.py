import bpy
import bpy_types
from bpy.app.translations import pgettext_iface as p_

from .utils import get_light_effect_obj_state, get_light_effect_coll_state
from .utils import set_light_effect_obj_state, set_light_effect_coll_state, CollectionType, StateValue


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


def get_area(area_type: str):
    areas = []
    for area in bpy.context.screen.areas:
        if area.type == area_type:
            areas.append(area)
    # get biggest area
    if len(areas) > 0:
        area = max(areas, key=lambda area: area.width * area.height)
        return area
    return None


def get_layer_collection_by_coll(coll: bpy_types.Collection) -> bpy.types.LayerCollection:
    layer_collection = bpy.context.view_layer.layer_collection

    def get_lc(lc: bpy.types.LayerCollection):
        if lc.collection == coll:
            return lc
        for i in lc.children:
            rs = get_lc(i)
            if rs:
                return rs

    return get_lc(layer_collection)


class LLP_OT_question(bpy.types.Operator):
    bl_idname = 'llp.question'
    bl_label = ""
    bl_options = {'INTERNAL'}

    data: bpy.props.StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        return properties.data

    def execute(self, context):
        return {"FINISHED"}


class LLP_OT_remove_light_linking(bpy.types.Operator):
    bl_idname = 'llp.remove_light_linking'
    bl_label = "Remove"

    coll_type: bpy.props.EnumProperty(
        items=enum_coll_type, options={'SKIP_SAVE'}
    )

    remove_all: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        obj = hasattr(context, "remove_light_linking_object")
        coll = hasattr(context, "remove_light_linking_collection")
        light = hasattr(context, "remove_light_linking_light_obj")
        return light and (obj or coll)

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
                    collection.objects.unlink(obj)
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
    bl_idname = 'llp.clear_light_linking'
    bl_label = "Clear"

    @classmethod
    def poll(cls, context):
        obj = hasattr(context, "clear_light_linking_object")
        light = get_light_obj(context)
        return obj is not None or light is not None

    def execute(self, context):
        obj = getattr(context, "clear_light_linking_object", None)
        light = obj if obj is not None else get_light_obj(context)
        light_linking = light.light_linking
        light_linking.receiver_collection = None
        light_linking.blocker_collection = None
        return {"FINISHED"}


class LLP_OT_add_light_linking(bpy.types.Operator):
    bl_idname = 'llp.add_light_linking'
    bl_label = "Add"

    coll_type: bpy.props.EnumProperty(
        items=enum_coll_type, options={'SKIP_SAVE'}
    )

    init: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})
    add_all: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        light = getattr(context, "add_light_linking_light_obj", None)
        from .utils import ILLUMINATED_OBJECT_TYPE_LIST
        return (light is not None) and light.type in ILLUMINATED_OBJECT_TYPE_LIST

    def execute(self, context):
        obj = getattr(context, "add_light_linking_object", None)
        light = getattr(context, "add_light_linking_light_obj", None)
        print("execute", self.bl_idname, obj, light)
        if not light:
            self.report({'ERROR'}, "No light selected")
            return {"CANCELLED"}

        if self.init or self.add_all:
            # create collection for light linking and shadow linking(create safe object)
            from .utils import ensure_linking_coll
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
                    light.light_linking.receiver_collection = coll
            elif self.coll_type == CollectionType.BLOCKER.value:
                coll = light.light_linking.blocker_collection
                if not coll:
                    coll = bpy.data.collections.new("Shadow Linking for " + light.name)
                    light.light_linking.blocker_collection = coll
            if coll and obj:
                coll.objects.link(obj)

        return {"FINISHED"}


class LLP_OT_toggle_light_linking(bpy.types.Operator):
    bl_idname = 'llp.toggle_light_linking'
    bl_label = "Toggle"

    coll_type: bpy.props.EnumProperty(
        items=enum_coll_type, options={'SKIP_SAVE'}
    )

    @classmethod
    def poll(cls, context):
        light = hasattr(context, "toggle_light_linking_light_obj")
        obj = hasattr(context, "toggle_light_linking_object")
        coll = hasattr(context, "toggle_light_linking_collection")
        return (obj and coll) or light

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
    bl_idname = 'llp.link_selected_objs'
    bl_label = "Add Selected Objects"

    @classmethod
    def poll(cls, context):
        return hasattr(context, "link_light_obj")

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
    bl_idname = 'llp.select_item'
    bl_label = "Select"

    @classmethod
    def poll(cls, context):
        obj = hasattr(context, "select_item_object")
        coll = hasattr(context, "select_item_collection")
        return obj or coll

    def execute(self, context):
        from .utils import view_selected
        obj = getattr(context, "select_item_object", None)
        coll = getattr(context, "select_item_collection", None)
        if not obj and not coll:
            self.report({'ERROR'}, "No object or collection selected")
            return {"CANCELLED"}

        if obj:
            area_3d = get_area('VIEW_3D')
            if not area_3d: return {"CANCELLED"}
            self.select_obj_in_view3d(obj)
        elif coll:
            area_outliner = get_area('OUTLINER')
            if not area_outliner:
                return {"CANCELLED"}

            with context.temp_override(area=area_outliner, id=coll, region=area_outliner.regions[0]):
                self.select_coll_in_outliner(coll)
        view_selected(context)
        return {"FINISHED"}

    def select_obj_in_view3d(self, obj: bpy.types.Object):
        # deselect all
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)

    def select_coll_in_outliner(self, coll: bpy.types.Collection):
        bpy.ops.object.select_all(action='DESELECT')
        # bpy.ops.outliner.item_activate(deselect_all=True)
        lc = get_layer_collection_by_coll(coll)
        if not lc:
            self.report({'ERROR'}, "Collection not in scene found")
            return
        bpy.context.view_layer.active_layer_collection = lc


class LLP_OT_instances_data(bpy.types.Operator):
    bl_idname = 'llp.instances_data'
    bl_label = "Instances Data"

    @classmethod
    def poll(cls, context):
        light_obj = get_light_obj(context)
        if not light_obj:
            return False
        light = light_obj.light_linking
        receiver = getattr(light, "receiver_collection", None)
        if receiver and receiver.users > 1:
            return True
        blocker = getattr(light, "blocker_collection", None)
        if blocker and blocker.users > 1:
            return True
        return False

    def execute(self, context):
        light_obj = get_light_obj(context)
        light = light_obj.light_linking
        receiver = getattr(light, "receiver_collection", None)
        if receiver and receiver.users > 1:
            setattr(light, "receiver_collection", receiver.copy())
            # bpy.ops.object.light_linking_receiver_collection_new()
        blocker = getattr(light, "blocker_collection", None)
        if blocker and blocker.users > 1:
            setattr(light, "blocker_collection", blocker.copy())
            # bpy.ops.object.light_linking_blocker_collection_new()
        return {"FINISHED"}


ops_list = [
    LLP_OT_question,
    LLP_OT_remove_light_linking,
    LLP_OT_clear_light_linking,
    LLP_OT_add_light_linking,
    LLP_OT_toggle_light_linking,
    LLP_OT_link_selected_objs,
    LLP_OT_select_item,
    LLP_OT_instances_data,
]
register_class, unregister_class = bpy.utils.register_classes_factory(ops_list)


def register():
    register_class()


def unregister():
    unregister_class()

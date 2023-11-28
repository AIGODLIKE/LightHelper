import bpy
from bpy.app.translations import pgettext_iface as p_

from .utils import get_light_effect_obj_state, get_light_effect_coll_state
from .utils import set_light_effect_obj_state, set_light_effect_coll_state, CollectionType, StateValue


def get_lights_from_receiver_obj(obj):
    # light_state = {}
    for o in iter(bpy.context.scene.objects):
        if coll := o.light_linking.receiver_collection:
            for i, obj in enumerate(coll.objects):
                # light_state[o] = coll.collection_objects[i].light_linking.link_state
                yield (o, coll.collection_objects[i].light_linking.link_state)

    # return light_state


def enum_coll_type(self, context):
    items = []
    for i in CollectionType:
        items.append((i.value, p_(i.value.title()), ''))

    return items


class LLP_OT_remove_light_linking(bpy.types.Operator):
    bl_idname = 'llp.remove_light_linking'
    bl_label = "Remove"

    obj: bpy.props.StringProperty(options={'SKIP_SAVE'})
    coll: bpy.props.StringProperty(options={'SKIP_SAVE'})
    light: bpy.props.StringProperty(options={'SKIP_SAVE'})

    coll_type: bpy.props.EnumProperty(
        items=enum_coll_type, options={'SKIP_SAVE'}
    )

    remove_all: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        obj = bpy.data.objects.get(self.obj)
        coll_item = bpy.data.collections.get(self.coll)
        light = bpy.data.objects.get(self.light)

        if obj is None:
            item = coll_item
        else:
            item = obj

        def remove_item_from_coll(coll: bpy.types.Collection, item: bpy.types.Object | bpy.types.Collection):
            if isinstance(item, bpy.types.Object):
                if item.name in coll.objects:
                    coll.objects.unlink(obj)
            elif isinstance(item, bpy.types.Collection):
                if item.name in coll.children:
                    coll.children.unlink(item)

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
            if coll := light.light_linking.receiver_collection:
                remove_item_from_coll(coll, item)

        return {"FINISHED"}


class LLP_OT_add_light_linking(bpy.types.Operator):
    bl_idname = 'llp.add_light_linking'
    bl_label = "Add"

    obj: bpy.props.StringProperty(options={'SKIP_SAVE'})
    light: bpy.props.StringProperty(options={'SKIP_SAVE'})

    coll_type: bpy.props.EnumProperty(
        items=enum_coll_type, options={'SKIP_SAVE'}
    )

    add_all: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        obj = bpy.data.objects.get(self.obj)
        light = bpy.data.objects.get(self.light)

        if not self.add_all:
            if not obj or not light: return {"CANCELLED"}
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
        else:
            from .utils import ensure_linking_coll
            ensure_linking_coll(CollectionType.RECEIVER, light)
            ensure_linking_coll(CollectionType.BLOCKER, light)

        return {"FINISHED"}


class LLP_OT_toggle_light_linking(bpy.types.Operator):
    bl_idname = 'llp.toggle_light_linking'
    bl_label = "Toggle"

    obj: bpy.props.StringProperty(options={'SKIP_SAVE'})
    coll: bpy.props.StringProperty(options={'SKIP_SAVE'})
    light: bpy.props.StringProperty(options={'SKIP_SAVE'})

    coll_type: bpy.props.EnumProperty(
        items=enum_coll_type, options={'SKIP_SAVE'}
    )

    def execute(self, context):
        obj = bpy.data.objects.get(self.obj)
        coll = bpy.data.collections.get(self.coll)
        light = bpy.data.objects.get(self.light)
        if (not obj and not coll) or not light: return {"CANCELLED"}

        if obj:
            state_get = get_light_effect_obj_state(light, obj)
        elif coll:
            state_get = get_light_effect_coll_state(light, coll)
        # check if state value exists, if is None, means that the object is not in the collection
        # if exists, set the other value of the state value
        coll_type = CollectionType.RECEIVER if self.coll_type == CollectionType.RECEIVER.value else CollectionType.BLOCKER

        if state_value := state_get.get(coll_type):  # exist
            # toggle state value
            # print(state_value)
            if state_value == StateValue.INCLUDE:
                value_set = StateValue.EXCLUDE
            else:
                value_set = StateValue.INCLUDE

            if obj:
                set_light_effect_obj_state(light, obj, (coll_type, value_set))
            elif coll:
                set_light_effect_coll_state(light, coll, (coll_type, value_set))

        return {"FINISHED"}


class LLP_OT_select_item(bpy.types.Operator):
    bl_idname = 'llp.select_item'
    bl_label = "Select"
    # bl_options = {'REGISTER', 'UNDO'}

    obj: bpy.props.StringProperty(options={'SKIP_SAVE'})
    coll: bpy.props.StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        obj = bpy.data.objects.get(self.obj)
        coll = bpy.data.collections.get(self.coll)
        if not obj and not coll: return {"CANCELLED"}

        if obj:
            area_3d = self.get_area('VIEW_3D')
            if not area_3d: return {"CANCELLED"}
            self.select_obj_in_view3d(obj)
        elif coll:
            area_outliner = self.get_area('OUTLINER')
            if not area_outliner: return {"CANCELLED"}

            with context.temp_override(area=area_outliner, id=coll):
                self.select_coll_in_outliner(coll)

        return {"FINISHED"}

    def get_area(self, area_type: str):
        areas = []
        for area in bpy.context.screen.areas:
            if area.type == area_type:
                areas.append(area)
        # get biggest area
        if len(areas) > 0:
            area = max(areas, key=lambda area: area.width * area.height)
            return area
        return None

    def select_obj_in_view3d(self, obj: bpy.types.Object):
        # deselect all
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)

    def select_coll_in_outliner(self, coll: bpy.types.Collection):
        # TODO select collection in outliner
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.outliner.item_activate(deselect_all=True)


def register():
    bpy.utils.register_class(LLP_OT_remove_light_linking)
    bpy.utils.register_class(LLP_OT_add_light_linking)
    bpy.utils.register_class(LLP_OT_toggle_light_linking)
    bpy.utils.register_class(LLP_OT_select_item)


def unregister():
    bpy.utils.unregister_class(LLP_OT_remove_light_linking)
    bpy.utils.unregister_class(LLP_OT_add_light_linking)
    bpy.utils.unregister_class(LLP_OT_toggle_light_linking)
    bpy.utils.unregister_class(LLP_OT_select_item)

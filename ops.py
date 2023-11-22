import bpy
from bpy.app.translations import pgettext_iface as p_

from .utils import get_light_effect_obj_state, set_light_effect_obj_state, CollectionType, StateValue


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

    obj: bpy.props.StringProperty()
    light: bpy.props.StringProperty()

    coll_type: bpy.props.EnumProperty(
        items=enum_coll_type, options={'SKIP_SAVE'}
    )

    remove_all: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        obj = bpy.data.objects.get(self.obj)
        light = bpy.data.objects.get(self.light)

        if not self.remove_all:
            if self.coll_type == CollectionType.RECEIVER.value:
                coll = light.light_linking.receiver_collection
            else:
                coll = light.light_linking.blocker_collection
            if coll and obj.name in coll.objects:
                coll.objects.unlink(obj)
        else:
            coll = light.light_linking.receiver_collection
            if coll and obj.name in coll.objects:
                coll.objects.unlink(obj)
            coll = light.light_linking.blocker_collection
            if coll and obj.name in coll.objects:
                coll.objects.unlink(obj)
        return {"FINISHED"}


class LLP_OT_add_light_linking(bpy.types.Operator):
    bl_idname = 'llp.add_light_linking'
    bl_label = "Add"

    obj: bpy.props.StringProperty()
    light: bpy.props.StringProperty()

    coll_type: bpy.props.EnumProperty(
        items=enum_coll_type, options={'SKIP_SAVE'}
    )

    def execute(self, context):
        obj = bpy.data.objects.get(self.obj)
        light = bpy.data.objects.get(self.light)
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

        if coll:
            coll.objects.link(obj)

        return {"FINISHED"}


class LLP_OT_toggle_light_linking(bpy.types.Operator):
    bl_idname = 'llp.toggle_light_linking'
    bl_label = "Toggle"

    obj: bpy.props.StringProperty()
    light: bpy.props.StringProperty()

    coll_type: bpy.props.EnumProperty(
        items=enum_coll_type, options={'SKIP_SAVE'}
    )

    def execute(self, context):
        obj = bpy.data.objects.get(self.obj)
        light = bpy.data.objects.get(self.light)
        if not obj or not light: return {"CANCELLED"}

        state_get = get_light_effect_obj_state(light, obj)
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
            set_light_effect_obj_state(light, obj, (coll_type, value_set))

        return {"FINISHED"}


def register():
    bpy.utils.register_class(LLP_OT_remove_light_linking)
    bpy.utils.register_class(LLP_OT_add_light_linking)
    bpy.utils.register_class(LLP_OT_toggle_light_linking)


def unregister():
    bpy.utils.unregister_class(LLP_OT_remove_light_linking)
    bpy.utils.unregister_class(LLP_OT_add_light_linking)
    bpy.utils.unregister_class(LLP_OT_toggle_light_linking)

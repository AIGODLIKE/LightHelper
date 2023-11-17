import bpy


def get_lights_from_receiver_obj(obj):
    # light_state = {}
    for o in iter(bpy.context.scene.objects):
        if coll := o.light_linking.receiver_collection:
            for i, obj in enumerate(coll.objects):
                # light_state[o] = coll.collection_objects[i].light_linking.link_state
                yield (o, coll.collection_objects[i].light_linking.link_state)

    # return light_state


class LLP_OT_remove_light_linking(bpy.types.Operator):
    bl_idname = 'llp.remove_light_linking'
    bl_label = "Remove"

    obj: bpy.props.StringProperty()
    light: bpy.props.StringProperty()

    def execute(self, context):
        obj = bpy.data.objects.get(self.obj)
        light = bpy.data.objects.get(self.light)
        coll = light.light_linking.receiver_collection
        coll.objects.unlink(obj)
        return {"FINISHED"}


def register():
    bpy.utils.register_class(LLP_OT_remove_light_linking)


def unregister():
    bpy.utils.unregister_class(LLP_OT_remove_light_linking)

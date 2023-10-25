import bpy
from bpy.app.handlers import persistent


def update_lightlinking_state(self, context):
    coll = self.light_linking.receiver_collection
    for obj in coll.collection_objects:
        obj.light_linking.link_state = self.light_linking_state


@persistent
def handle_all_lights(null):
    for obj in bpy.context.scene.objects:
        if obj.light_linking.receiver_collection:
            update_lightlinking_state(obj, bpy.context)


def register():
    # noinspection PyTypeChecker
    bpy.types.Object.light_linking_state = bpy.props.EnumProperty(
        items=[
            ("EXCLUDE", "Exclude", ""),
            ("INCLUDE", "Include", "")
        ],
        update=update_lightlinking_state,
        default="EXCLUDE"
    )

    bpy.types.Object.show_light_linking_collection = bpy.props.BoolProperty(
        default=True)

    bpy.app.handlers.depsgraph_update_pre.append(handle_all_lights)


def unregister():
    del bpy.types.Object.light_linking.state
    del bpy.types.Object.show_light_linking_collection

    bpy.app.handlers.depsgraph_update_pre.remove(handle_all_lights)

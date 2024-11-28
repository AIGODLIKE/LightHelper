import bpy
from bpy.app.handlers import persistent
from bpy.types import PropertyGroup


def update_lightlinking_state(self, context):
    if not context.scene.force_light_linking_state: return
    coll = self.light_linking.receiver_collection
    for obj in coll.collection_objects:
        obj.light_helper_property.light_linking.link_state = self.light_linking_state


@persistent
def handle_all_lights(null):
    for obj in bpy.context.scene.objects:
        if obj.light_linking.receiver_collection:
            update_lightlinking_state(obj, bpy.context)


class ObjectProperty(PropertyGroup):
    light_linking_state: bpy.props.EnumProperty(
        items=[
            ("EXCLUDE", "Exclude", ""),
            ("INCLUDE", "Include", "")
        ],
        update=update_lightlinking_state,
        default="EXCLUDE"
    )
    show_light_linking_collection: bpy.props.BoolProperty(
        default=True)


class SceneProperty(PropertyGroup):
    def update_pin_object(self, context):
        """Update pin object, effect the context layout object"""
        scene = context.scene
        obj = context.object
        if scene.light_helper_property.light_linking_pin is True:
            if obj and obj.select_get():
                scene.light_helper_property.light_linking_pin_object = obj
            else:
                scene.light_helper_property.light_linking_pin = False
        else:
            scene.light_helper_property.light_linking_pin_object = None

    def update_pin_object2(self, context):
        """Update pin object, effect the context layout object"""
        scene = context.scene
        obj = context.object
        if scene.light_helper_property.object_linking_pin is True:
            if obj and obj.select_get():
                scene.light_helper_property.object_linking_pin_object = obj
            else:
                scene.light_helper_property.object_linking_pin = False
        else:
            scene.light_helper_property.object_linking_pin_object = None

    # pin object, use to change context layout object
    light_linking_pin_object: bpy.props.PointerProperty(
        poll=lambda self, obj: obj.type in {'LIGHT', 'MESH'}, type=bpy.types.Object,
    )
    object_linking_pin_object: bpy.props.PointerProperty(
        poll=lambda self, obj: obj.type in {'MESH'}, type=bpy.types.Object,
    )
    # pin property to change context draw layout
    light_linking_pin: bpy.props.BoolProperty(name='Pin', update=update_pin_object)
    object_linking_pin: bpy.props.BoolProperty(name='Pin', update=update_pin_object2)

    force_light_linking_state: bpy.props.BoolProperty(
        name='Update',
        default=False)


class WindowManagerProperty(PropertyGroup):

    def update_add_collection(self, context):
        """Add collection to light's receiver and blocker collection
        Most of the time, use drag and drop in the property layout to add
        """
        wm = context.window_manager
        if wm.light_helper_property.light_linking_add_collection is None: return

        if context.scene.light_helper_property.light_linking_pin:
            obj = context.scene.light_helper_property.light_linking_pin_object
        else:
            obj = context.object
        if obj is None:
            wm.light_helper_property.light_linking_add_collection = None
            return

        coll = wm.light_helper_property.light_linking_add_collection
        # add collection to light's receiver and blocker collection
        if coll.name not in obj.light_linking.receiver_collection.children:
            obj.light_linking.receiver_collection.children.link(coll)
        if coll.name not in obj.light_linking.blocker_collection.children:
            obj.light_linking.blocker_collection.children.link(coll)
        # restore
        wm.light_helper_property.light_linking_add_collection = None

    def update_add_obj(self, context):
        """Add object to light's receiver and blocker collection
        Most of the time, use drag and drop in the property layout to add
        """
        wm = context.window_manager
        if wm.light_helper_property.light_linking_add_object is None: return

        if context.scene.light_helper_property.light_linking_pin:
            obj = context.scene.light_helper_property.light_linking_pin_object
        else:
            obj = context.object
        if obj is None:
            wm.light_helper_property.light_linking_add_object = None
            return

        obj2 = wm.light_helper_property.light_linking_add_object
        # add collection to light's receiver and blocker collection
        if obj2.name not in obj.light_linking.receiver_collection.objects:
            obj.light_linking.receiver_collection.objects.link(obj2)
        if obj2.name not in obj.light_linking.blocker_collection.objects:
            obj.light_linking.blocker_collection.objects.link(obj2)
        # restore
        wm.light_helper_property["light_linking_add_object"] = None

    def update_add_light(self, context):
        from .ops import LLP_OT_add_light_linking

        add_op_id = LLP_OT_add_light_linking.bl_idname
        wm = context.window_manager

        if wm.light_helper_property.object_linking_add_object is None:
            return
        if context.scene.light_helper_property.object_linking_pin:
            obj = context.scene.light_helper_property.object_linking_pin_object
        else:
            obj = context.object
        if obj is None or obj == wm.light_helper_property.object_linking_add_object:
            wm.light_helper_property.object_linking_add_object = None
            return

        light = wm.light_helper_property.object_linking_add_object

        init_op = getattr(getattr(bpy.ops, add_op_id.split('.')[0]), add_op_id.split('.')[1])
        init_op('INVOKE_DEFAULT', light=light.name, init=True, obj=obj.name)

        coll1 = light.light_linking.receiver_collection
        coll2 = light.light_linking.blocker_collection

        if coll1 and obj.name not in coll1.objects:
            coll1.objects.link(obj)
        if coll2 and obj.name not in coll2.objects:
            coll2.objects.link(obj)

        # restore
        wm.light_helper_property.object_linking_add_object = None

    # drag & drop to add
    light_linking_add_collection: bpy.props.PointerProperty(name='Drag and Drop to Add',
                                                            type=bpy.types.Collection,
                                                            update=update_add_collection
                                                            )
    light_linking_add_object: bpy.props.PointerProperty(name='Drag and Drop to Add',
                                                        type=bpy.types.Object,
                                                        update=update_add_obj
                                                        )
    object_linking_add_object: bpy.props.PointerProperty(name='Drag and Drop to Add',
                                                         type=bpy.types.Object,
                                                         update=update_add_light
                                                         )


property_list = [
    ObjectProperty,
    SceneProperty,
    WindowManagerProperty,
]
register_class, unregister_class = bpy.utils.register_classes_factory(property_list)


def register():
    # bpy.app.handlers.depsgraph_update_pre.append(handle_all_lights)
    register_class()
    bpy.types.Object.light_helper_property = bpy.props.PointerProperty(type=ObjectProperty)
    bpy.types.Scene.light_helper_property = bpy.props.PointerProperty(type=SceneProperty)
    bpy.types.WindowManager.light_helper_property = bpy.props.PointerProperty(type=WindowManagerProperty)


def unregister():
    # bpy.app.handlers.depsgraph_update_pre.remove(handle_all_lights)
    del bpy.types.Object.light_helper_property
    del bpy.types.Scene.light_helper_property
    del bpy.types.WindowManager.light_helper_property
    unregister_class()

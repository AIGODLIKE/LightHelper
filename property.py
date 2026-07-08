import bpy
from bpy.types import PropertyGroup


def update_linking_mode(self, context):
    from .utils import apply_linking_mode_to_light
    apply_linking_mode_to_light(self.id_data, self.linking_mode)


def check_light_object(obj: bpy.types.Object) -> bool:
    from .utils import ILLUMINATED_OBJECT_TYPE_LIST
    return obj.type in ILLUMINATED_OBJECT_TYPE_LIST


class ObjectProperty(PropertyGroup):
    linking_mode: bpy.props.EnumProperty(
        name="Linking Mode",
        description="Exclude: listed objects are excluded from this light. Include: only listed objects receive this light",
        translation_context="light_helper_zh_CN",
        items=[
            ("EXCLUDE", "Exclude", "Listed objects are excluded from illumination and shadow linking"),
            ("INCLUDE", "Include", "Only listed objects receive illumination and shadow linking"),
        ],
        default="EXCLUDE",
        update=update_linking_mode,
    )

    def get_show(self):
        obj = self.id_data
        return not obj.hide_viewport and not obj.hide_get()

    def set_show(self, value):
        obj = self.id_data
        obj.hide_render = obj.hide_viewport = not value
        if value:
            obj.hide_set(False)
        else:
            obj.hide_set(True)

    show_in_view: bpy.props.BoolProperty(name="Show", get=get_show, set=set_show, )


def poll_light_linking_pin_object(_self, obj: bpy.types.Object) -> bool:
    return obj.type == 'LIGHT'


def poll_object_linking_pin_object(_self, obj: bpy.types.Object) -> bool:
    from .utils import ILLUMINATED_OBJECT_TYPE_LIST
    return obj.type in ILLUMINATED_OBJECT_TYPE_LIST and obj.type != "LIGHT"


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

    light_linking_pin_object: bpy.props.PointerProperty(
        poll=poll_light_linking_pin_object, type=bpy.types.Object,
    )
    object_linking_pin_object: bpy.props.PointerProperty(
        poll=poll_object_linking_pin_object, type=bpy.types.Object,
    )
    light_linking_pin: bpy.props.BoolProperty(name='Pin', update=update_pin_object)
    object_linking_pin: bpy.props.BoolProperty(name='Pin', update=update_pin_object2)

    def update_active_object_index(self, context):
        from .utils import view_selected
        index = self.active_object_index
        objects = context.scene.objects
        if index < 0 or index >= len(objects):
            return
        act_obj = objects[index]
        context.view_layer.objects.active = act_obj

        act_obj.select_set(True)
        for obj in context.view_layer.objects.selected:
            if obj != act_obj:
                obj.select_set(False)

        view_selected(context)

    active_object_index: bpy.props.IntProperty(default=0, update=update_active_object_index)


class WindowManagerProperty(PropertyGroup):
    drop_light_obj: bpy.props.PointerProperty(type=bpy.types.Object)
    drop_object_obj: bpy.props.PointerProperty(type=bpy.types.Object)

    def update_add_collection(self, context):
        wm = context.window_manager
        if wm.light_helper_property.light_linking_add_collection is None:
            return

        if context.scene.light_helper_property.light_linking_pin:
            obj = context.scene.light_helper_property.light_linking_pin_object
        else:
            obj = context.object
        if obj is None:
            wm.light_helper_property.light_linking_add_collection = None
            return

        from .utils import link_item_both_channels
        coll = wm.light_helper_property.light_linking_add_collection
        link_item_both_channels(obj, coll, context)
        wm.light_helper_property["light_linking_add_collection"] = None

    def update_add_obj(self, context):
        wm = context.window_manager
        if wm.light_helper_property.light_linking_add_object is None:
            return

        if context.scene.light_helper_property.light_linking_pin:
            obj = context.scene.light_helper_property.light_linking_pin_object
        else:
            obj = context.object
        if obj is None:
            wm.light_helper_property.light_linking_add_object = None
            return

        from .utils import link_item_both_channels
        obj2 = wm.light_helper_property.light_linking_add_object
        link_item_both_channels(obj, obj2, context)
        wm.light_helper_property["light_linking_add_object"] = None

    def update_add_light(self, context):
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

        from .utils import init_light_linking, link_item_both_channels
        init_light_linking(light, context)
        link_item_both_channels(light, obj, context)
        wm.light_helper_property["object_linking_add_object"] = None

    def poll_object_linking_add_collection(self, coll: bpy.types.Collection):
        from .utils import get_all_light_effect_items_state, get_view_layer_collections_cache, is_managed_linking_collection
        light_obj = self.drop_light_obj
        if light_obj is None:
            return False
        light_ok = coll not in get_all_light_effect_items_state(light_obj)
        coll_ok = coll in get_view_layer_collections_cache()
        return not is_managed_linking_collection(coll) and light_ok and coll_ok

    def poll_light_linking_add_object(self, obj: bpy.types.Object):
        from .utils import get_all_light_effect_items_state
        light_obj = self.drop_light_obj
        if light_obj is None:
            return False
        light_ok = obj not in get_all_light_effect_items_state(light_obj)
        return check_light_object(obj) and obj.type != "LIGHT" and light_ok

    def poll_object_linking_add_object(self, obj: bpy.types.Object):
        from .utils import get_lights_from_effect_obj
        item = self.drop_object_obj
        if item is None:
            return False
        light_ok = obj not in get_lights_from_effect_obj(item, bpy.context)
        return check_light_object(obj) and obj.type == 'LIGHT' and light_ok

    light_linking_add_collection: bpy.props.PointerProperty(name='Drag and Drop to Add',
                                                            type=bpy.types.Collection,
                                                            update=update_add_collection,
                                                            poll=poll_object_linking_add_collection,
                                                            )
    light_linking_add_object: bpy.props.PointerProperty(name='Drag and Drop to Add',
                                                        type=bpy.types.Object,
                                                        update=update_add_obj,
                                                        poll=poll_light_linking_add_object,
                                                        )
    object_linking_add_object: bpy.props.PointerProperty(name='Drag and Drop to Add',
                                                         type=bpy.types.Object,
                                                         update=update_add_light,
                                                         poll=poll_object_linking_add_object,
                                                         )


property_list = [
    ObjectProperty,
    SceneProperty,
    WindowManagerProperty,
]
register_class, unregister_class = bpy.utils.register_classes_factory(property_list)


def register():
    register_class()
    bpy.types.Object.light_helper_property = bpy.props.PointerProperty(type=ObjectProperty)
    bpy.types.Scene.light_helper_property = bpy.props.PointerProperty(type=SceneProperty)
    bpy.types.WindowManager.light_helper_property = bpy.props.PointerProperty(type=WindowManagerProperty)


def unregister():
    del bpy.types.Object.light_helper_property
    del bpy.types.Scene.light_helper_property
    del bpy.types.WindowManager.light_helper_property
    unregister_class()

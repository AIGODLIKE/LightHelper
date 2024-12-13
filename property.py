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


def check_light_object(obj: bpy.types.Object) -> bool:
    from .utils import ILLUMINATED_OBJECT_TYPE_LIST, SAFE_OBJ_NAME
    type_ok = obj.type in ILLUMINATED_OBJECT_TYPE_LIST
    name_ok = obj.name != SAFE_OBJ_NAME
    return type_ok and name_ok and obj.type != "LIGHT"


def get_all_view_layout_collection() -> [bpy.types.Collection]:
    layer_collection = bpy.context.view_layer.layer_collection

    res = []

    def get_lc(lc: bpy.types.LayerCollection):
        res.append(lc.collection)
        for i in lc.children:
            get_lc(i)

    get_lc(layer_collection)
    return res


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

    def update_active_object_index(self, context):
        from .utils import view_selected
        index = self.active_object_index
        act_obj = context.scene.objects[index]
        context.view_layer.objects.active = act_obj

        # context.view_layer.objects.selected = bpy_prop_collection(act_obj)
        # 仅选中所选
        act_obj.select_set(True)
        for obj in context.view_layer.objects.selected:
            if obj != act_obj:
                obj.select_set(False)

        view_selected(context)

    active_object_index: bpy.props.IntProperty(default=0, update=update_active_object_index)


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
        if obj.light_linking.receiver_collection:
            if coll.name not in obj.light_linking.receiver_collection.children:
                obj.light_linking.receiver_collection.children.link(coll)
        if obj.light_linking.blocker_collection:
            if coll.name not in obj.light_linking.blocker_collection.children:
                obj.light_linking.blocker_collection.children.link(coll)
        # restore
        wm.light_helper_property["light_linking_add_collection"] = None

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
        if obj.light_linking.receiver_collection:
            if obj2.name not in obj.light_linking.receiver_collection.objects:
                obj.light_linking.receiver_collection.objects.link(obj2)
        if obj.light_linking.blocker_collection:
            if obj2.name not in obj.light_linking.blocker_collection.objects:
                obj.light_linking.blocker_collection.objects.link(obj2)
        # restore
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

        with context.temp_override(add_light_linking_light_obj=light, add_light_linking_object=obj):
            from .ops import LLP_OT_add_light_linking
            sp = LLP_OT_add_light_linking.bl_idname.split('.')
            ops = getattr(getattr(bpy.ops, sp[0]), sp[1])
            ops('INVOKE_DEFAULT', init=True)

        coll1 = light.light_linking.receiver_collection
        coll2 = light.light_linking.blocker_collection

        if coll1 and obj.name not in coll1.objects:
            coll1.objects.link(obj)
        if coll2 and obj.name not in coll2.objects:
            coll2.objects.link(obj)

        # restore
        wm.light_helper_property["object_linking_add_object"] = None

    # poll
    def poll_object_linking_add_collection(self, coll: bpy.types.Collection):
        from .utils import get_all_light_effect_items_state
        if bpy.context.scene.light_helper_property.light_linking_pin:
            light_obj = bpy.context.scene.light_helper_property.light_linking_pin_object
        else:
            light_obj = bpy.context.object
        light_ok = coll not in get_all_light_effect_items_state(light_obj)
        coll_ok = coll in get_all_view_layout_collection()

        shadow = not coll.name.startswith("Shadow Linking for ")
        light = not coll.name.startswith("Light Linking for ")

        return shadow and light and light_ok and coll_ok

    def poll_light_linking_add_object(self, obj: bpy.types.Object):
        from .utils import get_all_light_effect_items_state
        if bpy.context.scene.light_helper_property.light_linking_pin:
            light_obj = bpy.context.scene.light_helper_property.light_linking_pin_object
        else:
            light_obj = bpy.context.object
        light_ok = obj not in get_all_light_effect_items_state(light_obj)
        return check_light_object(obj) and light_ok

    def poll_object_linking_add_object(self, obj: bpy.types.Object):
        from .utils import get_lights_from_effect_obj
        if bpy.context.scene.light_helper_property.object_linking_pin:
            item = bpy.context.scene.light_helper_property.object_linking_pin_object
        else:
            item = bpy.context.object
        light_ok = obj not in get_lights_from_effect_obj(item)
        return check_light_object(obj) and light_ok and obj != light_ok

    # drag & drop to add
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

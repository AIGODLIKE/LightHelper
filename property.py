import bpy
from bpy.types import PropertyGroup


def update_linking_mode(self, context):
    from .utils import apply_linking_mode_to_light
    apply_linking_mode_to_light(self.id_data, self.linking_mode)
    from .utils.overlay import notify_linking_changed
    notify_linking_changed(context)


def check_light_object(obj: bpy.types.Object) -> bool:
    from .utils import ILLUMINATED_OBJECT_TYPE_LIST
    return obj.type in ILLUMINATED_OBJECT_TYPE_LIST


def update_world_dome_settings(self, context):
    scene = self.id_data
    if not isinstance(scene, bpy.types.Scene):
        return
    from .utils.world_environment import update_world_dome_from_properties
    update_world_dome_from_properties(scene)


class ObjectProperty(PropertyGroup):
    linking_mode: bpy.props.EnumProperty(
        name="Linking Mode",
        description="Include: only listed objects receive this light. Exclude: listed objects are excluded from this light",
        translation_context="light_helper_zh_CN",
        items=[
            ("INCLUDE", "Include", "Only listed objects receive illumination and shadow linking"),
            ("EXCLUDE", "Exclude", "Listed objects are excluded from illumination and shadow linking"),
        ],
        default="INCLUDE",
        update=update_linking_mode,
    )

    def get_show(self):
        obj = self.id_data
        return not obj.hide_viewport and not obj.hide_get()

    def set_show(self, value):
        obj = self.id_data
        obj.hide_viewport = not value
        if value:
            obj.hide_set(False)
        else:
            obj.hide_set(True)

    show_in_view: bpy.props.BoolProperty(name="Show", get=get_show, set=set_show, )

    def get_show_viewport(self):
        obj = self.id_data
        if obj.hide_viewport:
            return False
        try:
            return not obj.hide_get()
        except RuntimeError:
            return False

    def set_show_viewport(self, value):
        obj = self.id_data
        obj.hide_viewport = not value
        try:
            obj.hide_set(not value)
        except RuntimeError:
            pass

    show_viewport: bpy.props.BoolProperty(
        name="Show in Viewport",
        get=get_show_viewport,
        set=set_show_viewport,
    )

    def get_show_render(self):
        return not self.id_data.hide_render

    def set_show_render(self, value):
        self.id_data.hide_render = not value

    show_render: bpy.props.BoolProperty(
        name="Show in Render",
        get=get_show_render,
        set=set_show_render,
    )


def poll_light_linking_pin_object(_self, obj: bpy.types.Object) -> bool:
    from .utils import is_tool_light_source
    return is_tool_light_source(obj, bpy.context)


def poll_object_linking_pin_object(_self, obj: bpy.types.Object) -> bool:
    from .utils import ILLUMINATED_OBJECT_TYPE_LIST
    return obj.type in ILLUMINATED_OBJECT_TYPE_LIST and obj.type != "LIGHT"


class WorldSunLinkRecord(PropertyGroup):
    light: bpy.props.PointerProperty(type=bpy.types.Object)
    original_receiver: bpy.props.PointerProperty(type=bpy.types.Collection)
    managed_receiver: bpy.props.PointerProperty(type=bpy.types.Collection)
    proxy_collection: bpy.props.PointerProperty(type=bpy.types.Collection)
    receiver_created: bpy.props.BoolProperty(default=False)


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
    show_object_linking_panel: bpy.props.BoolProperty(
        name="Show Linked Objects List",
        description="Show the linked objects UI list in the Object Linking panel",
        default=True,
    )

    world_environment_dome: bpy.props.PointerProperty(
        name="World Environment Dome",
        type=bpy.types.Object,
    )
    world_environment_original_world: bpy.props.PointerProperty(
        name="Original World",
        type=bpy.types.World,
    )
    world_environment_managed_world: bpy.props.PointerProperty(
        name="Managed Fallback World",
        type=bpy.types.World,
    )
    world_environment_sun_records: bpy.props.CollectionProperty(
        type=WorldSunLinkRecord,
    )
    world_dome_color: bpy.props.FloatVectorProperty(
        name="Environment Color",
        description="Base color of a solid-color world environment dome",
        subtype='COLOR',
        size=3,
        default=(0.050876, 0.050876, 0.050876),
        min=0.0,
        soft_max=1.0,
        update=update_world_dome_settings,
    )
    world_dome_strength: bpy.props.FloatProperty(
        name="Strength",
        description="Emission strength of the world environment dome",
        default=1.0,
        min=0.0,
        soft_max=16.0,
        update=update_world_dome_settings,
    )
    world_dome_tint: bpy.props.FloatVectorProperty(
        name="Tint",
        description="Color multiplier applied to the environment source",
        subtype='COLOR',
        size=3,
        default=(1.0, 1.0, 1.0),
        min=0.0,
        soft_max=2.0,
        update=update_world_dome_settings,
    )
    world_dome_tint_factor: bpy.props.FloatProperty(
        name="Tint Factor",
        description="Blend amount for the environment tint multiplier",
        subtype='FACTOR',
        default=0.0,
        min=0.0,
        max=1.0,
        update=update_world_dome_settings,
    )
    world_dome_gamma: bpy.props.FloatProperty(
        name="Gamma",
        description="Gamma correction applied to the environment source",
        default=1.0,
        min=0.001,
        soft_max=4.0,
        update=update_world_dome_settings,
    )
    world_dome_saturation: bpy.props.FloatProperty(
        name="Saturation",
        description="Saturation applied to the environment source",
        default=1.0,
        min=0.0,
        soft_max=2.0,
        update=update_world_dome_settings,
    )
    world_dome_rotation: bpy.props.FloatVectorProperty(
        name="Rotation",
        description="HDRI mapping rotation",
        subtype='EULER',
        size=3,
        default=(0.0, 0.0, 0.0),
        update=update_world_dome_settings,
    )
    world_dome_mapping_location: bpy.props.FloatVectorProperty(
        name="Mapping Location",
        description="Advanced HDRI mapping offset copied from the World",
        subtype='TRANSLATION',
        size=3,
        default=(0.0, 0.0, 0.0),
        update=update_world_dome_settings,
    )
    world_dome_mapping_scale: bpy.props.FloatVectorProperty(
        name="Mapping Scale",
        description="Advanced HDRI mapping scale copied from the World",
        subtype='XYZ',
        size=3,
        default=(1.0, 1.0, 1.0),
        update=update_world_dome_settings,
    )
    world_dome_radius: bpy.props.FloatProperty(
        name="Radius",
        description="Radius of the generated inward-facing environment sphere",
        subtype='DISTANCE',
        default=50.0,
        min=0.1,
        soft_max=10000.0,
        update=update_world_dome_settings,
    )
    world_dome_max_bounces: bpy.props.IntProperty(
        name="Total",
        description="Maximum total indirect ray depth allowed to see the environment dome; 0 keeps direct rays only",
        default=2,
        min=0,
        max=1024,
        update=update_world_dome_settings,
    )
    world_dome_max_diffuse_bounces: bpy.props.IntProperty(
        name="Diffuse",
        description="Maximum diffuse indirect ray depth allowed to see the environment dome",
        default=1,
        min=0,
        max=1024,
        update=update_world_dome_settings,
    )
    world_dome_max_glossy_bounces: bpy.props.IntProperty(
        name="Glossy",
        description="Maximum glossy indirect ray depth allowed to see the environment dome",
        default=1,
        min=0,
        max=1024,
        update=update_world_dome_settings,
    )
    world_dome_max_transmission_bounces: bpy.props.IntProperty(
        name="Transmission",
        description="Maximum transmission indirect ray depth allowed to see the environment dome",
        default=2,
        min=0,
        max=1024,
        update=update_world_dome_settings,
    )
    world_dome_visible_camera: bpy.props.BoolProperty(
        name="Camera",
        description="Show the environment dome to camera rays",
        default=True,
        update=update_world_dome_settings,
    )
    world_dome_visible_diffuse: bpy.props.BoolProperty(
        name="Diffuse",
        description="Allow the environment dome to contribute to diffuse rays",
        default=True,
        update=update_world_dome_settings,
    )
    world_dome_visible_glossy: bpy.props.BoolProperty(
        name="Glossy",
        description="Allow the environment dome to appear in glossy rays",
        default=True,
        update=update_world_dome_settings,
    )
    world_dome_visible_transmission: bpy.props.BoolProperty(
        name="Transmission",
        description="Allow the environment dome to appear through transmission rays",
        default=True,
        update=update_world_dome_settings,
    )
    world_dome_visible_volume_scatter: bpy.props.BoolProperty(
        name="Volume Scatter",
        description="Allow the environment dome to contribute to volume scattering rays",
        default=True,
        update=update_world_dome_settings,
    )
    world_dome_show_viewport: bpy.props.BoolProperty(
        name="Show in Viewport",
        description="Show the generated environment dome in the viewport",
        default=True,
        update=update_world_dome_settings,
    )
    world_dome_lock_selection: bpy.props.BoolProperty(
        name="Lock Selection",
        description="Prevent accidental selection of the large environment dome",
        default=True,
        update=update_world_dome_settings,
    )

    def update_active_object_index(self, context):
        from .ui.tool import is_session_active, is_syncing_list_index, sync_tool_subject_from_selection
        if is_syncing_list_index():
            return
        from .utils import is_in_view_layer, view_selected
        index = self.active_object_index
        objects = context.scene.objects
        if index < 0 or index >= len(objects):
            return
        act_obj = objects[index]
        if is_in_view_layer(context, act_obj):
            context.view_layer.objects.active = act_obj
            act_obj.select_set(True)
            for obj in context.view_layer.objects.selected:
                if obj != act_obj:
                    obj.select_set(False)
            view_selected(context)
        if is_session_active(context):
            sync_tool_subject_from_selection(context)

    active_object_index: bpy.props.IntProperty(default=0, update=update_active_object_index)

    def update_active_linked_object_index(self, context):
        from .utils import is_in_view_layer, is_linkable_object, view_selected
        index = self.active_linked_object_index
        objects = context.scene.objects
        if index < 0 or index >= len(objects):
            return
        act_obj = objects[index]
        if not is_linkable_object(act_obj):
            return
        if is_in_view_layer(context, act_obj):
            context.view_layer.objects.active = act_obj
            act_obj.select_set(True)
            for obj in context.view_layer.objects.selected:
                if obj != act_obj:
                    obj.select_set(False)
            view_selected(context)
        if self.object_linking_pin:
            self.object_linking_pin_object = act_obj

    active_linked_object_index: bpy.props.IntProperty(
        default=0,
        update=update_active_linked_object_index,
    )


def poll_linking_tool_light(_self, obj: bpy.types.Object) -> bool:
    from .utils import is_tool_light_source
    return is_tool_light_source(obj, bpy.context)


def poll_linking_tool_object(_self, obj: bpy.types.Object) -> bool:
    from .utils import is_linkable_object
    return is_linkable_object(obj)


class SoloVisibilityItem(PropertyGroup):
    object: bpy.props.PointerProperty(type=bpy.types.Object)
    was_hide_viewport: bpy.props.BoolProperty(default=False)
    was_hide_render: bpy.props.BoolProperty(default=False)
    was_hide_local: bpy.props.BoolProperty(default=False)


def restore_solo_visibility(window_manager: bpy.types.WindowManager) -> None:
    if window_manager is None or not hasattr(window_manager, "light_helper_property"):
        return
    wm_props = window_manager.light_helper_property
    for item in wm_props.solo_visibility:
        obj = item.object
        if obj is None:
            continue
        try:
            obj.hide_viewport = bool(item.was_hide_viewport)
            obj.hide_render = bool(item.was_hide_render)
            obj.hide_set(bool(item.was_hide_local))
        except (AttributeError, ReferenceError, RuntimeError, TypeError):
            pass
    wm_props.solo_visibility.clear()
    wm_props.solo_light = None


class WindowManagerProperty(PropertyGroup):
    drop_light_obj: bpy.props.PointerProperty(type=bpy.types.Object)
    drop_object_obj: bpy.props.PointerProperty(type=bpy.types.Object)
    solo_light: bpy.props.PointerProperty(
        name="Solo Light",
        type=bpy.types.Object,
        options={'SKIP_SAVE'},
    )
    solo_visibility: bpy.props.CollectionProperty(
        type=SoloVisibilityItem,
        options={'SKIP_SAVE'},
    )

    linking_tool_active: bpy.props.BoolProperty(
        name="Linking Tool Active",
        default=False,
        options={'SKIP_SAVE'},
    )
    linking_tool_light: bpy.props.PointerProperty(
        name="Linking Tool Light",
        type=bpy.types.Object,
        poll=poll_linking_tool_light,
        options={'SKIP_SAVE'},
    )
    def update_linking_tool_subject_mode(self, context):
        from .utils.overlay import invalidate_overlay_cache, refresh_overlay_cache, tag_view3d_redraw
        if self.linking_tool_subject_mode == 'OBJECT':
            self.linking_tool_light = None
            if self.linking_tool_active and self.linking_tool_object is None:
                from .ui.tool import init_session_object
                self.linking_tool_object = init_session_object(context)
        else:
            self.linking_tool_object = None
            if self.linking_tool_active and self.linking_tool_light is None:
                from .ui.tool import init_session_light
                self.linking_tool_light = init_session_light(context)
        if self.linking_tool_active:
            invalidate_overlay_cache()
            refresh_overlay_cache(context)
        tag_view3d_redraw(context)

    linking_tool_subject_mode: bpy.props.EnumProperty(
        name="Subject Mode",
        description="Whether the tool edits links from a light or from an object",
        translation_context="light_helper_zh_CN",
        items=[
            ('LIGHT', "Light", "Edit links from the selected light", 'LIGHT', 0),
            ('OBJECT', "Object", "Edit links affecting the selected object", 'OBJECT_DATA', 1),
        ],
        default='LIGHT',
        update=update_linking_tool_subject_mode,
        options={'SKIP_SAVE'},
    )
    linking_tool_object: bpy.props.PointerProperty(
        name="Linking Tool Object",
        type=bpy.types.Object,
        poll=poll_linking_tool_object,
        options={'SKIP_SAVE'},
    )
    def update_linking_tool_overlay_mode(self, context):
        from .utils.overlay import invalidate_overlay_cache, refresh_overlay_cache, tag_view3d_redraw
        if not self.linking_tool_active:
            tag_view3d_redraw(context)
            return
        invalidate_overlay_cache()
        refresh_overlay_cache(context)
        tag_view3d_redraw(context)

    linking_tool_overlay_mode: bpy.props.EnumProperty(
        name="Overlay Mode",
        description="How link lines and object outlines are drawn in the viewport",
        translation_context="light_helper_zh_CN",
        items=[
            ('OFF', "Off", "Do not draw link overlays", 'HIDE_ON', 0),
            ('SELECTED', "Selected", "Only show links for the current subject", 'RESTRICT_SELECT_ON', 1),
            ('ALL', "All", "Show all links; inactive links at reduced opacity", 'OVERLAY', 2),
        ],
        default='SELECTED',
        update=update_linking_tool_overlay_mode,
        options={'SKIP_SAVE'},
    )
    def update_linking_tool_show_hud(self, context):
        from .utils.overlay import tag_view3d_redraw
        tag_view3d_redraw(context)

    linking_tool_show_hud: bpy.props.BoolProperty(
        name="Show Shortcuts",
        description="Show shortcut tips in the viewport",
        translation_context="light_helper_zh_CN",
        default=True,
        update=update_linking_tool_show_hud,
        options={'SKIP_SAVE'},
    )
    def get_linking_tool_hud_x(self):
        from .utils import get_pref
        return get_pref().linking_tool_hud_x

    def set_linking_tool_hud_x(self, value):
        from .utils import get_pref
        get_pref().linking_tool_hud_x = value

    def get_linking_tool_hud_y(self):
        from .utils import get_pref
        return get_pref().linking_tool_hud_y

    def set_linking_tool_hud_y(self, value):
        from .utils import get_pref
        get_pref().linking_tool_hud_y = value

    linking_tool_hud_x: bpy.props.IntProperty(
        name="HUD X",
        description="Horizontal position of the linking tool HUD",
        default=100,
        min=0,
        soft_max=4096,
        get=get_linking_tool_hud_x,
        set=set_linking_tool_hud_x,
        options={'SKIP_SAVE'},
    )
    linking_tool_hud_y: bpy.props.IntProperty(
        name="HUD Y",
        description="Vertical position of the linking tool HUD",
        default=150,
        min=0,
        soft_max=4096,
        get=get_linking_tool_hud_y,
        set=set_linking_tool_hud_y,
        options={'SKIP_SAVE'},
    )

    def update_add_collection(self, context):
        wm = context.window_manager
        if wm.light_helper_property.light_linking_add_collection is None:
            return

        from .utils import get_active_light_source
        obj = get_active_light_source(context)
        if obj is None:
            wm.light_helper_property.light_linking_add_collection = None
            return

        from .utils import link_item_both_channels
        coll = wm.light_helper_property.light_linking_add_collection
        link_item_both_channels(obj, coll, context)
        wm.light_helper_property["light_linking_add_collection"] = None
        from .utils.overlay import notify_linking_changed
        notify_linking_changed(context)

    def update_add_obj(self, context):
        wm = context.window_manager
        if wm.light_helper_property.light_linking_add_object is None:
            return

        from .utils import get_active_light_source
        obj = get_active_light_source(context)
        if obj is None:
            wm.light_helper_property.light_linking_add_object = None
            return

        from .utils import link_item_both_channels
        obj2 = wm.light_helper_property.light_linking_add_object
        link_item_both_channels(obj, obj2, context)
        wm.light_helper_property["light_linking_add_object"] = None
        from .utils.overlay import notify_linking_changed
        notify_linking_changed(context)

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
        from .utils.overlay import notify_linking_changed
        notify_linking_changed(context)

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
        # Prefer cached linking lights from refresh_drop_poll_context; no bpy.context in poll.
        light_ok = obj not in get_lights_from_effect_obj(item)
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
    WorldSunLinkRecord,
    SceneProperty,
    SoloVisibilityItem,
    WindowManagerProperty,
]
register_class, unregister_class = bpy.utils.register_classes_factory(property_list)


def register():
    register_class()
    bpy.types.Object.light_helper_property = bpy.props.PointerProperty(type=ObjectProperty)
    bpy.types.Scene.light_helper_property = bpy.props.PointerProperty(type=SceneProperty)
    bpy.types.WindowManager.light_helper_property = bpy.props.PointerProperty(type=WindowManagerProperty)


def unregister():
    for window_manager in bpy.data.window_managers:
        restore_solo_visibility(window_manager)
    del bpy.types.Object.light_helper_property
    del bpy.types.Scene.light_helper_property
    del bpy.types.WindowManager.light_helper_property
    unregister_class()

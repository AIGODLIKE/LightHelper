import bpy
from bpy.app.translations import pgettext_iface as p_

from ..utils.studio import (
    StudioEngineError,
    create_flag,
    create_reflector,
    create_scrim,
    ensure_track_to,
    ensure_unique_studio_data,
    is_studio_object,
    remove_managed_track_to,
    remove_studio_object,
)
from .common import LightHelperOperator


SHAPE_ITEMS = (
    ('RECTANGLE', "Rectangle", "Rectangular studio surface"),
    ('ELLIPSE', "Ellipse", "Elliptical studio surface"),
)


def _activate_created(context, obj) -> None:
    for selected in list(context.selected_objects):
        selected.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    obj.location = context.scene.cursor.location


class LLP_OT_create_scrim(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_create_scrim'
    bl_label = "Create Scrim"
    bl_description = "Create a managed Cycles emissive scrim"
    bl_options = {'REGISTER', 'UNDO'}

    shape: bpy.props.EnumProperty(name="Shape", items=SHAPE_ITEMS, default='RECTANGLE')
    width: bpy.props.FloatProperty(name="Width", default=2.0, min=0.001, soft_max=100.0, subtype='DISTANCE')
    height: bpy.props.FloatProperty(name="Height", default=2.0, min=0.001, soft_max=100.0, subtype='DISTANCE')
    feather: bpy.props.FloatProperty(name="Feather", default=0.2, min=0.0, max=1.0, subtype='FACTOR')
    gradient_direction: bpy.props.EnumProperty(
        name="Gradient",
        items=(
            ('NONE', "None", "Uniform emission"),
            ('X', "Horizontal", "Fade emission across the local X axis"),
            ('Y', "Vertical", "Fade emission across the local Y axis"),
            ('RADIAL', "Radial", "Fade emission from center to edge"),
        ),
        default='NONE',
    )
    gradient_amount: bpy.props.FloatProperty(name="Gradient Amount", default=0.5, min=0.0, max=1.0, subtype='FACTOR')
    color: bpy.props.FloatVectorProperty(
        name="Color", subtype='COLOR', size=3, default=(1.0, 1.0, 1.0), min=0.0, soft_max=1.0,
    )
    strength: bpy.props.FloatProperty(name="Strength", default=10.0, min=0.0, soft_max=1000.0)
    exposure: bpy.props.FloatProperty(name="Exposure", default=0.0, soft_min=-10.0, soft_max=10.0)
    visible_camera: bpy.props.BoolProperty(name="Camera Visible", default=False)

    @classmethod
    def poll(cls, context):
        if context.scene is None or context.scene.render.engine != 'CYCLES':
            cls.poll_message_set(p_("Scrims require Cycles"))
            return False
        return context.mode == 'OBJECT'

    def execute(self, context):
        try:
            obj = create_scrim(
                context.scene,
                shape=self.shape,
                width=self.width,
                height=self.height,
                feather=self.feather,
                gradient_direction=self.gradient_direction,
                gradient_amount=self.gradient_amount,
                color=self.color,
                strength=self.strength,
                exposure=self.exposure,
                visible_camera=self.visible_camera,
            )
        except (RuntimeError, StudioEngineError, ValueError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        _activate_created(context, obj)
        return {'FINISHED'}


class LLP_OT_create_flag(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_create_flag'
    bl_label = "Create Flag"
    bl_description = "Create a managed flag that blocks or shapes light"
    bl_options = {'REGISTER', 'UNDO'}

    shape: bpy.props.EnumProperty(name="Shape", items=SHAPE_ITEMS, default='RECTANGLE')
    width: bpy.props.FloatProperty(name="Width", default=2.0, min=0.001, soft_max=100.0, subtype='DISTANCE')
    height: bpy.props.FloatProperty(name="Height", default=2.0, min=0.001, soft_max=100.0, subtype='DISTANCE')
    thickness: bpy.props.FloatProperty(name="Thickness", default=0.02, min=0.0, soft_max=1.0, subtype='DISTANCE')
    color: bpy.props.FloatVectorProperty(
        name="Color", subtype='COLOR', size=3, default=(0.005, 0.005, 0.005), min=0.0, soft_max=1.0,
    )
    visible_camera: bpy.props.BoolProperty(name="Camera Visible", default=False)

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.mode == 'OBJECT'

    def execute(self, context):
        try:
            obj = create_flag(
                context.scene,
                shape=self.shape,
                width=self.width,
                height=self.height,
                thickness=self.thickness,
                color=self.color,
                visible_camera=self.visible_camera,
            )
        except (RuntimeError, ValueError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        _activate_created(context, obj)
        return {'FINISHED'}


class LLP_OT_create_reflector(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_create_reflector'
    bl_label = "Create Reflector"
    bl_description = "Create a managed Cycles diffuse reflector"
    bl_options = {'REGISTER', 'UNDO'}

    shape: bpy.props.EnumProperty(name="Shape", items=SHAPE_ITEMS, default='RECTANGLE')
    width: bpy.props.FloatProperty(name="Width", default=2.0, min=0.001, soft_max=100.0, subtype='DISTANCE')
    height: bpy.props.FloatProperty(name="Height", default=2.0, min=0.001, soft_max=100.0, subtype='DISTANCE')
    color: bpy.props.FloatVectorProperty(
        name="Color", subtype='COLOR', size=3, default=(1.0, 1.0, 1.0), min=0.0, soft_max=1.0,
    )
    reflectance: bpy.props.FloatProperty(name="Reflectance", default=0.8, min=0.0, max=1.0, subtype='FACTOR')
    roughness: bpy.props.FloatProperty(name="Roughness", default=0.5, min=0.0, max=1.0, subtype='FACTOR')

    @classmethod
    def poll(cls, context):
        if context.scene is None or context.scene.render.engine != 'CYCLES':
            cls.poll_message_set(p_("Reflectors require Cycles"))
            return False
        return context.mode == 'OBJECT'

    def execute(self, context):
        try:
            obj = create_reflector(
                context.scene,
                shape=self.shape,
                width=self.width,
                height=self.height,
                color=self.color,
                reflectance=self.reflectance,
                roughness=self.roughness,
            )
        except (RuntimeError, StudioEngineError, ValueError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        _activate_created(context, obj)
        return {'FINISHED'}


class LLP_OT_remove_studio_object(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_remove_studio_object'
    bl_label = "Remove Studio Object"
    bl_description = "Remove the active managed studio object and only its owned orphan data"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not is_studio_object(context.active_object):
            cls.poll_message_set(p_("No managed studio object selected"))
            return False
        return True

    def execute(self, context):
        if not remove_studio_object(context.active_object):
            self.report({'WARNING'}, p_("Studio object is read-only"))
            return {'CANCELLED'}
        return {'FINISHED'}


class LLP_OT_make_studio_single_user(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_make_studio_single_user'
    bl_label = "Make Studio Object Single User"
    bl_description = "Isolate mutable data and ownership after duplicating a managed studio object"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return is_studio_object(context.active_object)

    def execute(self, context):
        changed = ensure_unique_studio_data(context.active_object)
        if not changed:
            self.report({'INFO'}, p_("Studio object already has private data"))
        return {'FINISHED'}


class LLP_OT_add_track_target(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_add_track_target'
    bl_label = "Add Track Target"
    bl_description = "Make selected lights or studio objects track a managed target"
    bl_options = {'REGISTER', 'UNDO'}

    target_name: bpy.props.StringProperty(
        name="Target",
        description="Optional existing target object name; empty creates one managed target",
        default="",
        options={'SKIP_SAVE'},
    )

    @classmethod
    def poll(cls, context):
        candidates = [obj for obj in context.selected_objects if obj.type == 'LIGHT' or is_studio_object(obj)]
        if not candidates:
            cls.poll_message_set(p_("Select a light or managed studio object"))
            return False
        return context.scene is not None

    def execute(self, context):
        candidates = [obj for obj in context.selected_objects if obj.type == 'LIGHT' or is_studio_object(obj)]
        shared_target = bpy.data.objects.get(self.target_name) if self.target_name else None
        if self.target_name and shared_target is None:
            self.report({'ERROR'}, p_("Track target object not found"))
            return {'CANCELLED'}
        for source in candidates:
            _constraint, created_target = ensure_track_to(
                context.scene,
                source,
                shared_target,
                location=context.scene.cursor.location,
            )
            if shared_target is None:
                shared_target = created_target
        return {'FINISHED'}


class LLP_OT_remove_track_target(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_remove_track_target'
    bl_label = "Remove Track Target"
    bl_description = "Remove LightHelper Track To constraints and unused owned targets"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        removed = sum(remove_managed_track_to(obj) for obj in context.selected_objects)
        if not removed:
            self.report({'INFO'}, p_("No managed Track To constraints found"))
        return {'FINISHED'}


STUDIO_OPERATOR_CLASSES = (
    LLP_OT_create_scrim,
    LLP_OT_create_flag,
    LLP_OT_create_reflector,
    LLP_OT_remove_studio_object,
    LLP_OT_make_studio_single_user,
    LLP_OT_add_track_target,
    LLP_OT_remove_track_target,
)

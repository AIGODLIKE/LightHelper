import bpy
from bpy.app.translations import pgettext_iface as p_

from .common import LightHelperOperator, format_lights_report, get_light_obj


class LLP_OT_instances_data(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_instances_data'
    bl_label = "Instances Data"
    bl_description = "Make shared light linking collections single-user for this light"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        light_obj = get_light_obj(context)
        if not light_obj:
            cls.poll_message_set(p_("No light selected"))
            return False
        light = light_obj.light_linking
        receiver = getattr(light, "receiver_collection", None)
        if receiver and receiver.users > 1:
            return True
        blocker = getattr(light, "blocker_collection", None)
        if blocker and blocker.users > 1:
            return True
        cls.poll_message_set(p_("Light linking collections are not shared"))
        return False

    def execute(self, context):
        from ..utils import make_light_linking_single_user
        light_obj = get_light_obj(context)
        if light_obj is None:
            self.report({'ERROR'}, p_("No light selected"))
            return {"CANCELLED"}
        if not make_light_linking_single_user(light_obj):
            self.report({'WARNING'}, p_("Light linking collections are not shared"))
            return {"CANCELLED"}
        self.report({'INFO'}, p_("Light linking collections are now single-user"))
        return {"FINISHED"}


class LLP_OT_init_all_light_linking(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_init_all_light_linking'
    bl_label = "Init All Lights"
    bl_description = "Initialize light linking collections for all lights in the scene"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from ..utils import scene_has_uninitialized_lights
        if scene_has_uninitialized_lights(context.scene):
            return True
        cls.poll_message_set(p_("All lights are already initialized"))
        return False

    def execute(self, context):
        from ..utils import init_all_light_linking
        initialized = init_all_light_linking(context.scene, context)
        if not initialized:
            self.report({'WARNING'}, p_("All lights are already initialized"))
            return {"CANCELLED"}
        message = format_lights_report(
            initialized,
            p_("Initialized light linking for %d light(s): %s"),
            p_("Initialized light linking for %d light(s): %s, and %d more"),
        )
        self.report({'INFO'}, message)
        return {"FINISHED"}


class LLP_OT_instances_data_all(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_instances_data_all'
    bl_label = "Make All Single-User"
    bl_description = "Make shared light linking collections single-user for all lights in the scene"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from ..utils import has_shared_linking_collections
        for obj in context.scene.objects:
            if obj.type == 'LIGHT' and has_shared_linking_collections(obj):
                return True
        cls.poll_message_set(p_("No lights with shared linking collections"))
        return False

    def execute(self, context):
        from ..utils import fix_all_shared_light_linking
        fixed_lights = fix_all_shared_light_linking(context.scene)
        if not fixed_lights:
            self.report({'WARNING'}, p_("No lights with shared linking collections"))
            return {"CANCELLED"}
        message = format_lights_report(
            fixed_lights,
            p_("Made %d light(s) single-user: %s"),
            p_("Made %d light(s) single-user: %s, and %d more"),
        )
        self.report({'INFO'}, message)
        return {"FINISHED"}

import bpy

from . import light_groups, profiles
from .common import LightHelperOperator
from .desk import (
    DESK_CLASSES,
    LLP_OT_close_lighting_desk,
    LLP_OT_desk_set_channel,
    LLP_OT_desk_set_channel_bulk,
    LLP_OT_lighting_desk,
)
from .filter_ops import LLP_OT_invert_filter_show, LLP_OT_switch_filter_show
from .light_adjust import LLP_OT_adjust_light_ev, LLP_OT_reset_linking_hud, LLP_OT_solo_light
from .light_mixer import (
    LIGHT_MIXER_CLASSES,
    LLP_OT_light_mixer_batch,
    LLP_OT_light_mixer_collection_transform,
    LLP_OT_light_mixer_copy,
    LLP_OT_light_mixer_paste,
    LLP_OT_toggle_false_color,
    register_light_mixer_handlers,
    unregister_light_mixer_handlers,
)
from .maintenance import (
    LLP_OT_cleanup_legacy_data,
    LLP_OT_init_all_light_linking,
    LLP_OT_instances_data,
    LLP_OT_instances_data_all,
)
from .panel_linking import (
    LLP_OT_add_light_linking,
    LLP_OT_clear_light_linking,
    LLP_OT_clear_selected_light_linking,
    LLP_OT_link_selected_objs,
    LLP_OT_remove_light_linking,
    LLP_OT_set_item_channel_state,
    LLP_OT_set_linking_edit_mode,
    LLP_OT_toggle_light_linking,
)
from .placement import PLACEMENT_OPERATOR_CLASSES, LLP_OT_place_light, cancel_all_placements
from .selection import LLP_OT_select_item
from .studio import (
    STUDIO_OPERATOR_CLASSES,
    LLP_OT_add_track_target,
    LLP_OT_create_flag,
    LLP_OT_create_reflector,
    LLP_OT_create_scrim,
    LLP_OT_make_studio_single_user,
    LLP_OT_remove_studio_object,
    LLP_OT_remove_track_target,
)
from .tool_linking import (
    LLP_OT_light_linking_cycle_light,
    LLP_OT_light_linking_exit,
    LLP_OT_light_linking_hud_drag,
    LLP_OT_light_linking_pick,
    LLP_OT_light_linking_toggle_light,
    LLP_OT_light_linking_toggle_mode,
    LLP_OT_light_linking_toggle_overlay,
    LLP_OT_light_linking_toggle_shadow,
)
from .world_environment import (
    LLP_OT_convert_world_environment,
    LLP_OT_restore_world_environment,
    LLP_OT_select_world_environment_dome,
    LLP_OT_sync_world_sun_exclusions,
)

ops_list = [
    LLP_OT_remove_light_linking,
    LLP_OT_clear_light_linking,
    LLP_OT_clear_selected_light_linking,
    LLP_OT_add_light_linking,
    LLP_OT_toggle_light_linking,
    LLP_OT_link_selected_objs,
    LLP_OT_set_linking_edit_mode,
    LLP_OT_set_item_channel_state,
    LLP_OT_select_item,
    LLP_OT_cleanup_legacy_data,
    LLP_OT_instances_data,
    LLP_OT_init_all_light_linking,
    LLP_OT_instances_data_all,
    LLP_OT_switch_filter_show,
    LLP_OT_invert_filter_show,
    LLP_OT_adjust_light_ev,
    LLP_OT_reset_linking_hud,
    LLP_OT_solo_light,
    LLP_OT_light_linking_pick,
    LLP_OT_light_linking_hud_drag,
    LLP_OT_light_linking_toggle_light,
    LLP_OT_light_linking_toggle_shadow,
    LLP_OT_light_linking_toggle_mode,
    LLP_OT_light_linking_toggle_overlay,
    LLP_OT_light_linking_exit,
    LLP_OT_light_linking_cycle_light,
    LLP_OT_convert_world_environment,
    LLP_OT_restore_world_environment,
    LLP_OT_sync_world_sun_exclusions,
    LLP_OT_select_world_environment_dome,
    *DESK_CLASSES,
    *LIGHT_MIXER_CLASSES,
    *PLACEMENT_OPERATOR_CLASSES,
    *STUDIO_OPERATOR_CLASSES,
]
register_class, unregister_class = bpy.utils.register_classes_factory(ops_list)


def register():
    register_class()
    profiles.register()
    light_groups.register()
    register_light_mixer_handlers()


def unregister():
    cancel_all_placements()
    unregister_light_mixer_handlers()
    light_groups.unregister()
    profiles.unregister()
    # Session / draw-handler teardown lives in ui.unregister.
    unregister_class()


__all__ = [
    "LightHelperOperator",
    "LLP_OT_remove_light_linking",
    "LLP_OT_clear_light_linking",
    "LLP_OT_clear_selected_light_linking",
    "LLP_OT_add_light_linking",
    "LLP_OT_toggle_light_linking",
    "LLP_OT_link_selected_objs",
    "LLP_OT_set_linking_edit_mode",
    "LLP_OT_set_item_channel_state",
    "LLP_OT_select_item",
    "LLP_OT_cleanup_legacy_data",
    "LLP_OT_instances_data",
    "LLP_OT_init_all_light_linking",
    "LLP_OT_instances_data_all",
    "LLP_OT_switch_filter_show",
    "LLP_OT_invert_filter_show",
    "LLP_OT_adjust_light_ev",
    "LLP_OT_reset_linking_hud",
    "LLP_OT_solo_light",
    "LLP_OT_light_linking_pick",
    "LLP_OT_light_linking_hud_drag",
    "LLP_OT_light_linking_toggle_light",
    "LLP_OT_light_linking_toggle_shadow",
    "LLP_OT_light_linking_toggle_mode",
    "LLP_OT_light_linking_toggle_overlay",
    "LLP_OT_light_linking_exit",
    "LLP_OT_light_linking_cycle_light",
    "LLP_OT_convert_world_environment",
    "LLP_OT_restore_world_environment",
    "LLP_OT_sync_world_sun_exclusions",
    "LLP_OT_select_world_environment_dome",
    "LLP_OT_lighting_desk",
    "LLP_OT_close_lighting_desk",
    "LLP_OT_desk_set_channel",
    "LLP_OT_desk_set_channel_bulk",
    "LLP_OT_light_mixer_batch",
    "LLP_OT_light_mixer_copy",
    "LLP_OT_light_mixer_paste",
    "LLP_OT_light_mixer_collection_transform",
    "LLP_OT_toggle_false_color",
    "LLP_OT_place_light",
    "LLP_OT_create_scrim",
    "LLP_OT_create_flag",
    "LLP_OT_create_reflector",
    "LLP_OT_remove_studio_object",
    "LLP_OT_make_studio_single_user",
    "LLP_OT_add_track_target",
    "LLP_OT_remove_track_target",
    "profiles",
    "light_groups",
    "register",
    "unregister",
]

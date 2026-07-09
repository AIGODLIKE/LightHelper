import bpy

from .common import LightHelperOperator
from .filter_ops import LLP_OT_invert_filter_show, LLP_OT_switch_filter_show
from .maintenance import (
    LLP_OT_init_all_light_linking,
    LLP_OT_instances_data,
    LLP_OT_instances_data_all,
)
from .panel_linking import (
    LLP_OT_add_light_linking,
    LLP_OT_clear_light_linking,
    LLP_OT_link_selected_objs,
    LLP_OT_remove_light_linking,
    LLP_OT_toggle_light_linking,
)
from .question import LLP_OT_question
from .selection import LLP_OT_select_item
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

ops_list = [
    LLP_OT_question,
    LLP_OT_remove_light_linking,
    LLP_OT_clear_light_linking,
    LLP_OT_add_light_linking,
    LLP_OT_toggle_light_linking,
    LLP_OT_link_selected_objs,
    LLP_OT_select_item,
    LLP_OT_instances_data,
    LLP_OT_init_all_light_linking,
    LLP_OT_instances_data_all,
    LLP_OT_switch_filter_show,
    LLP_OT_invert_filter_show,
    LLP_OT_light_linking_pick,
    LLP_OT_light_linking_hud_drag,
    LLP_OT_light_linking_toggle_light,
    LLP_OT_light_linking_toggle_shadow,
    LLP_OT_light_linking_toggle_mode,
    LLP_OT_light_linking_toggle_overlay,
    LLP_OT_light_linking_exit,
    LLP_OT_light_linking_cycle_light,
]
register_class, unregister_class = bpy.utils.register_classes_factory(ops_list)


def register():
    register_class()


def unregister():
    # Session / draw-handler teardown lives in ui.tool.unregister.
    unregister_class()


__all__ = [
    "LightHelperOperator",
    "LLP_OT_question",
    "LLP_OT_remove_light_linking",
    "LLP_OT_clear_light_linking",
    "LLP_OT_add_light_linking",
    "LLP_OT_toggle_light_linking",
    "LLP_OT_link_selected_objs",
    "LLP_OT_select_item",
    "LLP_OT_instances_data",
    "LLP_OT_init_all_light_linking",
    "LLP_OT_instances_data_all",
    "LLP_OT_switch_filter_show",
    "LLP_OT_invert_filter_show",
    "LLP_OT_light_linking_pick",
    "LLP_OT_light_linking_hud_drag",
    "LLP_OT_light_linking_toggle_light",
    "LLP_OT_light_linking_toggle_shadow",
    "LLP_OT_light_linking_toggle_mode",
    "LLP_OT_light_linking_toggle_overlay",
    "LLP_OT_light_linking_exit",
    "LLP_OT_light_linking_cycle_light",
    "register",
    "unregister",
]

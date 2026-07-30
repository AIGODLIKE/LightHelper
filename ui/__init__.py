from . import panel
from . import ui_list
from . import tool
from . import desk
from . import placement_tool

module_list = [
    panel,
    ui_list,
    tool,
    placement_tool,
]


def register():
    for mod in module_list:
        mod.register()


def unregister():
    desk.cleanup_all_desks()
    for mod in reversed(module_list):
        mod.unregister()

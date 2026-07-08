from . import panel
from . import ui_list
from . import tool

module_list = [
    panel,
    ui_list,
    tool,
]


def register():
    for mod in module_list:
        mod.register()


def unregister():
    for mod in reversed(module_list):
        mod.unregister()

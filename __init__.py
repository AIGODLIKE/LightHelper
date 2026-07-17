from . import ui, property, ops, translation, preferences, handlers

module_list = [
    preferences,
    property,
    ops,
    ui,
    translation,
    handlers,
]


def register():
    for mod in module_list:
        mod.register()


def unregister():
    for mod in reversed(module_list):
        mod.unregister()

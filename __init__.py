from . import ui, property, ops, translation, preferences, migration

bl_info = {
    "name": "LightHelper",
    "author": "ACGGit Community,Atticus,小萌新",
    "blender": (4, 0, 0),
    "version": (0, 4, 7),
    "category": "Lighting",
    "support": "COMMUNITY",
    "doc_url": "",
    "tracker_url": "",
    "description": "",
    "location": "3D视图右侧控件栏",
}

module_list = [
    preferences,
    property,
    ops,
    ui,
    translation,
    migration,
]


def register():
    for mod in module_list:
        mod.register()


def unregister():
    for mod in reversed(module_list):
        mod.unregister()

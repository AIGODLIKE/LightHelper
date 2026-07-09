from . import ui, property, ops, translation, preferences, migration, handlers

bl_info = {
    "name": "Light Helper",
    "author": "ACGGit Community,Atticus,小萌新",
    "blender": (4, 2, 0),
    "version": (0, 4, 7),
    "category": "Lighting",
    "support": "COMMUNITY",
    "doc_url": "https://github.com/AIGODLIKE/LightHelper",
    "tracker_url": "https://github.com/AIGODLIKE/LightHelper/issues",
    "description": "Manage light linking and exclusions from the sidebar",
    "location": "3D Viewport > Sidebar",
}

module_list = [
    preferences,
    property,
    ops,
    ui,
    translation,
    migration,
    handlers,
]


def register():
    for mod in module_list:
        mod.register()


def unregister():
    for mod in reversed(module_list):
        mod.unregister()

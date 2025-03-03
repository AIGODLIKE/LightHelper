from . import ui, property, ops, translation, preferences

bl_info = {
    "name": "LightHelper",
    "author": "ACGGit Community,Atticus,小萌新",
    "blender": (4, 0, 0),
    "version": (0, 3, 9),
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
]


def register():
    for mod in module_list:
        mod.register()


def unregister():
    for mod in reversed(module_list):
        mod.unregister()


if __name__ == '__main__':
    register()

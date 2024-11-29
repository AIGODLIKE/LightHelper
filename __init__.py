bl_info = {
    "name": "LightHelper",
    "author": "ACGGit Community,Atticus,小萌新",
    "blender": (4, 0, 0),
    "version": (0, 3, 2),
    "category": "Render",
    "support": "COMMUNITY",
    "doc_url": "",
    "tracker_url": "",
    "description": "",
    "location": "3D视图右侧控件栏",
}

__ADDON_NAME__ = __name__

from . import panel, property, ops, translation, preferences

module_list = [
    preferences,
    property,
    ops,
    panel,
    translation,
]


def register():
    for mod in module_list:
        mod.register()


def unregister():
    for mod in module_list[::-1]:
        mod.unregister()


if __name__ == '__main__':
    register()

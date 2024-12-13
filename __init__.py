"""
例表,灯需要标示是否有链接表
无链接的需要有一个初始化按钮
有链接的需要有一个清除按钮
OUTLINER_DATA_LIGHT
OUTLINER_OB_LIGHT
"""
bl_info = {
    "name": "LightHelper",
    "author": "ACGGit Community,Atticus,小萌新",
    "blender": (4, 0, 0),
    "version": (0, 3, 3),
    "category": "Lighting",
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
    for mod in reversed(module_list):
        mod.unregister()


if __name__ == '__main__':
    register()

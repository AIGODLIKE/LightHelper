bl_info = {
    "name": "LightHelper",
    "author": "ACGGit Community,Atticus,小萌新",
    "blender": (4, 0, 0),
    "version": (0, 3, 2),
    "category": "AIGODLIKE",
    "support": "COMMUNITY",
    "doc_url": "",
    "tracker_url": "",
    "description": "",
    "location": "3D视图右侧控件栏",
}

__ADDON_NAME__ = __name__

from . import panel, property, ops, translation


def register():
    property.register()
    ops.register()
    panel.register()
    translation.register()


def unregister():
    panel.unregister()
    property.unregister()
    ops.unregister()
    translation.unregister()


if __name__ == '__main__':
    register()

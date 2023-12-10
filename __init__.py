bl_info = {
    "name": "LightHelper",
    "author": "AIGODLIKE社区,Atticus",
    "blender": (4, 0, 0),
    "version": (0, 2, 1),
    "category": "AIGODLIKE",
    "support": "COMMUNITY",
    "doc_url": "",
    "tracker_url": "",
    "description": "",
    "location": "3D视图右侧控件栏",
}

__ADDON_NAME__ = __name__

from . import panel, props, ops, translation


def register():
    props.register()
    ops.register()
    panel.register()
    translation.register()


def unregister():
    panel.unregister()
    props.unregister()
    ops.unregister()
    translation.unregister()


if __name__ == '__main__':
    register()

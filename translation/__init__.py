import bpy

from . import zh_HANS

zh_CN = None


def get_zh_language() -> str:
    if hasattr(bpy.app.translations, "locales"):
        for candidate in ("zh_HANS", "zh_CN"):
            if candidate in bpy.app.translations.locales:
                return candidate
    return "zh_HANS"


class TranslationHelper():
    def __init__(self, name: str, data: dict, lang='zh_HANS'):
        self.name = name
        self.translations_dict = dict()

        for src, src_trans in data.items():
            key = ("Operator", src)
            self.translations_dict.setdefault(lang, {})[key] = src_trans
            key = ("*", src)
            self.translations_dict.setdefault(lang, {})[key] = src_trans
            key = (name, src)
            self.translations_dict.setdefault(lang, {})[key] = src_trans

    def register(self):
        try:
            bpy.app.translations.register(self.name, self.translations_dict)
        except ValueError:
            pass

    def unregister(self):
        bpy.app.translations.unregister(self.name)


def register():
    global zh_CN
    language = get_zh_language()
    zh_CN = TranslationHelper('light_helper_zh_CN', zh_HANS.data, lang=language)
    zh_CN.register()


def unregister():
    if zh_CN is not None:
        zh_CN.unregister()

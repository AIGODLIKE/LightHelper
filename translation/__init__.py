import ast
import re

import bpy


def get_language_list() -> list:
    """
    Traceback (most recent call last):
  File "<blender_console>", line 1, in <module>
TypeError: bpy_struct: item.attr = val: enum "a" not found in ("DEFAULT", "en_US", "es", "ja_JP", "sk_SK", "vi_VN", "zh_HANS", "ar_EG", "de_DE", "fr_FR", "it_IT", "ko_KR", "pt_BR", "pt_PT", "ru_RU", "uk_UA", "zh_TW", "ab", "ca_AD", "cs_CZ", "eo", "eu_EU", "fa_IR", "ha", "he_IL", "hi_IN", "hr_HR", "hu_HU", "id_ID", "ky_KG", "nl_NL", "pl_PL", "sr_RS", "sr_RS@latin", "sv_SE", "th_TH", "tr_TR")
    """
    try:
        bpy.context.preferences.view.language = ""
    except TypeError as e:
        matches = re.findall(r"\(([^()]*)\)", e.args[-1])
        return ast.literal_eval(f"({matches[-1]})")


class TranslationHelper():
    def __init__(self, name: str, data: dict, lang='zh_CN'):
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
        except(ValueError):
            pass

    def unregister(self):
        bpy.app.translations.unregister(self.name)


# Set
############
from . import zh_HANS

all_language = get_language_list()

zh_CN = None


def register():
    global zh_CN

    language = "zh_CN"
    if language not in all_language:
        if language in ("zh_CN", "zh_HANS"):
            if "zh_CN" in all_language:
                language = "zh_CN"
            elif "zh_HANS" in all_language:
                language = "zh_HANS"
    zh_CN = TranslationHelper('light_helper_zh_CN', zh_HANS.data, lang=language)
    zh_CN.register()


def unregister():
    zh_CN.unregister()

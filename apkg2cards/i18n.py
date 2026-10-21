"""Traductions : t("clé", ...) renvoie le texte dans la langue courante."""
import locale
import os
import sys

LANGUAGES = {"fr": "Français", "en": "English"}
_strings = {}
_current = "en"


def _load(code):
    if code not in _strings:
        if code == "fr":
            from .locales.fr import STRINGS
        else:
            from .locales.en import STRINGS
        _strings[code] = STRINGS
    return _strings[code]


def detect_system_language():
    """'fr' si le système est en français, sinon 'en'."""
    try:
        if sys.platform.startswith("win"):
            import ctypes
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "fr" if (lang_id & 0x3FF) == 0x0C else "en"
    except Exception:  # noqa: BLE001
        pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
        value = os.environ.get(var, "")
        if value:
            return "fr" if value.lower().startswith("fr") else "en"
    try:
        return "fr" if (locale.getlocale()[0] or "").lower().startswith("fr") else "en"
    except Exception:  # noqa: BLE001
        return "en"


def set_language(code):
    global _current
    _current = code if code in LANGUAGES else "en"


def get_language():
    return _current


def t_in(lang, key, **fmt):
    """Texte `key` dans la langue `lang` (repli : anglais, puis la clé elle-même)."""
    code = lang if lang in LANGUAGES else "en"
    text = _load(code).get(key) or _load("en").get(key) or key
    return text.format(**fmt) if fmt else text


def t(key, **fmt):
    return t_in(_current, key, **fmt)


set_language(detect_system_language())

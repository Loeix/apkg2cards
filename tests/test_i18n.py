import os
import re
import string
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apkg2cards import i18n  # noqa: E402
from apkg2cards.core import ApkgError, card_labels  # noqa: E402


def fields(text):
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


class I18nTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def test_same_keys_in_every_language(self):
        fr, en = i18n._load("fr"), i18n._load("en")
        self.assertEqual(set(fr), set(en))

    def test_same_placeholders_in_every_language(self):
        fr, en = i18n._load("fr"), i18n._load("en")
        for key in fr:
            self.assertEqual(fields(fr[key]), fields(en[key]), key)

    def test_no_empty_strings(self):
        for code in i18n.LANGUAGES:
            for key, text in i18n._load(code).items():
                self.assertTrue(text.strip(), (code, key))

    def test_switch_language(self):
        i18n.set_language("fr")
        self.assertEqual(i18n.t("btn.generate"), "Générer le PDF")
        i18n.set_language("en")
        self.assertEqual(i18n.t("btn.generate"), "Generate PDF")

    def test_fallbacks(self):
        self.assertEqual(i18n.t_in("zz", "btn.generate"), "Generate PDF")  # langue inconnue
        self.assertEqual(i18n.t_in("fr", "cle.inconnue"), "cle.inconnue")  # clé inconnue

    def test_core_errors_follow_language(self):
        err = ApkgError("err.bad_color", value="zzz")
        i18n.set_language("fr")
        self.assertIn("Couleur invalide", str(err))
        i18n.set_language("en")
        self.assertIn("Invalid color", str(err))

    def test_card_labels(self):
        self.assertEqual(card_labels("fr"), ("QUESTION", "RÉPONSE"))
        self.assertEqual(card_labels("en"), ("QUESTION", "ANSWER"))
        i18n.set_language("fr")
        self.assertEqual(card_labels(), ("QUESTION", "RÉPONSE"))

    def test_all_keys_used_in_code_exist(self):
        root = os.path.join(os.path.dirname(__file__), "..", "apkg2cards")
        en = i18n._load("en")
        for name in ("core.py", "cli.py", "gui.py", "updater.py"):
            path = os.path.join(root, name)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                code = f.read()
            keys = re.findall(
                r"""\b(?:t|t_in|ApkgError|UpdateError|UpdateCancelled|_label|_button|_check|"""
                r"""_panel|set_status)\((?:[a-z_]+, )?["']([a-z_]+\.[a-z_.]+)["']""", code)
            keys += re.findall(r"""_reg\([^,()]+(?:\([^)]*\))?[^,()]*, ["']([a-z_]+\.[a-z_.]+)["']""", code)
            for key in keys:
                self.assertIn(key, en, f"{name}: clé manquante {key}")


if __name__ == "__main__":
    unittest.main()

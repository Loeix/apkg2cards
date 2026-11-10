import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

try:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtWidgets import QApplication

    from apkg2cards import formats as F
    from apkg2cards import i18n
    from apkg2cards.editor import FormatEditor
    from apkg2cards.gui import THEMES, CardView, MainWindow
    from apkg2cards.richcard import RichSide
except ImportError:  # PySide6 absent : on ignore ces tests
    QApplication = None

from qcm_fixture import make_qcm_apkg  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 indisponible")
class EditorTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"APKG2CARDS_CONFIG_DIR": self.tmp.name})
        self.env.start()  # formats enregistrés isolés (jamais ceux de l'utilisateur)
        self.settings = QSettings(os.path.join(self.tmp.name, "t.ini"), QSettings.IniFormat)
        self.settings.setValue("auto_check", False)
        self.settings.setValue("lang", "en")
        self.win = MainWindow(self.settings)
        self.win.show()
        self.win.load_collection(make_qcm_apkg(self.tmp.name))
        self.pump(lambda: self.win.collection is not None)

    def tearDown(self):
        self.win.pool.waitForDone(3000)
        if self.win.collection is not None:
            self.win.collection.close()
            self.win.collection = None
        self.win._timer.stop()
        self.win.close()
        self.win.deleteLater()
        self.app.processEvents()
        self.env.stop()
        self.tmp.cleanup()
        i18n.set_language("en")

    def pump(self, until, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end and not until():
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(until(), "délai dépassé")

    def editor(self):
        dlg = FormatEditor(self.win, self.win.collection, self.win.formats, self.win._opts(),
                           CardView, background=THEMES["light"]["panel"])
        self.addCleanup(dlg.deleteLater)
        return dlg

    def saved(self):
        path = F.formats_path()
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)["formats"]

    def test_main_window_has_formats_button(self):
        self.assertTrue(self.win.formats_btn.isEnabled())

    def test_qcm_detected_and_previewed(self):
        dlg = self.editor()
        dlg.name = None
        dlg._select_type(dlg.type_box.findData("QCM"))
        self.assertTrue(dlg.r_custom.isChecked())
        self.assertEqual(dlg.lists["front"].count(), 3)
        self.assertFalse(dlg.qcm_row.isHidden())
        self.pump(lambda: dlg.view_front._img is not None and dlg.view_back._img is not None)

    def test_back_mode_switch_and_save(self):
        dlg = self.editor()
        dlg._select_type(dlg.type_box.findData("QCM"))
        dlg.qcm_back.setCurrentIndex(dlg.qcm_back.findData("highlight"))
        self.assertEqual(F.back_choice_mode(dlg.fmt), "highlight")
        self.assertEqual(dlg.lists["back"].count(), 4)  # + la question répétée
        dlg._save()
        self.assertEqual(F.back_choice_mode(self.saved()["QCM"]), "highlight")
        card = self.win.collection.cards(model_name="QCM", formats_book=self.win.formats)[0]
        self.assertEqual(card[1].elements[2][3], "highlight")  # éléments : tag, titre, propositions

    def test_cancel_saves_nothing(self):
        dlg = self.editor()
        dlg._select_type(dlg.type_box.findData("QCM"))
        dlg.qcm_back.setCurrentIndex(dlg.qcm_back.findData("highlight"))
        dlg.reject()
        self.assertEqual(self.saved(), {})
        self.assertEqual(self.win.formats.formats, {})

    def test_auto_mode_is_remembered_and_reset_forgets_it(self):
        dlg = self.editor()
        dlg._select_type(dlg.type_box.findData("QCM"))
        dlg.r_auto.setChecked(True)
        self.assertFalse(dlg.left.isEnabled())
        dlg._save()
        self.assertEqual(self.saved()["QCM"]["mode"], "auto")
        card = self.win.collection.cards(model_name="QCM", formats_book=self.win.formats)[0]
        self.assertNotIsInstance(card[0], RichSide)
        dlg2 = self.editor()
        dlg2._select_type(dlg2.type_box.findData("QCM"))
        dlg2._reset()
        dlg2._save()
        self.assertNotIn("QCM", self.saved())
        card = self.win.collection.cards(model_name="QCM", formats_book=self.win.formats)[0]
        self.assertIsInstance(card[0], RichSide)  # reconnu automatiquement de nouveau

    def test_edit_blocks_on_a_basic_note_type(self):
        dlg = self.editor()
        dlg._select_type(dlg.type_box.findData("Basique"))
        self.assertTrue(dlg.r_auto.isChecked())
        dlg.r_custom.setChecked(True)  # propose un point de départ à partir des champs
        self.assertEqual(dlg.lists["front"].count(), 1)
        self.assertEqual(dlg.lists["back"].count(), 1)
        dlg.lists["back"].setCurrentRow(0)  # sélection d'un bloc « champ »
        self.assertEqual(dlg.stack.currentIndex(), 1)
        dlg.f_style.setCurrentIndex(dlg.f_style.findData("explain"))
        dlg.f_label.setText("Note")
        self.assertEqual(dlg.fmt["back"][0]["style"], "explain")
        self.assertEqual(dlg.fmt["back"][0]["label"], "Note")
        dlg._add("back", F.field_block("@deck", "tag"))
        self.assertEqual(dlg.lists["back"].count(), 2)
        dlg._move("back", -1)
        self.assertEqual(dlg.fmt["back"][0]["field"], "@deck")
        dlg._remove("back")
        self.assertEqual(dlg.lists["back"].count(), 1)
        dlg._save()
        self.assertEqual(self.saved()["Basique"]["back"][0]["label"], "Note")

    def test_choices_block_properties(self):
        dlg = self.editor()
        dlg._select_type(dlg.type_box.findData("QCM"))
        dlg.lists["front"].setCurrentRow(2)  # bloc « propositions »
        self.assertEqual(dlg.stack.currentIndex(), 2)
        self.assertTrue(dlg.c_show_row.isHidden())  # au recto : toujours sans mise en valeur
        dlg.c_fields.item(dlg.c_fields.count() - 2).setCheckState(Qt.Unchecked)  # retire « Reponse »
        dlg.c_answer.setCurrentIndex(dlg.c_answer.findData(""))
        self.assertEqual(dlg.fmt["front"][2]["answer"], "")

    def test_empty_custom_format_is_refused(self):
        dlg = self.editor()
        dlg._select_type(dlg.type_box.findData("Basique"))
        dlg.r_custom.setChecked(True)
        for side in ("front", "back"):
            while dlg.fmt[side]:
                dlg.lists[side].setCurrentRow(0)
                dlg._remove(side)
        with mock.patch("apkg2cards.editor.QMessageBox.warning") as warn:
            dlg._save()
        warn.assert_called_once()
        self.assertEqual(self.saved(), {})


if __name__ == "__main__":
    unittest.main()

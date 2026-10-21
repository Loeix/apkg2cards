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
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from apkg2cards import __version__, i18n, updater
    from apkg2cards.gui import MainWindow, UpdateDialog
except ImportError:  # PySide6 absent : on ignore ces tests
    QApplication = None

from test_core import make_apkg  # noqa: E402

INFO = {"available": True, "version": "99.0.0", "tag": "v99.0.0", "url": "https://example.test/r",
        "notes": "## Nouveautés\n\n- une chose", "prerelease": False, "channel": "stable",
        "asset_url": "https://example.test/setup.exe", "asset_name": "apkg2cards-setup.exe",
        "asset_size": 10, "sha256": "a" * 64, "sha_url": None}


@unittest.skipIf(QApplication is None, "PySide6 indisponible")
class GuiTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.tmp = tempfile.TemporaryDirectory()
        # réglages isolés (jamais ceux de l'utilisateur), sans vérification réseau au démarrage
        self.settings = QSettings(os.path.join(self.tmp.name, "t.ini"), QSettings.IniFormat)
        self.settings.setValue("auto_check", False)
        self.settings.setValue("lang", "en")
        self.win = MainWindow(self.settings)
        self.win.show()

    def tearDown(self):
        self.win.pool.waitForDone(3000)
        if self.win.collection is not None:
            self.win.collection.close()
            self.win.collection = None
        self.win.close()
        self.tmp.cleanup()
        i18n.set_language("en")

    def pump(self, until, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end and not until():
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(until(), "délai dépassé")

    def test_loads_deck_and_previews(self):
        w = self.win
        w.load_collection(make_apkg(self.tmp.name))
        self.pump(lambda: w.deck_box.count() > 1)
        self.assertEqual(w.deck_box.count(), 3)  # tous + 2 paquets
        w.set_color("#16a34a")
        self.pump(lambda: "deck" in w.prev_sub.text())
        self.assertIn("First card", w.prev_sub.text())

    def test_language_switch_retranslates_everything(self):
        w = self.win
        self.assertEqual(w.go_btn.text(), "Generate PDF")
        w.lang_box.setCurrentIndex(w.lang_box.findData("fr"))
        self.assertEqual(w.go_btn.text(), "Générer le PDF")
        self.assertEqual(w.windowTitle(), "apkg2cards — flashcards à imprimer")
        self.assertEqual(w.deck_box.itemText(0), "(tous les paquets)")
        self.assertIn("Choisis un fichier", w.status.text())
        self.assertEqual(w.theme_btn.text(), "☾  Sombre" if w.theme == "light" else "☀  Clair")
        w.lang_box.setCurrentIndex(w.lang_box.findData("en"))
        self.assertEqual(w.go_btn.text(), "Generate PDF")
        self.assertEqual(w.flip.itemText(1), "Short edge")

    def test_language_is_remembered(self):
        w = self.win
        w.lang_box.setCurrentIndex(w.lang_box.findData("fr"))
        w.save_settings()
        self.assertEqual(self.settings.value("lang"), "fr")

    def test_background_check_shows_banner(self):
        w = self.win
        with mock.patch.object(updater, "check_for_update", return_value=INFO):
            w.check_update(manual=False)
            self.pump(lambda: not w.update_banner.isHidden())
        self.assertIn("99.0.0", w.update_banner.text())

    def test_channel_is_passed_to_updater(self):
        w = self.win
        with mock.patch.object(updater, "check_for_update",
                               return_value=dict(INFO, available=False, channel="beta")) as chk:
            w.channel.setCurrentIndex(w.channel.findData("beta"))
            self.pump(lambda: chk.called)
        self.assertEqual(chk.call_args[0], (__version__, "beta"))

    def test_update_dialog_downloads_launches_and_quits(self):
        w = self.win
        installer = os.path.join(self.tmp.name, "setup.exe")

        def fake_download(info, progress=None, should_cancel=None):
            progress(5, 10)
            return installer

        with mock.patch.object(updater, "can_self_update", return_value=True), \
                mock.patch.object(updater, "download_installer", side_effect=fake_download), \
                mock.patch.object(updater, "launch_installer") as launch, \
                mock.patch.object(QApplication, "quit") as quit_app:
            d = UpdateDialog(w, INFO)
            d.show()
            d.go.click()
            self.pump(lambda: launch.called)
            self.pump(lambda: quit_app.called)
        launch.assert_called_once_with(installer)

    def test_update_dialog_shows_error_and_allows_retry(self):
        w = self.win
        err = updater.UpdateError("upd.err.checksum")
        with mock.patch.object(updater, "can_self_update", return_value=True), \
                mock.patch.object(updater, "download_installer", side_effect=err), \
                mock.patch.object(updater, "launch_installer") as launch:
            d = UpdateDialog(w, INFO)
            d.show()
            d.go.click()
            self.pump(lambda: d.go.isEnabled())
            self.assertIn("corrupted", d.msg.text())
        launch.assert_not_called()

    def test_dialog_outside_installed_app_opens_download_page(self):
        w = self.win
        with mock.patch.object(updater, "can_self_update", return_value=False), \
                mock.patch("apkg2cards.gui.QDesktopServices.openUrl") as open_url:
            d = UpdateDialog(w, INFO)
            d.show()
            self.assertEqual(d.go.text(), "Open download page")
            d.go.click()
        open_url.assert_called_once()


if __name__ == "__main__":
    unittest.main()

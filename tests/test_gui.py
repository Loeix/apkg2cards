import os
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

try:
    from PySide6.QtWidgets import QApplication

    from apkg2cards.gui import MainWindow
except ImportError as e:  # PySide6 absent : on ignore ce test
    QApplication = None
    _why = str(e)

from test_core import make_apkg  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 indisponible")
class GuiTests(unittest.TestCase):
    def pump(self, app, until, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end and not until():
            app.processEvents()
            time.sleep(0.01)

    def test_window_loads_deck_and_previews(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as d:
            apkg = make_apkg(d)
            w = MainWindow()
            w.show()
            w.apply_theme("dark")
            w.apply_theme("light")
            w.load_collection(apkg)
            self.pump(app, lambda: w.deck_box.count() > 1)
            self.assertEqual(w.deck_box.count(), 3)  # tous + 2 paquets
            w.set_color("#16a34a")
            self.pump(app, lambda: "paquet" in w.prev_sub.text())
            self.assertIn("paquet", w.prev_sub.text())
            w.collection.close()
            w.collection = None
            w.pool.waitForDone(2000)
            w.close()


if __name__ == "__main__":
    unittest.main()

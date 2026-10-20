"""Interface graphique PySide6 : aperçu en direct, thème clair/sombre."""
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request

from PySide6.QtCore import (QBuffer, QByteArray, QIODevice, QObject, QPointF, QRect, QRunnable,
                            QSettings, QSize, Qt, QThreadPool, QTimer, QUrl, Signal)
from PySide6.QtGui import QColor, QDesktopServices, QImage, QPainter, QPalette, QPen
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox,
                               QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
                               QSizePolicy, QSpinBox, QVBoxLayout, QWidget)

from . import __version__
from .core import DEFAULT_COLOR, ApkgError, Collection, convert, render_preview

ALL_DECKS = "(tous les paquets)"
PALETTE = ["#2563eb", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#db2777", "#0d9488", "#475569"]
ACCENT, ACCENT_HOVER = "#2563eb", "#1d4ed8"
RELEASES_API = "https://api.github.com/repos/Loeix/apkg2cards/releases/latest"

THEMES = {
    "light": dict(bg="#f3f4f6", panel="#ffffff", border="#e2e5ea", text="#1f2937",
                  muted="#6b7280", input="#ffffff", btn="#f3f4f6", btn_hover="#e5e7eb",
                  edge="#c4c9d1"),
    "dark": dict(bg="#121418", panel="#1c1f26", border="#2c313a", text="#e5e7eb",
                 muted="#9ca3af", input="#14161b", btn="#262a33", btn_hover="#313642",
                 edge="#475063"),
}


def make_icons(name, t):
    """Dessine les petites icônes de l'interface dans un dossier temporaire."""
    folder = os.path.join(tempfile.gettempdir(), f"apkg2cards-ui-{name}")
    os.makedirs(folder, exist_ok=True)
    shapes = {"down": ([(8, 12), (16, 20), (24, 12)], t["muted"]),
              "up": ([(8, 20), (16, 12), (24, 20)], t["muted"]),
              "check": ([(7, 17), (13, 23), (25, 9)], "#ffffff")}
    for key, (pts, color) in shapes.items():
        img = QImage(32, 32, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(color), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline([QPointF(x, y) for x, y in pts])
        p.end()
        img.save(os.path.join(folder, key + ".png"))
    return folder.replace("\\", "/")


def build_qss(t, icons):
    return f"""
    QWidget {{ color: {t['text']}; font-size: 13px; }}
    QMainWindow, QWidget#root {{ background: {t['bg']}; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QFrame#panel {{ background: {t['panel']}; border: 1px solid {t['border']};
                    border-radius: 12px; }}
    QLabel {{ background: transparent; }}
    QLabel#title {{ font-size: 14px; font-weight: 600; }}
    QLabel#appname {{ font-size: 18px; font-weight: 700; }}
    QLabel#muted {{ color: {t['muted']}; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {t['input']}; border: 1px solid {t['border']}; border-radius: 8px;
        padding: 5px 8px; min-height: 20px; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {ACCENT}; }}
    QComboBox QAbstractItemView {{ background: {t['panel']}; border: 1px solid {t['border']};
        selection-background-color: {ACCENT}; selection-color: white; outline: none; }}
    QPushButton {{ background: {t['btn']}; border: 1px solid {t['border']};
                   border-radius: 8px; padding: 6px 14px; }}
    QPushButton:hover {{ background: {t['btn_hover']}; }}
    QPushButton:disabled {{ color: {t['muted']}; }}
    QPushButton#primary {{ background: {ACCENT}; border: none; color: white;
                           font-weight: 600; padding: 11px 16px; font-size: 14px; }}
    QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
    QPushButton#primary:disabled {{ background: {t['border']}; color: {t['muted']}; }}
    QProgressBar {{ border: none; border-radius: 4px; background: {t['border']};
                    max-height: 8px; min-height: 8px; }}
    QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
    QCheckBox {{ spacing: 8px; background: transparent; }}
    QToolTip {{ background: {t['panel']}; color: {t['text']}; border: 1px solid {t['border']}; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox::down-arrow {{ image: url({icons}/down.png); width: 12px; height: 12px; }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        subcontrol-origin: border; subcontrol-position: top right; width: 22px; border: none;
        background: transparent; }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border: none;
        background: transparent; }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        image: url({icons}/up.png); width: 10px; height: 10px; }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        image: url({icons}/down.png); width: 10px; height: 10px; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px;
        border: 1px solid {t['edge']}; background: {t['input']}; }}
    QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT};
        image: url({icons}/check.png); }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t['edge']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    """


def make_palette(t):
    p = QPalette()
    for role, key in [(QPalette.Window, "bg"), (QPalette.Base, "input"),
                      (QPalette.AlternateBase, "panel"), (QPalette.Button, "btn"),
                      (QPalette.WindowText, "text"), (QPalette.Text, "text"),
                      (QPalette.ButtonText, "text"), (QPalette.ToolTipBase, "panel"),
                      (QPalette.ToolTipText, "text"), (QPalette.PlaceholderText, "muted")]:
        p.setColor(role, QColor(t[key]))
    p.setColor(QPalette.Highlight, QColor(ACCENT))
    p.setColor(QPalette.HighlightedText, QColor("white"))
    return p


def system_theme():
    try:
        dark = QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        return "dark" if dark else "light"
    except Exception:  # noqa: BLE001
        return "light"


def as_bool(v, default=False):
    if v is None:
        return default
    return str(v).lower() in ("true", "1", "yes")


def check_latest():
    """Cherche une nouvelle version sur GitHub. Renvoie (message, lien ou None)."""
    def parse(v):
        return tuple(int(x) for x in re.findall(r"\d+", v)[:3])

    link = None
    try:
        req = urllib.request.Request(
            RELEASES_API,
            headers={"User-Agent": "apkg2cards", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        latest = data.get("tag_name", "")
        if parse(latest) > parse(__version__):
            link = data.get("html_url")
            msg = (f"Nouvelle version disponible : {latest}\n"
                   f"Version installée : v{__version__}")
        else:
            msg = f"Tu as la dernière version (v{__version__})."
    except urllib.error.HTTPError as e:
        msg = ("Aucune version publiée sur GitHub pour le moment."
               if e.code == 404 else f"Erreur GitHub (code {e.code}).")
    except Exception as e:  # noqa: BLE001
        msg = f"Impossible de vérifier les mises à jour.\n\nDétail : {e}"
    return msg, link


# --------------------------------------------------------------------------
# Tâches de fond
# --------------------------------------------------------------------------
class _Signals(QObject):
    done = Signal(object)
    error = Signal(str)
    progress = Signal(int, int)


class Task(QRunnable):
    def __init__(self, fn, with_progress=False):
        super().__init__()
        self.setAutoDelete(False)  # on garde la référence côté fenêtre
        self.fn, self.with_progress = fn, with_progress
        self.signals = _Signals()

    def run(self):
        try:
            if self.with_progress:
                res = self.fn(lambda d, t: self.signals.progress.emit(d, t))
            else:
                res = self.fn()
        except ApkgError as e:
            self.signals.error.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.signals.error.emit(f"Erreur inattendue : {e}")
        else:
            self.signals.done.emit(res)


# --------------------------------------------------------------------------
# Widgets
# --------------------------------------------------------------------------
class CardView(QWidget):
    """Affiche l'image d'une carte, mise à l'échelle sans déformation."""

    def __init__(self):
        super().__init__()
        self._img = None
        self._text = ""
        self.setMinimumSize(170, 130)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_image(self, img):
        self._img, self._text = img, ""
        self.update()

    def set_text(self, text):
        self._img, self._text = None, text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if self._img is None:
            p.setPen(self.palette().color(QPalette.PlaceholderText))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, self._text)
            return
        size = QSize(self._img.size())
        size.scale(self.size(), Qt.KeepAspectRatio)
        x, y = (self.width() - size.width()) // 2, (self.height() - size.height()) // 2
        p.drawImage(QRect(x, y, size.width(), size.height()), self._img)


def muted(text="", wrap=False):
    lbl = QLabel(text)
    lbl.setObjectName("muted")
    lbl.setWordWrap(wrap)
    return lbl


def panel(title):
    frame = QFrame()
    frame.setObjectName("panel")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 16)
    lay.setSpacing(10)
    t = QLabel(title)
    t.setObjectName("title")
    lay.addWidget(t)
    return frame, lay


# --------------------------------------------------------------------------
# Fenêtre principale
# --------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("apkg2cards — flashcards à imprimer")
        self.setAcceptDrops(True)
        self.resize(1100, 820)
        self.setMinimumSize(980, 700)

        self.settings = QSettings("apkg2cards", "apkg2cards")
        self.pool = QThreadPool.globalInstance()
        self._tasks = set()
        self.collection = None
        self.apkg_path = ""
        self.last_pdf = None
        self.color = DEFAULT_COLOR
        self.theme = "light"
        self._gen = 0
        self._swatches = []

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh_preview)

        self._build_ui()
        self._load_settings()
        self.apply_theme(self.theme)

    # -- construction de l'interface ---------------------------------------
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 14, 18, 18)
        outer.setSpacing(12)

        # en-tête
        head = QHBoxLayout()
        name = QLabel("apkg2cards")
        name.setObjectName("appname")
        head.addWidget(name)
        head.addWidget(muted(f"v{__version__}"))
        head.addStretch(1)
        self.update_btn = QPushButton("Rechercher une mise à jour")
        self.update_btn.clicked.connect(self.check_update)
        head.addWidget(self.update_btn)
        self.theme_btn = QPushButton()
        self.theme_btn.setToolTip("Basculer entre le thème clair et sombre")
        self.theme_btn.clicked.connect(self.toggle_theme)
        head.addWidget(self.theme_btn)
        outer.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(14)
        outer.addLayout(body, 1)

        # colonne gauche : réglages (défilante) + actions
        left = QVBoxLayout()
        left.setSpacing(12)
        body.addLayout(left, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(440)
        inner = QWidget()
        sl = QVBoxLayout(inner)
        sl.setContentsMargins(0, 0, 6, 0)
        sl.setSpacing(12)
        scroll.setWidget(inner)
        left.addWidget(scroll, 1)

        # -- fichiers
        files, fl = panel("Fichiers")
        self.apkg_edit = QLineEdit()
        self.apkg_edit.setPlaceholderText("Choisis ou glisse un fichier .apkg ici")
        self.apkg_edit.editingFinished.connect(self._apkg_typed)
        b = QPushButton("Parcourir…")
        b.clicked.connect(self.pick_apkg)
        row = QHBoxLayout()
        row.addWidget(self.apkg_edit, 1)
        row.addWidget(b)
        fl.addLayout(row)

        self.deck_box = QComboBox()
        self.deck_box.addItem(ALL_DECKS)
        self.deck_box.currentIndexChanged.connect(self.schedule_preview)
        fl.addWidget(muted("Paquet à imprimer"))
        fl.addWidget(self.deck_box)

        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("PDF de sortie")
        b2 = QPushButton("Choisir…")
        b2.clicked.connect(self.pick_out)
        row = QHBoxLayout()
        row.addWidget(self.out_edit, 1)
        row.addWidget(b2)
        fl.addWidget(muted("PDF de sortie"))
        fl.addLayout(row)
        sl.addWidget(files)

        # -- couleur
        col_panel, cl = panel("Couleur des cartes")
        sw_row = QHBoxLayout()
        sw_row.setSpacing(8)
        for hexa in PALETTE:
            sw_row.addWidget(self._make_swatch(hexa))
        self.custom_sw = self._make_swatch("#888888")
        self.custom_sw.hide()
        sw_row.addWidget(self.custom_sw)
        other = QPushButton("Autre…")
        other.clicked.connect(self.pick_color)
        sw_row.addWidget(other)
        sw_row.addStretch(1)
        cl.addLayout(sw_row)
        sl.addWidget(col_panel)

        # -- mise en page
        lay_panel, ll = panel("Mise en page")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        def spin(cls, lo, hi, val, step=1):
            w = cls()
            w.setRange(lo, hi)
            w.setValue(val)
            w.setSingleStep(step)
            w.setMinimumWidth(78)
            w.valueChanged.connect(self.schedule_preview)
            return w

        self.cols = spin(QSpinBox, 1, 6, 2)
        self.rows = spin(QSpinBox, 1, 8, 4)
        self.margin = spin(QDoubleSpinBox, 0, 30, 8, 1)
        self.margin.setDecimals(0)
        self.font = spin(QDoubleSpinBox, 6, 40, 16, 1)
        self.font.setDecimals(0)
        grid.addWidget(muted("Colonnes"), 0, 0)
        grid.addWidget(self.cols, 0, 1)
        grid.addWidget(muted("Lignes"), 0, 2)
        grid.addWidget(self.rows, 0, 3)
        grid.addWidget(muted("Marge (mm)"), 1, 0)
        grid.addWidget(self.margin, 1, 1)
        grid.addWidget(muted("Texte max (pt)"), 1, 2)
        grid.addWidget(self.font, 1, 3)
        ll.addLayout(grid)

        self.landscape = QCheckBox("Page en paysage")
        self.landscape.toggled.connect(self.schedule_preview)
        self.reversed = QCheckBox("Inclure aussi les cartes inversées (doublons recto/verso)")
        self.reversed.toggled.connect(self.schedule_preview)
        ll.addWidget(self.landscape)
        ll.addWidget(self.reversed)

        ll.addWidget(muted("Retournement choisi à l'impression"))
        self.flip = QComboBox()
        self.flip.addItem("Bord long (le plus courant en portrait)", "long")
        self.flip.addItem("Bord court", "short")
        ll.addWidget(self.flip)
        sl.addWidget(lay_panel)

        sl.addWidget(muted(
            "Impression : recto-verso, retournement sur le bord long (portrait), échelle 100 %. "
            "Fais un test sur une feuille avant le paquet entier.", wrap=True))
        sl.addStretch(1)

        # -- actions (toujours visibles)
        self.go_btn = QPushButton("Générer le PDF")
        self.go_btn.setObjectName("primary")
        self.go_btn.setCursor(Qt.PointingHandCursor)
        self.go_btn.clicked.connect(self.start)
        left.addWidget(self.go_btn)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setValue(0)
        left.addWidget(self.bar)
        self.status = muted("Choisis un fichier .apkg pour commencer.", wrap=True)
        self.status.setFixedWidth(440)
        left.addWidget(self.status)
        self.open_btn = QPushButton("Ouvrir le PDF")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self.open_pdf)
        left.addWidget(self.open_btn)

        # colonne droite : aperçu
        prev, pl = panel("Aperçu")
        self.prev_sub = muted("")
        pl.addWidget(self.prev_sub)
        cards = QHBoxLayout()
        cards.setSpacing(16)
        self.view_front, self.view_back = CardView(), CardView()
        for caption, view in (("RECTO", self.view_front), ("VERSO", self.view_back)):
            colw = QVBoxLayout()
            cap = muted(caption)
            cap.setAlignment(Qt.AlignCenter)
            colw.addWidget(cap)
            colw.addWidget(view, 1)
            cards.addLayout(colw, 1)
        pl.addLayout(cards, 1)
        self.prev_info = muted("")
        self.prev_info.setAlignment(Qt.AlignCenter)
        pl.addWidget(self.prev_info)
        body.addWidget(prev, 1)

    def _make_swatch(self, hexa):
        btn = QPushButton()
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(hexa)
        btn.setProperty("hexa", hexa)
        btn.clicked.connect(lambda _=False, h=hexa: self.set_color(h))
        self._swatches.append(btn)
        return btn

    def _style_swatches(self):
        t = THEMES[self.theme]
        for btn in self._swatches:
            hexa = btn.property("hexa")
            selected = hexa.lower() == self.color.lower()
            border = f"3px solid {t['text']}" if selected else f"2px solid {t['border']}"
            btn.setStyleSheet(f"QPushButton {{ background: {hexa}; border: {border}; "
                              f"border-radius: 14px; padding: 0; }}")

    # -- thème ---------------------------------------------------------------
    def apply_theme(self, name):
        self.theme = name
        t = THEMES[name]
        app = QApplication.instance()
        try:  # barre de titre sombre (Qt récent)
            app.styleHints().setColorScheme(
                Qt.ColorScheme.Dark if name == "dark" else Qt.ColorScheme.Light)
        except Exception:  # noqa: BLE001
            pass
        app.setPalette(make_palette(t))
        app.setStyleSheet(build_qss(t, make_icons(name, t)))
        self.theme_btn.setText("☀  Clair" if name == "dark" else "☾  Sombre")
        self._style_swatches()
        self.schedule_preview()

    def toggle_theme(self):
        self.apply_theme("light" if self.theme == "dark" else "dark")

    # -- couleur -------------------------------------------------------------
    def set_color(self, hexa):
        self.color = hexa
        if hexa.lower() not in [p.lower() for p in PALETTE]:
            self.custom_sw.setProperty("hexa", hexa)
            self.custom_sw.setToolTip(hexa)
            self.custom_sw.show()
        self._style_swatches()
        self.schedule_preview()

    def pick_color(self):
        c = QColorDialog.getColor(QColor(self.color), self, "Couleur des cartes")
        if c.isValid():
            self.set_color(c.name())

    # -- fichiers --------------------------------------------------------------
    def pick_apkg(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choisir un paquet Anki", "",
                                           "Paquet Anki (*.apkg);;Tous les fichiers (*)")
        if p:
            self.load_collection(p)

    def pick_out(self):
        p, _ = QFileDialog.getSaveFileName(self, "Enregistrer le PDF", self.out_edit.text(),
                                           "PDF (*.pdf)")
        if p:
            self.out_edit.setText(p)

    def _apkg_typed(self):
        p = self.apkg_edit.text().strip()
        if p and p != self.apkg_path and os.path.isfile(p):
            self.load_collection(p)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and any(u.toLocalFile().lower().endswith(".apkg")
                                          for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.toLocalFile().lower().endswith(".apkg"):
                self.load_collection(u.toLocalFile())
                break

    def load_collection(self, path):
        self.apkg_path = path
        self.apkg_edit.setText(path)
        self.out_edit.setText(os.path.splitext(path)[0] + "_cartes.pdf")
        self.set_status("Chargement du paquet…")
        task = Task(lambda: Collection(path))
        task.signals.done.connect(lambda col, p=path: self._collection_loaded(col, p))
        task.signals.error.connect(self._collection_failed)
        self._run(task)

    def _collection_loaded(self, col, path):
        if path != self.apkg_path:  # l'utilisateur a changé de fichier entre-temps
            col.close()
            return
        if self.collection is not None:
            self.collection.close()
        self.collection = col
        self.deck_box.blockSignals(True)
        self.deck_box.clear()
        self.deck_box.addItem(ALL_DECKS)
        self.deck_box.addItems(col.deck_names())
        self.deck_box.blockSignals(False)
        self.set_status("Paquet chargé.")
        self.schedule_preview()

    def _collection_failed(self, msg):
        self.set_status(f"Erreur : {msg}")
        QMessageBox.critical(self, "Fichier invalide", msg)

    # -- aperçu en direct --------------------------------------------------------
    def _opts(self):
        return dict(cols=self.cols.value(), rows=self.rows.value(),
                    margin=float(self.margin.value()), font_size=float(self.font.value()),
                    landscape=self.landscape.isChecked(),
                    include_reversed=self.reversed.isChecked(), color=self.color)

    def _deck(self):
        return None if self.deck_box.currentIndex() <= 0 else self.deck_box.currentText()

    def schedule_preview(self, *_):
        self._timer.start(120)

    def refresh_preview(self):
        self._gen += 1
        gen, col, deck, opts = self._gen, self.collection, self._deck(), self._opts()
        bg = THEMES[self.theme]["panel"]

        def work():
            r = render_preview(col, deck=deck, background=bg, **opts)
            r["gen"] = gen
            return r

        task = Task(work)
        task.signals.done.connect(self._show_preview)
        task.signals.error.connect(self._preview_failed)
        self._run(task)

    def _show_preview(self, r):
        if r["gen"] != self._gen:
            return
        buf = QBuffer()
        buf.setData(QByteArray(r["pdf"]))
        buf.open(QIODevice.ReadOnly)
        doc = QPdfDocument()
        doc.load(buf)
        if doc.status() != QPdfDocument.Status.Ready:
            self._preview_failed("rendu impossible")
            return
        scale = 2.6 * self.devicePixelRatioF()
        imgs = []
        for i in (0, 1):
            ps = doc.pagePointSize(i)
            imgs.append(doc.render(i, QSize(int(ps.width() * scale), int(ps.height() * scale))))
        doc.close()
        buf.close()
        self.view_front.set_image(imgs[0])
        self.view_back.set_image(imgs[1])
        self.prev_sub.setText("Exemple de carte" if r["sample"]
                              else "Première carte de ton paquet")
        w, h = r["card_mm"]
        o = self._opts()
        self.prev_info.setText(f"Carte de {w:.0f} × {h:.0f} mm · "
                               f"{o['cols'] * o['rows']} cartes par page")

    def _preview_failed(self, msg):
        for v in (self.view_front, self.view_back):
            v.set_text(f"Aperçu indisponible\n{msg}")
        self.prev_info.setText("")

    # -- conversion ----------------------------------------------------------------
    def start(self):
        if not self.apkg_path:
            QMessageBox.warning(self, "Fichier manquant", "Choisis d'abord un fichier .apkg.")
            return
        args = dict(apkg=self.apkg_path, output=self.out_edit.text().strip() or None,
                    deck=self._deck(), flip=self.flip.currentData(), **self._opts())
        self.go_btn.setEnabled(False)
        self.open_btn.setEnabled(False)
        self.bar.setValue(0)
        self.set_status("Conversion en cours…")
        task = Task(lambda progress: convert(**args, on_progress=progress), with_progress=True)
        task.signals.progress.connect(self._progress)
        task.signals.done.connect(self._converted)
        task.signals.error.connect(self._convert_failed)
        self._run(task)

    def _progress(self, done, total):
        self.bar.setMaximum(total)
        self.bar.setValue(done)

    def _converted(self, r):
        self.last_pdf = r["output"]
        txt = f"{r['cards']} cartes → {r['pages']} pages (recto-verso)."
        if r["overflow"]:
            txt += f" {r['overflow']} face(s) très longue(s) : texte fortement réduit."
        self.set_status(txt)
        self.go_btn.setEnabled(True)
        self.open_btn.setEnabled(True)

    def _convert_failed(self, msg):
        self.set_status(f"Erreur : {msg}")
        self.go_btn.setEnabled(True)
        QMessageBox.critical(self, "Échec", msg)

    def open_pdf(self):
        if self.last_pdf and os.path.exists(self.last_pdf):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_pdf))

    # -- mise à jour -------------------------------------------------------------------
    def check_update(self):
        self.set_status("Recherche de mise à jour…")
        self.update_btn.setEnabled(False)
        task = Task(check_latest)
        task.signals.done.connect(self._update_result)
        task.signals.error.connect(self._convert_failed)
        self._run(task)

    def _update_result(self, res):
        msg, link = res
        self.update_btn.setEnabled(True)
        self.set_status(msg.split("\n")[0])
        if link:
            ans = QMessageBox.question(self, "Mise à jour",
                                       msg + "\n\nOuvrir la page de téléchargement ?")
            if ans == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl(link))
        else:
            QMessageBox.information(self, "Mise à jour", msg)

    # -- divers ---------------------------------------------------------------------------
    def set_status(self, text):
        self.status.setText(text)

    def _run(self, task):
        self._tasks.add(task)

        def cleanup(*_):
            self._tasks.discard(task)

        task.signals.done.connect(cleanup)
        task.signals.error.connect(cleanup)
        self.pool.start(task)

    def _load_settings(self):
        s = self.settings
        self.theme = s.value("theme", system_theme())
        if self.theme not in THEMES:
            self.theme = "light"
        self.cols.setValue(int(s.value("cols", 2)))
        self.rows.setValue(int(s.value("rows", 4)))
        self.margin.setValue(float(s.value("margin", 8)))
        self.font.setValue(float(s.value("font", 16)))
        self.landscape.setChecked(as_bool(s.value("landscape"), False))
        self.reversed.setChecked(as_bool(s.value("reversed"), False))
        i = self.flip.findData(s.value("flip", "long"))
        self.flip.setCurrentIndex(max(i, 0))
        self.color = s.value("color", DEFAULT_COLOR)
        if self.color.lower() not in [p.lower() for p in PALETTE]:
            self.custom_sw.setProperty("hexa", self.color)
            self.custom_sw.setToolTip(self.color)
            self.custom_sw.show()

    def closeEvent(self, e):
        s = self.settings
        s.setValue("theme", self.theme)
        s.setValue("cols", self.cols.value())
        s.setValue("rows", self.rows.value())
        s.setValue("margin", self.margin.value())
        s.setValue("font", self.font.value())
        s.setValue("landscape", self.landscape.isChecked())
        s.setValue("reversed", self.reversed.isChecked())
        s.setValue("flip", self.flip.currentData())
        s.setValue("color", self.color)
        self.pool.waitForDone(2000)
        if self.collection is not None:
            self.collection.close()
        super().closeEvent(e)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("apkg2cards")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

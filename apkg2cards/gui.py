"""Interface graphique PySide6 : aperçu en direct, thème clair/sombre, FR/EN, mises à jour."""
import os
import sys
import tempfile

from PySide6.QtCore import (QBuffer, QByteArray, QIODevice, QLibraryInfo, QObject, QPointF, QRect,
                            QRunnable, QSettings, QSize, Qt, QThreadPool, QTimer, QTranslator,
                            QUrl, Signal)
from PySide6.QtGui import QColor, QDesktopServices, QImage, QPainter, QPalette, QPen
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDialog,
                               QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
                               QPushButton, QScrollArea, QSizePolicy, QSpinBox, QTextBrowser,
                               QVBoxLayout, QWidget)

from . import __version__, updater
from .core import DEFAULT_COLOR, ApkgError, Collection, convert, render_preview
from .i18n import LANGUAGES, detect_system_language, get_language, set_language, t
from .updater import UpdateError

PALETTE = ["#2563eb", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#db2777", "#0d9488", "#475569"]
ACCENT, ACCENT_HOVER = "#2563eb", "#1d4ed8"
GREEN, GREEN_HOVER = "#16a34a", "#15803d"

THEMES = {
    "light": dict(bg="#f3f4f6", panel="#ffffff", border="#e2e5ea", text="#1f2937",
                  muted="#6b7280", input="#ffffff", btn="#f3f4f6", btn_hover="#e5e7eb",
                  edge="#c4c9d1", error="#b91c1c"),
    "dark": dict(bg="#121418", panel="#1c1f26", border="#2c313a", text="#e5e7eb",
                 muted="#9ca3af", input="#14161b", btn="#262a33", btn_hover="#313642",
                 edge="#475063", error="#f87171"),
}


def make_icons(name, t_):
    """Dessine les petites icônes de l'interface (flèches, coche) dans un dossier temporaire."""
    folder = os.path.join(tempfile.gettempdir(), f"apkg2cards-ui-{name}")
    os.makedirs(folder, exist_ok=True)
    shapes = {"down": ([(8, 12), (16, 20), (24, 12)], t_["muted"]),
              "up": ([(8, 20), (16, 12), (24, 20)], t_["muted"]),
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


def build_qss(t_, icons):
    return f"""
    QWidget {{ color: {t_['text']}; font-size: 13px; }}
    QMainWindow, QDialog, QWidget#root {{ background: {t_['bg']}; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QFrame#panel {{ background: {t_['panel']}; border: 1px solid {t_['border']};
                    border-radius: 12px; }}
    QLabel {{ background: transparent; }}
    QLabel#title {{ font-size: 14px; font-weight: 600; }}
    QLabel#heading {{ font-size: 16px; font-weight: 700; }}
    QLabel#appname {{ font-size: 18px; font-weight: 700; }}
    QLabel#muted {{ color: {t_['muted']}; }}
    QLabel#error {{ color: {t_['error']}; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextBrowser {{
        background: {t_['input']}; border: 1px solid {t_['border']}; border-radius: 8px;
        padding: 5px 8px; min-height: 20px; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {ACCENT}; }}
    QComboBox QAbstractItemView {{ background: {t_['panel']}; border: 1px solid {t_['border']};
        selection-background-color: {ACCENT}; selection-color: white; outline: none; }}
    QPushButton {{ background: {t_['btn']}; border: 1px solid {t_['border']};
                   border-radius: 8px; padding: 6px 14px; }}
    QPushButton:hover {{ background: {t_['btn_hover']}; }}
    QPushButton:disabled {{ color: {t_['muted']}; }}
    QPushButton#primary {{ background: {ACCENT}; border: none; color: white;
                           font-weight: 600; padding: 11px 16px; font-size: 14px; }}
    QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
    QPushButton#primary:disabled {{ background: {t_['border']}; color: {t_['muted']}; }}
    QPushButton#banner {{ background: {GREEN}; border: none; color: white; font-weight: 600; }}
    QPushButton#banner:hover {{ background: {GREEN_HOVER}; }}
    QProgressBar {{ border: none; border-radius: 4px; background: {t_['border']};
                    max-height: 8px; min-height: 8px; }}
    QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
    QCheckBox {{ spacing: 8px; background: transparent; }}
    QToolTip {{ background: {t_['panel']}; color: {t_['text']}; border: 1px solid {t_['border']}; }}
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
        border: 1px solid {t_['edge']}; background: {t_['input']}; }}
    QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT};
        image: url({icons}/check.png); }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t_['edge']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    """


def make_palette(t_):
    p = QPalette()
    for role, key in [(QPalette.Window, "bg"), (QPalette.Base, "input"),
                      (QPalette.AlternateBase, "panel"), (QPalette.Button, "btn"),
                      (QPalette.WindowText, "text"), (QPalette.Text, "text"),
                      (QPalette.ButtonText, "text"), (QPalette.ToolTipBase, "panel"),
                      (QPalette.ToolTipText, "text"), (QPalette.PlaceholderText, "muted")]:
        p.setColor(role, QColor(t_[key]))
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


def install_qt_translations(app, lang, holder):
    """Traduit les boîtes de dialogue propres à Qt (sélecteur de couleur...) si possible."""
    for tr in holder:
        app.removeTranslator(tr)
    holder.clear()
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for base in ("qtbase", "qt"):
        tr = QTranslator()
        if tr.load(f"{base}_{lang}", folder):
            app.installTranslator(tr)
            holder.append(tr)


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
                res = self.fn(lambda d, tot: self.signals.progress.emit(int(d), int(tot)))
            else:
                res = self.fn()
        except (ApkgError, UpdateError) as e:
            self.signals.error.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.signals.error.emit(t("err.unexpected", detail=str(e)))
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


def label(text="", object_name=None, wrap=False):
    lbl = QLabel(text)
    if object_name:
        lbl.setObjectName(object_name)
    lbl.setWordWrap(wrap)
    return lbl


def panel():
    """Cadre arrondi avec un titre ; renvoie (cadre, mise en page, étiquette du titre)."""
    frame = QFrame()
    frame.setObjectName("panel")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 16)
    lay.setSpacing(10)
    title = label(object_name="title")
    lay.addWidget(title)
    return frame, lay, title


class UpdateDialog(QDialog):
    """Notes de version + téléchargement vérifié + installation silencieuse."""

    def __init__(self, win, info):
        super().__init__(win)
        self.win, self.info = win, info
        self._busy = False
        self._cancel = False
        self.setWindowTitle(t("upd.dlg.title"))
        self.setMinimumWidth(540)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(10)
        lay.addWidget(label(t("upd.dlg.heading", v=info["version"]), "heading"))
        sub = t("upd.dlg.current", v=__version__)
        if info["prerelease"]:
            sub += "  ·  " + t("upd.dlg.beta_badge")
        lay.addWidget(label(sub, "muted"))
        lay.addWidget(label(t("upd.dlg.notes"), "title"))
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        self.notes.setMinimumHeight(190)
        self.notes.setMarkdown(info.get("notes") or t("upd.dlg.no_notes"))
        lay.addWidget(self.notes, 1)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.hide()
        lay.addWidget(self.bar)
        self.msg = label("", "muted", wrap=True)
        self.msg.hide()
        lay.addWidget(self.msg)
        if not updater.can_self_update():
            self.msg.setText(t("upd.dlg.manual"))
            self.msg.show()

        row = QHBoxLayout()
        row.addStretch(1)
        self.later = QPushButton(t("upd.dlg.later"))
        self.later.clicked.connect(self.reject)
        self.go = QPushButton(t("upd.dlg.install") if updater.can_self_update()
                              else t("upd.dlg.open_page"))
        self.go.setObjectName("primary")
        self.go.clicked.connect(self._on_go)
        row.addWidget(self.later)
        row.addWidget(self.go)
        lay.addLayout(row)

    def _on_go(self):
        if not updater.can_self_update():
            QDesktopServices.openUrl(QUrl(self.info["url"]))
            self.accept()
            return
        self._busy, self._cancel = True, False
        self.go.setEnabled(False)
        self.later.setText(t("upd.dlg.cancel"))
        self.msg.setObjectName("muted")
        self.msg.setStyleSheet("")
        self.bar.setRange(0, 0)  # animation d'attente tant que la taille est inconnue
        self.bar.show()
        self.msg.setText(t("upd.dlg.downloading", done="0.0", total="?"))
        self.msg.show()
        info = self.info
        task = Task(lambda progress: updater.download_installer(
            info, progress=progress, should_cancel=lambda: self._cancel), with_progress=True)
        task.signals.progress.connect(self._progress)
        task.signals.done.connect(self._downloaded)
        task.signals.error.connect(self._failed)
        self.win._run(task)

    def _progress(self, done, total):
        if total:
            self.bar.setRange(0, total)
            self.bar.setValue(done)
        self.msg.setText(t("upd.dlg.downloading", done=f"{done / 1e6:.1f}",
                           total=f"{total / 1e6:.1f}" if total else "?"))

    def _downloaded(self, path):
        self.bar.setRange(0, 0)
        self.msg.setText(t("upd.dlg.installing"))
        try:
            updater.launch_installer(path)
        except UpdateError as e:
            self._failed(str(e))
            return
        self.win.save_settings()
        self.accept()
        QApplication.quit()  # l'installateur remplace les fichiers puis relance l'application

    def _failed(self, message):
        self._busy = False
        self.bar.hide()
        self.msg.setObjectName("error")
        self.msg.setStyleSheet(f"color: {THEMES[self.win.theme]['error']};")
        self.msg.setText(message)
        self.msg.show()
        self.go.setEnabled(True)
        self.later.setText(t("upd.dlg.later"))

    def reject(self):
        if self._busy:  # pendant le téléchargement : on annule seulement le téléchargement
            self._cancel = True
            self.later.setEnabled(False)
            return
        super().reject()


# --------------------------------------------------------------------------
# Fenêtre principale
# --------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.setAcceptDrops(True)
        self.resize(1100, 860)
        self.setMinimumSize(980, 700)

        self.settings = settings or QSettings("apkg2cards", "apkg2cards")
        self.pool = QThreadPool.globalInstance()
        self._tasks = set()
        self._tr = []          # (fonction, clé, paramètres) : textes à retraduire
        self._qt_tr = []
        self._status = ("status.start", {})
        self.collection = None
        self.apkg_path = ""
        self.last_pdf = None
        self.update_info = None
        self.color = DEFAULT_COLOR
        self.theme = "light"
        self._gen = 0
        self._swatches = []

        lang = self.settings.value("lang") or detect_system_language()
        set_language(lang if lang in LANGUAGES else "en")
        install_qt_translations(QApplication.instance(), get_language(), self._qt_tr)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh_preview)

        self._build_ui()
        self._load_settings()
        self.apply_theme(self.theme)
        self.retranslate()
        QTimer.singleShot(2500, self._auto_check)

    # -- aides de traduction -------------------------------------------------
    def _reg(self, setter, key, **fmt):
        """Applique un texte traduit et mémorise comment le retraduire."""
        self._tr.append((setter, key, fmt))
        setter(t(key, **fmt))

    def _label(self, key, object_name="muted", wrap=False, **fmt):
        lbl = label("", object_name, wrap)
        self._reg(lbl.setText, key, **fmt)
        return lbl

    def _button(self, key, slot=None):
        b = QPushButton()
        self._reg(b.setText, key)
        if slot:
            b.clicked.connect(slot)
        return b

    def _check(self, key, slot):
        c = QCheckBox()
        self._reg(c.setText, key)
        c.toggled.connect(slot)
        return c

    def _panel(self, key):
        frame, lay, title = panel()
        self._reg(title.setText, key)
        return frame, lay

    def retranslate(self):
        for setter, key, fmt in self._tr:
            setter(t(key, **fmt))
        self.setWindowTitle(t("app.title"))
        self.flip.setItemText(0, t("flip.long"))
        self.flip.setItemText(1, t("flip.short"))
        self.deck_box.setItemText(0, t("deck.all"))
        self.card_lang.setItemText(0, t("card_lang.auto"))
        self.channel.setItemText(0, t("channel.stable"))
        self.channel.setItemText(1, t("channel.beta"))
        self._refresh_theme_btn()
        self._refresh_banner()
        self.set_status(*self._status[:1], **self._status[1])
        self.schedule_preview()

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
        head.addWidget(label("apkg2cards", "appname"))
        head.addWidget(label(f"v{__version__}", "muted"))
        head.addStretch(1)
        self.update_banner = QPushButton()
        self.update_banner.setObjectName("banner")
        self.update_banner.setCursor(Qt.PointingHandCursor)
        self.update_banner.clicked.connect(self.show_update_dialog)
        self.update_banner.hide()
        head.addWidget(self.update_banner)
        self.lang_box = QComboBox()
        for code, name in LANGUAGES.items():
            self.lang_box.addItem(name, code)
        self.lang_box.setCurrentIndex(max(self.lang_box.findData(get_language()), 0))
        self.lang_box.currentIndexChanged.connect(self._language_changed)
        self._reg(self.lang_box.setToolTip, "lang.tip")
        head.addWidget(self.lang_box)
        self.theme_btn = QPushButton()
        self._reg(self.theme_btn.setToolTip, "theme.tip")
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
        files, fl = self._panel("panel.files")
        self.apkg_edit = QLineEdit()
        self._reg(self.apkg_edit.setPlaceholderText, "files.apkg_ph")
        self.apkg_edit.editingFinished.connect(self._apkg_typed)
        row = QHBoxLayout()
        row.addWidget(self.apkg_edit, 1)
        row.addWidget(self._button("btn.browse", self.pick_apkg))
        fl.addLayout(row)

        fl.addWidget(self._label("files.deck"))
        self.deck_box = QComboBox()
        self.deck_box.addItem("")
        self.deck_box.currentIndexChanged.connect(self.schedule_preview)
        fl.addWidget(self.deck_box)

        fl.addWidget(self._label("files.out"))
        self.out_edit = QLineEdit()
        self._reg(self.out_edit.setPlaceholderText, "files.out_ph")
        row = QHBoxLayout()
        row.addWidget(self.out_edit, 1)
        row.addWidget(self._button("btn.choose", self.pick_out))
        fl.addLayout(row)
        sl.addWidget(files)

        # -- couleur
        col_panel, cl = self._panel("panel.color")
        sw_row = QHBoxLayout()
        sw_row.setSpacing(8)
        for hexa in PALETTE:
            sw_row.addWidget(self._make_swatch(hexa))
        self.custom_sw = self._make_swatch("#888888")
        self.custom_sw.hide()
        sw_row.addWidget(self.custom_sw)
        sw_row.addWidget(self._button("btn.other", self.pick_color))
        sw_row.addStretch(1)
        cl.addLayout(sw_row)
        sl.addWidget(col_panel)

        # -- mise en page
        lay_panel, ll = self._panel("panel.layout")
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
        grid.addWidget(self._label("layout.cols"), 0, 0)
        grid.addWidget(self.cols, 0, 1)
        grid.addWidget(self._label("layout.rows"), 0, 2)
        grid.addWidget(self.rows, 0, 3)
        grid.addWidget(self._label("layout.margin"), 1, 0)
        grid.addWidget(self.margin, 1, 1)
        grid.addWidget(self._label("layout.font"), 1, 2)
        grid.addWidget(self.font, 1, 3)
        ll.addLayout(grid)

        self.landscape = self._check("layout.landscape", self.schedule_preview)
        self.reversed = self._check("layout.reversed", self.schedule_preview)
        ll.addWidget(self.landscape)
        ll.addWidget(self.reversed)

        ll.addWidget(self._label("layout.flip"))
        self.flip = QComboBox()
        self.flip.addItem("", "long")
        self.flip.addItem("", "short")
        ll.addWidget(self.flip)

        ll.addWidget(self._label("layout.card_lang"))
        self.card_lang = QComboBox()
        self.card_lang.addItem("", "auto")
        for code, name in LANGUAGES.items():
            self.card_lang.addItem(name, code)
        self.card_lang.currentIndexChanged.connect(self.schedule_preview)
        ll.addWidget(self.card_lang)
        sl.addWidget(lay_panel)

        sl.addWidget(self._label("note.print", wrap=True))

        # -- application : canal et mises à jour
        app_panel, al = self._panel("panel.app")
        al.addWidget(self._label("app.channel"))
        self.channel = QComboBox()
        self.channel.addItem("", "stable")
        self.channel.addItem("", "beta")
        self._reg(self.channel.setToolTip, "channel.tip")
        self.channel.currentIndexChanged.connect(self._channel_changed)
        al.addWidget(self.channel)
        self.autocheck = self._check("app.autocheck", lambda *_: None)
        al.addWidget(self.autocheck)
        row = QHBoxLayout()
        self.check_btn = self._button("btn.check_update", lambda: self.check_update(manual=True))
        row.addWidget(self.check_btn)
        row.addStretch(1)
        row.addWidget(self._label("app.version", v=__version__))
        al.addLayout(row)
        sl.addWidget(app_panel)
        sl.addStretch(1)

        # -- actions (toujours visibles)
        self.go_btn = self._button("btn.generate", self.start)
        self.go_btn.setObjectName("primary")
        self.go_btn.setCursor(Qt.PointingHandCursor)
        left.addWidget(self.go_btn)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setValue(0)
        left.addWidget(self.bar)
        self.status = label("", "muted", wrap=True)
        self.status.setFixedWidth(440)
        left.addWidget(self.status)
        self.open_btn = self._button("btn.open", self.open_pdf)
        self.open_btn.setEnabled(False)
        left.addWidget(self.open_btn)

        # colonne droite : aperçu
        prev, pl = self._panel("preview.title")
        self.prev_sub = label("", "muted")
        pl.addWidget(self.prev_sub)
        cards = QHBoxLayout()
        cards.setSpacing(16)
        self.view_front, self.view_back = CardView(), CardView()
        for key, view in (("preview.recto", self.view_front), ("preview.verso", self.view_back)):
            colw = QVBoxLayout()
            cap = self._label(key)
            cap.setAlignment(Qt.AlignCenter)
            colw.addWidget(cap)
            colw.addWidget(view, 1)
            cards.addLayout(colw, 1)
        pl.addLayout(cards, 1)
        self.prev_info = label("", "muted")
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
        t_ = THEMES[self.theme]
        for btn in self._swatches:
            hexa = btn.property("hexa")
            selected = hexa.lower() == self.color.lower()
            border = f"3px solid {t_['text']}" if selected else f"2px solid {t_['border']}"
            btn.setStyleSheet(f"QPushButton {{ background: {hexa}; border: {border}; "
                              f"border-radius: 14px; padding: 0; }}")

    # -- langue --------------------------------------------------------------
    def _language_changed(self, _=None):
        code = self.lang_box.currentData()
        set_language(code)
        install_qt_translations(QApplication.instance(), code, self._qt_tr)
        self.retranslate()

    # -- thème ---------------------------------------------------------------
    def apply_theme(self, name):
        self.theme = name
        t_ = THEMES[name]
        app = QApplication.instance()
        try:  # barre de titre sombre (Qt récent)
            app.styleHints().setColorScheme(
                Qt.ColorScheme.Dark if name == "dark" else Qt.ColorScheme.Light)
        except Exception:  # noqa: BLE001
            pass
        app.setPalette(make_palette(t_))
        app.setStyleSheet(build_qss(t_, make_icons(name, t_)))
        self._refresh_theme_btn()
        self._style_swatches()
        self.schedule_preview()

    def _refresh_theme_btn(self):
        self.theme_btn.setText(t("theme.to_light") if self.theme == "dark" else t("theme.to_dark"))

    def toggle_theme(self):
        self.apply_theme("light" if self.theme == "dark" else "dark")

    # -- couleur -------------------------------------------------------------
    def set_color(self, hexa):
        self.color = hexa
        self._show_custom_swatch(hexa)
        self._style_swatches()
        self.schedule_preview()

    def _show_custom_swatch(self, hexa):
        if hexa.lower() not in [p.lower() for p in PALETTE]:
            self.custom_sw.setProperty("hexa", hexa)
            self.custom_sw.setToolTip(hexa)
            self.custom_sw.show()

    def pick_color(self):
        c = QColorDialog.getColor(QColor(self.color), self, t("dlg.color"))
        if c.isValid():
            self.set_color(c.name())

    # -- fichiers --------------------------------------------------------------
    def pick_apkg(self):
        p, _ = QFileDialog.getOpenFileName(self, t("dlg.pick_apkg"), "", t("filter.apkg"))
        if p:
            self.load_collection(p)

    def pick_out(self):
        p, _ = QFileDialog.getSaveFileName(self, t("dlg.save_pdf"), self.out_edit.text(),
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
        self.set_status("status.loading")
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
        self.deck_box.addItem(t("deck.all"))
        self.deck_box.addItems(col.deck_names())
        self.deck_box.blockSignals(False)
        self.set_status("status.loaded")
        self.schedule_preview()

    def _collection_failed(self, msg):
        self.set_status("status.error", msg=msg)
        QMessageBox.critical(self, t("dlg.invalid_file"), msg)

    # -- aperçu en direct --------------------------------------------------------
    def _card_lang(self):
        code = self.card_lang.currentData()
        return get_language() if code == "auto" else code

    def _opts(self):
        return dict(cols=self.cols.value(), rows=self.rows.value(),
                    margin=float(self.margin.value()), font_size=float(self.font.value()),
                    landscape=self.landscape.isChecked(),
                    include_reversed=self.reversed.isChecked(), color=self.color,
                    lang=self._card_lang())

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
            self._preview_failed(t("preview.render_failed"))
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
        self.prev_sub.setText(t("preview.sample") if r["sample"] else t("preview.first"))
        w, h = r["card_mm"]
        o = self._opts()
        self.prev_info.setText(t("preview.info", w=f"{w:.0f}", h=f"{h:.0f}",
                                 n=o["cols"] * o["rows"]))

    def _preview_failed(self, msg):
        for v in (self.view_front, self.view_back):
            v.set_text(t("preview.unavailable", msg=msg))
        self.prev_info.setText("")

    # -- conversion ----------------------------------------------------------------
    def start(self):
        if not self.apkg_path:
            QMessageBox.warning(self, t("dlg.missing_file"), t("dlg.choose_first"))
            return
        args = dict(apkg=self.apkg_path, output=self.out_edit.text().strip() or None,
                    deck=self._deck(), flip=self.flip.currentData(), **self._opts())
        self.go_btn.setEnabled(False)
        self.open_btn.setEnabled(False)
        self.bar.setValue(0)
        self.set_status("status.converting")
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
        self.set_status("status.done", cards=r["cards"], pages=r["pages"])
        if r["overflow"]:
            self.status.setText(self.status.text() + t("status.overflow", n=r["overflow"]))
        self.go_btn.setEnabled(True)
        self.open_btn.setEnabled(True)

    def _convert_failed(self, msg):
        self.set_status("status.error", msg=msg)
        self.go_btn.setEnabled(True)
        QMessageBox.critical(self, t("dlg.failed"), msg)

    def open_pdf(self):
        if self.last_pdf and os.path.exists(self.last_pdf):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_pdf))

    # -- mises à jour ----------------------------------------------------------------
    def _channel_changed(self, _=None):
        self.update_info = None
        self._refresh_banner()
        if self._ready:
            self.check_update(manual=False)

    def _auto_check(self):
        if self.autocheck.isChecked():
            self.check_update(manual=False)

    def check_update(self, manual=True):
        channel = self.channel.currentData()
        if manual:
            self.set_status("upd.checking")
            self.check_btn.setEnabled(False)
        task = Task(lambda: updater.check_for_update(__version__, channel))
        task.signals.done.connect(lambda info, m=manual: self._update_checked(info, m))
        task.signals.error.connect(lambda msg, m=manual: self._update_check_failed(msg, m))
        self._run(task)

    def _update_checked(self, info, manual):
        self.check_btn.setEnabled(True)
        if info["channel"] != self.channel.currentData():
            return  # le canal a changé pendant la vérification
        if info["available"]:
            self.update_info = info
            self._refresh_banner()
            self.set_status("upd.available", v=info["version"])
            if manual:
                self.show_update_dialog()
        else:
            self.update_info = None
            self._refresh_banner()
            if manual:
                self.set_status("upd.up_to_date", v=__version__,
                                channel=self.channel.currentText())
                QMessageBox.information(self, t("dlg.update"), self.status.text())

    def _update_check_failed(self, msg, manual):
        self.check_btn.setEnabled(True)
        if manual:  # au démarrage, on reste silencieux
            self.set_status("status.error", msg=msg)
            QMessageBox.critical(self, t("dlg.update"), msg)

    def _refresh_banner(self):
        if self.update_info:
            self.update_banner.setText(t("upd.banner", v=self.update_info["version"]))
            self.update_banner.show()
        else:
            self.update_banner.hide()

    def show_update_dialog(self):
        if self.update_info:
            UpdateDialog(self, self.update_info).exec()

    # -- divers ---------------------------------------------------------------------------
    def set_status(self, key, **fmt):
        self._status = (key, fmt)
        self.status.setText(t(key, **fmt))

    def _run(self, task):
        self._tasks.add(task)

        def cleanup(*_):
            self._tasks.discard(task)

        task.signals.done.connect(cleanup)
        task.signals.error.connect(cleanup)
        self.pool.start(task)

    _ready = False

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
        self.flip.setCurrentIndex(max(self.flip.findData(s.value("flip", "long")), 0))
        self.card_lang.setCurrentIndex(max(self.card_lang.findData(s.value("card_lang", "auto")), 0))
        self.autocheck.setChecked(as_bool(s.value("auto_check"), True))
        self.channel.setCurrentIndex(max(self.channel.findData(s.value("channel", "stable")), 0))
        self.color = s.value("color", DEFAULT_COLOR)
        self._show_custom_swatch(self.color)
        self._ready = True

    def save_settings(self):
        s = self.settings
        s.setValue("lang", get_language())
        s.setValue("theme", self.theme)
        s.setValue("cols", self.cols.value())
        s.setValue("rows", self.rows.value())
        s.setValue("margin", self.margin.value())
        s.setValue("font", self.font.value())
        s.setValue("landscape", self.landscape.isChecked())
        s.setValue("reversed", self.reversed.isChecked())
        s.setValue("flip", self.flip.currentData())
        s.setValue("card_lang", self.card_lang.currentData())
        s.setValue("auto_check", self.autocheck.isChecked())
        s.setValue("channel", self.channel.currentData())
        s.setValue("color", self.color)
        s.sync()

    def closeEvent(self, e):
        self.save_settings()
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

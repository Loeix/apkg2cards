"""Éditeur de formats de notes : choisir, pour chaque type de note, quels champs vont au recto
et au verso, avec quel style, et voir le résultat en direct."""
import copy

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt, QTimer
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
                               QPushButton, QRadioButton, QSpinBox, QStackedWidget, QVBoxLayout,
                               QWidget)

from . import formats as F
from .core import ApkgError, render_preview
from .i18n import t


def pdf_to_images(pdf, scale):
    """Pages d'un PDF (octets) -> liste de QImage."""
    buf = QBuffer()
    buf.setData(QByteArray(pdf))
    buf.open(QIODevice.ReadOnly)
    doc = QPdfDocument()
    doc.load(buf)
    imgs = []
    if doc.status() == QPdfDocument.Status.Ready:
        for i in range(doc.pageCount()):
            ps = doc.pagePointSize(i)
            imgs.append(doc.render(i, QSize(int(ps.width() * scale), int(ps.height() * scale))))
    doc.close()
    buf.close()
    return imgs


def _flat_button(text, tip=None):
    b = QPushButton(text)
    b.setObjectName("small")
    if tip:
        b.setToolTip(tip)
    return b


class FormatEditor(QDialog):
    """`win` : fenêtre principale (CardView, thème, réglages de mise en page) ; `col` :
    collection ouverte ; `book` : FormatBook modifié en place à l'enregistrement."""

    def __init__(self, win, col, book, opts, card_view_cls, background="#ffffff"):
        super().__init__(win)
        self.setWindowTitle(t("fmt.title"))
        self.resize(1120, 820)
        self.col, self.book, self.bg = col, book, background
        self.opts = {k: v for k, v in opts.items() if k != "formats"}
        self.types = col.note_types()
        self.work, self.dirty, self.reset = {}, set(), set()
        self.name = None
        self._cur = None           # (côté, position) du bloc sélectionné
        self._loading = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._refresh_preview)
        self._build(card_view_cls)
        if self.types:
            self._select_type(0)

    # -- construction -------------------------------------------------------------
    def _build(self, card_view_cls):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        top = QHBoxLayout()
        top.addWidget(QLabel(t("fmt.type")))
        self.type_box = QComboBox()
        for ty in self.types:
            self.type_box.addItem(t("fmt.type_item", name=ty["name"], n=ty["notes"]), ty["name"])
        self.type_box.currentIndexChanged.connect(self._select_type)
        top.addWidget(self.type_box, 1)
        root.addLayout(top)

        self.status = QLabel()
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        modes = QHBoxLayout()
        self.r_auto = QRadioButton(t("fmt.mode_auto"))
        self.r_custom = QRadioButton(t("fmt.mode_custom"))
        self.r_auto.toggled.connect(self._mode_toggled)
        modes.addWidget(self.r_auto)
        modes.addWidget(self.r_custom)
        modes.addStretch(1)
        self.css_check = QCheckBox(t("fmt.css"))
        self.css_check.toggled.connect(self._css_toggled)
        modes.addWidget(self.css_check)
        root.addLayout(modes)

        body = QHBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, 1)

        # colonne gauche : listes de blocs + propriétés
        self.left = QWidget()
        left = QVBoxLayout(self.left)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(8)
        self.qcm_row = QWidget()
        qr = QHBoxLayout(self.qcm_row)
        qr.setContentsMargins(0, 0, 0, 0)
        qr.addWidget(QLabel(t("fmt.qcm_back")))
        self.qcm_back = QComboBox()
        self.qcm_back.addItem(t("fmt.qcm_back.correct_only"), "correct_only")
        self.qcm_back.addItem(t("fmt.qcm_back.highlight"), "highlight")
        self.qcm_back.currentIndexChanged.connect(self._qcm_back_changed)
        qr.addWidget(self.qcm_back, 1)
        left.addWidget(self.qcm_row)

        self.lists = {}
        for side in ("front", "back"):
            left.addWidget(self._side_box(side), 1)
        left.addWidget(self._build_props(), 0)
        body.addWidget(self.left, 0)
        self.left.setFixedWidth(430)

        # colonne droite : aperçu
        right = QVBoxLayout()
        head = QHBoxLayout()
        head.addWidget(QLabel(t("fmt.preview")))
        head.addStretch(1)
        head.addWidget(QLabel(t("fmt.sample")))
        self.sample = QSpinBox()
        self.sample.setMinimum(1)
        self.sample.valueChanged.connect(self._schedule)
        head.addWidget(self.sample)
        right.addLayout(head)
        self.view_front, self.view_back = card_view_cls(), card_view_cls()
        for key, view in (("preview.recto", self.view_front), ("preview.verso", self.view_back)):
            cap = QLabel(t(key))
            cap.setAlignment(Qt.AlignCenter)
            right.addWidget(cap)
            right.addWidget(view, 1)
        self.info = QLabel()
        self.info.setObjectName("muted")
        self.info.setAlignment(Qt.AlignCenter)
        right.addWidget(self.info)
        body.addLayout(right, 1)

        # boutons
        bottom = QHBoxLayout()
        self.reset_btn = QPushButton(t("fmt.reset"))
        self.reset_btn.setToolTip(t("fmt.reset_tip"))
        self.reset_btn.clicked.connect(self._reset)
        bottom.addWidget(self.reset_btn)
        bottom.addStretch(1)
        cancel = QPushButton(t("fmt.cancel"))
        cancel.clicked.connect(self.reject)
        self.save_btn = QPushButton(t("fmt.save"))
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self._save)
        bottom.addWidget(cancel)
        bottom.addWidget(self.save_btn)
        root.addLayout(bottom)

    def _side_box(self, side):
        box = QFrame()
        box.setObjectName("panel")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        head = QHBoxLayout()
        title = QLabel(t("fmt." + side))
        title.setObjectName("title")
        head.addWidget(title)
        head.addStretch(1)
        add = _flat_button(t("fmt.add"))
        add.clicked.connect(lambda _=None, s=side, b=add: self._add_menu(s, b))
        up = _flat_button("↑", t("fmt.up"))
        down = _flat_button("↓", t("fmt.down"))
        rm = _flat_button("✕", t("fmt.remove"))
        up.clicked.connect(lambda _=None, s=side: self._move(s, -1))
        down.clicked.connect(lambda _=None, s=side: self._move(s, 1))
        rm.clicked.connect(lambda _=None, s=side: self._remove(s))
        for w in (add, up, down, rm):
            head.addWidget(w)
        lay.addLayout(head)
        lst = QListWidget()
        lst.setMinimumHeight(82)
        lst.currentRowChanged.connect(lambda row, s=side: self._row_changed(s, row))
        lay.addWidget(lst, 1)
        self.lists[side] = lst
        return box

    def _build_props(self):
        self.stack = QStackedWidget()
        # 0 : rien de sélectionné
        hint = QLabel(t("fmt.sel_hint"))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        self.stack.addWidget(hint)
        # 1 : bloc « champ »
        fw = QWidget()
        fl = QVBoxLayout(fw)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(6)
        row = QHBoxLayout()
        row.addWidget(QLabel(t("fmt.field")))
        self.f_field = QComboBox()
        self.f_field.currentIndexChanged.connect(self._field_edited)
        row.addWidget(self.f_field, 1)
        row.addWidget(QLabel(t("fmt.style")))
        self.f_style = QComboBox()
        for s in F.STYLES:
            self.f_style.addItem(t("fmt.style." + s), s)
        self.f_style.currentIndexChanged.connect(self._field_edited)
        row.addWidget(self.f_style, 1)
        fl.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel(t("fmt.label")))
        self.f_label = QLineEdit()
        self.f_label.setPlaceholderText(t("fmt.label_ph"))
        self.f_label.setToolTip(t("fmt.label_tip"))
        self.f_label.textChanged.connect(self._field_edited)
        row.addWidget(self.f_label, 1)
        fl.addLayout(row)
        self.f_hide = QCheckBox(t("fmt.hide_empty"))
        self.f_hide.toggled.connect(self._field_edited)
        fl.addWidget(self.f_hide)
        self.stack.addWidget(fw)
        # 2 : bloc « propositions »
        cw = QWidget()
        cl = QVBoxLayout(cw)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)
        cl.addWidget(QLabel(t("fmt.choices.fields")))
        self.c_fields = QListWidget()
        self.c_fields.setMaximumHeight(86)
        self.c_fields.itemChanged.connect(self._choices_edited)
        cl.addWidget(self.c_fields)
        row = QHBoxLayout()
        row.addWidget(QLabel(t("fmt.choices.answer")))
        self.c_answer = QComboBox()
        self.c_answer.currentIndexChanged.connect(self._choices_edited)
        row.addWidget(self.c_answer, 1)
        cl.addLayout(row)
        self.c_show_row = QWidget()
        sr = QHBoxLayout(self.c_show_row)
        sr.setContentsMargins(0, 0, 0, 0)
        sr.addWidget(QLabel(t("fmt.choices.show")))
        self.c_show = QComboBox()
        for s in ("highlight", "correct_only", "plain"):
            self.c_show.addItem(t("fmt.show." + s), s)
        self.c_show.currentIndexChanged.connect(self._choices_edited)
        sr.addWidget(self.c_show, 1)
        cl.addWidget(self.c_show_row)
        self.stack.addWidget(cw)
        return self.stack

    # -- état de travail -----------------------------------------------------------
    @property
    def model(self):
        return next(ty["model"] for ty in self.types if ty["name"] == self.name)

    @property
    def fmt(self):
        return self.work[self.name]

    def _default(self, ty):
        """Format d'un type de note sans réglage enregistré : QCM reconnu, sinon automatique."""
        d = F.detect_choice(ty["model"])
        if self.book.detect and d:
            return F.qcm_format(d, self.book.qcm_back)
        return {"version": F.FORMAT_VERSION, "mode": "auto", "css": True, "front": [],
                "back": []}

    def _initial(self, ty):
        """Format de travail : celui enregistré, sinon le format par défaut."""
        saved = self.book.formats.get(ty["name"])
        return copy.deepcopy(saved) if saved is not None else self._default(ty)

    def _mark(self):
        """Ce type de note a été modifié : il sera enregistré."""
        self.dirty.add(self.name)
        self.reset.discard(self.name)

    def _select_type(self, index):
        if index < 0 or index >= len(self.types):
            return
        ty = self.types[index]
        self.name = ty["name"]
        if self.name not in self.work:
            self.work[self.name] = self._initial(ty)
        self.sample.blockSignals(True)
        self.sample.setMaximum(max(1, ty["notes"]))
        self.sample.setValue(1)
        self.sample.blockSignals(False)
        self._load_ui()

    def _load_ui(self):
        self._loading = True
        fmt = self.fmt
        custom = fmt["mode"] == "custom"
        self.r_custom.setChecked(custom)
        self.r_auto.setChecked(not custom)
        self.css_check.setChecked(fmt.get("css", True))
        detected = F.detect_choice(self.model) is not None
        self.status.setText(t("fmt.detected") if detected and self.name not in self.book.formats
                            and custom else t("fmt.hint"))
        self.left.setEnabled(custom)
        self.css_check.setEnabled(custom)
        self._fill_lists()
        self._loading = False
        self._refresh_qcm_row()
        self._schedule()

    def _fill_lists(self, select=None):
        for side, lst in self.lists.items():
            lst.blockSignals(True)
            lst.clear()
            for b in self.fmt[side]:
                QListWidgetItem(self._describe(side, b), lst)
            lst.blockSignals(False)
        self._cur = None
        self.stack.setCurrentIndex(0)
        if select:
            side, pos = select
            self.lists[side].setCurrentRow(pos)

    def _describe(self, side, b):
        if b["t"] == "choices":
            txt = t("fmt.choices") + " : " + ", ".join(b["fields"])
            if side == "back":
                txt += "  ·  " + t("fmt.show." + b.get("show", "plain"))
            return txt
        name = {"@tags": t("fmt.special.tags"), "@deck": t("fmt.special.deck")}.get(
            b["field"], b["field"])
        return f"{name}  ·  {t('fmt.style.' + b['style'])}"

    def _refresh_qcm_row(self):
        mode = F.back_choice_mode(self.fmt)
        self.qcm_row.setVisible(mode in ("highlight", "correct_only"))
        if mode in ("highlight", "correct_only"):
            self.qcm_back.blockSignals(True)
            self.qcm_back.setCurrentIndex(max(self.qcm_back.findData(mode), 0))
            self.qcm_back.blockSignals(False)

    def _touch(self):
        """Quelque chose a changé : à enregistrer, et aperçu à rafraîchir."""
        if self._loading:
            return
        self._mark()
        self._schedule()

    # -- actions sur les modes -------------------------------------------------------
    def _mode_toggled(self, _):
        if self._loading:
            return
        custom = self.r_custom.isChecked()
        fmt = self.fmt
        fmt["mode"] = "custom" if custom else "auto"
        if custom and not (fmt["front"] or fmt["back"]):
            fmt.update(F.starter_format(self.model))
        self._mark()
        self._load_ui()

    def _css_toggled(self, on):
        if self._loading:
            return
        self.fmt["css"] = bool(on)
        self._touch()

    def _qcm_back_changed(self, _):
        if self._loading:
            return
        self.work[self.name] = F.set_qcm_back(self.fmt, self.qcm_back.currentData())
        self._mark()
        self._loading = True
        self._fill_lists()
        self._loading = False
        self._schedule()

    def _reset(self):
        """Oublie le format enregistré de ce type : retour à la reconnaissance automatique."""
        ty = next(ty for ty in self.types if ty["name"] == self.name)
        self.work[self.name] = self._default(ty)
        self.dirty.discard(self.name)
        self.reset.add(self.name)  # effacé du fichier seulement à l'enregistrement
        self._load_ui()

    # -- listes de blocs -----------------------------------------------------------------
    def _add_menu(self, side, button):
        names = F.field_names(self.model)
        menu = QMenu(self)
        sub = menu.addMenu(t("fmt.add_field"))
        for n in names:
            sub.addAction(n, lambda n=n: self._add(side, F.field_block(n, "text")))
        menu.addAction(t("fmt.add_tags"), lambda: self._add(side, F.field_block("@tags", "tag")))
        menu.addAction(t("fmt.add_deck"), lambda: self._add(side, F.field_block("@deck", "tag")))
        menu.addAction(t("fmt.add_choices"), lambda: self._add(
            side, F.choices_block(names[1:5] if len(names) > 2 else names, "",
                                  "plain" if side == "front" else "highlight")))
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _add(self, side, block):
        if not self.r_custom.isChecked():
            return
        blocks = self.fmt[side]
        pos = self.lists[side].currentRow() + 1 if self.lists[side].currentRow() >= 0 \
            else len(blocks)
        blocks.insert(pos, block)
        self._mark()
        self._fill_lists(select=(side, pos))
        self._refresh_qcm_row()
        self._schedule()

    def _move(self, side, delta):
        row = self.lists[side].currentRow()
        blocks = self.fmt[side]
        new = row + delta
        if row < 0 or not 0 <= new < len(blocks):
            return
        blocks[row], blocks[new] = blocks[new], blocks[row]
        self._mark()
        self._fill_lists(select=(side, new))
        self._schedule()

    def _remove(self, side):
        row = self.lists[side].currentRow()
        if row < 0:
            return
        del self.fmt[side][row]
        self._mark()
        self._fill_lists()
        self._refresh_qcm_row()
        self._schedule()

    def _row_changed(self, side, row):
        if self._loading or row < 0:
            return
        other = self.lists["back" if side == "front" else "front"]
        other.blockSignals(True)
        other.setCurrentRow(-1)
        other.blockSignals(False)
        self._cur = (side, row)
        self._show_props()

    # -- propriétés du bloc sélectionné -------------------------------------------------------
    def _show_props(self):
        side, row = self._cur
        b = self.fmt[side][row]
        names = F.field_names(self.model)
        self._loading = True
        if b["t"] == "choices":
            self.c_fields.clear()
            for n in names:
                it = QListWidgetItem(n)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if n in b["fields"] else Qt.Unchecked)
                self.c_fields.addItem(it)
            self.c_answer.clear()
            self.c_answer.addItem(t("fmt.choices.none"), "")
            for n in names:
                self.c_answer.addItem(n, n)
            self.c_answer.setCurrentIndex(max(self.c_answer.findData(b.get("answer", "")), 0))
            self.c_show_row.setVisible(side == "back")
            self.c_show.setCurrentIndex(max(self.c_show.findData(b.get("show", "plain")), 0))
            self.stack.setCurrentIndex(2)
        else:
            self.f_field.clear()
            for n in names:
                self.f_field.addItem(n, n)
            self.f_field.addItem(t("fmt.special.tags"), "@tags")
            self.f_field.addItem(t("fmt.special.deck"), "@deck")
            self.f_field.setCurrentIndex(max(self.f_field.findData(b["field"]), 0))
            self.f_style.setCurrentIndex(max(self.f_style.findData(b["style"]), 0))
            self.f_label.setText(b.get("label", ""))
            self.f_hide.setChecked(bool(b.get("hide_empty", True)))
            self.stack.setCurrentIndex(1)
        self._loading = False

    def _field_edited(self, *_):
        if self._loading or not self._cur:
            return
        side, row = self._cur
        b = self.fmt[side][row]
        b["field"] = self.f_field.currentData() or b["field"]
        b["style"] = self.f_style.currentData() or "text"
        b["label"] = self.f_label.text()
        b["hide_empty"] = self.f_hide.isChecked()
        self._after_block_edit(side, row)

    def _choices_edited(self, *_):
        if self._loading or not self._cur:
            return
        side, row = self._cur
        b = self.fmt[side][row]
        picked = [self.c_fields.item(i).text() for i in range(self.c_fields.count())
                  if self.c_fields.item(i).checkState() == Qt.Checked]
        if not picked:  # un bloc de propositions sans champ n'a pas de sens
            return
        b["fields"] = picked
        b["answer"] = self.c_answer.currentData() or ""
        if side == "back":
            b["show"] = self.c_show.currentData() or "plain"
        self._after_block_edit(side, row)

    def _after_block_edit(self, side, row):
        item = self.lists[side].item(row)
        if item is not None:
            item.setText(self._describe(side, self.fmt[side][row]))
        self._refresh_qcm_row()
        self._touch()

    # -- aperçu ------------------------------------------------------------------------------------
    def _schedule(self, *_):
        self._timer.start(120)

    def _preview_book(self):
        fmt = self.fmt
        if fmt["mode"] == "custom":
            try:
                return F.FormatBook({self.name: fmt}, detect=False)
            except (ValueError, AttributeError):
                pass
        return F.FormatBook({self.name: {"mode": "auto"}}, detect=False)

    def _refresh_preview(self):
        if self.name is None:
            return
        try:
            r = render_preview(self.col, background=self.bg, formats=self._preview_book(),
                               model_name=self.name, index=self.sample.value() - 1, **self.opts)
        except ApkgError as e:
            for v in (self.view_front, self.view_back):
                v.set_text(str(e))
            return
        imgs = pdf_to_images(r["pdf"], 2.6 * self.devicePixelRatioF())
        if len(imgs) < 2 or r["sample"]:
            for v in (self.view_front, self.view_back):
                v.set_text(t("fmt.preview_none"))
            self.info.setText("")
            return
        self.view_front.set_image(imgs[0])
        self.view_back.set_image(imgs[1])
        w, h = r["card_mm"]
        self.info.setText(t("preview.info", w=f"{w:.0f}", h=f"{h:.0f}",
                            n=self.opts["cols"] * self.opts["rows"]))

    # -- enregistrement ------------------------------------------------------------------------------
    def _save(self):
        for name in self.reset:
            self.book.remove(name)
        for name in self.dirty:
            fmt = self.work[name]
            try:
                if fmt["mode"] == "auto":
                    # « Automatique » choisi explicitement : on le retient (sinon un QCM
                    # reconnu automatiquement reprendrait le dessus).
                    self.book.set(name, {"mode": "auto"})
                else:
                    self.book.set(name, fmt)
            except ValueError:
                QMessageBox.warning(self, t("fmt.title"), t("fmt.empty_format", name=name))
                return
        try:
            F.save_book(self.book)
        except OSError as e:
            QMessageBox.warning(self, t("fmt.title"), t("fmt.saved_err", detail=str(e)))
        self.accept()

"""Dessin d'un côté de carte décrit par un format (voir formats.py).

Étiquettes, question, propositions A/B/C… (avec la bonne réponse en surbrillance ou seule),
explication : tout est dessiné avec les couleurs et proportions du CSS du type de note
(voir cssstyle.py). La mise à l'échelle suit celle des cartes classiques : si le contenu est
trop long, le texte est réduit jusqu'à tenir.
"""
import html
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph

from .core import plain, to_items


def _font(font, bold=False):
    if font == "Helvetica":
        return "Helvetica-Bold" if bold else "Helvetica"
    return font + ("-B" if bold else "")


def _pstyle(font, size, color, bold=False):
    return ParagraphStyle("r", fontName=_font(font, bold), fontSize=size, leading=size * 1.25,
                          alignment=TA_LEFT, textColor=color)


def _flows(items, style, aw, ah, media, scale, only_text=False):
    flows = []
    for kind, val in items:
        if kind == "p":
            try:
                flows.append(Paragraph(val, style))
            except Exception:  # noqa: BLE001
                flows.append(Paragraph(html.escape(plain(val)), style))
        elif not only_text:
            path = media.get(os.path.basename(val))
            if not path:
                continue
            try:
                iw, ih = ImageReader(path).getSize()
                r = min(aw / iw, ah * 0.6 * scale / ih, 1.5)
                flows.append(Image(path, iw * r, ih * r))
            except Exception:  # noqa: BLE001
                flows.append(Paragraph("[image]", style))
    return flows


def _stack(c, flows, width):
    """Hauteur d'une pile de blocs + fonction qui la dessine (haut-gauche = x, ytop)."""
    heights = [f.wrapOn(c, width, 10 ** 6)[1] for f in flows]
    total = sum(heights) + 2 * max(0, len(flows) - 1)

    def draw(x, ytop):
        cur = ytop
        for f, h in zip(flows, heights):
            cur -= h
            f.drawOn(c, x + ((width - f.drawWidth) / 2 if isinstance(f, Image) else 0), cur)
            cur -= 2

    return total, draw


class RichSide:
    """Un côté de carte : liste d'éléments (voir formats.resolve_side) + apparence."""

    def __init__(self, elements, skin):
        self.skin = skin
        acc = skin.accent_hex
        self.elements = []
        for el in elements:
            kind = el[0]
            if kind == "tag":
                self.elements.append(el)
            elif kind == "text":
                _, raw, style, label = el
                self.elements.append(("text", to_items(raw, acc), style, label))
            elif kind == "explain":
                _, label, raw = el
                self.elements.append(("explain", label, to_items(raw, acc)))
            elif kind == "choices":
                _, rows, good, show = el
                self.elements.append(
                    ("choices", [(letter, to_items(raw, acc)) for letter, raw in rows],
                     good, show))

    def __bool__(self):
        return bool(self.elements)

    # -- construction des blocs -------------------------------------------------
    def _boxes(self, c, aw, ah, size, font, media, scale):
        boxes = []
        for el in self.elements:
            kind = el[0]
            if kind == "tag":
                boxes.append(self._tag(c, el[1], aw, size, font) + (0.55,))
            elif kind == "text":
                boxes.append(self._text(c, el, aw, ah, size, font, media, scale))
            elif kind == "explain":
                boxes.append(self._explain(c, el, aw, size, font) + (0.55,))
            else:
                boxes.append(self._choices(c, el, aw, size, font) + (0.55,))
        return boxes

    def _tag(self, c, labels, aw, size, font):
        sk = self.skin
        fs = max(5.0, size * 0.62)
        face = _font(font, True)
        text = "  ·  ".join(labels).upper()
        maxw = aw - fs * 1.6
        while text and c.stringWidth(text, face, fs) > maxw:
            text = text[:-2].rstrip() + "…"
        h, w = fs * 1.9, c.stringWidth(text, face, fs) + fs * 1.6

        def draw(x, ytop):
            c.saveState()
            c.setFillColor(sk.accent_soft)
            c.roundRect(x, ytop - h, w, h, h / 2, stroke=0, fill=1)
            c.setFillColor(sk.accent)
            c.setFont(face, fs)
            c.drawString(x + fs * 0.8, ytop - h / 2 - fs * 0.34, text)
            c.restoreState()

        return h, draw

    def _text(self, c, el, aw, ah, size, font, media, scale):
        sk = self.skin
        _, items, style, label = el
        fs, color, bold, after = {
            "title": (size * sk.q_ratio, sk.text, True, 0.9),
            "small": (size * 0.8, sk.text, False, 0.55),
            "muted": (size * 0.8, sk.muted, False, 0.55),
            "answer": (size, sk.ok, True, 0.55),
        }.get(style, (size, sk.text, False, 0.55))
        flows = []
        if label:
            lab = _pstyle(font, max(5.0, size * 0.62), sk.muted, True)
            flows.append(Paragraph(html.escape(label.upper()), lab))
        flows += _flows(items, _pstyle(font, fs, color, bold), aw, ah, media, scale)
        h, draw = _stack(c, flows, aw)
        return h, draw, after

    def _explain(self, c, el, aw, size, font):
        sk = self.skin
        _, label, items = el
        pad, bar = size * 0.55, 3.0
        inner = aw - 2 * pad - bar
        flows = []
        if label:
            flows.append(Paragraph(html.escape(label.upper()),
                                   _pstyle(font, max(5.0, size * 0.62), sk.ok, True)))
        flows += _flows(items, _pstyle(font, size * sk.explain_ratio, sk.text), inner, 0, {}, 1,
                        only_text=True)
        th, draw_text = _stack(c, flows, inner)
        h = th + 2 * pad
        radius = min(sk.radius, h * 0.3)

        def draw(x, ytop):
            c.saveState()
            path = c.beginPath()
            path.roundRect(x, ytop - h, aw, h, radius)
            c.clipPath(path, stroke=0, fill=0)
            c.setFillColor(sk.surface)
            c.rect(x, ytop - h, aw, h, stroke=0, fill=1)
            c.setFillColor(sk.ok)
            c.rect(x, ytop - h, bar, h, stroke=0, fill=1)
            c.restoreState()
            draw_text(x + bar + pad, ytop - pad)

        return h, draw

    def _choices(self, c, el, aw, size, font):
        sk = self.skin
        _, rows, good, show = el
        if show == "correct_only" and good:
            rows = [(r, k in good, "correct") for k, r in enumerate(rows) if k in good]
        else:
            rows = [(r, k in good, "correct" if (show == "highlight" and k in good)
                     else "wrong" if (show == "highlight" and good) else "normal")
                    for k, r in enumerate(rows)]
        fs = max(5.0, size * sk.opt_ratio)
        d, padx, padv, gapc, rgap = max(fs * 1.65, 11.0), fs * 0.7, fs * 0.5, fs * 0.6, fs * 0.45
        tw = aw - 2 * padx - d - gapc
        built = []
        for (letter, items), _, state in rows:
            flows = _flows(items, _pstyle(font, fs, sk.text), tw, 0, {}, 1, only_text=True)
            th, draw_text = _stack(c, flows, tw)
            built.append((letter, state, th, draw_text, max(th, d * 0.8) + 2 * padv))
        total = sum(b[4] for b in built) + rgap * max(0, len(built) - 1)
        bold = _font(font, True)

        def draw(x, ytop):
            cur = ytop
            for letter, state, th, draw_text, rh in built:
                c.saveState()
                if state == "wrong":
                    c.setFillAlpha(sk.wrong_opacity)
                    c.setStrokeAlpha(sk.wrong_opacity)
                ok = state == "correct"
                c.setLineWidth(1.1)
                c.setFillColor(sk.ok_soft if ok else sk.surface)
                c.setStrokeColor(sk.ok if ok else sk.border)
                c.roundRect(x, cur - rh, aw, rh, min(sk.radius, rh * 0.4), stroke=1, fill=1)
                cy = cur - padv - max(d / 2, 0) if rh > d + 2 * padv + 1 else cur - rh / 2
                c.setFillColor(sk.ok if ok else sk.accent_soft)
                c.circle(x + padx + d / 2, cy, d / 2, stroke=0, fill=1)
                c.setFillColor(colors.white if ok else sk.accent)
                c.setFont(bold, d * 0.5)
                c.drawCentredString(x + padx + d / 2, cy - d * 0.18, letter)
                draw_text(x + padx + d + gapc, cur - (rh - th) / 2)
                c.restoreState()
                cur -= rh + rgap

        return total, draw

    # -- dessin ----------------------------------------------------------------------
    def draw(self, c, x, y, w, h, font, media, base_size):
        """Dessine le contenu centré dans (x, y, w, h). Renvoie True si ça déborde même réduit."""
        pad = 4 * mm
        aw, ah = w - 2 * pad, h - 2 * pad
        scale = 1.0
        while True:
            size = max(5.0, base_size * scale)
            boxes = self._boxes(c, aw, ah, size, font, media, scale)
            gaps = [b[2] * size for b in boxes[:-1]]
            total = sum(b[0] for b in boxes) + sum(gaps)
            if total <= ah or scale <= 0.3:
                break
            scale -= 0.05
        cur = y + pad + ah - max(0, (ah - total) / 2)
        for (bh, draw, _), gap in zip(boxes, gaps + [0]):
            draw(x + pad, cur)
            cur -= bh + gap
        return total > ah

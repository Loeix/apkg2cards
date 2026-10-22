"""Logique de conversion .apkg -> PDF de cartes recto-verso."""
import html
import io
import json
import os
import re
import sqlite3
import tempfile
import threading
import zipfile
from html.parser import HTMLParser
from urllib.parse import unquote

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, Paragraph

from .i18n import get_language, t, t_in


class ApkgError(Exception):
    """Erreur lisible par l'utilisateur. Le message est une clé de traduction (voir locales/),
    traduite dans la langue courante au moment de l'affichage."""

    def __init__(self, key, **params):
        super().__init__(key)
        self.key, self.params = key, params

    def __str__(self):
        return t(self.key, **self.params)


# --------------------------------------------------------------------------
# Couleurs
# --------------------------------------------------------------------------
DEFAULT_COLOR = "#2563eb"
TEXT_COLOR = colors.HexColor("#1f2937")


def parse_color(value):
    try:
        return colors.toColor(value)
    except Exception:
        raise ApkgError("err.bad_color", value=str(value))


def _luminance(c):
    return 0.299 * c.red + 0.587 * c.green + 0.114 * c.blue


def _mix(c, other, t):
    return colors.Color(c.red * (1 - t) + other.red * t,
                        c.green * (1 - t) + other.green * t,
                        c.blue * (1 - t) + other.blue * t)


def _hex(c):
    return "#%02x%02x%02x" % (round(c.red * 255), round(c.green * 255), round(c.blue * 255))


def make_theme(color):
    main = parse_color(color)
    lum = _luminance(main)
    return {
        "main": main,
        "tint": _mix(main, colors.white, 0.90),          # fond du verso
        "on": colors.white if lum < 0.65 else TEXT_COLOR,  # texte du bandeau
        # couleur du texte des trous (cloze), assez foncée pour rester lisible
        "accent": _hex(_mix(main, colors.black, 0.15 if lum <= 0.6 else 0.5)),
    }


# --------------------------------------------------------------------------
# Polices (accents, symboles ; DejaVu / Arial, sinon Helvetica)
# --------------------------------------------------------------------------
FONT_SETS = [
    ("DejaVu", [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"]),
    ("ArialW", [
        r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\ariali.ttf", r"C:\Windows\Fonts\arialbi.ttf"]),
    ("ArialM", [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf"]),
]


def setup_font():
    for name, paths in FONT_SETS:
        if all(os.path.exists(p) for p in paths):
            try:
                for tag, p in zip(("", "-B", "-I", "-BI"), paths):
                    pdfmetrics.registerFont(TTFont(name + tag, p))
                pdfmetrics.registerFontFamily(
                    name, normal=name, bold=name + "-B",
                    italic=name + "-I", boldItalic=name + "-BI")
                return name
            except Exception:
                continue
    return "Helvetica"


# --------------------------------------------------------------------------
# Lecture du .apkg
# --------------------------------------------------------------------------
def _read_collection(dbpath):
    con = sqlite3.connect(dbpath)
    try:
        models_json, decks_json = con.execute("select models, decks from col").fetchone()
        notes = {nid: (mid, flds.split("\x1f"))
                 for nid, mid, flds in con.execute("select id, mid, flds from notes")}
        rows = con.execute(
            "select nid, did, odid, ord from cards order by did, nid, ord").fetchall()
    except sqlite3.Error as e:
        raise ApkgError("err.collection", detail=str(e))
    finally:
        con.close()
    return json.loads(models_json), json.loads(decks_json), notes, rows


class LazyMedia:
    """Médias du .apkg, extraits seulement quand une carte en a besoin."""

    def __init__(self, zf, mapping, tmpdir):
        names = set(zf.namelist())
        self._zf, self._tmp = zf, tmpdir
        self._num = {fname: num for num, fname in mapping.items() if num in names}
        self._done = {}
        self._lock = threading.Lock()

    def get(self, name, default=None):
        num = self._num.get(name)
        if num is None:
            return default
        with self._lock:
            if name not in self._done:
                self._done[name] = self._zf.extract(num, self._tmp)
            return self._done[name]


class Collection:
    """Un .apkg ouvert : paquets, notes et cartes. À fermer avec close() (ou `with`)."""

    def __init__(self, apkg):
        self.path = apkg
        self._tmp = tempfile.TemporaryDirectory()
        self._zf = None
        try:
            self._open(apkg)
        except Exception:
            self.close()
            raise

    def _open(self, apkg):
        try:
            self._zf = zipfile.ZipFile(apkg)
        except (zipfile.BadZipFile, OSError) as e:
            raise ApkgError("err.open", detail=str(e))
        names = self._zf.namelist()
        if "collection.anki21" in names:
            dbname = "collection.anki21"
        elif "collection.anki2" in names and "collection.anki21b" not in names:
            dbname = "collection.anki2"
        elif "collection.anki21b" in names:
            raise ApkgError("err.new_format")
        else:
            raise ApkgError("err.invalid_apkg")
        self._zf.extract(dbname, self._tmp.name)
        mapping = {}
        if "media" in names:
            try:
                mapping = json.loads(self._zf.read("media").decode("utf-8"))
            except Exception:
                mapping = {}
        self.media = LazyMedia(self._zf, mapping, self._tmp.name)
        self.models, self.decks, self.notes, self._rows = _read_collection(
            os.path.join(self._tmp.name, dbname))

    def deck_names(self):
        return sorted(d["name"] for d in self.decks.values())

    def cards(self, deck=None, include_reversed=False, accent="#1a5fb4", limit=None):
        """Liste de (items_recto, items_verso, nom_du_paquet)."""
        out, seen = [], set()
        for nid, did, odid, ord_ in self._rows:
            deck_name = self.decks.get(str(odid or did), {}).get("name", "")
            if deck and deck.lower() not in deck_name.lower():
                continue
            if nid not in self.notes:
                continue
            mid, flds = self.notes[nid]
            model = self.models.get(str(mid))
            if not model:
                continue
            if model.get("type") != 1 and not include_reversed:
                if nid in seen:
                    continue
                seen.add(nid)
            sides = build_card_sides(model, flds, ord_)
            if not sides:
                continue
            fi, bi = to_items(sides[0], accent), to_items(sides[1], accent)
            if fi or bi:
                out.append((fi, bi, deck_name.split("::")[-1]))
                if limit and len(out) >= limit:
                    break
        return out

    def close(self):
        if self._zf is not None:
            try:
                self._zf.close()
            except Exception:
                pass
            self._zf = None
        try:
            self._tmp.cleanup()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def list_decks(apkg):
    """Noms des paquets contenus dans le .apkg."""
    with Collection(apkg) as col:
        return col.deck_names()


# --------------------------------------------------------------------------
# Rendu des templates Anki
# --------------------------------------------------------------------------
CLOZE_RE = re.compile(r"\{\{c(\d+)::(.*?)(?:::(.*?))?\}\}", re.S)
HR_RE = re.compile(r"<hr\s+id=[\"']?answer[\"']?\s*/?>", re.I)


def apply_cloze(text, n, reveal):
    def repl(m):
        if int(m.group(1)) == n:
            if reveal:
                return f"<cl>{m.group(2)}</cl>"
            return f"<cl>[{m.group(3) or '...'}]</cl>"
        return m.group(2)
    return CLOZE_RE.sub(repl, text)


def plain(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def render(tmpl, fields, front_side="", cloze_n=None, reveal=False):
    def cond(m):
        neg, name, inner = m.group(1) == "^", m.group(2).strip(), m.group(3)
        has = bool(plain(fields.get(name, "")).strip())
        return inner if has != neg else ""

    prev = None
    while prev != tmpl:
        prev = tmpl
        tmpl = re.sub(r"\{\{([#^])([^}]+)\}\}(.*?)\{\{/\2\}\}", cond, tmpl, flags=re.S)

    def sub(m):
        name = m.group(1).strip()
        if name == "FrontSide":
            return front_side
        parts = name.split(":")
        field, filters = parts[-1], parts[:-1]
        if "type" in filters or "hint" in filters:
            return ""
        value = fields.get(field, "")
        if "cloze" in filters:
            return apply_cloze(value, cloze_n or 1, reveal)
        if "text" in filters:
            return plain(value)
        return value

    return re.sub(r"\{\{([^}]+)\}\}", sub, tmpl)


def build_card_sides(model, flds, ord_):
    names = [f["name"] for f in sorted(model["flds"], key=lambda f: f["ord"])]
    fields = {n: (flds[i] if i < len(flds) else "") for i, n in enumerate(names)}
    is_cloze = model.get("type") == 1
    tmpls = model["tmpls"]
    t = tmpls[0] if is_cloze else (tmpls[ord_] if ord_ < len(tmpls) else None)
    if t is None:
        return None
    n = ord_ + 1 if is_cloze else None
    front = render(t["qfmt"], fields, cloze_n=n, reveal=False)
    back = render(t["afmt"], fields, front_side="@@FS@@", cloze_n=n, reveal=True)
    m = HR_RE.search(back)
    back = back[m.end():] if m else back.replace("@@FS@@", "")
    return front, back


# --------------------------------------------------------------------------
# HTML Anki -> blocs (paragraphes ReportLab / images)
# --------------------------------------------------------------------------
TAGMAP = {
    "b": ["b"], "strong": ["b"], "i": ["i"], "em": ["i"], "u": ["u"],
    "sup": ["super"], "sub": ["sub"],
    "cl": ["b", 'font color="ACCENT"'],
}
BLOCK = {"div", "p", "li", "tr", "ul", "ol", "table",
         "h1", "h2", "h3", "h4", "h5", "h6"}


class _Conv(HTMLParser):
    def __init__(self, accent="#1a5fb4"):
        super().__init__(convert_charrefs=True)
        self.accent = accent
        self.items, self.buf = [], []
        self.stack, self.stack_start = [], []
        self.skip = 0

    def flush(self):
        body = "".join(self.buf)
        body = re.sub(r"^(\s|<br/>)+|(\s|<br/>)+$", "", body)
        if re.sub(r"<[^>]+>", "", body).strip():
            pre = "".join(f"<{t}>" for t in self.stack_start)
            post = "".join(f"</{t.split()[0]}>" for t in reversed(self.stack))
            self.items.append(("p", pre + body + post))
        self.buf = []
        self.stack_start = list(self.stack)

    def _opens(self, tag):
        return [t.replace("ACCENT", self.accent) for t in TAGMAP[tag]]

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.skip += 1
        elif tag == "br":
            self.buf.append("<br/>")
        elif tag == "img":
            src = dict(attrs).get("src")
            if src:
                self.flush()
                self.items.append(("img", unquote(src)))
        elif tag in TAGMAP:
            for t in self._opens(tag):
                self.buf.append(f"<{t}>")
                self.stack.append(t)
        elif tag in BLOCK:
            self.flush()
            if tag == "li":
                self.buf.append("• ")

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.skip = max(0, self.skip - 1)
        elif tag in TAGMAP:
            for t in reversed(self._opens(tag)):
                if self.stack and self.stack[-1] == t:
                    self.stack.pop()
                    self.buf.append(f"</{t.split()[0]}>")
        elif tag in BLOCK:
            self.flush()

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(html.escape(data.replace("\n", " "), quote=False))


def to_items(raw, accent="#1a5fb4"):
    raw = re.sub(r"\[sound:[^\]]*\]", "", raw)
    c = _Conv(accent)
    c.feed(raw)
    c.flush()
    return c.items


# --------------------------------------------------------------------------
# Dessin
# --------------------------------------------------------------------------
def _make_flowables(items, size, aw, ah, font, media, scale):
    style = ParagraphStyle("c", fontName=font, fontSize=size, leading=size * 1.25,
                           alignment=TA_CENTER, textColor=TEXT_COLOR)
    flows = []
    for kind, val in items:
        if kind == "p":
            try:
                flows.append(Paragraph(val, style))
            except Exception:
                flows.append(Paragraph(html.escape(plain(val)), style))
        else:
            path = media.get(os.path.basename(val))
            if not path:
                continue
            try:
                iw, ih = ImageReader(path).getSize()
                r = min(aw / iw, ah * 0.7 * scale / ih, 1.5)
                flows.append(Image(path, iw * r, ih * r))
            except Exception:
                flows.append(Paragraph("[image]", style))
    return flows


def _draw_content(c, items, x, y, w, h, font, media, base_size):
    """Dessine le contenu centré ; renvoie True si ça déborde même réduit."""
    pad = 4 * mm
    aw, ah = w - 2 * pad, h - 2 * pad
    gap = 3
    scale = 1.0
    while True:
        size = max(5, base_size * scale)
        flows = _make_flowables(items, size, aw, ah, font, media, scale)
        heights = [f.wrapOn(c, aw, 10 ** 6)[1] for f in flows]
        total = sum(heights) + gap * max(0, len(flows) - 1)
        if total <= ah or scale <= 0.3:
            break
        scale -= 0.05
    cur = y + pad + ah - max(0, (ah - total) / 2)
    for f, hgt in zip(flows, heights):
        cur -= hgt
        if isinstance(f, Image):
            f.drawOn(c, x + pad + (aw - f.drawWidth) / 2, cur)
        else:
            f.drawOn(c, x + pad, cur)
        cur -= gap
    return total > ah


def _draw_card(c, x, y, w, h, items, side, deck, font, media, base_size, theme, labels):
    """Carte arrondie avec bandeau coloré (QUESTION / RÉPONSE + nom du paquet)."""
    r, band, main = 3.5 * mm, 8 * mm, theme["main"]
    bold = "Helvetica-Bold" if font == "Helvetica" else font + "-B"

    # fond (blanc au recto, teinté au verso) + bandeau, découpés aux coins arrondis
    c.saveState()
    path = c.beginPath()
    path.roundRect(x, y, w, h, r)
    c.clipPath(path, stroke=0, fill=0)
    c.setFillColor(colors.white if side == 0 else theme["tint"])
    c.rect(x, y, w, h, stroke=0, fill=1)
    c.setFillColor(main)
    c.rect(x, y + h - band, w, band, stroke=0, fill=1)
    c.restoreState()

    # contour : sert aussi de guide de découpe
    c.saveState()
    c.setStrokeColor(main)
    c.setLineWidth(1.2)
    c.roundRect(x, y, w, h, r, stroke=1, fill=0)
    c.restoreState()

    # libellés du bandeau
    label = labels[side]
    ty = y + h - band / 2 - 2.7
    c.setFillColor(theme["on"])
    c.setFont(bold, 7.5)
    c.drawString(x + 4 * mm, ty, label)
    maxw = w - 12 * mm - c.stringWidth(label, bold, 7.5)
    name = deck
    if c.stringWidth(name, font, 7) > maxw:
        while name and c.stringWidth(name + "…", font, 7) > maxw:
            name = name[:-1]
        name = name + "…" if name else ""
    c.setFont(font, 7)
    c.drawRightString(x + w - 4 * mm, ty, name)

    return _draw_content(c, items, x, y, w, h - band, font, media, base_size)


GAP = 1.5 * mm  # espace entre cartes : la découpe n'a pas à être parfaite


def _geometry(cols, rows, margin, landscape):
    if cols < 1 or rows < 1:
        raise ApkgError("err.grid_min")
    page = A4[::-1] if landscape else A4
    W, H = page
    m = margin * mm
    cw, ch = (W - 2 * m) / cols, (H - 2 * m) / rows
    if cw < 25 * mm or ch < 20 * mm:
        raise ApkgError("err.too_small")
    return page, m, cw, ch


def _mirror_cols(landscape, flip):
    """Au verso, on miroite l'axe autour duquel la feuille est retournée."""
    long_edge_is_vertical = not landscape
    return (flip == "long") == long_edge_is_vertical


def _draw_sheet(c, chunk, side, page, m, cw, ch, cols, rows, mirror_cols, font, media,
                base_size, theme, labels):
    """Dessine une page de cartes (side 0 = recto, 1 = verso en miroir). Renvoie le nombre
    de faces dont le texte a dû être très réduit."""
    H = page[1]
    overflow = 0
    for i, card in enumerate(chunk):
        col_i, row_i = i % cols, i // cols
        if side == 1:
            if mirror_cols:
                col_i = cols - 1 - col_i
            else:
                row_i = rows - 1 - row_i
        x = m + col_i * cw + GAP
        y = H - m - (row_i + 1) * ch + GAP
        if _draw_card(c, x, y, cw - 2 * GAP, ch - 2 * GAP, card[side], side,
                      card[2], font, media, base_size, theme, labels):
            overflow += 1
    return overflow


def convert(apkg, output=None, cols=2, rows=4, margin=8.0, font_size=16.0,
            landscape=False, flip="long", deck=None, include_reversed=False,
            color=DEFAULT_COLOR, lang=None, on_progress=None):
    """Convertit `apkg` en PDF. `lang` : langue des libellés des cartes (défaut : langue courante). Renvoie un dict (output, cards, pages, overflow).

    Une carte physique a deux faces : par défaut, on ne garde qu'une carte par note
    (hors cloze), ce qui évite les doublons des types « Basique (et carte inversée) ».
    Mets `include_reversed=True` pour imprimer aussi les cartes inversées.
    """
    theme = make_theme(color)
    labels = card_labels(lang)
    page, m, cw, ch = _geometry(cols, rows, margin, landscape)

    with Collection(apkg) as col:
        cards = col.cards(deck, include_reversed, theme["accent"])
        if not cards:
            raise ApkgError("err.no_cards")

        font = setup_font()
        out = output or os.path.splitext(apkg)[0] + "_cartes.pdf"
        c = canvas.Canvas(out, pagesize=page)
        c.setTitle("Flashcards")

        mirror = _mirror_cols(landscape, flip)
        per = cols * rows
        overflow = 0
        for start in range(0, len(cards), per):
            chunk = cards[start:start + per]
            for side in (0, 1):
                overflow += _draw_sheet(c, chunk, side, page, m, cw, ch, cols, rows, mirror,
                                        font, col.media, font_size, theme, labels)
                c.showPage()
            if on_progress:
                on_progress(min(start + per, len(cards)), len(cards))
        c.save()

    return {"output": out, "cards": len(cards),
            "pages": -(-len(cards) // per) * 2, "overflow": overflow}


# --------------------------------------------------------------------------
# Aperçu d'une carte (PDF de 2 pages : recto, verso) pour l'interface
# --------------------------------------------------------------------------
def card_labels(lang=None):
    """Libellés imprimés sur le bandeau : (recto, verso)."""
    lang = lang or get_language()
    return t_in(lang, "card.front"), t_in(lang, "card.back")


def render_page_preview(col=None, deck=None, include_reversed=False, color=DEFAULT_COLOR,
                        cols=2, rows=4, margin=8.0, font_size=16.0, landscape=False,
                        flip="long", lang=None):
    """Dessine la première page telle qu'elle sera imprimée : recto puis verso en miroir.

    Utilise les premières cartes de `col` si fourni (sinon une carte d'exemple répétée).
    Même code de mise en page que convert() : ce que tu vois est ce que tu imprimes.
    Renvoie {"pdf", "size_pt", "card_mm", "sample", "landscape", "per_page", "shown"}.
    """
    theme = make_theme(color)
    lang = lang or get_language()
    labels = card_labels(lang)
    page, m, cw, ch = _geometry(cols, rows, margin, landscape)
    per = cols * rows

    cards, media = [], {}
    if col is not None:
        cards = col.cards(deck, include_reversed, theme["accent"], limit=per)
        media = col.media
    sample = not cards
    if sample:
        one = (to_items(t_in(lang, "sample.front"), theme["accent"]),
               to_items(t_in(lang, "sample.back"), theme["accent"]),
               t_in(lang, "sample.deck"))
        cards, media = [one] * per, {}

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page)
    font = setup_font()
    mirror = _mirror_cols(landscape, flip)
    for side in (0, 1):
        c.setFillColor(colors.white)  # la feuille de papier
        c.rect(0, 0, page[0], page[1], stroke=0, fill=1)
        _draw_sheet(c, cards, side, page, m, cw, ch, cols, rows, mirror, font, media,
                    font_size, theme, labels)
        c.showPage()
    c.save()
    return {"pdf": buf.getvalue(), "size_pt": page,
            "card_mm": ((cw - 2 * GAP) / mm, (ch - 2 * GAP) / mm), "sample": sample,
            "landscape": landscape, "per_page": per, "shown": len(cards)}


def render_preview(col=None, deck=None, include_reversed=False, color=DEFAULT_COLOR,
                   cols=2, rows=4, margin=8.0, font_size=16.0, landscape=False,
                   background="#ffffff", lang=None):
    """Dessine une seule carte (recto + verso) à la taille réelle de la grille choisie.

    Utilise la première carte de `col` si fourni, sinon une carte d'exemple.
    Renvoie {"pdf": bytes, "size_pt": (w, h), "card_mm": (w, h), "sample": bool}.
    """
    theme = make_theme(color)
    lang = lang or get_language()
    labels = card_labels(lang)
    _, _, cw, ch = _geometry(cols, rows, margin, landscape)
    w, h = cw - 2 * GAP, ch - 2 * GAP

    card, media = None, {}
    if col is not None:
        found = col.cards(deck, include_reversed, theme["accent"], limit=1)
        if found:
            card, media = found[0], col.media
    sample = card is None
    if sample:
        card = (to_items(t_in(lang, "sample.front"), theme["accent"]),
                to_items(t_in(lang, "sample.back"), theme["accent"]),
                t_in(lang, "sample.deck"))

    pad = 4 * mm
    pw, ph = w + 2 * pad, h + 2 * pad
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pw, ph))
    font = setup_font()
    bg = parse_color(background)
    for side in (0, 1):
        c.setFillColor(bg)
        c.rect(0, 0, pw, ph, stroke=0, fill=1)
        _draw_card(c, pad, pad, w, h, card[side], side, card[2], font, media, font_size,
                   theme, labels)
        c.showPage()
    c.save()
    return {"pdf": buf.getvalue(), "size_pt": (pw, ph),
            "card_mm": (w / mm, h / mm), "sample": sample}

"""Logique de conversion .apkg -> PDF de cartes recto-verso."""
import html
import json
import os
import re
import sqlite3
import tempfile
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


class ApkgError(Exception):
    """Erreur lisible par l'utilisateur (fichier invalide, format non géré...)."""


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
def load_apkg(path, tmp):
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, FileNotFoundError, IsADirectoryError) as e:
        raise ApkgError(f"Impossible d'ouvrir le fichier : {e}")
    with z:
        names = z.namelist()
        if "collection.anki21" in names:
            dbname = "collection.anki21"
        elif "collection.anki2" in names and "collection.anki21b" not in names:
            dbname = "collection.anki2"
        elif "collection.anki21b" in names:
            raise ApkgError(
                "Ce .apkg est au format récent. Ré-exporte-le depuis Anki en cochant "
                "« Prendre en charge les anciennes versions d'Anki ».")
        else:
            raise ApkgError("Fichier .apkg invalide (aucune collection trouvée).")
        z.extract(dbname, tmp)
        media = {}
        if "media" in names:
            try:
                mapping = json.loads(z.read("media").decode("utf-8"))
            except Exception:
                mapping = {}
            for num, fname in mapping.items():
                if num in names:
                    media[fname] = z.extract(num, tmp)
    return os.path.join(tmp, dbname), media


def read_collection(dbpath):
    con = sqlite3.connect(dbpath)
    try:
        models_json, decks_json = con.execute("select models, decks from col").fetchone()
        notes = {nid: (mid, flds.split("\x1f"))
                 for nid, mid, flds in con.execute("select id, mid, flds from notes")}
        rows = con.execute(
            "select nid, did, odid, ord from cards order by did, nid, ord").fetchall()
    except sqlite3.Error as e:
        raise ApkgError(f"Collection Anki illisible : {e}")
    finally:
        con.close()
    return json.loads(models_json), json.loads(decks_json), notes, rows


def list_decks(apkg):
    """Noms des paquets contenus dans le .apkg."""
    with tempfile.TemporaryDirectory() as tmp:
        dbpath, _ = load_apkg(apkg, tmp)
        _, decks, _, _ = read_collection(dbpath)
    return sorted(d["name"] for d in decks.values())


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
    "cl": ["b", 'font color="#1a5fb4"'],
}
BLOCK = {"div", "p", "li", "tr", "ul", "ol", "table",
         "h1", "h2", "h3", "h4", "h5", "h6"}


class _Conv(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
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
            for t in TAGMAP[tag]:
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
            for t in reversed(TAGMAP[tag]):
                if self.stack and self.stack[-1] == t:
                    self.stack.pop()
                    self.buf.append(f"</{t.split()[0]}>")
        elif tag in BLOCK:
            self.flush()

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(html.escape(data.replace("\n", " "), quote=False))


def to_items(raw):
    raw = re.sub(r"\[sound:[^\]]*\]", "", raw)
    c = _Conv()
    c.feed(raw)
    c.flush()
    return c.items


# --------------------------------------------------------------------------
# Dessin
# --------------------------------------------------------------------------
def _make_flowables(items, size, aw, ah, font, media, scale):
    style = ParagraphStyle("c", fontName=font, fontSize=size, leading=size * 1.25,
                           alignment=TA_CENTER)
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


def convert(apkg, output=None, cols=2, rows=4, margin=8.0, font_size=16.0,
            landscape=False, flip="long", deck=None, on_progress=None):
    """Convertit `apkg` en PDF. Renvoie un dict (output, cards, pages, overflow)."""
    if cols < 1 or rows < 1:
        raise ApkgError("Il faut au moins 1 colonne et 1 ligne.")
    page = A4[::-1] if landscape else A4
    W, H = page
    m = margin * mm
    cw, ch = (W - 2 * m) / cols, (H - 2 * m) / rows
    if cw < 25 * mm or ch < 20 * mm:
        raise ApkgError("Cartes trop petites : réduis le nombre de colonnes/lignes.")

    with tempfile.TemporaryDirectory() as tmp:
        dbpath, media = load_apkg(apkg, tmp)
        models, decks, notes, rows_db = read_collection(dbpath)

        cards = []
        for nid, did, odid, ord_ in rows_db:
            deck_name = decks.get(str(odid or did), {}).get("name", "")
            if deck and deck.lower() not in deck_name.lower():
                continue
            if nid not in notes:
                continue
            mid, flds = notes[nid]
            model = models.get(str(mid))
            if not model:
                continue
            sides = build_card_sides(model, flds, ord_)
            if not sides:
                continue
            fi, bi = to_items(sides[0]), to_items(sides[1])
            if fi or bi:
                cards.append((fi, bi))
        if not cards:
            raise ApkgError("Aucune carte trouvée (vérifie le filtre de paquet).")

        font = setup_font()
        out = output or os.path.splitext(apkg)[0] + "_cartes.pdf"
        c = canvas.Canvas(out, pagesize=page)
        c.setTitle("Flashcards")

        # Au verso, on miroite l'axe autour duquel la feuille est retournée.
        long_edge_is_vertical = not landscape
        mirror_cols = (flip == "long") == long_edge_is_vertical

        per = cols * rows
        overflow = 0
        for start in range(0, len(cards), per):
            chunk = cards[start:start + per]
            for side in (0, 1):
                for i, card in enumerate(chunk):
                    col, row = i % cols, i // cols
                    if side == 1:
                        if mirror_cols:
                            col = cols - 1 - col
                        else:
                            row = rows - 1 - row
                    x = m + col * cw
                    y = H - m - (row + 1) * ch
                    c.setStrokeColor(colors.Color(0.6, 0.6, 0.6))
                    c.setLineWidth(0.4)
                    c.setDash(2, 2)
                    c.rect(x, y, cw, ch)
                    c.setDash()
                    if _draw_content(c, card[side], x, y, cw, ch, font, media, font_size):
                        overflow += 1
                c.showPage()
            if on_progress:
                on_progress(min(start + per, len(cards)), len(cards))
        c.save()

    return {"output": out, "cards": len(cards),
            "pages": -(-len(cards) // per) * 2, "overflow": overflow}

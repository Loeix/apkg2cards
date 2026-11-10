"""Lecture simplifiée du CSS d'un type de note Anki.

On ne cherche pas à rendre du CSS complet (ce n'est pas possible dans un PDF dessiné avec
ReportLab) : on retient seulement ce qui compte sur une carte imprimée — couleurs, tailles
relatives, arrondis — à partir des variables (`--accent`…) et des classes usuelles (`.opt`,
`.letter`, `.question`, `.explain`…). Le mode nuit (`.nightMode`, `@media`) est ignoré :
on imprime sur du papier.
"""
import re

from reportlab.lib import colors

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_VAR = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^)]*))?\)")
_IMPORTANT = re.compile(r"\s*!important\s*$", re.I)


def _strip_at_blocks(css):
    """Retire les blocs `@media …{…}`, `@font-face{…}`… (accolades imbriquées comprises)."""
    out, i, n = [], 0, len(css)
    while i < n:
        if css[i] == "@":
            j = css.find("{", i)
            if j == -1:
                break
            depth, k = 1, j + 1
            while k < n and depth:
                depth += (css[k] == "{") - (css[k] == "}")
                k += 1
            i = k
        else:
            out.append(css[i])
            i += 1
    return "".join(out)


class Stylesheet:
    def __init__(self, css=""):
        self.rules, self.vars = {}, {}
        css = _strip_at_blocks(_COMMENT.sub("", css or ""))
        for selectors, body in _RULE.findall(css):
            props = {}
            for decl in body.split(";"):
                if ":" not in decl:
                    continue
                key, value = decl.split(":", 1)
                key = key.strip()
                key = key if key.startswith("--") else key.lower()
                props[key] = _IMPORTANT.sub("", value.strip())
            for sel in selectors.split(","):
                sel = " ".join(sel.split())
                if sel and "night" not in sel.lower():
                    self.rules.setdefault(sel, {}).update(props)
        for sel in (":root", "html", "body", ".card"):
            for key, value in self.rules.get(sel, {}).items():
                if key.startswith("--"):
                    self.vars[key] = value

    def resolve(self, value, depth=0):
        """Remplace les `var(--x, repli)` par leur valeur."""
        if value is None:
            return None

        def sub(m):
            found = self.vars.get(m.group(1))
            if found is None:
                return (m.group(2) or "").strip()
            return self.resolve(found, depth + 1) if depth < 6 else ""

        return _VAR.sub(sub, value).strip()

    def get(self, selector, prop):
        raw = self.rules.get(selector, {}).get(prop)
        return self.resolve(raw) if raw else None

    def var(self, name):
        return self.resolve(self.vars.get(name)) if name in self.vars else None


# --------------------------------------------------------------------------
# Valeurs CSS
# --------------------------------------------------------------------------
def parse_color(value):
    """Couleur CSS -> reportlab Color, ou None (transparent, valeur inconnue…)."""
    if not value:
        return None
    v = value.strip().lower()
    if v in ("transparent", "none", "inherit", "initial", "currentcolor"):
        return None
    m = re.fullmatch(r"#([0-9a-f]{3,8})", v)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(ch * 2 for ch in h[:3])
        elif len(h) >= 6:
            h = h[:6]
        else:
            return None
        return colors.HexColor("#" + h)
    m = re.fullmatch(r"rgba?\(([^)]*)\)", v)
    if m:
        parts = [p for p in re.split(r"[\s,/]+", m.group(1).strip()) if p]
        try:
            rgb = []
            for p in parts[:3]:
                rgb.append(float(p[:-1]) / 100 if p.endswith("%") else float(p) / 255)
            if len(rgb) == 3:
                return colors.Color(*[min(max(c, 0), 1) for c in rgb])
        except ValueError:
            return None
        return None
    try:
        return colors.toColor(v)
    except Exception:  # noqa: BLE001
        return None


def parse_length(value, base_pt=13.5):
    """Longueur CSS -> points (1 px = 0.75 pt ; em/rem/% relatifs à `base_pt`)."""
    if not value:
        return None
    m = re.match(r"^\s*(-?\d*\.?\d+)\s*(px|pt|em|rem|%)?", value.strip().lower())
    if not m:
        return None
    n, unit = float(m.group(1)), m.group(2) or "px"
    if unit == "px":
        return n * 0.75
    if unit == "pt":
        return n
    if unit in ("em", "rem"):
        return n * base_pt
    return n / 100 * base_pt


def _tokens(value):
    """Découpe une valeur sur les espaces, sans casser `rgb(1, 2, 3)`."""
    out, cur, depth = [], "", 0
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch.isspace() and not depth:
            if cur:
                out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def border_color(value):
    """Couleur d'un raccourci `border: 1.5px solid #e3e6ee`."""
    for tok in reversed(_tokens(value or "")):
        c = parse_color(tok)
        if c is not None:
            return c
    return None


# --------------------------------------------------------------------------
# Apparence d'une carte
# --------------------------------------------------------------------------
def _c(hexa):
    return colors.HexColor(hexa)


class Skin:
    """Couleurs et proportions utilisées pour dessiner le contenu d'une carte."""

    def __init__(self):
        # valeurs par défaut : celles du type de note « QCM » (bleu/vert, sobre)
        self.text = _c("#1d2130")
        self.muted = _c("#6b7285")
        self.surface = _c("#ffffff")
        self.border = _c("#e3e6ee")
        self.accent = _c("#4f6bed")
        self.accent_soft = _c("#eaeefe")
        self.ok = _c("#1e9e6a")
        self.ok_soft = _c("#e3f6ee")
        self.wrong_opacity = 0.55
        self.radius = 10 * 0.75
        # tailles relatives au texte courant (question 21 px / texte 18 px, etc.)
        self.q_ratio, self.opt_ratio, self.explain_ratio = 1.17, 0.94, 0.89

    @property
    def accent_hex(self):
        return "#%02x%02x%02x" % (round(self.accent.red * 255), round(self.accent.green * 255),
                                  round(self.accent.blue * 255))

    @classmethod
    def from_css(cls, css):
        """Apparence décrite par le CSS du type de note (valeurs absentes : défauts)."""
        skin, sheet = cls(), Stylesheet(css)

        def pick(*candidates):
            for selector, prop, parser in candidates:
                value = sheet.get(selector, prop) if selector else sheet.var(prop)
                color = parser(value) if value else None
                if color is not None:
                    return color
            return None

        def first(*candidates):
            return pick(*candidates) or None

        text = first((".card", "color", parse_color), (None, "--text", parse_color))
        skin.text = text or skin.text
        skin.muted = first((None, "--muted", parse_color)) or skin.muted
        skin.surface = first((".opt", "background", parse_color),
                             (".opt", "background-color", parse_color),
                             (None, "--surface", parse_color)) or skin.surface
        skin.border = first((".opt", "border", border_color),
                            (".opt", "border-color", parse_color),
                            (None, "--border", parse_color)) or skin.border
        skin.accent = first((".letter", "color", parse_color),
                            (".tag", "color", parse_color),
                            (None, "--accent", parse_color)) or skin.accent
        skin.accent_soft = first((".letter", "background", parse_color),
                                 (".letter", "background-color", parse_color),
                                 (None, "--accent-soft", parse_color)) or skin.accent_soft
        skin.ok = first((".opt.correct", "border-color", parse_color),
                        (".opt.correct", "border", border_color),
                        (None, "--ok", parse_color)) or skin.ok
        skin.ok_soft = first((".opt.correct", "background", parse_color),
                             (".opt.correct", "background-color", parse_color),
                             (None, "--ok-soft", parse_color)) or skin.ok_soft

        base = parse_length(sheet.get(".card", "font-size"), 13.5) or 13.5

        def ratio(selector, default):
            size = parse_length(sheet.get(selector, "font-size"), base)
            return min(max(size / base, 0.6), 2.0) if size else default

        skin.q_ratio = ratio(".question", skin.q_ratio)
        skin.opt_ratio = ratio(".txt", ratio(".opt", skin.opt_ratio))
        skin.explain_ratio = ratio(".explain", skin.explain_ratio)
        try:
            op = float(sheet.get(".opt.wrong", "opacity") or skin.wrong_opacity)
            skin.wrong_opacity = min(max(op, 0.2), 1.0)
        except ValueError:
            pass
        radius = parse_length(sheet.get(".opt", "border-radius"), base)
        if radius is not None:
            skin.radius = min(max(radius, 0), 12)
        return skin

    @classmethod
    def from_color(cls, main):
        """Apparence dérivée de la couleur choisie dans l'application (CSS ignoré)."""
        skin = cls()
        skin.accent = main
        skin.accent_soft = colors.Color(main.red * 0.12 + 0.88, main.green * 0.12 + 0.88,
                                        main.blue * 0.12 + 0.88)
        return skin

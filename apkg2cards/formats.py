"""Formats de notes : comment les champs d'un type de note Anki sont disposés sur la carte.

Un *format* décrit le recto et le verso comme une liste de blocs :

    {"t": "field", "field": "Question", "style": "title", "label": "", "hide_empty": True}
    {"t": "choices", "fields": ["A", "B", "C", "D"], "answer": "Reponse", "show": "plain"}

`show` (blocs « choices ») : "plain" (propositions sans mise en valeur), "highlight" (toutes
les propositions, la bonne en surbrillance) ou "correct_only" (seulement la bonne réponse).

Un format est associé au *nom* du type de note et enregistré dans un fichier JSON de
l'utilisateur. Sans format enregistré, un type de note qui ressemble à un QCM (champs A, B, C…
+ un champ « réponse ») est reconnu automatiquement ; les autres restent rendus d'après les
modèles Anki (mode « auto »).

Ce module ne dessine rien : il décide *quoi* afficher (voir richcard.py pour le dessin).
"""
import copy
import json
import os
import re
import sys

from .i18n import t_in

FORMAT_VERSION = 1
STYLES = ("title", "text", "small", "muted", "answer", "explain", "tag")
SHOW_MODES = ("plain", "highlight", "correct_only")
SPECIAL_FIELDS = ("@tags", "@deck")

_ANSWER_NAME = re.compile(
    r"(?i)^(bonnes?[ _-]?)?(r[ée]ponses?|answers?|solutions?|corrig[ée]s?|correct(e|es|s)?)$")
_EXPLAIN_NAME = re.compile(
    r"(?i)(expl|commentaire|comment|justif|d[ée]tail|rappel|extra|remarque|note|source)")
_CHOICE_NAME = re.compile(
    r"(?i)^(option|choix|choice|proposition|reponse|r[ée]ponse|answer)[ _-]?(\d+|[a-z])$")


# --------------------------------------------------------------------------
# Construction et validation
# --------------------------------------------------------------------------
def field_block(field, style="text", label="", hide_empty=True):
    return {"t": "field", "field": field, "style": style, "label": label,
            "hide_empty": hide_empty}


def choices_block(fields, answer="", show="plain"):
    return {"t": "choices", "fields": list(fields), "answer": answer, "show": show,
            "letters": "auto"}


def normalize_block(b):
    """Bloc nettoyé, ou ValueError s'il est inutilisable."""
    if not isinstance(b, dict):
        raise ValueError("bloc invalide")
    if b.get("t") == "choices":
        fields = [str(f) for f in b.get("fields", []) if isinstance(f, str) and f]
        if not fields:
            raise ValueError("bloc de choix sans champ")
        show = b.get("show", "plain")
        return choices_block(fields, str(b.get("answer") or ""),
                             show if show in SHOW_MODES else "plain")
    if b.get("t") == "field":
        name = b.get("field")
        if not isinstance(name, str) or not name:
            raise ValueError("champ manquant")
        style = b.get("style", "text")
        return field_block(name, style if style in STYLES else "text",
                           str(b.get("label") or ""), bool(b.get("hide_empty", True)))
    raise ValueError("type de bloc inconnu")


def normalize_format(f):
    """Format nettoyé (copie), ou ValueError."""
    if not isinstance(f, dict):
        raise ValueError("format invalide")
    mode = f.get("mode", "custom")
    if mode not in ("auto", "custom"):
        raise ValueError("mode inconnu")
    out = {"version": FORMAT_VERSION, "mode": mode, "css": bool(f.get("css", True)),
           "front": [], "back": []}
    for side in ("front", "back"):
        for b in f.get(side, []):
            try:
                out[side].append(normalize_block(b))
            except ValueError:
                continue  # un bloc abîmé ne doit pas empêcher d'utiliser le reste
    if mode == "custom" and not (out["front"] or out["back"]):
        raise ValueError("format vide")
    return out


# --------------------------------------------------------------------------
# Détection d'un QCM et format de départ
# --------------------------------------------------------------------------
def field_names(model):
    return [f["name"] for f in sorted(model.get("flds", []), key=lambda f: f.get("ord", 0))]


def detect_choice(model):
    """Si le type de note ressemble à un QCM : {question, choices, answer, explain}, sinon None."""
    names = field_names(model)
    singles = [n for n in names if re.fullmatch(r"[A-Za-z]", n.strip())]
    numbered = [n for n in names if _CHOICE_NAME.match(n.strip())
                and not _ANSWER_NAME.match(n.strip())]
    choices = singles if len(singles) >= len(numbered) else numbered
    answer = next((n for n in names if n not in choices and _ANSWER_NAME.match(n.strip())), "")
    if len(choices) < 3 and not (len(choices) >= 2 and answer):
        return None
    rest = [n for n in names if n not in choices and n != answer]
    if not rest:
        return None
    explain = next((n for n in rest[1:] if _EXPLAIN_NAME.search(n)), "")
    return {"question": rest[0], "choices": choices, "answer": answer, "explain": explain,
            "others": [n for n in rest[1:] if n != explain]}


def qcm_format(d, back="correct_only"):
    """Format d'un QCM détecté. `back` : "correct_only" (réponse seule + explication) ou
    "highlight" (QCM complet, bonne réponse en surbrillance)."""
    front = [field_block("@tags", "tag"), field_block(d["question"], "title"),
             choices_block(d["choices"], d["answer"], "plain")]
    verso = [field_block("@tags", "tag")]
    if back == "highlight":
        verso.append(field_block(d["question"], "title"))
    verso.append(choices_block(d["choices"], d["answer"], back))
    for name in d["others"]:
        verso.append(field_block(name, "text"))
    if d["explain"]:
        verso.append(field_block(d["explain"], "explain", "@auto"))
    return {"version": FORMAT_VERSION, "mode": "custom", "css": True,
            "front": front, "back": verso}


def starter_format(model, back="correct_only"):
    """Point de départ proposé quand on personnalise un type de note."""
    d = detect_choice(model)
    if d:
        return qcm_format(d, back)
    names = field_names(model)
    if model.get("type") == 1:  # trous (cloze)
        text = names[0] if names else ""
        verso = [field_block(text, "text")] + [field_block(n, "small") for n in names[1:]]
        return {"version": FORMAT_VERSION, "mode": "custom", "css": True,
                "front": [field_block(text, "text")], "back": verso}
    front = [field_block(names[0], "title")] if names else []
    verso = [field_block(n, "text") for n in names[1:]]
    return {"version": FORMAT_VERSION, "mode": "custom", "css": True,
            "front": front, "back": verso}


def back_choice_mode(fmt):
    """Mode de la première liste de propositions du verso (None s'il n'y en a pas)."""
    for b in fmt.get("back", []):
        if b.get("t") == "choices":
            return b.get("show")
    return None


def set_qcm_back(fmt, mode):
    """Passe le verso d'un QCM entre « réponse seule » et « QCM complet » : règle l'affichage
    des propositions et ajoute (ou retire) la question répétée en tête du verso."""
    fmt = copy.deepcopy(fmt)
    question = next((b["field"] for b in fmt["front"]
                     if b.get("t") == "field" and b.get("style") == "title"), None)
    back = fmt["back"]
    for b in back:
        if b.get("t") == "choices":
            b["show"] = mode
    repeated = [i for i, b in enumerate(back) if b.get("t") == "field"
                and b.get("field") == question and b.get("style") == "title"]
    if mode == "highlight" and question and not repeated:
        at = next((i for i, b in enumerate(back) if b.get("t") == "choices"), 0)
        back.insert(at, field_block(question, "title"))
    elif mode == "correct_only":
        for i in reversed(repeated):
            del back[i]
    return fmt


# --------------------------------------------------------------------------
# Lecture de la bonne réponse
# --------------------------------------------------------------------------
def _plain(s):
    import html
    return html.unescape(re.sub(r"<[^>]+>", " ", s or "")).strip()


def choice_letters(names):
    """Lettres affichées : le nom du champ s'il tient en un caractère, sinon A, B, C…"""
    return [n.strip().upper() if len(n.strip()) == 1 else chr(65 + i)
            for i, n in enumerate(names)]


def parse_answer(value, option_texts, letters=None):
    """Positions (0, 1…) des bonnes propositions d'après le champ « réponse ».

    Accepte « B », « AC », « A, C », « A et C », « 2 », « 1;3 », ou le texte même d'une
    proposition. Renvoie [] si on ne sait pas lire la valeur (rien n'est alors mis en valeur).
    """
    n = len(option_texts)
    letters = letters or choice_letters([""] * n)
    text = _plain(value)
    if not text:
        return []
    for i, opt in enumerate(option_texts):  # la réponse est le texte d'une proposition
        if _plain(opt) and _plain(opt).casefold() == text.casefold():
            return [i]
    t = re.sub(r"(?i)\b(et|and|ou|or)\b|[&+/;,]", " ", text).upper()
    tokens = t.split()
    if len(tokens) == 1 and re.fullmatch(r"[A-Z]{2,}", tokens[0]):
        tokens = list(tokens[0])  # « AC »
    found = []
    for tok in tokens:
        tok = tok.strip(".):")
        if tok in letters:
            idx = letters.index(tok)
        elif tok.isdigit() and 1 <= int(tok) <= n:
            idx = int(tok) - 1
        else:
            return []  # une phrase, pas un code de réponse
        if idx not in found:
            found.append(idx)
    return sorted(found)


# --------------------------------------------------------------------------
# Décider quoi afficher pour une note
# --------------------------------------------------------------------------
def tag_labels(tags):
    """'DT::Licenciement_éco  Révision' -> ['DT › Licenciement éco', 'Révision']."""
    return [tg.replace("_", " ").replace("::", " › ") for tg in (tags or "").split() if tg]


def _subst(label, fields, answer_letters):
    def sub(m):
        name = m.group(1)
        if name == "answer":
            return ", ".join(answer_letters)
        return _plain(fields.get(name, ""))
    return re.sub(r"\{([^{}]+)\}", sub, label)


def resolve_side(fmt, side, fields, tags, deck, lang, cloze=None):
    """Éléments à dessiner pour un côté (« front » ou « back ») d'une note.

    `fields` : nom -> HTML brut. `cloze` : (numéro, révélé ?) pour les types « trous ».
    Éléments : ("tag", [str]), ("text", html, style, label), ("explain", label, html),
    ("choices", [(lettre, html)], [positions correctes], show).
    """
    from .core import apply_cloze  # import tardif : core importe ce module

    def value(name):
        raw = fields.get(name, "")
        return apply_cloze(raw, cloze[0], cloze[1]) if cloze and "{{c" in raw else raw

    # réponse du QCM (pour l'étiquette « Bonne réponse : B »)
    answer_letters = []
    for b in fmt.get("front", []) + fmt.get("back", []):
        if b.get("t") == "choices" and b.get("answer"):
            texts = [fields.get(f, "") for f in b["fields"]]
            letters = choice_letters(b["fields"])
            answer_letters = [letters[i] for i in parse_answer(
                fields.get(b["answer"], ""), texts, letters)]
            break

    out = []
    for b in fmt.get(side, []):
        if b["t"] == "choices":
            names = b["fields"]
            letters = choice_letters(names)
            texts = [value(f) for f in names]
            good = parse_answer(fields.get(b["answer"], ""), texts, letters) if b["answer"] else []
            show = b.get("show", "plain")
            if side == "front":
                show = "plain"
            if show != "plain" and not good:
                show = "plain"  # réponse illisible : on n'invente rien
            kept = [i for i in range(len(names)) if _plain(texts[i]) or "<img" in texts[i]]
            rows = [(letters[i], texts[i]) for i in kept]
            good_pos = [k for k, i in enumerate(kept) if i in good]
            if rows:
                out.append(("choices", rows, good_pos, show))
            continue
        name = b["field"]
        if name == "@tags":
            labels = tag_labels(tags)
            if labels:
                out.append(("tag", labels))
            continue
        if name == "@deck":
            if deck:
                out.append(("tag", [deck]))
            continue
        html_value = value(name)
        if b.get("hide_empty", True) and not _plain(html_value) and "<img" not in html_value:
            continue
        label = b.get("label") or ""
        if label == "@auto":
            label = (t_in(lang, "qcm.correct_answer", answer=", ".join(answer_letters))
                     if answer_letters else t_in(lang, "qcm.explanation"))
        else:
            label = _subst(label, fields, answer_letters)
        if b["style"] == "tag":
            if _plain(html_value):
                out.append(("tag", [_plain(html_value)]))
        elif b["style"] == "explain":
            out.append(("explain", label, html_value))
        else:
            out.append(("text", html_value, b["style"], label))
    return out


# --------------------------------------------------------------------------
# Ensemble des formats d'un utilisateur
# --------------------------------------------------------------------------
class FormatBook:
    """Formats enregistrés (nom du type de note -> format) + reconnaissance automatique."""

    def __init__(self, formats=None, detect=True, qcm_back="correct_only"):
        self.formats = {}
        for name, f in (formats or {}).items():
            try:
                self.formats[str(name)] = normalize_format(f) if f.get("mode") != "auto" \
                    else {"version": FORMAT_VERSION, "mode": "auto", "css": True,
                          "front": [], "back": []}
            except (ValueError, AttributeError):
                continue
        self.detect = detect
        self.qcm_back = qcm_back if qcm_back in ("correct_only", "highlight") else "correct_only"

    def for_model(self, model):
        """Format à appliquer à ce type de note, ou None (= modèles Anki, comme avant)."""
        saved = self.formats.get(model.get("name", ""))
        if saved is not None:
            return None if saved["mode"] == "auto" else saved
        if self.detect:
            d = detect_choice(model)
            if d:
                return qcm_format(d, self.qcm_back)
        return None

    def mode_of(self, model):
        """'auto' (modèles Anki), 'custom' (format enregistré) ou 'detected' (QCM reconnu)."""
        saved = self.formats.get(model.get("name", ""))
        if saved is not None:
            return saved["mode"]
        return "detected" if self.detect and detect_choice(model) else "auto"

    def set(self, name, fmt):
        self.formats[name] = normalize_format(fmt) if fmt.get("mode") != "auto" else \
            {"version": FORMAT_VERSION, "mode": "auto", "css": True, "front": [], "back": []}

    def remove(self, name):
        self.formats.pop(name, None)

    def to_json(self):
        return {"version": FORMAT_VERSION, "formats": self.formats}

    @classmethod
    def from_json(cls, data, **kw):
        formats = data.get("formats", {}) if isinstance(data, dict) else {}
        return cls(formats if isinstance(formats, dict) else {}, **kw)


def config_dir():
    """Dossier des réglages de l'utilisateur (modifiable avec APKG2CARDS_CONFIG_DIR)."""
    custom = os.environ.get("APKG2CARDS_CONFIG_DIR")
    if custom:
        return custom
    if sys.platform.startswith("win"):
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "apkg2cards")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/apkg2cards")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
                        "apkg2cards")


def formats_path():
    return os.path.join(config_dir(), "formats.json")


def load_book(path=None, **kw):
    """Formats enregistrés ; un fichier absent ou abîmé donne simplement un carnet vide."""
    try:
        with open(path or formats_path(), encoding="utf-8") as f:
            return FormatBook.from_json(json.load(f), **kw)
    except (OSError, ValueError):
        return FormatBook(**kw)


def save_book(book, path=None):
    """Écrit les formats (écriture atomique). Renvoie le chemin du fichier."""
    path = path or formats_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(book.to_json(), f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path

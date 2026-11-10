"""Paquet .apkg de test avec un type de note « QCM » (champs A-D, réponse, explication)."""
import json
import os
import sqlite3
import zipfile

CSS = """
.card { --surface:#ffffff; --text:#1d2130; --border:#e3e6ee; --accent:#4f6bed;
  --accent-soft:#eaeefe; --ok:#1e9e6a; --ok-soft:#e3f6ee; font-size: 18px; color: var(--text); }
.card.nightMode { --surface:#1e212b; --accent:#8ea0ff; }
@media (prefers-color-scheme: dark) { .card { --accent:#000000; } }
.question { font-size: 21px; }
.opt { background: var(--surface); border: 1.5px solid var(--border); border-radius: 14px; }
.letter { background: var(--accent-soft); color: var(--accent); }
.opt.correct { border-color: var(--ok); background: var(--ok-soft); }
.opt.wrong { opacity: 0.55; }
"""

QCM_FIELDS = ["Question", "A", "B", "C", "D", "Reponse", "Explication"]
MODELS = {
    "10": {"name": "QCM", "type": 0, "css": CSS,
           "flds": [{"name": n, "ord": i} for i, n in enumerate(QCM_FIELDS)],
           "tmpls": [{"qfmt": "{{Question}}", "afmt": "{{FrontSide}}<hr id=answer>{{Reponse}}"}]},
    "11": {"name": "Basique", "type": 0, "css": ".card { color: #222; }",
           "flds": [{"name": "Front", "ord": 0}, {"name": "Back", "ord": 1}],
           "tmpls": [{"qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"},
                     {"qfmt": "{{Back}}", "afmt": "{{FrontSide}}<hr id=answer>{{Front}}"}]},
    "12": {"name": "Trous", "type": 1, "css": "",
           "flds": [{"name": "Text", "ord": 0}, {"name": "Extra", "ord": 1}],
           "tmpls": [{"qfmt": "{{cloze:Text}}", "afmt": "{{cloze:Text}}<br>{{Extra}}"}]},
}
DECKS = {"1": {"name": "Droit::QCM"}, "2": {"name": "Divers"}}

QCM_NOTES = [
    ("Quel organe adopte les conventions ?", "Le BIT", "Le Conseil", "La Conférence",
     "Le secrétariat", "C", "La <b>Conférence</b> adopte les conventions.", "DT::Sources"),
    ("Quels textes sont directement applicables ?", "Article 6", "Article 8", "Article 10",
     "Article 11", "A, D", "Les articles 6 et 11.", "DT::Preuve_loyale revision"),
    ("Question sans réponse lisible", "Un", "Deux", "Trois", "Quatre",
     "voir le cours", "", ""),
]


def make_qcm_apkg(folder, name="qcm.apkg", legacy=True):
    db = os.path.join(folder, "collection.anki21")
    if os.path.exists(db):
        os.remove(db)
    con = sqlite3.connect(db)
    con.execute("create table col(models text, decks text)")
    con.execute("create table notes(id int, mid int, flds text, tags text)")
    con.execute("create table cards(id int, nid int, did int, odid int, ord int)")
    con.execute("insert into col values(?,?)", (json.dumps(MODELS), json.dumps(DECKS)))
    nid = cid = 0
    for q, a, b, c, d, rep, expl, tags in QCM_NOTES:
        nid += 1
        flds = "\x1f".join([q, a, b, c, d, rep, expl])
        con.execute("insert into notes values(?,?,?,?)", (nid, 10, flds, f" {tags} " if tags else ""))
        cid += 1
        con.execute("insert into cards values(?,?,?,0,0)", (cid, nid, 1))
    nid += 1  # note « Basique » à deux modèles (carte inversée)
    con.execute("insert into notes values(?,?,?,?)", (nid, 11, "Avant\x1fArrière", " perso "))
    for o in range(2):
        cid += 1
        con.execute("insert into cards values(?,?,?,0,?)", (cid, nid, 2, o))
    nid += 1  # note à trous : deux trous = deux cartes
    con.execute("insert into notes values(?,?,?,?)",
                (nid, 12, "{{c1::Alpha}} et {{c2::bêta}}\x1fExtra", ""))
    for o in range(2):
        cid += 1
        con.execute("insert into cards values(?,?,?,0,?)", (cid, nid, 2, o))
    con.commit()
    con.close()
    path = os.path.join(folder, name)
    with zipfile.ZipFile(path, "w") as z:
        z.write(db, "collection.anki21" if legacy else "collection.anki21b")
        z.writestr("media", "{}")
    return path

import json
import os
import sqlite3
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402

from apkg2cards import ApkgError, convert, list_decks  # noqa: E402
from apkg2cards.core import to_items  # noqa: E402

MODELS = {
    "1": {"type": 0,
          "flds": [{"name": "Front", "ord": 0}, {"name": "Back", "ord": 1}],
          "tmpls": [{"qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"},
                    {"qfmt": "{{Back}}", "afmt": "{{FrontSide}}<hr id=answer>{{Front}}"}]},
    "2": {"type": 1,
          "flds": [{"name": "Text", "ord": 0}, {"name": "Extra", "ord": 1}],
          "tmpls": [{"qfmt": "{{cloze:Text}}", "afmt": "{{cloze:Text}}<br>{{Extra}}"}]},
}
DECKS = {"1": {"name": "Droit civil"}, "2": {"name": "Droit pénal"}}


def make_apkg(folder, legacy=True):
    db = os.path.join(folder, "collection.anki21")
    con = sqlite3.connect(db)
    con.execute("create table col(models text, decks text)")
    con.execute("create table notes(id int, mid int, flds text)")
    con.execute("create table cards(id int, nid int, did int, odid int, ord int)")
    con.execute("insert into col values(?,?)", (json.dumps(MODELS), json.dumps(DECKS)))
    notes = [(1, 1, "Question <b>1</b> ?<br><img src='a.png'>", "Réponse 1"),
             (2, 2, "{{c1::Alpha}} et {{c2::bêta::hint}}", "Extra")]
    cid = 1
    for nid, mid, f, b in notes:
        con.execute("insert into notes values(?,?,?)", (nid, mid, f + "\x1f" + b))
        for o in range(2):
            con.execute("insert into cards values(?,?,?,0,?)",
                        (cid, nid, 1 if nid == 1 else 2, o))
            cid += 1
    con.commit()
    con.close()
    img = os.path.join(folder, "0")
    Image.new("RGB", (80, 40), (200, 40, 40)).save(img, format="PNG")
    path = os.path.join(folder, "test.apkg")
    with zipfile.ZipFile(path, "w") as z:
        z.write(db, "collection.anki21" if legacy else "collection.anki21b")
        z.write(img, "0")
        z.writestr("media", json.dumps({"0": "a.png"}))
    return path


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.apkg = make_apkg(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_decks(self):
        self.assertEqual(list_decks(self.apkg), ["Droit civil", "Droit pénal"])

    def test_convert_all(self):
        out = os.path.join(self.tmp.name, "o.pdf")
        r = convert(self.apkg, out)
        self.assertEqual(r["cards"], 3)  # la carte inversée de la note 1 est ignorée
        self.assertEqual(r["pages"], 2)
        self.assertTrue(os.path.getsize(out) > 1000)

    def test_include_reversed(self):
        r = convert(self.apkg, os.path.join(self.tmp.name, "o.pdf"), include_reversed=True)
        self.assertEqual(r["cards"], 4)

    def test_custom_color(self):
        r = convert(self.apkg, os.path.join(self.tmp.name, "o.pdf"), color="#16a34a")
        self.assertEqual(r["cards"], 3)
        r = convert(self.apkg, os.path.join(self.tmp.name, "o2.pdf"), color="yellow")
        self.assertEqual(r["cards"], 3)

    def test_invalid_color(self):
        with self.assertRaises(ApkgError):
            convert(self.apkg, os.path.join(self.tmp.name, "o.pdf"), color="zzz")

    def test_deck_filter(self):
        r = convert(self.apkg, os.path.join(self.tmp.name, "o.pdf"), deck="pénal")
        self.assertEqual(r["cards"], 2)

    def test_pagination(self):
        r = convert(self.apkg, os.path.join(self.tmp.name, "o.pdf"), cols=1, rows=1)
        self.assertEqual(r["pages"], 6)

    def test_unknown_deck_raises(self):
        with self.assertRaises(ApkgError):
            convert(self.apkg, os.path.join(self.tmp.name, "o.pdf"), deck="zzz")

    def test_new_format_rejected(self):
        bad = make_apkg(tempfile.mkdtemp(), legacy=False)
        with self.assertRaises(ApkgError):
            convert(bad)

    def test_not_a_zip(self):
        p = os.path.join(self.tmp.name, "x.apkg")
        with open(p, "w") as f:
            f.write("nope")
        with self.assertRaises(ApkgError):
            convert(p)

    def test_html_items(self):
        items = to_items("a <b>gras</b><br>b<div>c</div><img src='x.png'>")
        self.assertEqual([k for k, _ in items], ["p", "p", "img"])


if __name__ == "__main__":
    unittest.main()

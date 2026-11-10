import copy
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from apkg2cards import core, formats as F  # noqa: E402
from apkg2cards.cli import main as cli_main  # noqa: E402
from apkg2cards.cssstyle import Skin, Stylesheet, parse_color, parse_length  # noqa: E402
from apkg2cards.richcard import RichSide  # noqa: E402
from qcm_fixture import CSS, MODELS, make_qcm_apkg  # noqa: E402

QCM = MODELS["10"]


def hexcolor(c):
    return "#%02x%02x%02x" % (round(c.red * 255), round(c.green * 255), round(c.blue * 255))


class CssTests(unittest.TestCase):
    def test_colors_and_lengths(self):
        self.assertEqual(hexcolor(parse_color("#abc")), "#aabbcc")
        self.assertEqual(hexcolor(parse_color("rgb(10, 20, 30)")), "#0a141e")
        self.assertEqual(hexcolor(parse_color("RED")), "#ff0000")
        self.assertIsNone(parse_color("transparent"))
        self.assertIsNone(parse_color("nimportequoi"))
        self.assertAlmostEqual(parse_length("20px"), 15.0)
        self.assertAlmostEqual(parse_length("2em", 10), 20)

    def test_variables_with_fallback(self):
        sheet = Stylesheet(".card{--a:#111; --b:var(--a);} .x{color:var(--b); border:var(--nope, 3px)}")
        self.assertEqual(sheet.get(".x", "color"), "#111")
        self.assertEqual(sheet.get(".x", "border"), "3px")

    def test_night_mode_and_media_are_ignored(self):
        skin = Skin.from_css(CSS)
        self.assertEqual(hexcolor(skin.accent), "#4f6bed")  # pas #8ea0ff ni #000000
        self.assertEqual(hexcolor(skin.ok), "#1e9e6a")
        self.assertEqual(hexcolor(skin.ok_soft), "#e3f6ee")
        self.assertAlmostEqual(skin.wrong_opacity, 0.55)
        self.assertAlmostEqual(skin.q_ratio, 21 / 18, places=2)

    def test_empty_css_gives_defaults(self):
        self.assertEqual(hexcolor(Skin.from_css("").ok), "#1e9e6a")
        self.assertEqual(hexcolor(Skin.from_css("garbage {{{").accent), "#4f6bed")

    def test_skin_from_app_color(self):
        skin = Skin.from_color(parse_color("#dc2626"))
        self.assertEqual(hexcolor(skin.accent), "#dc2626")
        self.assertEqual(hexcolor(skin.ok), "#1e9e6a")


class DetectionTests(unittest.TestCase):
    def test_qcm_detected(self):
        d = F.detect_choice(QCM)
        self.assertEqual(d["question"], "Question")
        self.assertEqual(d["choices"], ["A", "B", "C", "D"])
        self.assertEqual(d["answer"], "Reponse")
        self.assertEqual(d["explain"], "Explication")

    def test_numbered_options(self):
        model = {"flds": [{"name": n, "ord": i} for i, n in enumerate(
            ["Enoncé", "Option 1", "Option 2", "Option 3", "Réponse", "Commentaire"])]}
        d = F.detect_choice(model)
        self.assertEqual(d["choices"], ["Option 1", "Option 2", "Option 3"])
        self.assertEqual(d["answer"], "Réponse")
        self.assertEqual(d["explain"], "Commentaire")

    def test_ordinary_types_are_not_qcm(self):
        self.assertIsNone(F.detect_choice(MODELS["11"]))
        self.assertIsNone(F.detect_choice(MODELS["12"]))
        self.assertIsNone(F.detect_choice({"flds": [{"name": "A", "ord": 0},
                                                    {"name": "B", "ord": 1}]}))


class AnswerTests(unittest.TestCase):
    OPTS = ["Un", "Deux", "Trois", "Quatre"]

    def test_codes(self):
        for text, expected in (("B", [1]), ("b", [1]), ("AC", [0, 2]), ("A, C", [0, 2]),
                               ("A et C", [0, 2]), ("<b>D</b>", [3]), ("2", [1]),
                               ("1;3", [0, 2]), ("B.", [1])):
            self.assertEqual(F.parse_answer(text, self.OPTS), expected, text)

    def test_text_of_an_option(self):
        self.assertEqual(F.parse_answer("trois", self.OPTS), [2])

    def test_unreadable(self):
        for text in ("", "voir le cours", "E", "0", "A B Z"):
            self.assertEqual(F.parse_answer(text, self.OPTS), [], text)

    def test_letters_from_field_names(self):
        self.assertEqual(F.choice_letters(["A", "b", "Option 3"]), ["A", "B", "C"])


class BackModeTests(unittest.TestCase):
    def setUp(self):
        self.fmt = F.qcm_format(F.detect_choice(QCM))

    def test_default_back_is_answer_only(self):
        self.assertEqual(F.back_choice_mode(self.fmt), "correct_only")
        self.assertEqual([b["t"] for b in self.fmt["back"]], ["field", "choices", "field"])

    def test_switch_back_and_forth(self):
        full = F.set_qcm_back(self.fmt, "highlight")
        self.assertEqual(F.back_choice_mode(full), "highlight")
        titles = [b for b in full["back"] if b.get("style") == "title"]
        self.assertEqual([b["field"] for b in titles], ["Question"])
        again = F.set_qcm_back(full, "highlight")
        self.assertEqual(len([b for b in again["back"] if b.get("style") == "title"]), 1)
        short = F.set_qcm_back(full, "correct_only")
        self.assertEqual(short["back"], self.fmt["back"])

    def test_input_not_modified(self):
        before = copy.deepcopy(self.fmt)
        F.set_qcm_back(self.fmt, "highlight")
        self.assertEqual(self.fmt, before)


class NormalizeTests(unittest.TestCase):
    def test_bad_blocks_are_dropped(self):
        f = F.normalize_format({"mode": "custom", "front": [
            {"t": "field", "field": "Front", "style": "weird"}, {"t": "zzz"}, 42,
            {"t": "choices", "fields": []}], "back": []})
        self.assertEqual(f["front"], [F.field_block("Front", "text")])

    def test_empty_custom_is_refused(self):
        with self.assertRaises(ValueError):
            F.normalize_format({"mode": "custom", "front": [], "back": []})
        with self.assertRaises(ValueError):
            F.normalize_format({"mode": "nope"})


class ResolveTests(unittest.TestCase):
    FIELDS = dict(zip(["Question", "A", "B", "C", "D", "Reponse", "Explication"],
                      ["Q ?", "un", "deux", "trois", "quatre", "C", "Parce que."]))

    def setUp(self):
        self.fmt = F.qcm_format(F.detect_choice(QCM))

    def side(self, side, fmt=None, lang="fr", fields=None, tags=" DT::Sources "):
        return F.resolve_side(fmt or self.fmt, side, fields or self.FIELDS, tags, "Droit", lang)

    def test_front_lists_options_plainly(self):
        els = self.side("front")
        self.assertEqual([e[0] for e in els], ["tag", "text", "choices"])
        self.assertEqual(els[0][1], ["DT › Sources"])
        kind, rows, good, show = els[2]
        self.assertEqual([r[0] for r in rows], ["A", "B", "C", "D"])
        self.assertEqual((good, show), ([2], "plain"))

    def test_back_answer_only_with_localized_label(self):
        els = self.side("back")
        self.assertEqual([e[0] for e in els], ["tag", "choices", "explain"])
        self.assertEqual((els[1][2], els[1][3]), ([2], "correct_only"))
        self.assertEqual(els[2][1], "Bonne réponse : C")
        self.assertEqual(self.side("back", lang="en")[2][1], "Correct answer: C")

    def test_unreadable_answer_falls_back_to_plain(self):
        els = self.side("back", fields=dict(self.FIELDS, Reponse="voir le cours"))
        self.assertEqual(els[1][3], "plain")
        self.assertEqual(els[2][1], "Explication")

    def test_empty_options_and_fields_are_skipped(self):
        els = self.side("front", fields=dict(self.FIELDS, B="", D=" "), tags="")
        self.assertEqual([e[0] for e in els], ["text", "choices"])
        self.assertEqual([r[0] for r in els[1][1]], ["A", "C"])
        self.assertEqual(els[1][2], [1])  # « C » est maintenant la 2e proposition affichée

    def test_label_substitution(self):
        fmt = {"mode": "custom", "css": True, "front": [],
               "back": [F.field_block("Explication", "explain", "Réponse {Reponse} / {answer}")]}
        self.assertEqual(self.side("back", fmt)[0][1], "Réponse C / ")

    def test_cloze_in_custom_format(self):
        fmt = {"mode": "custom", "css": True, "front": [F.field_block("Text", "text")],
               "back": [F.field_block("Text", "text")]}
        fields = {"Text": "{{c1::Alpha}} et {{c2::bêta}}"}
        front = F.resolve_side(fmt, "front", fields, "", "", "fr", cloze=(1, False))
        back = F.resolve_side(fmt, "back", fields, "", "", "fr", cloze=(1, True))
        self.assertIn("[...]", front[0][1])
        self.assertIn("Alpha</cl>", back[0][1])


class BookTests(unittest.TestCase):
    def test_detection_and_overrides(self):
        book = F.FormatBook()
        self.assertEqual(book.mode_of(QCM), "detected")
        self.assertIsNotNone(book.for_model(QCM))
        self.assertIsNone(book.for_model(MODELS["11"]))
        book.set("QCM", {"mode": "auto"})  # « Automatique » choisi explicitement
        self.assertEqual(book.mode_of(QCM), "auto")
        self.assertIsNone(book.for_model(QCM))
        book.set("Basique", F.starter_format(MODELS["11"]))
        self.assertEqual(book.mode_of(MODELS["11"]), "custom")
        self.assertEqual(book.for_model(MODELS["11"])["front"][0]["field"], "Front")
        self.assertIsNone(F.FormatBook(detect=False).for_model(QCM))

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(
                os.environ, {"APKG2CARDS_CONFIG_DIR": d}):
            book = F.FormatBook()
            book.set("Basique", F.starter_format(MODELS["11"]))
            path = F.save_book(book)
            self.assertEqual(path, os.path.join(d, "formats.json"))
            loaded = F.load_book()
            self.assertEqual(loaded.formats["Basique"], book.formats["Basique"])

    def test_missing_or_broken_file_gives_empty_book(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(F.load_book(os.path.join(d, "absent.json")).formats, {})
            bad = os.path.join(d, "bad.json")
            with open(bad, "w") as f:
                f.write("{pas du json")
            self.assertEqual(F.load_book(bad).formats, {})
            with open(bad, "w") as f:
                json.dump({"formats": {"X": {"mode": "custom", "front": [], "back": []}}}, f)
            self.assertEqual(F.load_book(bad).formats, {})  # format vide ignoré


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.apkg = make_qcm_apkg(self.tmp.name)
        self.col = core.Collection(self.apkg)

    def tearDown(self):
        self.col.close()
        self.tmp.cleanup()

    def test_note_types_listing(self):
        names = {t["name"]: t["notes"] for t in self.col.note_types()}
        self.assertEqual(names, {"QCM": 3, "Basique": 1, "Trous": 1})

    def test_qcm_cards_are_rich_and_one_per_note(self):
        cards = self.col.cards(model_name="QCM", lang="fr")
        self.assertEqual(len(cards), 3)
        front, back, deck = cards[0]
        self.assertIsInstance(front, RichSide)
        self.assertEqual(deck, "QCM")
        kinds = [e[0] for e in back.elements]
        self.assertEqual(kinds, ["tag", "choices", "explain"])

    def test_other_types_keep_template_rendering(self):
        cards = self.col.cards(model_name="Basique")
        self.assertEqual(len(cards), 1)  # la carte inversée n'est pas dupliquée
        self.assertNotIsInstance(cards[0][0], RichSide)

    def test_tags_field_available_to_anki_templates(self):
        fields = core.build_card_sides(
            {"flds": [{"name": "Front", "ord": 0}], "type": 0,
             "tmpls": [{"qfmt": "{{#Tags}}[{{Tags}}] {{/Tags}}{{Front}}", "afmt": "{{Front}}"}]},
            ["Q"], 0, extra={"Tags": "DT::Sources"})
        self.assertEqual(fields[0], "[DT::Sources] Q")

    def test_explicit_auto_disables_detection(self):
        book = F.FormatBook({"QCM": {"mode": "auto"}})
        cards = self.col.cards(model_name="QCM", formats_book=book)
        self.assertNotIsInstance(cards[0][0], RichSide)

    def test_custom_format_on_basic_and_cloze_types(self):
        book = F.FormatBook({
            "Basique": F.starter_format(MODELS["11"]),
            "Trous": F.starter_format(MODELS["12"])})
        basic = self.col.cards(model_name="Basique", formats_book=book, include_reversed=True)
        self.assertEqual(len(basic), 1)  # un format décrit la note entière
        self.assertIsInstance(basic[0][0], RichSide)
        cloze = self.col.cards(model_name="Trous", formats_book=book)
        self.assertEqual(len(cloze), 2)  # un trou = une carte
        self.assertIn("[...]", cloze[0][0].elements[0][1][0][1])

    def test_missing_tags_column_is_tolerated(self):
        from test_core import make_apkg
        with tempfile.TemporaryDirectory() as d:
            with core.Collection(make_apkg(d)) as col:
                self.assertTrue(col.cards())

    def test_convert_both_back_modes(self):
        for mode in ("correct_only", "highlight"):
            out = os.path.join(self.tmp.name, f"{mode}.pdf")
            r = core.convert(self.apkg, out, formats=F.FormatBook(qcm_back=mode), lang="fr")
            self.assertEqual(r["cards"], 3 + 1 + 2)
            self.assertGreater(os.path.getsize(out), 3000)

    def test_css_off_uses_app_color(self):
        fmt = F.qcm_format(F.detect_choice(QCM))
        fmt["css"] = False
        book = F.FormatBook({"QCM": fmt})
        cards = self.col.cards(model_name="QCM", formats_book=book,
                               theme=core.make_theme("#dc2626"))
        self.assertEqual(hexcolor(cards[0][0].skin.accent), "#dc2626")
        css_cards = self.col.cards(model_name="QCM")
        self.assertEqual(hexcolor(css_cards[0][0].skin.accent), "#4f6bed")

    def test_preview_index_and_model_filter(self):
        a = core.render_preview(self.col, model_name="QCM", index=0)
        b = core.render_preview(self.col, model_name="QCM", index=1)
        c = core.render_preview(self.col, model_name="QCM", index=99)  # au-delà : la dernière
        self.assertFalse(a["sample"])
        self.assertNotEqual(a["pdf"], b["pdf"])
        self.assertTrue(c["pdf"])
        self.assertTrue(core.render_preview(self.col, model_name="Inconnu")["sample"])


class CliTests(unittest.TestCase):
    def test_options(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(
                os.environ, {"APKG2CARDS_CONFIG_DIR": d}):
            apkg = make_qcm_apkg(d)
            out = os.path.join(d, "o.pdf")
            self.assertEqual(cli_main([apkg, "-o", out, "--qcm-back", "highlight",
                                       "--lang", "fr"]), 0)
            self.assertTrue(os.path.getsize(out) > 3000)
            fmts = os.path.join(d, "mes_formats.json")
            book = F.FormatBook()
            book.set("QCM", {"mode": "auto"})
            F.save_book(book, fmts)
            self.assertEqual(cli_main([apkg, "-o", out, "--formats", fmts]), 0)
            self.assertEqual(cli_main([apkg, "-o", out, "--formats",
                                       os.path.join(d, "absent.json")]), 1)


if __name__ == "__main__":
    unittest.main()

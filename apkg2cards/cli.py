"""Interface en ligne de commande."""
import argparse
import sys

from .core import DEFAULT_COLOR, ApkgError, convert, list_decks
from .i18n import set_language, t


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="apkg2cards",
        description="Convertit un .apkg Anki en PDF de flashcards à imprimer "
                    "en recto-verso et à découper. / Converts an Anki .apkg into "
                    "double-sided printable flashcards.")
    ap.add_argument("apkg", help="fichier .apkg à convertir")
    ap.add_argument("-o", "--output", help="PDF de sortie")
    ap.add_argument("--cols", type=int, default=2, help="cartes par ligne (défaut 2)")
    ap.add_argument("--rows", type=int, default=4, help="lignes par page (défaut 4)")
    ap.add_argument("--margin", type=float, default=8, help="marge en mm (défaut 8)")
    ap.add_argument("--font-size", type=float, default=16, help="taille max du texte (défaut 16)")
    ap.add_argument("--landscape", action="store_true", help="page en paysage")
    ap.add_argument("--flip", choices=["long", "short"], default="long",
                    help="retournement choisi à l'impression (défaut : bord long)")
    ap.add_argument("--deck", help="garder les paquets dont le nom contient ce texte")
    ap.add_argument("--color", default=DEFAULT_COLOR,
                    help=f"couleur des cartes : #rrggbb ou nom anglais (défaut {DEFAULT_COLOR})")
    ap.add_argument("--with-reversed", action="store_true",
                    help="imprimer aussi les cartes inversées (par défaut : une carte par note)")
    ap.add_argument("--lang", choices=["fr", "en"],
                    help="langue des messages (défaut : celle du système)")
    ap.add_argument("--card-lang", choices=["fr", "en"],
                    help="langue des libellés imprimés sur les cartes (défaut : --lang)")
    ap.add_argument("--list-decks", action="store_true", help="liste les paquets et quitte")
    a = ap.parse_args(argv)

    if a.lang:
        set_language(a.lang)

    try:
        if a.list_decks:
            print("\n".join(list_decks(a.apkg)))
            return 0
        r = convert(a.apkg, a.output, a.cols, a.rows, a.margin, a.font_size,
                    a.landscape, a.flip, a.deck,
                    include_reversed=a.with_reversed, color=a.color, lang=a.card_lang)
    except ApkgError as e:
        print(t("cli.error", msg=e), file=sys.stderr)
        return 1
    print(t("cli.result", cards=r["cards"], output=r["output"], pages=r["pages"]))
    if r["overflow"]:
        print(t("cli.overflow", n=r["overflow"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

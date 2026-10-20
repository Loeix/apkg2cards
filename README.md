# apkg2cards

Convertit un paquet **Anki (`.apkg`)** en **PDF de flashcards physiques** : les cartes sont
mises en page pour être imprimées en recto-verso puis découpées. Les versos sont placés en
miroir pour tomber pile derrière leur recto.

- Interface graphique (Tkinter) **et** ligne de commande
- Grille réglable (2×4 par défaut, soit ~95×71 mm par carte), portrait ou paysage
- Texte centré, taille réduite automatiquement si la carte est longue
- Gère le gras / italique / exposant, les images, les cartes inversées et les cloze
  (trou `[...]` au recto, réponse en bleu gras au verso)
- Cartes arrondies à bandeau coloré (QUESTION / RÉPONSE + nom du paquet), verso teinté,
  **couleur au choix** (palette ou couleur libre)
- Une carte par note : les cartes inversées (« Basique et carte inversée ») ne sont pas
  imprimées en double, puisqu'une carte physique a déjà deux faces (option pour les inclure)
- Filtre par paquet

## Installation

Python 3.9+ requis (Tkinter est inclus avec Python sur Windows et macOS ;
sous Debian/Ubuntu : `sudo apt install python3-tk`).

```bash
git clone https://github.com/<ton-pseudo>/apkg2cards.git
cd apkg2cards
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

## Utilisation

**Interface graphique** (sans argument) :

```bash
python -m apkg2cards
```

**Ligne de commande** :

```bash
python -m apkg2cards mon_paquet.apkg
python -m apkg2cards mon_paquet.apkg -o cartes.pdf --cols 3 --rows 3
python -m apkg2cards mon_paquet.apkg --deck "Droit civil"
python -m apkg2cards mon_paquet.apkg --list-decks
```

| Option | Rôle | Défaut |
|---|---|---|
| `-o, --output` | PDF de sortie | `<nom>_cartes.pdf` |
| `--cols` / `--rows` | cartes par ligne / par page | 2 / 4 |
| `--margin` | marge de page (mm) | 8 |
| `--font-size` | taille max du texte (pt) | 16 |
| `--landscape` | page en paysage | non |
| `--flip long\|short` | retournement choisi à l'impression | `long` |
| `--deck TEXTE` | ne garder que les paquets contenant ce texte | tous |
| `--color` | couleur des cartes (`#rrggbb` ou nom anglais : `red`, `green`…) | `#2563eb` |
| `--with-reversed` | imprimer aussi les cartes inversées | non |
| `--list-decks` | liste les paquets et quitte | |

Installation en tant que commande (optionnel) : `pip install .` puis `apkg2cards` /
`apkg2cards-gui`.

## Application Windows (installateur)

Pas besoin de Python pour l'utiliser : télécharge `apkg2cards-setup.exe` dans l'onglet
**Releases** du dépôt, lance-le, puis ouvre apkg2cards depuis le menu Démarrer
(l'installation ne demande pas les droits administrateur).

> L'installateur n'est pas signé : Windows peut afficher « Windows a protégé votre PC ».
> Clique sur **Informations complémentaires → Exécuter quand même**.

**Construire l'installateur soi-même**

- *Automatiquement (GitHub)* : onglet **Releases → Draft a new release**, tag `v` suivi du numéro de
  `__version__` (ex. `v0.1.2`, « Create new tag on publish »). puis **Publish release**. Le tag doit correspondre à la
  version du code, sinon le workflow s'arrête. Le workflow `build-windows`
  (onglet Actions) construit l'installateur et l'ajoute à la release au bout de quelques minutes.
- *Sur ton PC* : installe [Inno Setup 6](https://jrsoftware.org/isinfo.php), puis double-clique
  sur `build_windows.bat`. Résultat : `installer\apkg2cards-setup.exe`.
  Sans Inno Setup, le script produit seulement `dist\apkg2cards\apkg2cards.exe`.

## Export depuis Anki

Dans Anki : *Fichier → Exporter…* → format **Paquet Anki (`.apkg`)** et coche
**« Prendre en charge les anciennes versions d'Anki »**. Sans cette case, le fichier est au
format récent (`.anki21b`) que l'outil ne lit pas, et il t'en avertit.

## Impression

1. Imprime en **recto-verso**, retournement sur le **bord long** (portrait).
   En paysage, choisis le bord court. Si tu règles l'autre option dans ton imprimante,
   utilise `--flip short` (ou le menu « Retournement » de l'interface).
2. Échelle **100 %** (pas « ajuster à la page »).
3. Fais un **test sur une seule feuille** avant d'imprimer tout le paquet.
4. Découpe le long des pointillés.

## Limites

- Le rendu suit les templates du type de note (champs, conditions, cloze) mais ignore le CSS
  d'Anki ; les images webp/svg ne sont pas gérées (affichées `[image]`).
- Le LaTeX / MathJax n'est pas rendu.
- Les polices DejaVu (Linux) ou Arial (Windows/macOS) sont utilisées si présentes,
  sinon Helvetica (certains symboles peuvent manquer).

## Développement

```bash
python -m unittest discover -s tests -v
```

## Licence

MIT — voir [LICENSE](LICENSE).

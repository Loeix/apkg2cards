# apkg2cards

🇫🇷 Français · [🇬🇧 English](README.en.md)

Convertit un paquet **Anki (`.apkg`)** en **PDF de flashcards physiques** : les cartes sont
mises en page pour être imprimées en recto-verso puis découpées. Les versos sont placés en
miroir pour tomber pile derrière leur recto.

## Fonctionnalités

- Interface moderne (Qt / PySide6) **et** ligne de commande
- **Aperçu en direct de la page A4 entière** (recto et verso en miroir, avec les vraies cartes de
  ton paquet), ou d'une seule carte en gros plan ; bouton **Réinitialiser** pour la mise en page
- **Français / anglais** : interface, messages et libellés imprimés sur les cartes
  (réglage séparé possible), changement sans redémarrer
- Thème **clair ou sombre** (suit le système au premier lancement), réglages mémorisés
- **Mise à jour intégrée** (Windows) : un clic, sans rien télécharger à la main, avec vérification
  de la somme de contrôle ; deux **canaux** au choix : *Stable* ou *Bêta*
- Cartes arrondies à bandeau coloré (QUESTION / RÉPONSE + nom du paquet), verso teinté,
  **couleur au choix** (palette ou couleur libre)
- Grille réglable (2×4 par défaut, soit ~95×67 mm par carte), portrait ou paysage
- Texte centré, taille réduite automatiquement si la carte est longue
- Gras / italique / exposant, images, cartes inversées et cloze
  (trou `[...]` au recto, réponse en couleur et en gras au verso)
- Une carte par note : les cartes inversées ne sont pas imprimées en double (option pour les inclure)
- Glisser-déposer d'un `.apkg` dans la fenêtre, filtre par paquet

## Installation

### Windows (le plus simple)

Télécharge `apkg2cards-setup.exe` dans l'onglet **Releases** du dépôt et lance-le
(pas de droits administrateur nécessaires). Ensuite, l'application se met à jour toute seule :
bouton **Rechercher une mise à jour**, ou bandeau vert qui apparaît au démarrage.

> L'installateur n'est pas signé : Windows peut afficher « Windows a protégé votre PC ».
> Clique sur **Informations complémentaires → Exécuter quand même**.

### Depuis le code source

Python 3.10+ requis. L'interface utilise PySide6 (environ 200 Mo de dépendances).

```bash
git clone https://github.com/Loeix/apkg2cards.git
cd apkg2cards
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
python -m apkg2cards             # interface graphique
```

La mise à jour automatique n'existe que dans l'application installée ; depuis le code source,
le bouton ouvre simplement la page de téléchargement.

## Ligne de commande

```bash
python -m apkg2cards mon_paquet.apkg
python -m apkg2cards mon_paquet.apkg -o cartes.pdf --cols 3 --rows 3 --color "#16a34a"
python -m apkg2cards mon_paquet.apkg --deck "Droit civil" --lang en
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
| `--lang fr\|en` | langue des messages | celle du système |
| `--card-lang fr\|en` | langue des libellés imprimés (QUESTION / ANSWER) | `--lang` |
| `--list-decks` | liste les paquets et quitte | |

## Export depuis Anki

Dans Anki : *Fichier → Exporter…* → format **Paquet Anki (`.apkg`)** et coche
**« Prendre en charge les anciennes versions d'Anki »**. Sans cette case, le fichier est au
format récent (`.anki21b`) que l'outil ne lit pas, et il t'en avertit.

## Impression

1. Imprime en **recto-verso**, retournement sur le **bord long** (portrait).
   En paysage, choisis le bord court. Si ton imprimante est réglée autrement,
   change le menu « Retournement » de l'interface (ou `--flip short`).
2. Échelle **100 %** (pas « ajuster à la page »).
3. Fais un **test sur une seule feuille** avant d'imprimer tout le paquet.
4. Découpe le long des contours arrondis.

## Mises à jour : canaux stable et bêta

| Canal | Reçoit | Pour qui |
|---|---|---|
| **Stable** (défaut) | les versions finales (`v0.4.0`) | tout le monde |
| **Bêta** | les versions finales **et** les pré-versions (`v0.4.1-beta.1`) | ceux qui veulent tester en avance |

Le canal se choisit dans le panneau **Application** de l'interface. On ne rétrograde jamais
automatiquement : si tu es sur une bêta plus récente que la dernière stable, tu y restes jusqu'à la
prochaine version stable.

Comment ça marche : l'application lit la liste des releases GitHub, télécharge
`apkg2cards-setup.exe`, vérifie son SHA-256, le lance en mode silencieux puis se ferme ;
l'installateur remplace les fichiers et relance l'application.

## Publier une version (mainteneur)

Le numéro de version existe à **un seul endroit** : `__version__` dans `apkg2cards/__init__.py`.

| Type | `__version__` | Tag de la release | Case « pre-release » |
|---|---|---|---|
| Stable | `0.4.0` | `v0.4.0` | **non** |
| Bêta | `0.4.1-beta.1` | `v0.4.1-beta.1` | **oui** |

1. Change `__version__`, commit, synchronise.
2. Sur GitHub : **Releases → Draft a new release**, tag `v` + la version, coche (ou non)
   « Set as a pre-release », écris les notes (elles s'affichent dans la fenêtre de mise à jour),
   puis **Publish release**.
3. Le workflow `build-windows` (onglet Actions) vérifie que le tag, la version du code et la case
   pre-release sont cohérents, construit l'installateur et joint `apkg2cards-setup.exe` ainsi que
   son `.sha256` à la release. Sans ces deux fichiers, la mise à jour automatique ne propose rien.

Ordre des versions : `0.4.0-beta.1` < `0.4.0-beta.2` < `0.4.0-rc.1` < `0.4.0` < `0.4.1-beta.1`.

Construire l'installateur sur son PC : installe [Inno Setup 6](https://jrsoftware.org/isinfo.php)
puis double-clique sur `build_windows.bat` (résultat : `installer\apkg2cards-setup.exe`).

## Ajouter une langue

Copie `apkg2cards/locales/en.py` en `xx.py`, traduis les valeurs (pas les clés), puis déclare la
langue dans `apkg2cards/i18n.py` (`LANGUAGES` et `_load`). Le test `tests/test_i18n.py` vérifie que
toutes les clés et tous les paramètres `{...}` sont présents.

## Limites

- Le rendu suit les templates du type de note (champs, conditions, cloze) mais ignore le CSS
  d'Anki ; les images webp/svg ne sont pas gérées (affichées `[image]`).
- Le LaTeX / MathJax n'est pas rendu.
- Les polices DejaVu (Linux) ou Arial (Windows/macOS) sont utilisées si présentes,
  sinon Helvetica (certains symboles peuvent manquer).
- Mise à jour automatique : Windows uniquement, application installée.

## Développement

```bash
python -m unittest discover -s tests -v
```

Les tests de l'interface sont ignorés si PySide6 n'est pas installé.

## Licence

MIT — voir [LICENSE](LICENSE). L'interface utilise PySide6 (Qt for Python), sous licence LGPL.

# apkg2cards

[🇫🇷 Français](README.md) · 🇬🇧 English

Converts an **Anki (`.apkg`)** deck into a **PDF of physical flashcards**: cards are laid out
to be printed double-sided and cut out. Backs are mirrored so each one lands exactly behind its front.

## Features

- Modern interface (Qt / PySide6) **and** command line
- **Live preview** of a card (front + back) using the first card of your deck
- **English / French**: interface, messages and the labels printed on the cards
  (can be set separately), switchable without restarting
- **Light or dark** theme (follows the system on first launch), settings remembered
- **Built-in updates** (Windows): one click, nothing to download by hand, checksum verified;
  two **channels**: *Stable* or *Beta*
- Rounded cards with a colored header (QUESTION / ANSWER + deck name), tinted back,
  **any color** (palette or custom)
- Adjustable grid (2×4 by default, about 95×67 mm per card), portrait or landscape
- Centered text, automatically shrunk when a card is long
- Bold / italic / superscript, images, reversed cards and cloze deletions
  (`[...]` on the front, colored bold answer on the back)
- One card per note: reversed cards are not printed twice (option to include them)
- Drag and drop an `.apkg` into the window, deck filter

## Installation

### Windows (easiest)

Download `apkg2cards-setup.exe` from the repository's **Releases** tab and run it
(no administrator rights needed). After that the app updates itself: use
**Check for updates**, or the green banner that appears at startup.

> The installer is not code-signed: Windows may show “Windows protected your PC”.
> Click **More info → Run anyway**.

### From source

Python 3.9+ required. The interface uses PySide6 (about 200 MB of dependencies).

```bash
git clone https://github.com/Loeix/apkg2cards.git
cd apkg2cards
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m apkg2cards             # graphical interface
```

Automatic updates only exist in the installed app; from source, the button just opens the
download page.

## Command line

```bash
python -m apkg2cards my_deck.apkg
python -m apkg2cards my_deck.apkg -o cards.pdf --cols 3 --rows 3 --color "#16a34a"
python -m apkg2cards my_deck.apkg --deck "Civil law" --lang en
python -m apkg2cards my_deck.apkg --list-decks
```

| Option | Purpose | Default |
|---|---|---|
| `-o, --output` | output PDF | `<name>_cartes.pdf` |
| `--cols` / `--rows` | cards per row / per page | 2 / 4 |
| `--margin` | page margin (mm) | 8 |
| `--font-size` | max text size (pt) | 16 |
| `--landscape` | landscape page | no |
| `--flip long\|short` | flip option chosen when printing | `long` |
| `--deck TEXT` | keep only decks whose name contains this text | all |
| `--color` | card color (`#rrggbb` or English name: `red`, `green`…) | `#2563eb` |
| `--with-reversed` | also print reversed cards | no |
| `--lang fr\|en` | message language | system language |
| `--card-lang fr\|en` | language of the printed labels (QUESTION / ANSWER) | `--lang` |
| `--list-decks` | list decks and exit | |

## Exporting from Anki

In Anki: *File → Export…* → **Anki Deck Package (`.apkg`)** and tick
**“Support older Anki versions”**. Without it the file uses the new format (`.anki21b`),
which this tool cannot read (it will tell you so).

## Printing

1. Print **double-sided**, flipping on the **long edge** (portrait). In landscape choose the short
   edge. If your printer is set differently, change the “Flip” menu in the interface (or `--flip short`).
2. **100 %** scale (not “fit to page”).
3. Do a **test on a single sheet** before printing the whole deck.
4. Cut along the rounded outlines.

## Updates: stable and beta channels

| Channel | Receives | For whom |
|---|---|---|
| **Stable** (default) | final versions (`v0.4.0`) | everyone |
| **Beta** | final versions **and** pre-releases (`v0.4.1-beta.1`) | people who want to test early |

Pick the channel in the **Application** panel. The app never downgrades automatically: if you are on
a beta newer than the latest stable, you stay on it until the next stable release.

How it works: the app reads the GitHub releases list, downloads `apkg2cards-setup.exe`, verifies
its SHA-256, runs it silently and closes; the installer replaces the files and restarts the app.

## Publishing a release (maintainer)

The version number lives in **one place**: `__version__` in `apkg2cards/__init__.py`.

| Type | `__version__` | Release tag | “pre-release” box |
|---|---|---|---|
| Stable | `0.4.0` | `v0.4.0` | **no** |
| Beta | `0.4.1-beta.1` | `v0.4.1-beta.1` | **yes** |

1. Change `__version__`, commit, push.
2. On GitHub: **Releases → Draft a new release**, tag `v` + the version, tick (or not)
   “Set as a pre-release”, write the notes (they appear in the update window), then **Publish release**.
3. The `build-windows` workflow checks that the tag, the code version and the pre-release box agree,
   builds the installer and attaches `apkg2cards-setup.exe` and its `.sha256` to the release.
   Without those two files automatic updates offer nothing.

Version order: `0.4.0-beta.1` < `0.4.0-beta.2` < `0.4.0-rc.1` < `0.4.0` < `0.4.1-beta.1`.

## Adding a language

Copy `apkg2cards/locales/en.py` to `xx.py`, translate the values (not the keys), then register the
language in `apkg2cards/i18n.py` (`LANGUAGES` and `_load`). `tests/test_i18n.py` checks that every key
and every `{...}` placeholder is present.

## Limitations

- Rendering follows the note type's templates (fields, conditionals, cloze) but ignores Anki's CSS;
  webp/svg images are not supported (shown as `[image]`).
- LaTeX / MathJax is not rendered.
- DejaVu (Linux) or Arial (Windows/macOS) fonts are used when available, otherwise Helvetica.
- Automatic update: Windows only, installed app.

## Development

```bash
python -m unittest discover -s tests -v
```

GUI tests are skipped when PySide6 is not installed.

## License

MIT — see [LICENSE](LICENSE). The interface uses PySide6 (Qt for Python), licensed under the LGPL.

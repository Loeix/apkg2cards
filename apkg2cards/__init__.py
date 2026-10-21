"""apkg2cards — convertit un paquet Anki (.apkg) en PDF de flashcards imprimables."""
from .core import ApkgError, convert, list_decks

__all__ = ["ApkgError", "convert", "list_decks"]
__version__ = "0.4.0-beta"

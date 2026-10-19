"""Recherche de mise à jour : compare la version installée à la dernière release GitHub."""
import json
import re
import urllib.error
import urllib.request

from . import __version__

REPO = "Loeix/apkg2cards"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
DOWNLOAD_URL = f"https://github.com/{REPO}/releases/latest/download/apkg2cards-setup.exe"


class UpdateError(Exception):
    """Impossible de joindre GitHub ou réponse illisible."""


def parse_version(text):
    """'v0.1.2' -> (0, 1, 2). Lève ValueError si le texte ne ressemble pas à une version."""
    m = re.match(r"^\s*v?(\d+(?:\.\d+)*)", text or "")
    if not m:
        raise ValueError(f"Version illisible : {text!r}")
    return tuple(int(p) for p in m.group(1).split("."))


def is_newer(latest, current=__version__):
    a, b = list(parse_version(latest)), list(parse_version(current))
    n = max(len(a), len(b))
    a += [0] * (n - len(a))
    b += [0] * (n - len(b))
    return a > b


def check_for_update(current=__version__, timeout=8):
    """Renvoie {'current', 'latest', 'available', 'url'}. Lève UpdateError en cas d'échec."""
    req = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"apkg2cards/{current}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError("Aucune version publiée sur GitHub pour l'instant.")
        raise UpdateError(f"GitHub a répondu une erreur ({e.code}).")
    except (urllib.error.URLError, TimeoutError, OSError):
        raise UpdateError("Impossible de joindre GitHub. Vérifie ta connexion Internet.")
    except ValueError:
        raise UpdateError("Réponse de GitHub illisible.")
    tag = data.get("tag_name", "")
    try:
        available = is_newer(tag, current)
    except ValueError:
        raise UpdateError("Numéro de version de la dernière release illisible.")
    return {"current": current, "latest": tag.lstrip("v"), "available": available,
            "url": data.get("html_url") or RELEASES_URL}

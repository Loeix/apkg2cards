"""Mises à jour : canaux stable/bêta, téléchargement vérifié, installation silencieuse.

Principe (Windows, application installée) :
1. on lit la liste des releases GitHub et on choisit la plus récente du canal voulu ;
2. on télécharge l'installateur en vérifiant sa somme de contrôle SHA-256 ;
3. on le lance en mode silencieux et l'application se ferme : l'installateur remplace les
   fichiers puis relance l'application.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from .i18n import t

REPO = "Loeix/apkg2cards"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
INSTALLER_NAME = "apkg2cards-setup.exe"
CHANNELS = ("stable", "beta")
USER_AGENT = "apkg2cards-updater"


class UpdateError(Exception):
    """Erreur lisible par l'utilisateur ; le message est une clé de traduction."""

    def __init__(self, key, **params):
        super().__init__(key)
        self.key, self.params = key, params

    def __str__(self):
        return t(self.key, **self.params)


class UpdateCancelled(UpdateError):
    """L'utilisateur a annulé le téléchargement."""


# --------------------------------------------------------------------------
# Numéros de version : 0.4.0-beta.2 < 0.4.0 < 0.4.1-beta.1
# --------------------------------------------------------------------------
_VERSION_RE = re.compile(
    r"^[vV]?\.?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-.]?([A-Za-z]+)[.-]?(\d+)?)?$")
_PHASES = {"alpha": 0, "a": 0, "beta": 1, "b": 1, "rc": 2}
_STABLE = 3


def parse_version(v):
    """'v0.4.0-beta.2' -> (0, 4, 0, phase, 2). Lève ValueError si le texte n'est pas une version."""
    m = _VERSION_RE.match(str(v).strip())
    if not m:
        raise ValueError(f"version invalide : {v!r}")
    major, minor, patch, phase, num = m.groups()
    nums = (int(major), int(minor or 0), int(patch or 0))
    if phase is None:
        return nums + (_STABLE, 0)
    rank = _PHASES.get(phase.lower())
    if rank is None:
        raise ValueError(f"phase de version inconnue : {phase!r}")
    return nums + (rank, int(num or 0))


def is_newer(candidate, current):
    return parse_version(candidate) > parse_version(current)


def is_prerelease_version(v):
    return parse_version(v)[3] < _STABLE


def display_version(v):
    """'v.0.4.0-beta.1' -> '0.4.0-beta.1'."""
    return re.sub(r"^[vV]?\.?", "", str(v).strip())


# --------------------------------------------------------------------------
# Réseau
# --------------------------------------------------------------------------
def _request(url):
    return urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})


def _http_get(url, timeout=15):
    try:
        with urllib.request.urlopen(_request(url), timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise UpdateError("upd.err.rate")
        if e.code == 404:
            raise UpdateError("upd.err.no_release")
        raise UpdateError("upd.err.http", code=e.code)
    except OSError:  # URLError, délai dépassé, pas de réseau...
        raise UpdateError("upd.err.offline")


def _open(url, timeout=30):
    return urllib.request.urlopen(_request(url), timeout=timeout)


# --------------------------------------------------------------------------
# Choix de la release
# --------------------------------------------------------------------------
def _asset(release, name):
    for a in release.get("assets") or []:
        if a.get("name") == name:
            return a
    return None


def pick_latest(releases, channel):
    """Release la plus récente du canal, parmi celles qui ont un installateur."""
    best = None
    for rel in releases:
        if not isinstance(rel, dict) or rel.get("draft"):
            continue
        try:
            ver = parse_version(rel.get("tag_name") or "")
        except ValueError:
            continue
        prerelease = bool(rel.get("prerelease")) or ver[3] < _STABLE
        if channel == "stable" and prerelease:
            continue
        if _asset(rel, INSTALLER_NAME) is None:
            continue  # l'installateur est peut-être encore en construction
        if best is None or ver > best[0]:
            best = (ver, rel)
    return best[1] if best else None


def check_for_update(current, channel="stable"):
    """Cherche une version plus récente que `current` sur le canal `channel`.

    Renvoie un dict : available, version, tag, url, notes, prerelease, channel,
    asset_url, asset_name, asset_size, sha256, sha_url.
    """
    if channel not in CHANNELS:
        channel = "stable"
    raw = _http_get(RELEASES_URL)
    try:
        releases = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise UpdateError("upd.err.bad_response")
    if not isinstance(releases, list):
        raise UpdateError("upd.err.bad_response")

    rel = pick_latest(releases, channel)
    if rel is None:
        raise UpdateError("upd.err.no_release")
    tag = rel["tag_name"]
    asset = _asset(rel, INSTALLER_NAME)
    sha_asset = _asset(rel, INSTALLER_NAME + ".sha256")
    digest = str(asset.get("digest") or "")
    sha256 = digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else None
    try:
        available = is_newer(tag, current)
    except ValueError:
        raise UpdateError("upd.err.bad_response")
    return {
        "available": available,
        "version": display_version(tag),
        "tag": tag,
        "url": rel.get("html_url") or "",
        "notes": rel.get("body") or "",
        "prerelease": bool(rel.get("prerelease")) or is_prerelease_version(tag),
        "channel": channel,
        "asset_url": asset.get("browser_download_url"),
        "asset_name": asset.get("name") or INSTALLER_NAME,
        "asset_size": int(asset.get("size") or 0),
        "sha256": sha256,
        "sha_url": sha_asset.get("browser_download_url") if sha_asset else None,
    }


# --------------------------------------------------------------------------
# Téléchargement vérifié
# --------------------------------------------------------------------------
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def resolve_checksum(info):
    """SHA-256 attendu de l'installateur (empreinte GitHub, sinon fichier .sha256)."""
    sha = (info.get("sha256") or "").lower()
    if _SHA_RE.match(sha):
        return sha
    if info.get("sha_url"):
        words = _http_get(info["sha_url"]).decode("utf-8", "replace").split()
        if words and _SHA_RE.match(words[0].lower()):
            return words[0].lower()
    raise UpdateError("upd.err.no_checksum")


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def download_installer(info, progress=None, should_cancel=None):
    """Télécharge l'installateur dans un dossier temporaire et vérifie son SHA-256.

    `progress(octets_lus, total)` est appelé régulièrement ; `should_cancel()` permet
    d'interrompre. Renvoie le chemin du fichier vérifié.
    """
    url = info.get("asset_url")
    if not url:
        raise UpdateError("upd.err.no_release")
    expected = resolve_checksum(info)

    folder = os.path.join(tempfile.gettempdir(), "apkg2cards-update")
    os.makedirs(folder, exist_ok=True)
    for name in os.listdir(folder):  # anciens téléchargements
        _remove(os.path.join(folder, name))
    dest = os.path.join(folder, info.get("asset_name") or INSTALLER_NAME)
    part = dest + ".part"

    digest = hashlib.sha256()
    done = 0
    try:
        with _open(url) as resp, open(part, "wb") as out:
            headers = getattr(resp, "headers", None) or {}
            total = int(headers.get("Content-Length") or info.get("asset_size") or 0)
            while True:
                if should_cancel and should_cancel():
                    raise UpdateCancelled("upd.err.cancelled")
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except UpdateError:
        _remove(part)
        raise
    except urllib.error.URLError:
        _remove(part)
        raise UpdateError("upd.err.offline")
    except OSError as e:
        _remove(part)
        raise UpdateError("upd.err.disk", detail=str(e))

    if digest.hexdigest() != expected:
        _remove(part)
        raise UpdateError("upd.err.checksum")
    os.replace(part, dest)
    return dest


# --------------------------------------------------------------------------
# Installation
# --------------------------------------------------------------------------
def can_self_update():
    """Vrai seulement dans l'application Windows installée (pas depuis le code source)."""
    return sys.platform.startswith("win") and bool(getattr(sys, "frozen", False))


def launch_installer(path, relaunch=True):
    """Lance l'installateur en silencieux. L'appelant doit ensuite fermer l'application."""
    if not can_self_update():
        raise UpdateError("upd.err.unsupported")
    args = [path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
    if relaunch:
        args.append("/RELAUNCH=1")
    flags = getattr(subprocess, "DETACHED_PROCESS", 0x8) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
    try:
        subprocess.Popen(args, creationflags=flags, close_fds=True)
    except OSError as e:
        raise UpdateError("upd.err.launch", detail=str(e))

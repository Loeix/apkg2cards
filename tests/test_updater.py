import hashlib
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apkg2cards import __version__, updater  # noqa: E402
from apkg2cards.updater import UpdateCancelled, UpdateError  # noqa: E402

# Tous les numéros sont calculés à partir de la version en cours : aucun chiffre en dur,
# les tests ne cassent donc pas quand on change __version__.
_base = updater.parse_version(__version__)[:3]
CURRENT = __version__
PATCH_UP = f"{_base[0]}.{_base[1]}.{_base[2] + 1}"
MINOR_UP = f"{_base[0]}.{_base[1] + 1}.0"
MAJOR_UP = f"{_base[0] + 1}.0.0"
SHA = "a" * 64


def release(tag, prerelease=False, installer=True, body="notes", draft=False, digest=SHA):
    assets = []
    if installer:
        assets.append({"name": updater.INSTALLER_NAME, "size": 123, "digest": f"sha256:{digest}",
                       "browser_download_url": f"https://example.test/{tag}/setup.exe"})
        assets.append({"name": updater.INSTALLER_NAME + ".sha256",
                       "browser_download_url": f"https://example.test/{tag}/setup.exe.sha256"})
    return {"tag_name": tag, "prerelease": prerelease, "draft": draft, "body": body,
            "html_url": f"https://example.test/{tag}", "assets": assets}


def fake_get(releases):
    return mock.patch.object(updater, "_http_get", return_value=json.dumps(releases).encode())


class VersionTests(unittest.TestCase):
    def test_parse_formats(self):
        self.assertEqual(updater.parse_version("v0.1.2"), (0, 1, 2, 3, 0))
        self.assertEqual(updater.parse_version("1.0"), (1, 0, 0, 3, 0))
        self.assertEqual(updater.parse_version("v.0.1.3"), (0, 1, 3, 3, 0))  # faute de frappe tolérée
        self.assertEqual(updater.parse_version("0.4.0-beta.2"), (0, 4, 0, 1, 2))
        self.assertEqual(updater.parse_version("0.3.1-beta"), (0, 3, 1, 1, 0))

    def test_parse_invalid(self):
        for bad in ("latest", "nightly", "", "0.4.0-weird.1"):
            with self.assertRaises(ValueError):
                updater.parse_version(bad)

    def test_display_version(self):
        self.assertEqual(updater.display_version("v.0.4.0-beta.1"), "0.4.0-beta.1")

    def test_newer_than_current(self):
        for v in (PATCH_UP, MINOR_UP, MAJOR_UP):
            self.assertTrue(updater.is_newer("v" + v, CURRENT))

    def test_not_newer_than_current(self):
        self.assertFalse(updater.is_newer("v" + CURRENT, CURRENT))
        self.assertFalse(updater.is_newer("v" + CURRENT, PATCH_UP))
        self.assertFalse(updater.is_newer("v" + PATCH_UP, MINOR_UP))

    def test_prerelease_ordering(self):
        self.assertTrue(updater.is_newer("0.4.0", "0.4.0-beta.2"))   # la finale dépasse la bêta
        self.assertTrue(updater.is_newer("0.4.0-beta.2", "0.4.0-beta.1"))
        self.assertTrue(updater.is_newer("0.4.0-rc.1", "0.4.0-beta.9"))
        self.assertFalse(updater.is_newer("0.4.0-beta.1", "0.4.0"))
        self.assertTrue(updater.is_newer("0.4.1-beta.1", "0.4.0"))

    def test_numbers_not_text(self):
        self.assertTrue(updater.is_newer("0.10.0", "0.9.0"))


class ChannelTests(unittest.TestCase):
    def setUp(self):
        self.rels = [release("v" + PATCH_UP + "-beta.1", prerelease=True),
                     release("v" + CURRENT),
                     release("v" + MINOR_UP + "-beta.1", prerelease=True),
                     release("v" + MINOR_UP, installer=False),  # installateur pas encore prêt
                     release("v" + MAJOR_UP, draft=True),
                     release("nightly")]

    def test_stable_ignores_betas(self):
        with fake_get(self.rels):
            r = updater.check_for_update(CURRENT, "stable")
        self.assertFalse(r["available"])
        self.assertEqual(r["version"], CURRENT)

    def test_beta_takes_newest_including_prereleases(self):
        with fake_get(self.rels):
            r = updater.check_for_update(CURRENT, "beta")
        self.assertTrue(r["available"])
        self.assertEqual(r["version"], MINOR_UP + "-beta.1")
        self.assertTrue(r["prerelease"])
        self.assertEqual(r["asset_name"], updater.INSTALLER_NAME)
        self.assertEqual(r["sha256"], SHA)

    def test_unknown_channel_falls_back_to_stable(self):
        with fake_get(self.rels):
            self.assertEqual(updater.check_for_update(CURRENT, "???")["channel"], "stable")

    def test_stable_update_available(self):
        with fake_get([release("v" + PATCH_UP, body="Nouveautés")]):
            r = updater.check_for_update(CURRENT)
        self.assertTrue(r["available"])
        self.assertEqual(r["notes"], "Nouveautés")
        self.assertTrue(r["asset_url"].endswith("setup.exe"))

    def test_prerelease_flag_wins_over_tag(self):
        with fake_get([release("v" + PATCH_UP, prerelease=True)]):
            with self.assertRaises(UpdateError):  # rien pour le canal stable
                updater.check_for_update(CURRENT, "stable")

    def test_no_downgrade_from_beta_to_older_stable(self):
        installed = PATCH_UP + "-beta.1"
        with fake_get([release("v" + CURRENT)]):
            self.assertFalse(updater.check_for_update(installed, "stable")["available"])

    def test_final_replaces_installed_beta(self):
        installed = PATCH_UP + "-beta.2"
        with fake_get([release("v" + PATCH_UP)]):
            self.assertTrue(updater.check_for_update(installed, "stable")["available"])

    def test_no_release(self):
        with fake_get([]):
            with self.assertRaises(UpdateError):
                updater.check_for_update(CURRENT)

    def test_garbage(self):
        with mock.patch.object(updater, "_http_get", return_value=b"<html>"):
            with self.assertRaises(UpdateError):
                updater.check_for_update(CURRENT)
        with mock.patch.object(updater, "_http_get", return_value=b'{"a": 1}'):
            with self.assertRaises(UpdateError):
                updater.check_for_update(CURRENT)

    def test_errors_are_translated(self):
        from apkg2cards import i18n
        err = UpdateError("upd.err.http", code=500)
        i18n.set_language("fr")
        self.assertIn("500", str(err))
        self.assertIn("GitHub", str(err))
        i18n.set_language("en")
        self.assertIn("returned an error", str(err))


class _Handler(http.server.BaseHTTPRequestHandler):
    payload = b""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *a):
        pass


class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _Handler.payload = os.urandom(700_000)
        cls.sha = hashlib.sha256(_Handler.payload).hexdigest()
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/apkg2cards-setup.exe"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def info(self, **kw):
        base = {"asset_url": self.url, "asset_name": "apkg2cards-setup.exe",
                "asset_size": len(_Handler.payload), "sha256": self.sha}
        base.update(kw)
        return base

    def test_download_and_verify(self):
        steps = []
        path = updater.download_installer(self.info(), progress=lambda d, t: steps.append((d, t)))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), _Handler.payload)
        self.assertEqual(steps[-1], (len(_Handler.payload), len(_Handler.payload)))
        self.assertFalse(os.path.exists(path + ".part"))

    def test_bad_checksum_removes_file(self):
        with self.assertRaises(UpdateError):
            updater.download_installer(self.info(sha256="0" * 64))
        folder = os.path.join(tempfile.gettempdir(), "apkg2cards-update")
        self.assertEqual([f for f in os.listdir(folder) if f.endswith(".exe")], [])

    def test_missing_checksum_refuses(self):
        with self.assertRaises(UpdateError):
            updater.download_installer(self.info(sha256=None, sha_url=None))

    def test_checksum_from_sha_file(self):
        with mock.patch.object(updater, "_http_get",
                               return_value=f"{self.sha}  apkg2cards-setup.exe\n".encode()):
            path = updater.download_installer(self.info(sha256=None, sha_url="https://x/y.sha256"))
        self.assertTrue(os.path.exists(path))

    def test_cancel(self):
        with self.assertRaises(UpdateCancelled):
            updater.download_installer(self.info(), should_cancel=lambda: True)

    def test_unreachable(self):
        with self.assertRaises(UpdateError):
            updater.download_installer(self.info(asset_url="http://127.0.0.1:9/x.exe"))


class InstallTests(unittest.TestCase):
    def test_refused_when_not_installed_app(self):
        with mock.patch.object(updater, "can_self_update", return_value=False):
            with self.assertRaises(UpdateError):
                updater.launch_installer("setup.exe")

    def test_command_line(self):
        with mock.patch.object(updater, "can_self_update", return_value=True), \
                mock.patch("subprocess.Popen") as popen:
            updater.launch_installer("C:/tmp/setup.exe")
        args = popen.call_args[0][0]
        self.assertEqual(args[0], "C:/tmp/setup.exe")
        for flag in ("/SILENT", "/CLOSEAPPLICATIONS", "/RELAUNCH=1"):
            self.assertIn(flag, args)

    def test_not_frozen_means_no_self_update(self):
        self.assertFalse(updater.can_self_update())  # les tests tournent depuis le code source


if __name__ == "__main__":
    unittest.main()

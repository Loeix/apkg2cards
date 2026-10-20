import io
import json
import os
import re
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apkg2cards import __version__, updater  # noqa: E402

# Versions calculées à partir de la version en cours : aucun numéro écrit en dur,
# donc les tests ne cassent plus quand on change __version__.
_cur = [int(x) for x in re.findall(r"\d+", __version__)[:3]]
_cur += [0] * (3 - len(_cur))

CURRENT = __version__
PATCH_UP = f"{_cur[0]}.{_cur[1]}.{_cur[2] + 1}"
MINOR_UP = f"{_cur[0]}.{_cur[1] + 1}.0"
MAJOR_UP = f"{_cur[0] + 1}.0.0"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_release(tag):
    body = json.dumps({"tag_name": tag, "html_url": "https://example.test/r"}).encode()
    return FakeResponse(body)


class VersionTests(unittest.TestCase):
    def test_parse(self):
        # format du texte : indépendant de la version de l'appli
        self.assertEqual(updater.parse_version("v0.1.2"), (0, 1, 2))
        self.assertEqual(updater.parse_version("1.0"), (1, 0))

    def test_parse_invalid(self):
        with self.assertRaises(ValueError):
            updater.parse_version("latest")

    def test_is_newer_than_current(self):
        self.assertTrue(updater.is_newer("v" + PATCH_UP, CURRENT))
        self.assertTrue(updater.is_newer("v" + MINOR_UP, CURRENT))
        self.assertTrue(updater.is_newer("v" + MAJOR_UP, CURRENT))

    def test_not_newer_than_current(self):
        self.assertFalse(updater.is_newer("v" + CURRENT, CURRENT))
        self.assertFalse(updater.is_newer("v" + CURRENT, PATCH_UP))
        self.assertFalse(updater.is_newer("v" + PATCH_UP, MINOR_UP))
        self.assertFalse(updater.is_newer("v" + MINOR_UP, MAJOR_UP))

    def test_is_newer_compares_numbers_not_text(self):
        # logique de comparaison pure (0.10 > 0.9), indépendante de la version de l'appli
        self.assertTrue(updater.is_newer("v0.2", "0.1.9"))
        self.assertTrue(updater.is_newer("v0.10.0", "0.9.0"))
        self.assertFalse(updater.is_newer("v0.1", "0.1.0"))


class CheckTests(unittest.TestCase):
    def test_update_available(self):
        with mock.patch("urllib.request.urlopen", return_value=fake_release("v" + MAJOR_UP)):
            r = updater.check_for_update(CURRENT)
        self.assertTrue(r["available"])
        self.assertEqual(r["latest"], MAJOR_UP)
        self.assertEqual(r["url"], "https://example.test/r")

    def test_up_to_date(self):
        with mock.patch("urllib.request.urlopen", return_value=fake_release("v" + CURRENT)):
            self.assertFalse(updater.check_for_update(CURRENT)["available"])

    def test_older_release_is_not_an_update(self):
        with mock.patch("urllib.request.urlopen", return_value=fake_release("v" + CURRENT)):
            self.assertFalse(updater.check_for_update(PATCH_UP)["available"])

    def test_no_release_404(self):
        err = urllib.error.HTTPError("u", 404, "nf", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(updater.UpdateError):
                updater.check_for_update(CURRENT)

    def test_offline(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("x")):
            with self.assertRaises(updater.UpdateError):
                updater.check_for_update(CURRENT)

    def test_garbage_response(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"<html>")):
            with self.assertRaises(updater.UpdateError):
                updater.check_for_update(CURRENT)

    def test_bad_tag(self):
        with mock.patch("urllib.request.urlopen", return_value=fake_release("nightly")):
            with self.assertRaises(updater.UpdateError):
                updater.check_for_update(CURRENT)


if __name__ == "__main__":
    unittest.main()

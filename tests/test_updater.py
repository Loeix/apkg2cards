import io
import json
import os
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apkg2cards import updater  # noqa: E402


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
        self.assertEqual(updater.parse_version("v0.1.2"), (0, 1, 2))
        self.assertEqual(updater.parse_version("1.0"), (1, 0))

    def test_parse_invalid(self):
        with self.assertRaises(ValueError):
            updater.parse_version("latest")

    def test_is_newer(self):
        self.assertTrue(updater.is_newer("v0.1.2", "0.1.1"))
        self.assertTrue(updater.is_newer("v0.2", "0.1.9"))
        self.assertTrue(updater.is_newer("v0.10.0", "0.9.0"))
        self.assertFalse(updater.is_newer("v0.1.1", "0.1.1"))
        self.assertFalse(updater.is_newer("v0.1", "0.1.0"))
        self.assertFalse(updater.is_newer("v0.1.0", "0.1.1"))


class CheckTests(unittest.TestCase):
    def test_update_available(self):
        with mock.patch("urllib.request.urlopen", return_value=fake_release("v9.0.0")):
            r = updater.check_for_update("0.1.1")
        self.assertTrue(r["available"])
        self.assertEqual(r["latest"], "9.0.0")
        self.assertEqual(r["url"], "https://example.test/r")

    def test_up_to_date(self):
        with mock.patch("urllib.request.urlopen", return_value=fake_release("v0.1.1")):
            self.assertFalse(updater.check_for_update("0.1.1")["available"])

    def test_no_release_404(self):
        err = urllib.error.HTTPError("u", 404, "nf", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(updater.UpdateError):
                updater.check_for_update("0.1.1")

    def test_offline(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("x")):
            with self.assertRaises(updater.UpdateError):
                updater.check_for_update("0.1.1")

    def test_garbage_response(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"<html>")):
            with self.assertRaises(updater.UpdateError):
                updater.check_for_update("0.1.1")

    def test_bad_tag(self):
        with mock.patch("urllib.request.urlopen", return_value=fake_release("nightly")):
            with self.assertRaises(updater.UpdateError):
                updater.check_for_update("0.1.1")


if __name__ == "__main__":
    unittest.main()

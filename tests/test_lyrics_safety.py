import unittest
from unittest import mock

from app import lyrics


class LyricsSafetyTests(unittest.TestCase):
    def test_artistless_lookup_rejects_unrelated_lyrics(self):
        search = b"<a href='/track/1'>wrong</a><a href='/track/2'>right</a>"
        wrong = (
            "<title>Drowning/Drowning Pool - Bugs</title>"
            "<xmp>Let the bodies hit the floor\nBeaten why for\n"
            "Nothing wrong with me\nSomething has got to give</xmp>"
        ).encode()
        right = (
            "<title>Drowning/WOODZ - Bugs</title>"
            "<xmp>Oh I am drowning\nIt's raining all day\n"
            "I cannot breathe\nYou're taking me down</xmp>"
        ).encode()

        def fake_get(url):
            if url.endswith("/1"):
                return wrong
            if url.endswith("/2"):
                return right
            return search

        with mock.patch("app.lyrics._http_get", fake_get):
            result = lyrics._fetch_kr(None, "Drowning")

        self.assertIn("raining all day", result["text"])
        self.assertNotIn("bodies hit the floor", result["text"])

    def test_artistless_lookup_requires_exact_track_title(self):
        self.assertTrue(lyrics._same_title("Drowning", "DROWNING"))
        self.assertFalse(lyrics._same_title("Drowning", "Drowning Shadows"))


if __name__ == "__main__":
    unittest.main()

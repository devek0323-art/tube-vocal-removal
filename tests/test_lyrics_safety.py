import unittest
from unittest import mock

from app import lyrics


class LyricsSafetyTests(unittest.TestCase):
    def test_same_title_by_other_artists_needs_the_artist_in_the_title(self):
        """`Since You've Been Gone`은 Rainbow·Kelly Clarkson·Aretha Franklin이 각각
        다른 곡이다. 정규화하면 제목이 같아 길이만 맞으면 아무거나 통과했다."""
        rows = [
            {"trackName": "Since You`ve Been Gone", "artistName": "Slank",
             "duration": 212, "plainLyrics": "엉뚱한 가사"},
            {"trackName": "Since You´ve Been Gone", "artistName": "Graham Bonnet Band",
             "duration": 213, "plainLyrics": "I get the same old dreams"},
        ]
        hint = "Graham Bonnet Band - Since Youve Been Gone"
        hit = lyrics._lrclib_pick(rows, None, "Since Youve Been Gone", 213, strict=True, hint=hint)
        self.assertEqual(hit["text"], "I get the same old dreams")

        # 후보가 하나뿐이면 예전처럼 그대로 받는다 — 가수명 없는 업로드를 막으면 안 된다.
        only = [dict(rows[0], artistName="Slank")]
        hit = lyrics._lrclib_pick(only, None, "Since Youve Been Gone", 213, strict=True, hint="Since Youve Been Gone")
        self.assertEqual(hit["text"], "엉뚱한 가사")

    def test_fullwidth_quotes_and_apostrophes_leave_the_search_term(self):
        """`＂Since You've Been Gone＂` → `Since Youve Been Gone`.
        아포스트로피를 공백으로 바꾸면 `You ve`로 쪼개진다."""
        raw = "Graham Bonnet Band - ＂Since You've Been Gone＂ - Official Live Video"
        cleaned = lyrics.clean_title(raw)
        _, track = lyrics.split_artist_title(cleaned)
        self.assertEqual(lyrics.title_candidates(track)[0], "Since Youve Been Gone")

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

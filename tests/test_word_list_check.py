"""Tests for word_list_check.py: catching Whisper writing the word list back
in place of what was said. The leak strings are real outputs from the
2026-11-21 test on Chris's own mic recordings, plus the one pasted that day.

    python -m unittest discover tests
"""

import unittest

from word_list_check import hotwords_text, same_words, word_list_leak

LIST = ["WBTO", "AMWIC", "AMRAC", "NWRESD", "Clackamas"]


class HotwordsText(unittest.TestCase):
    def test_list_ends_with_a_period(self):
        self.assertEqual(hotwords_text(LIST), "WBTO, AMWIC, AMRAC, NWRESD, Clackamas.")

    def test_empty_list_sends_nothing(self):
        self.assertIsNone(hotwords_text([]))
        self.assertIsNone(hotwords_text(["", "  "]))

    def test_no_second_period(self):
        self.assertEqual(hotwords_text(["WBTO", "U.S."]), "WBTO, U.S.")


class Leaks(unittest.TestCase):
    def test_the_list_written_back(self):
        for text in [
            "WBTO, AMWIC, AMRAC, NWRESD, Clackamas",
            "WBTO, AMWIC, AMRAC, NWRESD, Clackamas.",
            "WBTO, AMWIC, AMRAC, NWRESD, Clackamas WBTO, AMWIC, AMWIC, NWRESD, Clackamas",
            "WBTO, AMWIC, NWRESD, Clackamas",
            "WBTO, AMWIC, AMRC, NWRESD, Clackamas",
            "WBTO, AMWIC, AMWR, NWR, Clackamas, WBTO, AMWR, NWR, Clackamas,",
            "WBTO, AMWIC, AMWRT",
            "WBTO.",
        ]:
            self.assertEqual(word_list_leak(text, LIST), "whole", text)

    def test_the_list_inside_other_speech(self):
        text = ("That worked out really well. WBTO, AMWIC, AMRAC, NWRESD, Clackamas "
                "Can you update the email?")
        self.assertEqual(word_list_leak(text, LIST), "run")

    def test_real_speech_is_left_alone(self):
        for text in [
            "",
            "The NWRESD report is due Friday.",
            "AMWIC and AMRAC both meet on Tuesday.",
            "Send the Clackamas numbers to WBTO today.",
            "This morning I had two cups of coffee.",
            "Meet me at 8 AM in Clackamas.",
        ]:
            self.assertIsNone(word_list_leak(text, LIST), text)

    def test_no_list_means_no_check(self):
        self.assertIsNone(word_list_leak("WBTO, AMWIC, AMRAC", []))


class SameWords(unittest.TestCase):
    def test_a_list_word_said_on_purpose_keeps_the_list_spelling(self):
        self.assertTrue(same_words("AMWIC.", "Amwick."))
        self.assertTrue(same_words("WBTO, AMWIC, AMRAC.", "WBTO, Amwick, Amrak."))

    def test_a_leak_is_not_kept(self):
        self.assertFalse(same_words("WBTO, AMWIC, AMRAC, NWRESD, Clackamas",
                                    "the way you have it drawn, but before"))
        self.assertFalse(same_words("WBTO.", "as she took."))
        self.assertFalse(same_words("WBTO, AMWIC", ""))


if __name__ == "__main__":
    unittest.main()

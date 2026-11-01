"""Tests for text_processor.py. Run from the project folder:

    python -m unittest discover tests

Kept in tests/ on purpose: test_mic.py and test_ptt.py in the project root are
manual scripts that record from the mic as soon as they are imported.
"""

import unittest

from text_processor import process_text

# The Text tab settings in config.yaml on 2026-11-01.
LIVE = {
    "remove_fillers": True,
    "punctuation_commands": False,
    "newline_commands": False,
    "informal_to_formal": True,
    "fix_capitalization": True,
    "ensure_sentence_spacing": True,
    "add_trailing_space": True,
    "collapse_repeated_words": True,
}


class LeavesGoodTextAlone(unittest.TestCase):
    """Whisper output that is already right must paste unchanged, plus the
    trailing space that separates dictations. All but the last two were
    damaged before 2026-11-01 (for example "0.010" became "0. 010")."""

    CASES = [
        "The powder coat adds 0.010 per surface.",
        "We moved to version 3.5 last week.",
        "It costs $1.50 per unit.",
        "Email chris@wbto.partners about it.",
        "Open config.yaml and check the model.",
        "The meeting is at 10 a.m. tomorrow.",
        "Do you know where the file is?",
        "I actually finished the report.",
        "Wait... let me think.",
        "Use the U.S. standard, e.g. the first one.",
        "I took him to the ER today.",
        "Uh-huh, that works.",
    ]

    def test_unchanged(self):
        for text in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(process_text(text, LIVE), text + " ")


class FixesWhatItShould(unittest.TestCase):
    def test_filler_takes_its_comma_with_it(self):
        self.assertEqual(
            process_text("So, um, I think we should go.", LIVE),
            "So, I think we should go. ",
        )

    def test_filler_at_start(self):
        self.assertEqual(process_text("Um, so I think.", LIVE), "So I think. ")

    def test_filler_before_period(self):
        self.assertEqual(process_text("I agree, um.", LIVE), "I agree. ")

    def test_missing_space_between_sentences(self):
        self.assertEqual(
            process_text("It works.Next we test it.", LIVE),
            "It works. Next we test it. ",
        )

    def test_standalone_i_but_not_ie(self):
        self.assertEqual(
            process_text("i think i.e. this one", LIVE),
            "I think i.e. this one ",
        )

    def test_fillers_kept_when_option_off(self):
        opts = dict(LIVE, remove_fillers=False)
        self.assertEqual(process_text("So, um, I think.", opts), "So, um, I think. ")


if __name__ == "__main__":
    unittest.main()

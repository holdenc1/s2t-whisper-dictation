"""Tests for the word list (vocabulary) setting in config.py. Every test uses
its own temporary config.yaml; the real one is never read or written.

    python -m unittest discover tests
"""

import tempfile
import unittest
from pathlib import Path

from config import Config


class WordList(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "config.yaml"

    def tearDown(self):
        self._tmp.cleanup()

    def test_older_config_without_a_word_list_still_loads(self):
        self.path.write_text("model: medium\nlanguage: en\n", encoding="utf-8")
        self.assertEqual(Config.load(self.path).vocabulary, [])

    def test_hand_typed_comma_list_is_split(self):
        self.path.write_text("vocabulary: WBTO, AMWIC , ,Clackamas\n", encoding="utf-8")
        self.assertEqual(Config.load(self.path).vocabulary, ["WBTO", "AMWIC", "Clackamas"])

    def test_save_and_load_keep_the_list(self):
        config = Config()
        config.vocabulary = ["WBTO", "AMWIC", "AMRAC", "NWRESD", "Clackamas"]
        config.save(self.path)
        self.assertEqual(Config.load(self.path).vocabulary, config.vocabulary)


if __name__ == "__main__":
    unittest.main()

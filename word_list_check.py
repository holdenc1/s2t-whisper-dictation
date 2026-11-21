"""Catch Whisper writing the word list back in place of what was said.

The word list goes to Whisper as hotwords, which sit in the "previous text"
slot of every 30-second window. Sometimes Whisper copies that slot instead of
transcribing the audio, and the list gets pasted in place of the speech
("WBTO, AMWIC, AMRAC, NWRESD, Clackamas", sometimes twice). Measured
2026-11-21 on 110 dictation-shaped clips of Chris's own mic with the medium
model: 10 came back as the list, none with no list. It happens on real speech,
not silence, so vad_filter does not catch it. transcriber.py runs a clip
again without the list when its result looks like the list.
"""

import re
from difflib import SequenceMatcher
from typing import Iterable, Optional

_WORD = re.compile(r"[A-Za-z0-9']+")


def hotwords_text(vocabulary: Iterable[str]) -> Optional[str]:
    """The word list as the hotwords string, ending in a period.

    The period matters: in the same test it cut the copies from 10 of 110
    clips to 1, and from 63 to 24 of 152 harder clips cut mid-sentence.
    """
    text = ", ".join(w.strip() for w in vocabulary if w.strip())
    if not text:
        return None
    return text if text.endswith((".", "!", "?")) else text + "."


def word_list_leak(text: str, vocabulary: Iterable[str]) -> Optional[str]:
    """Say whether a transcript looks like the word list written back.

    Returns "whole" if every word is a list word, "run" if three list words in
    a row sit inside other text, and None otherwise. A broken copy of an
    acronym counts as a list word: Whisper's copies included AMRC, AMWR and
    NWR for AMRAC, AMWIC and NWRESD, so a capitalized word whose first two
    letters start a list acronym is treated as one.
    """
    entries = [w for entry in vocabulary for w in _WORD.findall(entry)]
    if not entries:
        return None
    words = {w.lower() for w in entries}
    acronyms = [w for w in entries if w.isupper() and len(w) >= 3]

    def listed(token: str) -> bool:
        if token.lower() in words:
            return True
        return (token.isalpha() and token.isupper() and len(token) >= 2
                and any(a.startswith(token[:2]) for a in acronyms))

    flags = [listed(t) for t in _WORD.findall(text)]
    if not flags:
        return None
    if all(flags):
        return "whole"
    run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        if run >= 3:
            return "run"
    return None


def same_words(a: str, b: str) -> bool:
    """True when two transcripts are the same words spelled differently, for
    example "AMWIC." with the list and "Amwick." without it, so a list word
    said on purpose keeps the list's spelling. Compares letters and digits."""
    la = re.sub(r"[^a-z0-9]", "", a.lower())
    lb = re.sub(r"[^a-z0-9]", "", b.lower())
    return bool(la and lb) and SequenceMatcher(None, la, lb).ratio() >= 0.6

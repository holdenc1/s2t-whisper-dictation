"""Rule-based text post-processing for cleaning up transcriptions."""

import re


# Hesitation sounds only. Real words (actually, basically, literally, "you
# know") used to be here too: dropping them changed what was said, and "you
# know" also matched inside "do you know". The first letter's case is spelled
# out instead of using IGNORECASE so acronyms such as ER and UM are kept.
FILLER_WORDS = [
    r"[Uu]m+",
    r"[Uu]h+",
    r"[Ee]rm",
    r"[Ee]r",
    r"[Aa]h",
]

# A filler takes one following comma and its spaces with it ("So, um, I" ->
# "So, I"). A hyphen next to it means a real word (uh-huh, uh-oh).
_FILLER_RE = re.compile(r"(?<!-)\b(?:" + "|".join(FILLER_WORDS) + r")\b(?!-),?\s*")

# Punctuation command replacements
PUNCTUATION_COMMANDS = [
    (r"\bperiod\b", "."),
    (r"\bfull stop\b", "."),
    (r"\bcomma\b", ","),
    (r"\bquestion mark\b", "?"),
    (r"\bexclamation point\b", "!"),
    (r"\bexclamation mark\b", "!"),
    (r"\bcolon\b", ":"),
    (r"\bsemicolon\b", ";"),
    (r"\bsemi colon\b", ";"),
    (r"\bhyphen\b", "-"),
    (r"\bdash\b", " - "),
    (r"\bellipsis\b", "..."),
    (r"\bopen quote\b", '"'),
    (r"\bclose quote\b", '"'),
    (r"\bopen paren\b", "("),
    (r"\bclose paren\b", ")"),
    (r"\bopen bracket\b", "["),
    (r"\bclose bracket\b", "]"),
    (r"\bampersand\b", "&"),
    (r"\bat sign\b", "@"),
    (r"\bhash\b", "#"),
    (r"\bhashtag\b", "#"),
    (r"\bdollar sign\b", "$"),
    (r"\bpercent sign\b", "%"),
    (r"\bpercent\b", "%"),
]

# Newline commands
NEWLINE_COMMANDS = [
    r"\bnew line\b",
    r"\bnewline\b",
    r"\bnew paragraph\b",
    r"\bparagraph break\b",
    r"\bline break\b",
]

# Common informal -> formal replacements
INFORMAL_REPLACEMENTS = [
    (r"\bgonna\b", "going to"),
    (r"\bwanna\b", "want to"),
    (r"\bgotta\b", "got to"),
    (r"\bkinda\b", "kind of"),
    (r"\bsorta\b", "sort of"),
    (r"\bdunno\b", "don't know"),
    (r"\blemme\b", "let me"),
    (r"\bgimme\b", "give me"),
    (r"\bc'mon\b", "come on"),
    (r"\by'all\b", "you all"),
]


def remove_fillers(text: str) -> str:
    """Remove hesitation sounds and the commas they leave behind."""
    text = _FILLER_RE.sub("", text)
    text = re.sub(r",(\s*,)+", ",", text)        # "So, , I" -> "So, I"
    text = re.sub(r",\s*(?=[.!?]|$)", "", text)  # "I agree, ." -> "I agree."
    text = re.sub(r"^\s*,\s*", "", text)         # comma left at the very start
    return text


def apply_punctuation_commands(text: str) -> str:
    """Convert spoken punctuation to actual punctuation."""
    for pattern, replacement in PUNCTUATION_COMMANDS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def apply_newline_commands(text: str) -> str:
    """Convert newline commands to actual newlines."""
    for pattern in NEWLINE_COMMANDS:
        text = re.sub(pattern, "\n", text, flags=re.IGNORECASE)
    return text


def apply_informal_replacements(text: str) -> str:
    """Replace informal contractions with formal versions."""
    for pattern, replacement in INFORMAL_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def fix_spacing(text: str) -> str:
    """Fix spacing issues."""
    # Remove space before punctuation
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    # No "space after punctuation" rule here: it split config.yaml, wbto.partners
    # and a.m. ensure_sentence_spacing() handles real sentence breaks.
    # Remove multiple spaces
    text = re.sub(r" +", " ", text)
    # Remove space at start of lines
    text = re.sub(r"^\s+", "", text, flags=re.MULTILINE)
    # Remove multiple newlines
    text = re.sub(r"\n\n+", "\n\n", text)
    return text.strip()


def ensure_sentence_spacing(text: str) -> str:
    """Add a missing space between two sentences: 'word.Next' -> 'word. Next'.

    Fires only on a lowercase letter or digit, then . ! or ?, then a capital
    letter that starts a word. Numbers (0.010, $1.50), addresses (wbto.partners,
    config.yaml) and abbreviations (a.m., e.g., U.S.) are left alone."""
    return re.sub(r"(?<=[a-z0-9][.!?])(?=[A-Z](?:[a-z]|\b))", " ", text)


def collapse_repeated_words(text: str) -> str:
    """Collapse immediate word repetitions: 'the the cat' -> 'the cat'."""
    return re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", text, flags=re.IGNORECASE)


def capitalize_sentences(text: str) -> str:
    """Capitalize the first letter of each sentence."""
    # Capitalize after period, question mark, exclamation, or newline
    def cap_match(match):
        return match.group(1) + match.group(2).upper()

    # After sentence-ending punctuation, but not after an abbreviation with
    # inner periods (a.m., e.g., U.S.) or an ellipsis, where the sentence
    # usually goes on. Whisper capitalizes real sentence starts itself.
    text = re.sub(r"(?<!\.\w)(?<!\.\.)([.!?]\s+)([a-z])", cap_match, text)
    # After newline
    text = re.sub(r"(\n\s*)([a-z])", cap_match, text)
    # Capitalize first character
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    # Capitalize "I" as a standalone word, but not the i in "i.e."
    text = re.sub(r"\bi\b(?!\.\w)", "I", text)
    return text


def process_text(text: str, options: dict = None) -> str:
    """
    Apply all text processing rules.

    Options:
        remove_fillers: bool (default True)
        punctuation_commands: bool (default True)
        newline_commands: bool (default True)
        informal_to_formal: bool (default False)
        fix_capitalization: bool (default True)
    """
    if options is None:
        options = {}

    # Apply processing steps
    if options.get("remove_fillers", True):
        text = remove_fillers(text)

    if options.get("punctuation_commands", True):
        text = apply_punctuation_commands(text)

    if options.get("newline_commands", True):
        text = apply_newline_commands(text)

    if options.get("informal_to_formal", False):
        text = apply_informal_replacements(text)

    if options.get("collapse_repeated_words", False):
        text = collapse_repeated_words(text)

    # Always fix spacing
    text = fix_spacing(text)

    if options.get("ensure_sentence_spacing", True):
        text = ensure_sentence_spacing(text)

    if options.get("fix_capitalization", True):
        text = capitalize_sentences(text)

    if options.get("add_trailing_space", True) and text and not text.endswith((" ", "\n")):
        text = text + " "

    return text

from __future__ import annotations

import re
import unicodedata

_FEATURING_RE = re.compile(r"\b(feat\.?|ft\.?|featuring)\b", re.IGNORECASE)
_PUNCTUATION_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold()
    text = _FEATURING_RE.sub("featuring", text)
    text = _PUNCTUATION_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_FEATURING_RE = re.compile(r"\b(feat\.?|ft\.?|featuring)\b", re.IGNORECASE)
_PUNCTUATION_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")

_NEUTRAL_QUALIFIER_RE = re.compile(
    r"\(?\s*remaster(?:ed)?(?:\s+\d{4})?\s*\)?", re.IGNORECASE
)

_DISTINGUISHING_QUALIFIER_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("live", re.compile(r"\blive\b", re.IGNORECASE)),
    ("demo", re.compile(r"\bdemo\b", re.IGNORECASE)),
    ("radio edit", re.compile(r"\bradio edit\b", re.IGNORECASE)),
    ("extended mix", re.compile(r"\bextended mix\b", re.IGNORECASE)),
    ("12in mix", re.compile(r'\b12[\s"\-]*(?:inch)?\s*mix\b', re.IGNORECASE)),
    ("instrumental", re.compile(r"\binstrumental\b", re.IGNORECASE)),
    ("acoustic", re.compile(r"\bacoustic\b", re.IGNORECASE)),
    ("remix", re.compile(r"\bremix\b", re.IGNORECASE)),
    ("mono", re.compile(r"\bmono\b", re.IGNORECASE)),
    ("stereo", re.compile(r"\bstereo\b", re.IGNORECASE)),
    ("session", re.compile(r"\bsession\b", re.IGNORECASE)),
]


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold()
    text = _FEATURING_RE.sub("featuring", text)
    text = _PUNCTUATION_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


@dataclass
class ExtractedTitle:
    base_title: str
    qualifiers: list[str]


def extract_qualifiers(raw_title: str) -> ExtractedTitle:
    working = raw_title
    found: list[str] = []

    # Extract parenthetical text to check for free-text mixes
    paren_pattern = re.compile(r'\(([^)]+)\)')
    parens = paren_pattern.findall(working)

    for label, pattern in _DISTINGUISHING_QUALIFIER_PATTERNS:
        if pattern.search(working) and label not in found:
            found.append(label)

    # Check for free-text mix names in parentheses
    for paren_text in parens:
        normalized_paren = paren_text.lower().strip()
        # Check if it's a known pattern (already handled above)
        is_known = any(pattern.search(paren_text) for _, pattern in _DISTINGUISHING_QUALIFIER_PATTERNS)
        is_neutral = _NEUTRAL_QUALIFIER_RE.search(paren_text)

        if not is_known and not is_neutral and normalized_paren.endswith("mix"):
            # It's a free-text mix qualifier
            normalized_mix = normalize_text(paren_text)
            if normalized_mix not in found:
                found.append(normalized_mix)

    working = _NEUTRAL_QUALIFIER_RE.sub(" ", working)
    for _, pattern in _DISTINGUISHING_QUALIFIER_PATTERNS:
        working = pattern.sub(" ", working)
    working = re.sub(r"[()\[\]]", " ", working)

    base_title = normalize_text(working)
    return ExtractedTitle(base_title=base_title, qualifiers=found)

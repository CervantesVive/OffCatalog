from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_FEATURING_RE = re.compile(r"\b(feat\.?|ft\.?|featuring)\b", re.IGNORECASE)
_PUNCTUATION_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")

_NEUTRAL_QUALIFIER_RE = re.compile(
    r"^\s*remaster(?:ed)?(?:\s+\d{4})?\s*$", re.IGNORECASE
)

_PAREN_GROUP_RE = re.compile(r"[\(\[]([^\)\]]*)[\)\]]")
_FEATURING_GROUP_RE = re.compile(r"^\s*(feat\.?|ft\.?|featuring)\b", re.IGNORECASE)

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
    found: list[str] = []

    def replace_group(match: re.Match) -> str:
        group_text = match.group(1).strip()
        if not group_text:
            return match.group(0)
        if _FEATURING_GROUP_RE.match(group_text):
            return match.group(0)  # artist-credit parenthetical, not a version qualifier — leave untouched
        if _NEUTRAL_QUALIFIER_RE.match(group_text):
            return " "
        for label, pattern in _DISTINGUISHING_QUALIFIER_PATTERNS:
            if pattern.search(group_text):
                if label not in found:
                    found.append(label)
                return " "
        label = normalize_text(group_text)
        if label and label not in found:
            found.append(label)
        return " "

    working = _PAREN_GROUP_RE.sub(replace_group, raw_title)
    base_title = normalize_text(working)
    return ExtractedTitle(base_title=base_title, qualifiers=found)

import unicodedata

from offcatalog.normalize import normalize_text, extract_qualifiers


def test_normalize_casefolds():
    assert normalize_text("Enjoy The Silence") == normalize_text("enjoy the silence")


def test_normalize_unicode_nfkc():
    composed = "Café"  # é as a single codepoint U+00E9
    decomposed = unicodedata.normalize("NFD", composed)  # e + combining acute U+0301
    assert composed != decomposed  # sanity: the two literals really do differ before normalization
    assert normalize_text(composed) == normalize_text(decomposed)


def test_normalize_unifies_featuring_variants():
    a = normalize_text("Track (feat. Someone)")
    b = normalize_text("Track (ft. Someone)")
    c = normalize_text("Track (featuring Someone)")
    assert a == b == c


def test_normalize_collapses_punctuation_and_whitespace():
    assert normalize_text("Track   Name!!") == normalize_text("Track Name")


def test_extract_qualifiers_plain_title_has_none():
    result = extract_qualifiers("Enjoy the Silence")
    assert result.qualifiers == []
    assert "silence" in result.base_title


def test_extract_qualifiers_live_is_distinguishing():
    result = extract_qualifiers("Enjoy the Silence (Live)")
    assert result.qualifiers == ["live"]
    assert "live" not in result.base_title


def test_extract_qualifiers_remaster_is_neutral():
    result = extract_qualifiers("Enjoy the Silence (Remastered 2011)")
    assert result.qualifiers == []
    assert "remaster" not in result.base_title
    plain = extract_qualifiers("Enjoy the Silence")
    assert result.base_title == plain.base_title


def test_extract_qualifiers_hands_and_feet_mix_is_distinguishing():
    result = extract_qualifiers("Enjoy the Silence (Hands and Feet Mix)")
    assert "hands and feet mix" in result.qualifiers


def test_extract_qualifiers_twelve_inch_mix():
    result = extract_qualifiers('Track (12" Mix)')
    assert "12in mix" in result.qualifiers


def test_extract_qualifiers_multiple_distinguishing():
    result = extract_qualifiers("Track (Live) (Acoustic)")
    assert set(result.qualifiers) == {"live", "acoustic"}

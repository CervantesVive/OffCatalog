import unicodedata

from offcatalog.normalize import extract_qualifiers, normalize_text


def test_normalize_casefolds():
    assert normalize_text("Enjoy The Silence") == normalize_text("enjoy the silence")


def test_normalize_unicode_nfkc():
    composed = "Café"  # é as a single codepoint U+00E9
    decomposed = unicodedata.normalize("NFD", composed)  # e + combining acute U+0301
    assert (
        composed != decomposed
    )  # sanity: the two literals really do differ before normalization
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
    assert "hands and feet mix" not in result.base_title


def test_extract_qualifiers_twelve_inch_mix():
    result = extract_qualifiers('Track (12" Mix)')
    assert "12in mix" in result.qualifiers
    assert "12in mix" not in result.base_title


def test_extract_qualifiers_multiple_distinguishing():
    result = extract_qualifiers("Track (Live) (Acoustic)")
    assert set(result.qualifiers) == {"live", "acoustic"}


def test_extract_qualifiers_common_words_not_mistaken_for_live():
    result = extract_qualifiers("Live and Let Die")
    assert result.qualifiers == []
    assert "live and let die" in result.base_title


def test_extract_qualifiers_dash_suffix_live():
    result = extract_qualifiers("Enjoy the Silence - Live")
    assert result.qualifiers == ["live"]
    assert "live" not in result.base_title
    assert result.base_title == extract_qualifiers("Enjoy the Silence").base_title


def test_extract_qualifiers_dash_suffix_radio_edit_and_neutral_remaster():
    assert extract_qualifiers("Song - Radio Edit").qualifiers == ["radio edit"]
    neutral = extract_qualifiers("Song - Remastered 2011")
    assert neutral.qualifiers == []
    assert neutral.base_title == "song"


def test_extract_qualifiers_dash_suffix_does_not_misfire_on_ordinary_titles():
    # The suffix must match a qualifier in full: "Live and Let Die" merely contains
    # the word "live", and stripping it would destroy the real title.
    result = extract_qualifiers("Guns N' Roses - Live and Let Die")
    assert result.qualifiers == []
    assert "live and let die" in result.base_title

    plain = extract_qualifiers("Song - Part Two")
    assert plain.qualifiers == []
    assert plain.base_title == "song part two"


def test_extract_qualifiers_regional_edition_via_free_text():
    result = extract_qualifiers("Track (UK Edition)")
    assert "uk edition" in result.qualifiers


def test_extract_qualifiers_featuring_not_a_qualifier():
    result1 = extract_qualifiers("Track (feat. Other Artist)")
    assert result1.qualifiers == []
    result2 = extract_qualifiers("Track (ft. Other Artist)")
    assert result2.qualifiers == []
    result3 = extract_qualifiers("Track (featuring Other Artist)")
    assert result3.qualifiers == []

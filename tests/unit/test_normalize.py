from offcatalog.normalize import normalize_text


def test_normalize_casefolds():
    assert normalize_text("Enjoy The Silence") == normalize_text("enjoy the silence")


def test_normalize_unicode_nfkc():
    assert normalize_text("Café") == normalize_text("Café")


def test_normalize_unifies_featuring_variants():
    a = normalize_text("Track (feat. Someone)")
    b = normalize_text("Track (ft. Someone)")
    c = normalize_text("Track (featuring Someone)")
    assert a == b == c


def test_normalize_collapses_punctuation_and_whitespace():
    assert normalize_text("Track   Name!!") == normalize_text("Track Name")

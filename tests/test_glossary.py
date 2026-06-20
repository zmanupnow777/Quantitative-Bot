from __future__ import annotations

from bot.glossary import GLOSSARY, detect_terms


def test_glossary_has_core_terms():
    for term in ["Bollinger band", "Sharpe ratio", "stop-loss", "kill switch"]:
        assert term in GLOSSARY
        assert GLOSSARY[term].strip()


def test_detect_terms_finds_terms_case_insensitive_in_order():
    text = "Price hit the lower BOLLINGER BAND, so the stop-loss was set."
    assert detect_terms(text) == ["Bollinger band", "stop-loss"]


def test_detect_terms_whole_word_only_and_deduped():
    # "averages" must not match the term "average"; repeated term appears once
    text = "A moving average crossed; the moving average held."
    assert detect_terms(text) == ["moving average"]


def test_detect_terms_returns_empty_for_no_match():
    assert detect_terms("nothing relevant here") == []

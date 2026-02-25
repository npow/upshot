"""Tests for text utilities."""

from upshot.utils.text import (
    truncate_words,
    clean_text,
    word_count,
    extract_domain,
    is_likely_tracking_url,
)


def test_truncate_words():
    assert truncate_words("one two three four five", 3) == "one two three..."
    assert truncate_words("one two", 5) == "one two"


def test_clean_text():
    assert clean_text("  hello   world  ") == "hello world"
    assert clean_text("a\n\n\n\n\nb") == "a\n\nb"
    assert clean_text("hello\x00world") == "helloworld"


def test_word_count():
    assert word_count("one two three") == 3
    assert word_count("") == 0


def test_extract_domain():
    assert extract_domain("https://example.com/path") == "example.com"
    assert extract_domain("https://sub.example.com") == "sub.example.com"


def test_is_likely_tracking_url():
    assert is_likely_tracking_url("https://click.convertkit.com/abc")
    assert is_likely_tracking_url("https://track.example.com/link")
    assert is_likely_tracking_url("https://substack.com/redirect/abc")
    assert not is_likely_tracking_url("https://example.com/article")

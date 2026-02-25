"""Tests for newsletter parsing."""

from upshot.parsers.newsletter import parse_newsletter
from upshot.models import ContentType


def test_parse_newsletter_segments(sample_newsletter_html):
    items = parse_newsletter(sample_newsletter_html, email_id=1)
    assert len(items) >= 3  # at least the 3 non-header sections

    # Check that we found the GPT-5 article
    titles = [i.title for i in items if i.title]
    assert any("GPT-5" in t for t in titles)


def test_parse_newsletter_detects_ads(sample_newsletter_html):
    items = parse_newsletter(sample_newsletter_html, email_id=1)
    ads = [i for i in items if i.is_ad]
    assert len(ads) >= 1

    # The sponsored section should be marked as ad
    ad_titles = [i.title for i in ads if i.title]
    assert any("Sponsored" in t for t in ad_titles)


def test_parse_newsletter_detects_content_types(sample_newsletter_html):
    items = parse_newsletter(sample_newsletter_html, email_id=1)

    # Should detect arxiv link as paper
    papers = [i for i in items if i.content_type == ContentType.PAPER]
    assert len(papers) >= 1

    # Should detect spotify link as podcast
    podcasts = [i for i in items if i.content_type == ContentType.PODCAST]
    assert len(podcasts) >= 1


def test_parse_newsletter_extracts_urls(sample_newsletter_html):
    items = parse_newsletter(sample_newsletter_html, email_id=1)
    urls = [i.url for i in items if i.url]
    assert any("example.com" in u for u in urls)
    assert any("arxiv.org" in u for u in urls)


def test_parse_empty_html():
    items = parse_newsletter("<html><body></body></html>", email_id=1)
    assert len(items) >= 1  # at least one fallback segment


def test_parse_plain_text_fallback():
    items = parse_newsletter("<html><body><p>Just some plain text about AI.</p></body></html>", email_id=1)
    assert len(items) >= 1

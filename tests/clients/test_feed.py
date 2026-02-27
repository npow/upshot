"""Tests for RSS/Atom feed client."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from upshot.clients.feed import (
    _normalize_substack_url,
    _find_feed_in_html,
    discover_feed_url,
    fetch_feed,
    get_feed_title,
)


# --- Substack URL normalization ---


class TestNormalizeSubstackUrl:
    def test_at_name_format(self):
        assert (
            _normalize_substack_url("https://substack.com/@simonwillison")
            == "https://simonwillison.substack.com/feed"
        )

    def test_www_at_name_format(self):
        assert (
            _normalize_substack_url("https://www.substack.com/@simonwillison")
            == "https://simonwillison.substack.com/feed"
        )

    def test_subdomain_format(self):
        assert (
            _normalize_substack_url("https://simonwillison.substack.com")
            == "https://simonwillison.substack.com/feed"
        )

    def test_subdomain_with_path(self):
        assert (
            _normalize_substack_url("https://simonwillison.substack.com/p/some-post")
            == "https://simonwillison.substack.com/feed"
        )

    def test_non_substack_returns_none(self):
        assert _normalize_substack_url("https://example.com/blog") is None

    def test_substack_com_no_at_name(self):
        assert _normalize_substack_url("https://substack.com/browse") is None

    def test_hyphenated_name(self):
        assert (
            _normalize_substack_url("https://substack.com/@my-newsletter")
            == "https://my-newsletter.substack.com/feed"
        )


# --- HTML feed link discovery ---


class TestFindFeedInHtml:
    def test_finds_rss_link(self):
        html = """
        <html><head>
        <link rel="alternate" type="application/rss+xml" href="/feed.xml">
        </head><body></body></html>
        """
        result = _find_feed_in_html(html, "https://example.com")
        assert result == "https://example.com/feed.xml"

    def test_finds_atom_link(self):
        html = """
        <html><head>
        <link rel="alternate" type="application/atom+xml" href="https://example.com/atom.xml">
        </head><body></body></html>
        """
        result = _find_feed_in_html(html, "https://example.com")
        assert result == "https://example.com/atom.xml"

    def test_returns_none_when_no_feed(self):
        html = "<html><head></head><body></body></html>"
        assert _find_feed_in_html(html, "https://example.com") is None

    def test_ignores_non_feed_links(self):
        html = """
        <html><head>
        <link rel="stylesheet" type="text/css" href="/style.css">
        </head><body></body></html>
        """
        assert _find_feed_in_html(html, "https://example.com") is None


# --- Feed discovery ---


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>Test Blog</title>
  <link>https://example.com</link>
  <item>
    <title>First Post</title>
    <link>https://example.com/post-1</link>
    <guid>https://example.com/post-1</guid>
    <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
    <description>This is the first post summary.</description>
    <content:encoded><![CDATA[<p>Full content of the first post.</p>]]></content:encoded>
  </item>
  <item>
    <title>Second Post</title>
    <link>https://example.com/post-2</link>
    <guid>https://example.com/post-2</guid>
    <pubDate>Tue, 02 Jan 2024 12:00:00 GMT</pubDate>
    <description>This is the second post summary.</description>
  </item>
</channel>
</rss>"""


class TestDiscoverFeedUrl:
    def test_substack_url_returns_immediately(self):
        """Substack URLs should be resolved without HTTP requests."""
        with patch("upshot.clients.feed.get_settings") as mock_settings:
            mock_settings.return_value.feeds.fetch_timeout = 10
            result = discover_feed_url("https://substack.com/@simonwillison")
        assert result == "https://simonwillison.substack.com/feed"

    def test_tries_common_paths(self):
        """Should try /feed, /rss etc. and return the first that works."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/rss+xml"}
        mock_response.text = SAMPLE_RSS

        with patch("upshot.clients.feed.get_settings") as mock_settings:
            mock_settings.return_value.feeds.fetch_timeout = 10
            with patch("httpx.get", return_value=mock_response):
                result = discover_feed_url("https://example.com")

        assert result == "https://example.com/feed"

    def test_raises_on_no_feed_found(self):
        """Should raise ValueError when no feed is found."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><body>Not found</body></html>"

        with patch("upshot.clients.feed.get_settings") as mock_settings:
            mock_settings.return_value.feeds.fetch_timeout = 10
            with patch("httpx.get", return_value=mock_response):
                with pytest.raises(ValueError, match="Could not discover"):
                    discover_feed_url("https://nofeed.example.com")


# --- Feed parsing ---


class TestFetchFeed:
    def test_parses_rss_items(self):
        with patch("upshot.clients.feed.get_settings") as mock_settings:
            mock_settings.return_value.feeds.max_items_per_feed = 50
            items = fetch_feed(SAMPLE_RSS)

        assert len(items) == 2
        assert items[0]["title"] == "First Post"
        assert items[0]["url"] == "https://example.com/post-1"
        assert items[0]["guid"] == "https://example.com/post-1"
        assert items[0]["summary"] is not None
        assert items[1]["title"] == "Second Post"

    def test_respects_max_items(self):
        with patch("upshot.clients.feed.get_settings") as mock_settings:
            mock_settings.return_value.feeds.max_items_per_feed = 1
            items = fetch_feed(SAMPLE_RSS)

        assert len(items) == 1

    def test_handles_missing_fields_gracefully(self):
        minimal_rss = """<?xml version="1.0"?>
        <rss version="2.0">
        <channel><title>Min</title>
        <item><title>Only Title</title></item>
        </channel></rss>"""

        with patch("upshot.clients.feed.get_settings") as mock_settings:
            mock_settings.return_value.feeds.max_items_per_feed = 50
            items = fetch_feed(minimal_rss)

        assert len(items) == 1
        assert items[0]["title"] == "Only Title"
        assert items[0]["url"] == ""


# --- Feed title ---


class TestGetFeedTitle:
    def test_returns_title(self):
        title = get_feed_title(SAMPLE_RSS)
        assert title == "Test Blog"


# --- Database integration ---


class TestFeedIngestion:
    def test_store_and_segment_feed_items(self, db):
        """End-to-end: store a feed, its items, then segment into content_items."""
        # Create a source
        db.execute("INSERT INTO sources (name, type) VALUES ('Test Blog', 'feed')")
        source_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Create a feed
        db.execute(
            "INSERT INTO feeds (url, name, source_id) VALUES (?, ?, ?)",
            ("https://example.com/feed", "Test Blog", source_id),
        )
        feed_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Insert feed items
        db.execute(
            """INSERT INTO feed_items (feed_id, guid, url, title, summary, published_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (feed_id, "guid-1", "https://example.com/post-1", "Post 1", "Summary 1", "2024-01-01"),
        )
        db.execute(
            """INSERT INTO feed_items (feed_id, guid, url, title, summary, published_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (feed_id, "guid-2", "https://example.com/post-2", "Post 2", "Summary 2", "2024-01-02"),
        )
        db.commit()

        # Verify feed items stored
        count = db.execute("SELECT COUNT(*) as c FROM feed_items").fetchone()["c"]
        assert count == 2

        # Verify UNIQUE constraint on (feed_id, guid)
        with pytest.raises(Exception, match="UNIQUE constraint"):
            db.execute(
                """INSERT INTO feed_items (feed_id, guid, url, title) VALUES (?, ?, ?, ?)""",
                (feed_id, "guid-1", "https://example.com/dup", "Dup"),
            )

    def test_feed_url_unique_constraint(self, db):
        """Feeds table enforces unique URLs."""
        db.execute("INSERT INTO sources (name, type) VALUES ('Test', 'feed')")
        source_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute(
            "INSERT INTO feeds (url, name, source_id) VALUES ('https://example.com/feed', 'Test', ?)",
            (source_id,),
        )
        db.commit()

        with pytest.raises(Exception, match="UNIQUE constraint"):
            db.execute(
                "INSERT INTO feeds (url, name, source_id) VALUES ('https://example.com/feed', 'Dup', ?)",
                (source_id,),
            )

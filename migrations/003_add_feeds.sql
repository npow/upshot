-- Add RSS/URL feed support

CREATE TABLE IF NOT EXISTS feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    source_id INTEGER REFERENCES sources(id),
    feed_type TEXT DEFAULT 'rss',  -- rss, atom
    enabled INTEGER DEFAULT 1,
    last_fetched_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_feeds_url ON feeds(url);
CREATE INDEX IF NOT EXISTS idx_feeds_enabled ON feeds(enabled);

CREATE TABLE IF NOT EXISTS feed_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id INTEGER NOT NULL REFERENCES feeds(id),
    guid TEXT,
    url TEXT,
    title TEXT,
    author TEXT,
    published_at TEXT,
    summary TEXT,
    content_html TEXT,
    content_hash TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(feed_id, guid)
);

CREATE INDEX IF NOT EXISTS idx_feed_items_feed_id ON feed_items(feed_id);
CREATE INDEX IF NOT EXISTS idx_feed_items_published_at ON feed_items(published_at);
CREATE INDEX IF NOT EXISTS idx_feed_items_content_hash ON feed_items(content_hash);

-- Add nullable feed_item_id to content_items
ALTER TABLE content_items ADD COLUMN feed_item_id INTEGER REFERENCES feed_items(id);

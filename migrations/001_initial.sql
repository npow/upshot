-- Initial schema for upshot

CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmail_id TEXT UNIQUE NOT NULL,
    thread_id TEXT,
    subject TEXT,
    sender TEXT,
    sender_email TEXT,
    received_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    raw_html TEXT,
    raw_text TEXT,
    label TEXT,
    processed_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_emails_gmail_id ON emails(gmail_id);
CREATE INDEX IF NOT EXISTS idx_emails_received_at ON emails(received_at);
CREATE INDEX IF NOT EXISTS idx_emails_content_hash ON emails(content_hash);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    sender_email TEXT,
    type TEXT DEFAULT 'newsletter',  -- newsletter, blog, podcast, paper
    trust_score REAL DEFAULT 0.5,
    first_seen_at TEXT DEFAULT (datetime('now')),
    last_seen_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS content_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id INTEGER REFERENCES emails(id),
    source_id INTEGER REFERENCES sources(id),
    title TEXT,
    url TEXT,
    resolved_url TEXT,
    content_type TEXT DEFAULT 'article',  -- article, paper, podcast, video, thread
    snippet TEXT,                          -- newsletter blurb
    full_text TEXT,                        -- extracted article content
    content_hash TEXT,
    word_count INTEGER,
    fetch_status TEXT DEFAULT 'pending',   -- pending, fetched, failed, paywall, skipped
    fetch_error TEXT,
    is_ad INTEGER DEFAULT 0,
    position_in_email INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    fetched_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_content_items_email_id ON content_items(email_id);
CREATE INDEX IF NOT EXISTS idx_content_items_url ON content_items(url);
CREATE INDEX IF NOT EXISTS idx_content_items_fetch_status ON content_items(fetch_status);
CREATE INDEX IF NOT EXISTS idx_content_items_content_hash ON content_items(content_hash);
CREATE INDEX IF NOT EXISTS idx_content_items_created_at ON content_items(created_at);

CREATE TABLE IF NOT EXISTS podcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_item_id INTEGER UNIQUE REFERENCES content_items(id),
    audio_url TEXT,
    audio_path TEXT,
    duration_seconds REAL,
    transcript TEXT,
    transcription_status TEXT DEFAULT 'pending',  -- pending, transcribed, skipped, failed
    transcribed_at TEXT
);

CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_item_id INTEGER UNIQUE REFERENCES content_items(id),
    arxiv_id TEXT,
    pdf_url TEXT,
    pdf_path TEXT,
    authors TEXT,    -- JSON array
    abstract TEXT,
    extracted_text TEXT
);

CREATE INDEX IF NOT EXISTS idx_papers_arxiv_id ON papers(arxiv_id);

CREATE TABLE IF NOT EXISTS clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    title TEXT,
    summary TEXT,
    key_insights TEXT,        -- JSON array
    significance TEXT,
    primary_source TEXT,
    topics TEXT,              -- JSON array
    contrarian_views TEXT,    -- JSON array
    category TEXT,
    coverage_breadth INTEGER DEFAULT 1,
    composite_score REAL DEFAULT 0.0,
    novelty_score REAL DEFAULT 0.0,
    interest_score REAL DEFAULT 0.0,
    contrarian_score REAL DEFAULT 0.0,
    recency_score REAL DEFAULT 0.0,
    section TEXT,             -- top_stories, hidden_gems, trend_watch, paper_drops
    section_rank INTEGER,
    enriched_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_clusters_date ON clusters(date);
CREATE INDEX IF NOT EXISTS idx_clusters_section ON clusters(section);

CREATE TABLE IF NOT EXISTS cluster_items (
    cluster_id INTEGER REFERENCES clusters(id),
    content_item_id INTEGER REFERENCES content_items(id),
    is_primary INTEGER DEFAULT 0,
    similarity_to_centroid REAL,
    PRIMARY KEY (cluster_id, content_item_id)
);

CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT UNIQUE NOT NULL,
    markdown TEXT,
    stats TEXT,               -- JSON with counts, cost info
    generated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_interests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS api_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key TEXT UNIQUE NOT NULL,
    model TEXT,
    prompt_version TEXT,
    input_hash TEXT,
    response TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_api_cache_key ON api_cache(cache_key);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    stage TEXT NOT NULL,       -- ingest, extract, transcribe, deduplicate, enrich, rank, digest
    status TEXT DEFAULT 'running',  -- running, completed, failed
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    items_processed INTEGER DEFAULT 0,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_date ON pipeline_runs(date);

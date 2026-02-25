-- Add embedding storage tables

CREATE TABLE IF NOT EXISTS embeddings (
    content_item_id INTEGER PRIMARY KEY REFERENCES content_items(id),
    embedding BLOB NOT NULL,       -- numpy float32 array stored as bytes
    model TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cluster_centroids (
    cluster_id INTEGER PRIMARY KEY REFERENCES clusters(id),
    centroid BLOB NOT NULL,        -- numpy float32 array stored as bytes
    model TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS interest_embeddings (
    interest_id INTEGER PRIMARY KEY REFERENCES user_interests(id),
    embedding BLOB NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

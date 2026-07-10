PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS Logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    level TEXT NOT NULL,
    raw_message TEXT,
    indexed_at TEXT,
    UNIQUE(timestamp, source, level, raw_message)
);

CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON Logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_source ON Logs(source);

CREATE TABLE IF NOT EXISTS Terms (
    term_id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_terms_token ON Terms(token);

CREATE TABLE IF NOT EXISTS PostingList (
    term_id INTEGER NOT NULL,
    log_id INTEGER NOT NULL,
    FOREIGN KEY(term_id) REFERENCES Terms(term_id),
    FOREIGN KEY(log_id) REFERENCES Logs(id)
);

CREATE INDEX IF NOT EXISTS idx_postinglist_term_log ON PostingList(term_id, log_id);

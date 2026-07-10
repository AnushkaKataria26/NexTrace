PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS Logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    level TEXT NOT NULL,
    raw_message TEXT,
    UNIQUE(timestamp, source, level, raw_message)
);

CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON Logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_source ON Logs(source);

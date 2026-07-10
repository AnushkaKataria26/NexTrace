import sqlite3
import pytest
import os
import tempfile
from nextrace.indexer import index_logs, reindex_all, get_or_create_term_id

@pytest.fixture
def test_db():
    # Create a temporary database
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    conn = sqlite3.connect(path)
    
    # Load schema
    schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema.sql")
    with open(schema_path, "r") as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)
    
    conn.close()
    
    yield path
    
    os.remove(path)

def insert_log(db_path, msg, timestamp="2026-07-10 12:00:00", source="test", level="INFO"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO Logs (timestamp, source, level, raw_message) VALUES (?, ?, ?, ?)",
        (timestamp, source, level, msg)
    )
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id

def test_indexer_basic_and_cache(test_db):
    log_id = insert_log(test_db, "hello world hello")
    
    stats = index_logs(test_db)
    assert stats["logs_indexed"] == 1
    assert stats["unique_terms"] == 2 # hello, world
    assert stats["postings_created"] == 2 # 2 distinct terms in the log
    
    # Verify cache reuse conceptually by checking the DB state
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    
    cursor.execute("SELECT token FROM Terms ORDER BY token")
    terms = [row[0] for row in cursor.fetchall()]
    assert set(terms) == {"hello", "world"}
    
    cursor.execute("SELECT term_id, log_id FROM PostingList")
    postings = cursor.fetchall()
    assert len(postings) == 2
    for p in postings:
        assert p[1] == log_id
    conn.close()

def test_incremental_and_idempotency(test_db):
    insert_log(test_db, "error 500")
    
    # First run
    stats1 = index_logs(test_db)
    assert stats1["logs_indexed"] == 1
    
    # Second run without new logs
    stats2 = index_logs(test_db)
    assert stats2["logs_indexed"] == 0
    assert stats2["postings_created"] == 0
    
    # Insert new log
    insert_log(test_db, "timeout 404")
    
    # Third run
    stats3 = index_logs(test_db)
    assert stats3["logs_indexed"] == 1
    assert stats3["postings_created"] == 2 # timeout, 404
    
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM PostingList")
    assert cursor.fetchone()[0] == 4
    conn.close()

def test_transaction_rollback(test_db, monkeypatch):
    insert_log(test_db, "good log")
    insert_log(test_db, "poison log")
    
    # Create a mock tokenizer that fails on "poison log"
    from nextrace import indexer
    original_tokenize = indexer.tokenize
    
    def fake_tokenize(text, **kwargs):
        if "poison" in text:
            raise ValueError("Simulated tokenization failure")
        return original_tokenize(text, **kwargs)
        
    monkeypatch.setattr(indexer, "tokenize", fake_tokenize)
    
    with pytest.raises(RuntimeError) as excinfo:
        index_logs(test_db)
        
    assert "transaction rolled back" in str(excinfo.value)
    
    # Ensure database state was rolled back completely
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM PostingList")
    assert cursor.fetchone()[0] == 0
    
    cursor.execute("SELECT indexed_at FROM Logs")
    for row in cursor.fetchall():
        assert row[0] is None # None of them should be marked as indexed
    conn.close()

def test_reindex_all(test_db):
    insert_log(test_db, "first message")
    index_logs(test_db)
    
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM PostingList")
    assert cursor.fetchone()[0] == 2
    conn.close()
    
    # Reindex should clear and recreate
    stats = reindex_all(test_db)
    assert stats["logs_indexed"] == 1
    assert stats["unique_terms"] == 2
    assert stats["postings_created"] == 2
    
    # Try reindexing with a new log
    insert_log(test_db, "second message")
    stats2 = reindex_all(test_db)
    assert stats2["logs_indexed"] == 2
    assert stats2["unique_terms"] == 3 # first, message, second (message is duplicated)
    assert stats2["postings_created"] == 4

def test_empty_database(test_db):
    stats = index_logs(test_db)
    assert stats["logs_indexed"] == 0
    assert stats["unique_terms"] == 0
    assert stats["postings_created"] == 0
    
def test_empty_message(test_db):
    insert_log(test_db, "")
    insert_log(test_db, "   \n  ")
    
    stats = index_logs(test_db)
    assert stats["logs_indexed"] == 2
    assert stats["unique_terms"] == 0
    assert stats["postings_created"] == 0
    
    # Ensure they are marked indexed
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    cursor.execute("SELECT indexed_at FROM Logs")
    for row in cursor.fetchall():
        assert row[0] is not None
    conn.close()

def test_deduplication(test_db):
    insert_log(test_db, "error error error code 500")
    index_logs(test_db)
    
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    cursor.execute("SELECT term_id FROM Terms WHERE token = 'error'")
    term_id = cursor.fetchone()[0]
    
    # Should only be one posting for 'error'
    cursor.execute("SELECT COUNT(*) FROM PostingList WHERE term_id = ?", (term_id,))
    assert cursor.fetchone()[0] == 1
    conn.close()

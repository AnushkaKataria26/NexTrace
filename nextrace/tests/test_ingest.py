import os
import sqlite3
import tempfile
import threading
import time
import pytest

from ingest import (
    parse_log_line,
    init_db,
    ingest_file
)

def test_parse_valid_line():
    line = "2026-06-14 10:23:45 INFO api-gateway User logged in"
    parsed = parse_log_line(line)
    assert parsed is not None
    assert parsed["timestamp"] == "2026-06-14 10:23:45"
    assert parsed["level"] == "INFO"
    assert parsed["source"] == "api-gateway"
    assert parsed["raw_message"] == "User logged in"

def test_parse_invalid_date():
    line = "2026-13-14 10:23:45 INFO api-gateway User logged in"
    assert parse_log_line(line) is None

def test_parse_unknown_level():
    line = "2026-06-14 10:23:45 WEIRD api-gateway User logged in"
    parsed = parse_log_line(line)
    assert parsed is not None
    assert parsed["level"] == "UNKNOWN"

def test_parse_extra_whitespace():
    line = "  2026-06-14 10:23:45    INFO   api-gateway    "
    parsed = parse_log_line(line)
    assert parsed is not None
    assert parsed["raw_message"] == ""

def test_parse_malformed():
    line = "2026-06-14 10:23:45 INFO"
    assert parse_log_line(line) is None
    
@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    init_db(path)
    yield path
    try:
        os.remove(path)
        # also remove wal files if they exist
        if os.path.exists(path + "-wal"):
            os.remove(path + "-wal")
        if os.path.exists(path + "-shm"):
            os.remove(path + "-shm")
    except OSError:
        pass

@pytest.fixture
def temp_log():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass

def test_ingest_multiline(temp_db, temp_log):
    with open(temp_log, "w") as f:
        f.write("2026-06-14 10:23:45 ERROR app Exception occurred\n")
        f.write("  at line 1\n")
        f.write("  at line 2\n")
        f.write("2026-06-14 10:23:46 INFO app Recovered\n")
    
    stats = ingest_file(temp_log, temp_db)
    assert stats["parsed"] == 2
    assert stats["rejected"] == 0
    
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT raw_message FROM Logs ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    
    assert len(rows) == 2
    assert "Exception occurred\n  at line 1\n  at line 2" in rows[0][0]
    assert rows[1][0] == "Recovered"

def test_ingest_duplicates(temp_db, temp_log):
    with open(temp_log, "w") as f:
        f.write("2026-06-14 10:23:45 INFO app test\n")
        f.write("2026-06-14 10:23:45 INFO app test\n")
        
    stats = ingest_file(temp_log, temp_db)
    assert stats["parsed"] == 2
    assert stats["duplicates"] == 1
    
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM Logs")
    count = cursor.fetchone()[0]
    conn.close()
    
    assert count == 1

def test_empty_file(temp_db, temp_log):
    stats = ingest_file(temp_log, temp_db)
    assert stats["total_read"] == 0
    assert stats["parsed"] == 0

def test_large_file(temp_db, temp_log):
    num_lines = 50000
    with open(temp_log, "w") as f:
        for i in range(num_lines):
            f.write(f"2026-06-14 10:23:45 INFO app msg {i}\n")
            
    start_time = time.time()
    stats = ingest_file(temp_log, temp_db, batch_size=5000)
    end_time = time.time()
    
    assert stats["parsed"] == num_lines
    print(f"\nLarge file (50000 lines) ingestion took {end_time - start_time:.2f} seconds")

def test_encoding_fallback(temp_db, temp_log):
    with open(temp_log, "wb") as f:
        f.write(b"2026-06-14 10:23:45 INFO app Normal message\n")
        # Write invalid utf-8 byte (e.g., 0xFF)
        f.write(b"2026-06-14 10:23:46 INFO app Bad byte: \xff\n")
        
    stats = ingest_file(temp_log, temp_db)
    assert stats["parsed"] == 2
    
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT raw_message FROM Logs ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    assert len(rows) == 2
    assert "Normal message" in rows[0][0]
    assert "Bad byte:" in rows[1][0]

def test_concurrent_ingestion(temp_db):
    def worker(worker_id):
        fd, t_log = tempfile.mkstemp()
        with os.fdopen(fd, "w") as f:
            for i in range(500):
                f.write(f"2026-06-14 10:23:45 INFO worker{worker_id} msg {i}\n")
        ingest_file(t_log, temp_db)
        try:
            os.remove(t_log)
        except OSError:
            pass
        
    threads = []
    for i in range(4):
        t = threading.Thread(target=worker, args=(i,))
        t.start()
        threads.append(t)
        
    for t in threads:
        t.join()
        
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM Logs")
    count = cursor.fetchone()[0]
    conn.close()
    
    # 4 workers * 500 = 2000 lines inserted
    assert count == 2000

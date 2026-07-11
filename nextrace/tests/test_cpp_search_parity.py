import os
import sqlite3
import subprocess
import json
import pytest
from nextrace.query_parser import parse_query
from nextrace.search import execute_search, apply_filters

DB_FILE = "test_parity.db"

@pytest.fixture(scope="module")
def setup_db():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.executescript("""
        CREATE TABLE Logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            source TEXT NOT NULL,
            level TEXT NOT NULL,
            raw_message TEXT
        );
        CREATE TABLE Terms (
            term_id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT NOT NULL UNIQUE
        );
        CREATE TABLE PostingList (
            term_id INTEGER NOT NULL,
            log_id INTEGER NOT NULL
        );
    """)
    
    logs = [
        ("2023-01-01T10:00:00", "app", "INFO", "server started"),
        ("2023-01-01T10:05:00", "api", "ERROR", "connection timeout"),
        ("2023-01-01T10:10:00", "db", "WARN", "slow query detected"),
        ("2023-01-02T11:00:00", "app", "ERROR", "server crashed timeout")
    ]
    cursor.executemany("INSERT INTO Logs (timestamp, source, level, raw_message) VALUES (?, ?, ?, ?)", logs)
    
    large_logs = []
    for i in range(1500):
        large_logs.append((f"2023-02-01T10:00:{(i%60):02d}", "app", "INFO", f"bulk message {i}"))
    cursor.executemany("INSERT INTO Logs (timestamp, source, level, raw_message) VALUES (?, ?, ?, ?)", large_logs)
    
    terms = [("server",), ("started",), ("connection",), ("timeout",), ("slow",), ("query",), ("crashed",), ("bulk",), ("message",)]
    cursor.executemany("INSERT INTO Terms (token) VALUES (?)", terms)
    
    postings = [
        (1, 1), (2, 1),
        (3, 2), (4, 2),
        (5, 3), (6, 3),
        (1, 4), (7, 4), (4, 4)
    ]
    
    for i in range(1500):
        log_id = i + 5
        postings.extend([(8, log_id), (9, log_id)])
        
    cursor.executemany("INSERT INTO PostingList (term_id, log_id) VALUES (?, ?)", postings)
    
    conn.commit()
    conn.close()
    
    yield DB_FILE
    
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

def run_cpp_engine(query, db, **kwargs):
    binary_path = os.path.join(os.path.dirname(__file__), "..", "build", "nextrace_search")
    cmd = [binary_path, query, "--db", db, "--json"]
    for k, v in kwargs.items():
        if v is not None:
            cmd.extend([f"--{k}", str(v)])
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    output = json.loads(res.stdout)
    return output.get("results", []), output.get("total_count", 0)

def run_python_engine(query, db, **kwargs):
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    parsed = parse_query(query)
    log_ids = execute_search(parsed, cursor)
    results, total_count = apply_filters(
        log_ids=log_ids,
        since=kwargs.get("since"),
        until=kwargs.get("until"),
        source=kwargs.get("source"),
        level=kwargs.get("level"),
        limit=kwargs.get("limit", 100),
        offset=kwargs.get("offset", 0),
        cursor=cursor
    )
    conn.close()
    return results, total_count

def assert_parity(query, db, **kwargs):
    cpp_res, cpp_count = run_cpp_engine(query, db, **kwargs)
    py_res, py_count = run_python_engine(query, db, **kwargs)
    
    assert cpp_count == py_count
    assert len(cpp_res) == len(py_res)
    for cr, pr in zip(cpp_res, py_res):
        assert cr["timestamp"] == pr["timestamp"]
        assert cr["level"] == pr["level"]
        assert cr["source"] == pr["source"]
        assert cr["raw_message"] == pr["raw_message"]

# Fixed set of 15 representative queries
QUERIES = [
    # 1. Single term
    ("server", {}),
    # 2. Single term (missing)
    ("missingterm", {}),
    # 3. AND query
    ("server AND timeout", {}),
    # 4. OR query
    ("started OR crashed", {}),
    # 5. AND query with missing term
    ("server AND missingterm", {}),
    # 6. OR query with missing term
    ("started OR missingterm", {}),
    # 7. Single term + level filter
    ("timeout", {"level": "ERROR"}),
    # 8. Single term + source filter
    ("timeout", {"source": "app"}),
    # 9. Time filter exact match
    ("timeout", {"since": "2023-01-01T10:05:00", "until": "2023-01-01T10:05:00"}),
    # 10. Time filter range
    ("server", {"since": "2023-01-01", "until": "2023-01-02T23:59:59"}),
    # 11. Large result set (bulk)
    ("bulk AND message", {"limit": 2000}),
    # 12. Large result set + pagination
    ("bulk AND message", {"limit": 50, "offset": 100}),
    # 13. Empty term list defense (quotes but no word)
    ('""', {}), # This triggers ValueError in python parse_query
    # 14. Multiple filters
    ("bulk", {"level": "INFO", "source": "app", "since": "2023-02-01T00:00:00", "limit": 10}),
    # 15. Contradictory time filter
    ("server", {"since": "2024-01-01", "until": "2023-01-01"}),
]

def test_queries_parity(setup_db):
    db = setup_db
    for query, kwargs in QUERIES:
        if query == '""':
            # Handle expected parse errors
            with pytest.raises(ValueError):
                run_python_engine(query, db, **kwargs)
            
            # C++ engine should exit with non-zero code on parse error
            with pytest.raises(subprocess.CalledProcessError):
                run_cpp_engine(query, db, **kwargs)
            continue
            
        assert_parity(query, db, **kwargs)

def test_sql_injection_defense(setup_db):
    db = setup_db
    # Pass malicious string to C++ engine
    query = "timeout"
    malicious_level = "ERROR'; DROP TABLE Logs; --"
    
    # Python engine raises ValueError or just returns empty
    py_res, py_count = run_python_engine(query, db, level=malicious_level)
    cpp_res, cpp_count = run_cpp_engine(query, db, level=malicious_level)
    
    assert py_count == 0
    assert cpp_count == 0
    assert py_res == []
    assert cpp_res == []
    
    # Confirm DB is intact
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM Logs")
    assert cursor.fetchone()[0] == 1504
    conn.close()

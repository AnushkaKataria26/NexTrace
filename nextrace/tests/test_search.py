import sqlite3
import pytest
from nextrace.search import (
    get_term_id, get_posting_list, intersect_posting_lists,
    execute_search, apply_filters, validate_date
)

@pytest.fixture
def db_cursor():
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    
    # Create schema
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
    
    # Insert dummy data
    logs = [
        ("2023-01-01T10:00:00", "app", "INFO", "server started"),
        ("2023-01-01T10:05:00", "api", "ERROR", "connection timeout"),
        ("2023-01-01T10:10:00", "db", "WARN", "slow query detected"),
        ("2023-01-02T11:00:00", "app", "ERROR", "server crashed timeout")
    ]
    cursor.executemany("INSERT INTO Logs (timestamp, source, level, raw_message) VALUES (?, ?, ?, ?)", logs)
    
    terms = [("server",), ("started",), ("connection",), ("timeout",), ("slow",), ("query",), ("crashed",)]
    cursor.executemany("INSERT INTO Terms (token) VALUES (?)", terms)
    
    # term_ids: server=1, started=2, connection=3, timeout=4, slow=5, query=6, crashed=7
    # log_ids: 1(server started), 2(connection timeout), 3(slow query), 4(crashed timeout)
    postings = [
        (1, 1), (2, 1), # server, started in log 1
        (3, 2), (4, 2), # connection, timeout in log 2
        (5, 3), (6, 3), # slow, query in log 3
        (1, 4), (7, 4), (4, 4) # server, crashed, timeout in log 4
    ]
    cursor.executemany("INSERT INTO PostingList (term_id, log_id) VALUES (?, ?)", postings)
    
    conn.commit()
    yield cursor
    conn.close()


def test_intersect_posting_lists():
    sets = [{1, 2, 3}, {2, 3, 4}, {3, 5, 6}]
    assert intersect_posting_lists(sets) == {3}
    assert intersect_posting_lists([]) == set()
    
    # Test ascending size optimization by mocking order processing implicitly
    sets_unbalanced = [{i for i in range(1000)}, {1, 2}, {1, 2, 3}]
    assert intersect_posting_lists(sets_unbalanced) == {1, 2}


def test_get_term_id(db_cursor):
    assert get_term_id("server", db_cursor) == 1
    assert get_term_id("missing", db_cursor) is None


def test_get_posting_list(db_cursor):
    assert get_posting_list(1, db_cursor) == {1, 4}
    assert get_posting_list(2, db_cursor) == {1}
    assert get_posting_list(None, db_cursor) == set()


def test_execute_search_single(db_cursor):
    res = execute_search({"terms": ["server"], "operator": None}, db_cursor)
    assert res == {1, 4}


def test_execute_search_and(db_cursor):
    res = execute_search({"terms": ["server", "timeout"], "operator": "AND"}, db_cursor)
    assert res == {4}


def test_execute_search_and_missing_term(db_cursor):
    res = execute_search({"terms": ["server", "missing"], "operator": "AND"}, db_cursor)
    assert res == set()


def test_execute_search_or(db_cursor):
    res = execute_search({"terms": ["started", "crashed"], "operator": "OR"}, db_cursor)
    assert res == {1, 4}


def test_execute_search_or_missing_term(db_cursor):
    res = execute_search({"terms": ["started", "missing"], "operator": "OR"}, db_cursor)
    assert res == {1}


def test_apply_filters_empty_log_ids(db_cursor):
    res, count = apply_filters(set(), None, None, None, None, db_cursor)
    assert res == []
    assert count == 0


def test_apply_filters_basic(db_cursor):
    res, count = apply_filters({1, 4}, None, None, None, None, db_cursor)
    # Ordered by timestamp desc
    assert len(res) == 2
    assert count == 2
    assert res[0]["timestamp"] == "2023-01-02T11:00:00"
    assert res[1]["timestamp"] == "2023-01-01T10:00:00"


def test_apply_filters_time(db_cursor):
    res, count = apply_filters({1, 2, 3, 4}, since="2023-01-01T10:05:00", until="2023-01-01T10:15:00", source=None, level=None, cursor=db_cursor)
    assert len(res) == 2
    assert count == 2
    assert res[0]["timestamp"] == "2023-01-01T10:10:00"
    assert res[1]["timestamp"] == "2023-01-01T10:05:00"


def test_apply_filters_contradictory_time(db_cursor):
    res, count = apply_filters({1, 2, 3, 4}, since="2023-02-01", until="2023-01-01", source=None, level=None, cursor=db_cursor)
    assert res == []
    assert count == 0


def test_apply_filters_source_level(db_cursor):
    res, count = apply_filters({1, 2, 3, 4}, since=None, until=None, source="api", level="ERROR", cursor=db_cursor)
    assert len(res) == 1
    assert count == 1
    assert res[0]["raw_message"] == "connection timeout"


def test_apply_filters_pagination(db_cursor):
    res, count = apply_filters({1, 2, 3, 4}, since=None, until=None, source=None, level=None, cursor=db_cursor, limit=1, offset=1)
    assert len(res) == 1
    assert count == 4
    # Full order desc: 4, 3, 2, 1
    # Offset 1 is log id 3
    assert res[0]["raw_message"] == "slow query detected"


def test_apply_filters_large_in_clause(db_cursor):
    # Insert 1500 logs to test if temp table batching works without limits
    logs = []
    for i in range(1500):
        logs.append((f"2023-02-01T10:00:{i%60:02d}", "app", "INFO", f"msg {i}"))
    db_cursor.executemany("INSERT INTO Logs (timestamp, source, level, raw_message) VALUES (?, ?, ?, ?)", logs)
    
    # We inserted 1500 logs. Their IDs will be 5 to 1504
    large_ids = set(range(5, 1505))
    res, count = apply_filters(large_ids, since=None, until=None, source=None, level=None, cursor=db_cursor, limit=2000, offset=0)
    assert len(res) == 1500
    assert count == 1500


def test_apply_filters_sql_injection(db_cursor):
    # Attempt SQL injection in level parameter
    res, count = apply_filters({1, 2}, since=None, until=None, source=None, level="ERROR'; DROP TABLE Logs; --", cursor=db_cursor)
    assert res == []
    assert count == 0
    
    # Check that Logs table still exists and data is untouched
    db_cursor.execute("SELECT COUNT(*) FROM Logs")
    assert db_cursor.fetchone()[0] == 4

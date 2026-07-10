import sqlite3
import argparse
import time
from datetime import datetime, timezone
from nextrace.tokenizer import tokenize

def get_or_create_term_id(token: str, cursor: sqlite3.Cursor, cache: dict) -> int:
    """
    Retrieves term_id for a given token, inserting it if not present.
    Uses a local cache dict to reduce DB trips within a batch.
    """
    if token in cache:
        return cache[token]
        
    # Attempt to insert, ignoring if it already exists (due to UNIQUE constraint)
    cursor.execute("INSERT OR IGNORE INTO Terms (token) VALUES (?)", (token,))
    
    # Retrieve the term_id (whether it was just inserted or already existed)
    cursor.execute("SELECT term_id FROM Terms WHERE token = ?", (token,))
    result = cursor.fetchone()
    
    if result:
        term_id = result[0]
        cache[token] = term_id
        return term_id
    else:
        raise RuntimeError(f"Failed to retrieve term_id for token: {token}")

def index_logs(db_path: str, batch_size: int = 1000) -> dict:
    """
    Incrementally indexes logs where indexed_at IS NULL.
    Updates the indexed_at timestamp atomically within the same transaction.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check if Logs table has any records at all
    cursor.execute("SELECT COUNT(*) FROM Logs")
    total_logs_count = cursor.fetchone()[0]
    if total_logs_count == 0:
        conn.close()
        return {"logs_indexed": 0, "unique_terms": 0, "postings_created": 0, "time_taken": 0.0}
    
    stats = {
        "logs_indexed": 0,
        "unique_terms": 0,
        "postings_created": 0,
        "time_taken": 0.0
    }
    
    term_cache = {}
    # Warm up cache with some existing terms? Not strictly necessary, it will populate as we go.
    
    start_time = time.time()
    
    while True:
        # Fetch a batch of unindexed logs
        cursor.execute("SELECT id, raw_message FROM Logs WHERE indexed_at IS NULL LIMIT ?", (batch_size,))
        rows = cursor.fetchall()
        
        if not rows:
            break
            
        try:
            # We want to do the processing within a transaction
            cursor.execute("BEGIN TRANSACTION")
            
            posting_inserts = []
            log_ids_processed = []
            
            for row in rows:
                log_id = row["id"]
                raw_message = row["raw_message"]
                
                log_ids_processed.append((log_id,))
                
                # Tokenize the message
                tokens = tokenize(raw_message, filter_stopwords=False)
                
                for token in tokens:
                    term_id = get_or_create_term_id(token, cursor, term_cache)
                    posting_inserts.append((term_id, log_id))
            
            # Batch insert posting lists
            if posting_inserts:
                cursor.executemany("INSERT INTO PostingList (term_id, log_id) VALUES (?, ?)", posting_inserts)
                stats["postings_created"] += len(posting_inserts)
                
            # Mark these logs as indexed
            # Using current ISO-8601 UTC timestamp
            now_iso = datetime.now(timezone.utc).isoformat()
            
            # Executemany to update indexed_at for the processed batch
            update_data = [(now_iso, lid[0]) for lid in log_ids_processed]
            cursor.executemany("UPDATE Logs SET indexed_at = ? WHERE id = ?", update_data)
            
            conn.commit()
            stats["logs_indexed"] += len(rows)
            
        except Exception as e:
            conn.rollback()
            conn.close()
            raise RuntimeError(f"Error during batch indexing, transaction rolled back: {e}")
            
    cursor.execute("SELECT COUNT(*) FROM Terms")
    stats["unique_terms"] = cursor.fetchone()[0]
            
    conn.close()
    
    stats["time_taken"] = time.time() - start_time
    return stats

def reindex_all(db_path: str):
    """
    Clears existing index and re-runs the indexing process.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("DELETE FROM PostingList")
        cursor.execute("DELETE FROM Terms")
        cursor.execute("UPDATE Logs SET indexed_at = NULL")
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise RuntimeError(f"Error during reindex clearing, transaction rolled back: {e}")
        
    conn.close()
    
    # Re-run index_logs
    return index_logs(db_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NexTrace Tokenizer and Indexer")
    parser.add_argument("--db", required=True, help="Path to the NexTrace SQLite database")
    parser.add_argument("--reindex", action="store_true", help="Clear existing index and re-index all logs")
    parser.add_argument("--batch-size", type=int, default=1000, help="Number of logs to process per batch")
    
    args = parser.parse_args()
    
    if args.reindex:
        print("Starting full re-index...")
        stats = reindex_all(args.db)
    else:
        print("Starting incremental indexing...")
        stats = index_logs(args.db, args.batch_size)
        
    print("Indexing Complete.")
    print(f"Logs Indexed: {stats['logs_indexed']}")
    print(f"Total Unique Terms (Vocabulary): {stats['unique_terms']}")
    print(f"Posting List Entries Created: {stats['postings_created']}")
    print(f"Time Taken: {stats['time_taken']:.2f} seconds")

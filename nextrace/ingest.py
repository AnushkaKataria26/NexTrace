import os
import sys
import time
import sqlite3
import argparse
import re
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

LOG_PATTERN = re.compile(
    r"^\s*(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>\S+)\s+"
    r"(?P<source>\S+)\s*"
    r"(?P<message>.*)$"
)

VALID_LEVELS = {"INFO", "WARN", "ERROR", "DEBUG"}

def init_db(db_path: str, schema_path: str = None):
    if schema_path is None:
        schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
        
    os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    
    if os.path.exists(schema_path):
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()
            conn.executescript(schema_sql)
    else:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS Logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                level TEXT NOT NULL,
                raw_message TEXT,
                UNIQUE(timestamp, source, level, raw_message)
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON Logs(timestamp);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_source ON Logs(source);")
        
    conn.commit()
    conn.close()

def parse_log_line(line: str) -> dict | None:
    match = LOG_PATTERN.match(line)
    if not match:
        return None
        
    group = match.groupdict()
    
    try:
        datetime.strptime(group["timestamp"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
        
    level = group["level"].upper()
    if level not in VALID_LEVELS:
        level = "UNKNOWN"
        
    return {
        "timestamp": group["timestamp"],
        "level": level,
        "source": group["source"],
        "raw_message": group["message"]
    }

def flush_batch(conn, batch, stats):
    if not batch:
        return
    try:
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT OR IGNORE INTO Logs (timestamp, source, level, raw_message) VALUES (?, ?, ?, ?)",
            [(r["timestamp"], r["source"], r["level"], r["raw_message"]) for r in batch]
        )
        conn.commit()
        stats["parsed"] += len(batch)
        stats["duplicates"] += (len(batch) - cursor.rowcount)
    except sqlite3.Error as e:
        print(f"Database error during insertion: {e}", file=sys.stderr)
        conn.rollback()
    batch.clear()

def _process_file_lines(filepath, db_path, start_offset, batch_size, tailing, encoding):
    stats = {"total_read": 0, "parsed": 0, "rejected": 0, "duplicates": 0, "bytes_read": 0}
    
    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
    except sqlite3.Error as e:
        print(f"Error connecting to DB: {e}", file=sys.stderr)
        return stats

    batch = []
    last_record = None
    
    try:
        with open(filepath, "r", encoding=encoding) as f:
            f.seek(start_offset)
            while True:
                pos = f.tell()
                line = f.readline()
                if not line:
                    break
                    
                if tailing and not line.endswith("\n"):
                    f.seek(pos)
                    break
                    
                stats["total_read"] += 1
                stats["bytes_read"] = f.tell() - start_offset
                line_stripped = line.rstrip("\r\n")
                
                parsed = parse_log_line(line_stripped)
                
                if parsed:
                    if last_record:
                        batch.append(last_record)
                        if len(batch) >= batch_size:
                            flush_batch(conn, batch, stats)
                    last_record = parsed
                else:
                    if last_record:
                        last_record["raw_message"] += "\n" + line_stripped
                    else:
                        stats["rejected"] += 1
                        
            if last_record:
                batch.append(last_record)
                flush_batch(conn, batch, stats)
                
    except UnicodeDecodeError:
        conn.close()
        raise
    except Exception as e:
        print(f"Error reading file {filepath}: {e}", file=sys.stderr)
    finally:
        conn.close()
        
    return stats

def process_file_lines_with_fallback(filepath, db_path, start_offset=0, batch_size=1000, tailing=False):
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        return {"total_read": 0, "parsed": 0, "rejected": 0, "duplicates": 0, "bytes_read": 0}
        
    if os.path.islink(filepath):
        filepath = os.path.realpath(filepath)
    if not os.access(filepath, os.R_OK):
        print(f"Error: Permission denied reading file: {filepath}", file=sys.stderr)
        return {"total_read": 0, "parsed": 0, "rejected": 0, "duplicates": 0, "bytes_read": 0}
        
    try:
        return _process_file_lines(filepath, db_path, start_offset, batch_size, tailing, encoding="utf-8")
    except UnicodeDecodeError:
        print(f"Warning: Failed to decode {filepath} as UTF-8, falling back to latin-1.", file=sys.stderr)
        return _process_file_lines(filepath, db_path, start_offset, batch_size, tailing, encoding="latin-1")

def ingest_file(filepath: str, db_path: str, batch_size: int = 1000) -> dict:
    return process_file_lines_with_fallback(filepath, db_path, 0, batch_size, tailing=False)

class LogTailer(FileSystemEventHandler):
    def __init__(self, db_path, batch_size=1000):
        self.db_path = db_path
        self.batch_size = batch_size
        self.file_offsets = {}
        self.file_inodes = {}
        self.last_process_time = {}
        
    def _process(self, filepath):
        now = time.time()
        last_time = self.last_process_time.get(filepath, 0)
        if now - last_time < 0.2:
            return
        self.last_process_time[filepath] = now
        
        if not filepath.endswith(".log"):
            return
            
        try:
            stat = os.stat(filepath)
        except OSError:
            return
            
        inode = stat.st_ino
        size = stat.st_size
        
        if filepath in self.file_offsets:
            old_inode = self.file_inodes.get(filepath)
            old_offset = self.file_offsets.get(filepath, 0)
            if inode != old_inode or size < old_offset:
                self.file_offsets[filepath] = 0
                
        offset = self.file_offsets.get(filepath, 0)
        
        stats = process_file_lines_with_fallback(filepath, self.db_path, start_offset=offset, batch_size=self.batch_size, tailing=True)
        
        if stats["bytes_read"] > 0:
            self.file_offsets[filepath] = offset + stats["bytes_read"]
            self.file_inodes[filepath] = inode
            
    def on_modified(self, event):
        if not event.is_directory:
            self._process(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._process(event.src_path)

def tail_directory(directory: str, db_path: str, batch_size: int = 1000):
    if not os.path.exists(directory) or not os.path.isdir(directory):
        print(f"Error: Directory to watch does not exist: {directory}", file=sys.stderr)
        sys.exit(1)
        
    handler = LogTailer(db_path, batch_size)
    
    for filename in os.listdir(directory):
        if filename.endswith(".log"):
            filepath = os.path.join(directory, filename)
            handler._process(filepath)
            
    observer = Observer()
    observer.schedule(handler, directory, recursive=False)
    observer.start()
    
    print(f"Watching directory {directory} for log changes. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

def main():
    parser = argparse.ArgumentParser(description="Ingest logs into NexTrace SQLite database.")
    parser.add_argument("--db", type=str, required=True, help="Path to SQLite database file")
    parser.add_argument("--file", type=str, help="Path to a single log file to batch ingest")
    parser.add_argument("--watch", type=str, help="Path to directory to watch for continuous tailing")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for database inserts")
    
    args = parser.parse_args()
    
    if not args.file and not args.watch:
        print("Error: Must specify either --file or --watch", file=sys.stderr)
        parser.print_help()
        sys.exit(1)
        
    init_db(args.db)
    
    if args.file:
        stats = ingest_file(args.file, args.db, args.batch_size)
        print("Batch Ingestion Complete")
        print(f"Total lines read:   {stats['total_read']}")
        print(f"Lines parsed:       {stats['parsed']}")
        print(f"Lines rejected:     {stats['rejected']}")
        print(f"Duplicates skipped: {stats['duplicates']}")
        
    if args.watch:
        tail_directory(args.watch, args.db, args.batch_size)

if __name__ == "__main__":
    main()

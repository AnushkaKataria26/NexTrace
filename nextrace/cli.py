import argparse
import sys
import time
import os
import sqlite3

from nextrace.query_parser import parse_query
from nextrace.search import execute_search, apply_filters

def main():
    parser = argparse.ArgumentParser(description="NexTrace CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    search_parser = subparsers.add_parser("search", help="Search the NexTrace index")
    search_parser.add_argument("query", type=str, help="Search query string")
    search_parser.add_argument("--since", type=str, help="Filter by start time (YYYY-MM-DD[THH:MM:SS])")
    search_parser.add_argument("--until", type=str, help="Filter by end time (YYYY-MM-DD[THH:MM:SS])")
    search_parser.add_argument("--source", type=str, help="Filter by source")
    search_parser.add_argument("--level", type=str, help="Filter by level")
    search_parser.add_argument("--limit", type=int, default=100, help="Max results to return")
    search_parser.add_argument("--offset", type=int, default=0, help="Pagination offset")
    search_parser.add_argument("--db", type=str, default="nextrace.db", help="Path to database file")
    search_parser.add_argument("--engine", type=str, choices=["python", "cpp"], default="python", help="Search engine implementation to use")
    
    args = parser.parse_args()
    
    if args.command == "search":
        if not os.path.exists(args.db):
            print(f"Error: Database file '{args.db}' not found.", file=sys.stderr)
            sys.exit(1)
            
        start_time = time.perf_counter()
        
        if args.engine == "python":
            try:
                parsed_query = parse_query(args.query)
            except ValueError as e:
                print(f"Query Error: {e}", file=sys.stderr)
                sys.exit(1)
                
            try:
                conn = sqlite3.connect(args.db)
                cursor = conn.cursor()
                
                log_ids = execute_search(parsed_query, cursor)
                
                results, total_count = apply_filters(
                    log_ids=log_ids,
                    since=args.since,
                    until=args.until,
                    source=args.source,
                    level=args.level,
                    cursor=cursor,
                    limit=args.limit,
                    offset=args.offset
                )
                
            except sqlite3.Error as e:
                print(f"Database Error: {e}", file=sys.stderr)
                sys.exit(1)
            except ValueError as e:
                print(f"Filter Error: {e}", file=sys.stderr)
                sys.exit(1)
            finally:
                if 'conn' in locals():
                    conn.close()
                    
            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000
            
        elif args.engine == "cpp":
            import subprocess
            import json
            
            binary_path = os.path.join(os.path.dirname(__file__), "build", "nextrace_search")
            if not os.path.exists(binary_path):
                print(f"Error: C++ binary not found at {binary_path}. Please build it using CMake.", file=sys.stderr)
                sys.exit(1)
                
            cmd = [binary_path, args.query, "--db", args.db, "--json"]
            if args.since: cmd.extend(["--since", args.since])
            if args.until: cmd.extend(["--until", args.until])
            if args.source: cmd.extend(["--source", args.source])
            if args.level: cmd.extend(["--level", args.level])
            cmd.extend(["--limit", str(args.limit), "--offset", str(args.offset)])
            
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            except subprocess.TimeoutExpired:
                print("Error: C++ search engine timed out after 30 seconds.", file=sys.stderr)
                sys.exit(1)
                
            if res.returncode != 0:
                print(f"Error from C++ engine:\n{res.stderr}", file=sys.stderr)
                sys.exit(1)
                
            try:
                output = json.loads(res.stdout)
                results = output.get("results", [])
                total_count = output.get("total_count", 0)
                latency_ms = output.get("latency_ms", 0.0)
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON from C++ engine: {e}\nRaw Output: {res.stdout}", file=sys.stderr)
                sys.exit(1)
        
        if not results:
            print("No matches found.")
            print(f"\nFound 0 matches in {latency_ms:.2f} ms")
        else:
            for r in results:
                print(f"[{r['timestamp']}] [{r['level']}] [{r['source']}] {r['raw_message']}")
                
            print(f"\nFound {total_count} matches (showing limit {args.limit}) in {latency_ms:.2f} ms")

if __name__ == "__main__":
    main()

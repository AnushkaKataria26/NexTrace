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
    
    args = parser.parse_args()
    
    if args.command == "search":
        if not os.path.exists(args.db):
            print(f"Error: Database file '{args.db}' not found.", file=sys.stderr)
            sys.exit(1)
            
        start_time = time.perf_counter()
        
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
        
        if not results:
            print("No matches found.")
            print(f"\nFound 0 matches in {latency_ms:.2f} ms")
        else:
            for r in results:
                print(f"[{r['timestamp']}] [{r['level']}] [{r['source']}] {r['raw_message']}")
                
            print(f"\nFound {total_count} matches (showing limit {args.limit}) in {latency_ms:.2f} ms")

if __name__ == "__main__":
    main()

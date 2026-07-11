import os
import time
import subprocess
import sqlite3
import re
import shlex

def run_command(cmd: list[str]) -> tuple[float, str]:
    start = time.perf_counter()
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    end = time.perf_counter()
    return end - start, res.stdout + res.stderr

def main():
    num_lines = 1000000
    log_file = "nextrace/data/benchmark_1M.log"
    db_file = "nextrace_benchmark.db"
    
    if os.path.exists(db_file):
        os.remove(db_file)
        
    print(f"Generating {num_lines} synthetic logs... (this may take a minute or two)")
    run_command(["python", "nextrace/data/generate_logs.py", "--lines", str(num_lines), "--output", log_file])
    print("Generation complete.\n")
    
    print("Running ingestion...")
    ingest_time, _ = run_command(["python", "nextrace/ingest.py", "--file", log_file, "--db", db_file])
    ingest_throughput = num_lines / ingest_time
    print(f"Ingestion took {ingest_time:.2f} s ({ingest_throughput:.2f} logs/sec).\n")
    
    print("Running indexing...")
    index_time, _ = run_command(["python", "nextrace/indexer.py", "--db", db_file])
    index_throughput = num_lines / index_time
    print(f"Indexing took {index_time:.2f} s ({index_throughput:.2f} logs/sec).\n")
    
    db_size_mb = os.path.getsize(db_file) / (1024 * 1024)
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM Terms")
    terms_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM PostingList")
    posting_count = cursor.fetchone()[0]
    conn.close()
    
    # We will pick a year that generate_logs uses, which is around 'now'.
    # For a robust time filter test, since the script uses (now - 1 day) and adds ms,
    # we can use a wide range. We'll use 2000-01-01 to 2099-01-01 to be safe, 
    # or just --since 2023-01-01 to capture recent stuff.
    
    queries = [
        ("Single term common word", "search processed --db " + db_file),
        ("Single term rare word", "search crashed --db " + db_file),
        ("AND of two common terms", 'search "timeout AND connection" --db ' + db_file),
        ("OR of two terms", 'search "error OR warning" --db ' + db_file),
        ("Time-filtered query", 'search authenticate --since 2020-01-01 --until 2099-01-01 --db ' + db_file)
    ]
    
    results = []
    latency_pattern = re.compile(r"in ([\d.]+) ms")
    
    print("Running sample queries...")
    for name, args_str in queries:
        cmd = ["python", "nextrace/cli.py"] + shlex.split(args_str)
        try:
            _, out = run_command(cmd)
            match = latency_pattern.search(out)
            if match:
                latency = match.group(1)
            else:
                latency = "N/A"
        except subprocess.CalledProcessError as e:
            latency = f"Error: {e.stderr}"
            
        results.append((name, latency))
        
    print("\n" + "="*40)
    print("BENCHMARK SUMMARY")
    print("="*40)
    print(f"Ingestion Throughput: {ingest_throughput:.2f} logs/sec")
    print(f"Indexing Throughput:  {index_throughput:.2f} logs/sec")
    print(f"Index Size:           {db_size_mb:.2f} MB")
    print(f"Terms Count:          {terms_count:,}")
    print(f"PostingList Count:    {posting_count:,}")
    print("-" * 40)
    print("Query Latencies:")
    for name, lat in results:
        print(f"  - {name}: {lat} ms")
        
if __name__ == "__main__":
    main()

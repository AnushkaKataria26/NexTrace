import os
import time
import subprocess
import sqlite3
import re
import shlex
def run_command(cmd: list[str]) -> tuple[float, str]:
    start = time.perf_counter()
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    res = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
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
        ("Single term common", "search processed --db " + db_file),
        ("Single term rare", "search crashed --db " + db_file),
        ("AND two terms", 'search "timeout AND connection" --db ' + db_file),
        ("OR two terms", 'search "error OR warning" --db ' + db_file),
        ("Time filtered", 'search authenticate --since 2020-01-01 --until 2099-01-01 --db ' + db_file)
    ]
    
    results = []
    latency_pattern = re.compile(r"in ([\d.]+) ms")
    
    print("Running sample queries for Python and C++ engines...")
    for name, args_str in queries:
        # Python
        cmd_py = ["python", "nextrace/cli.py"] + shlex.split(args_str) + ["--engine", "python"]
        try:
            _, out_py = run_command(cmd_py)
            match = latency_pattern.search(out_py)
            lat_py = float(match.group(1)) if match else -1.0
        except subprocess.CalledProcessError as e:
            lat_py = -1.0
            
        # C++
        cmd_cpp = ["python", "nextrace/cli.py"] + shlex.split(args_str) + ["--engine", "cpp"]
        try:
            _, out_cpp = run_command(cmd_cpp)
            match = latency_pattern.search(out_cpp)
            lat_cpp = float(match.group(1)) if match else -1.0
        except subprocess.CalledProcessError as e:
            lat_cpp = -1.0
            
        speedup = lat_py / lat_cpp if lat_cpp > 0 and lat_py > 0 else 0.0
        results.append((name, lat_py, lat_cpp, speedup))
        
    print("\n" + "="*60)
    print("BENCHMARK SUMMARY")
    print("="*60)
    print(f"Ingestion Throughput: {ingest_throughput:.2f} logs/sec")
    print(f"Indexing Throughput:  {index_throughput:.2f} logs/sec")
    print(f"Index Size:           {db_size_mb:.2f} MB")
    print(f"Terms Count:          {terms_count:,}")
    print(f"PostingList Count:    {posting_count:,}")
    print("-" * 60)
    print(f"{'Query Type':<25} | {'Python (ms)':<11} | {'C++ (ms)':<10} | {'Speedup':<8}")
    print("-" * 60)
    for name, py_lat, cpp_lat, speedup in results:
        py_str = f"{py_lat:.2f}" if py_lat >= 0 else "Error"
        cpp_str = f"{cpp_lat:.2f}" if cpp_lat >= 0 else "Error"
        speedup_str = f"{speedup:.1f}x" if speedup > 0 else "N/A"
        print(f"{name:<25} | {py_str:<11} | {cpp_str:<10} | {speedup_str:<8}")
        
if __name__ == "__main__":
    main()

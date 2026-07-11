# NexTrace

NexTrace is a real-time log analytics platform with an ingestion pipeline, inverted-index search engine, and CLI. This project runs entirely locally and offline, requiring no external APIs or cloud services.

## Setup Instructions

To recreate this development environment from scratch:

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd nextrace
   ```

2. **Set up the Python Virtual Environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
   *Note:* Python 3.10+ is required. If `venv` creation fails (e.g., on Ubuntu/Debian), you may need to install the venv package first: `sudo apt install python3-venv`. If pip install fails due to network restrictions, ensure you have proxy settings configured properly or pip is allowed network access.

3. **Build the C++ Search Engine Skeleton:**
   ```bash
   mkdir -p build
   cd build
   cmake ..
   make
   ```
   *Note:* Requires a C++17 compatible compiler (`g++` version 7+) and `cmake`. To install on Debian/Ubuntu, run `sudo apt install build-essential cmake`. For macOS, you can use `xcode-select --install` or `brew install cmake`.

## Architecture: Hybrid Python & C++ Search Engine

NexTrace features a two-engine search architecture designed for both correctness and high performance:

1. **Python Reference Implementation (`--engine python`)**: Provides a highly readable, correctness-first implementation used as the baseline for logic and functionality.
2. **C++ Performance Port (`--engine cpp`)**: A standalone C++ binary (`nextrace_search`) that reimplements the posting-list retrieval, set operations, and SQL filtering using the SQLite C API. It communicates with the Python CLI via JSON. It yields significantly lower query latencies, especially for large dataset set-intersections.

The test suite (`tests/test_cpp_search_parity.py`) enforces strict parity between both engines to guarantee the C++ performance port never deviates from the reference implementation's correctness.

## C++ Search Engine Build & Setup

To use the C++ search engine:

1. **Install SQLite3 Development Headers:**
   - Debian/Ubuntu: `sudo apt install libsqlite3-dev`
   - macOS: Built-in, or install via `brew install sqlite`
   - Windows: Use `vcpkg install sqlite3:x64-windows`

2. **Build the C++ Binary:**
   ```bash
   cd nextrace
   mkdir -p build
   cd build
   cmake -DCMAKE_BUILD_TYPE=Release ..
   make -j4
   ```
   *Verification:* `ldd build/nextrace_search` (or `otool -L` on macOS) confirms the binary only links to SQLite3 and the C++ standard library. There is no Python runtime dependency.

## CLI Usage

Use the `--engine` flag to switch between the Python and C++ implementations (defaults to Python):

```bash
python cli.py search "error AND timeout" --level ERROR --limit 10 --engine cpp
```

## Benchmarks

Run the benchmark suite to generate a 1-million line synthetic log dataset, run the indexing pipeline, and compare the latencies between the Python and C++ search engines:

```bash
python benchmark.py
```

**Results (1 Million Logs)**
The C++ engine provides massive performance gains (up to 500x speedup) on complex intersections by avoiding Python's object overhead during large set operations, bringing query latencies down from ~1.7 seconds to ~3-4 milliseconds.

```text
============================================================
BENCHMARK SUMMARY
============================================================
Ingestion Throughput: 39650.35 logs/sec
Indexing Throughput:  1188.57 logs/sec
Index Size:           418.75 MB
------------------------------------------------------------
Query Type                | Python (ms) | C++ (ms)   | Speedup 
------------------------------------------------------------
Single term common        | 1265.82     | 4.67       | 271.1x  
Single term rare          | 1.16        | 3.21       | 0.4x    
AND two terms             | 1702.18     | 3.00       | 567.4x  
OR two terms              | 1.07        | 2.75       | 0.4x    
Time filtered             | 1409.76     | 3.06       | 460.7x  
```

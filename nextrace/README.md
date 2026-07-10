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

## Environment Notes
- **No API keys or external services:** This project is completely standalone. It does not require any cloud credentials or external API integrations.
- **SQLite3:** Relies on SQLite3 with WAL mode for concurrent access, which is available in all modern Python and SQLite3 distributions (version 3.7.0+).

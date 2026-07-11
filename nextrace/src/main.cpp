#include <iostream>
#include <vector>
#include <string>
#include <chrono>
#include <sqlite3.h>
#include "query_parser.hpp"
#include "posting_list.hpp"
#include "filters.hpp"

void print_usage() {
    std::cerr << "Usage: nextrace_search <query> [--since <time>] [--until <time>] [--source <source>] [--level <level>] [--limit <limit>] [--offset <offset>] [--db <db_path>] [--json]\n";
}

// Very basic JSON escaping
std::string escape_json(const std::string& s) {
    std::string res;
    for (char c : s) {
        if (c == '"') res += "\\\"";
        else if (c == '\\') res += "\\\\";
        else if (c == '\b') res += "\\b";
        else if (c == '\f') res += "\\f";
        else if (c == '\n') res += "\\n";
        else if (c == '\r') res += "\\r";
        else if (c == '\t') res += "\\t";
        else res += c;
    }
    return res;
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        print_usage();
        return 1;
    }

    std::string query_str;
    FilterParams params;
    std::string db_path = "nextrace.db";
    bool json_output = false;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--since" && i + 1 < argc) params.since = argv[++i];
        else if (arg == "--until" && i + 1 < argc) params.until = argv[++i];
        else if (arg == "--source" && i + 1 < argc) params.source = argv[++i];
        else if (arg == "--level" && i + 1 < argc) params.level = argv[++i];
        else if (arg == "--limit" && i + 1 < argc) {
            try { params.limit = std::stoi(argv[++i]); }
            catch (...) { std::cerr << "Invalid --limit\n"; return 1; }
        }
        else if (arg == "--offset" && i + 1 < argc) {
            try { params.offset = std::stoi(argv[++i]); }
            catch (...) { std::cerr << "Invalid --offset\n"; return 1; }
        }
        else if (arg == "--db" && i + 1 < argc) db_path = argv[++i];
        else if (arg == "--json") json_output = true;
        else if (arg[0] == '-') {
            std::cerr << "Unknown argument: " << arg << "\n";
            print_usage();
            return 1;
        } else {
            if (!query_str.empty()) {
                std::cerr << "Multiple queries provided. Enclose query in quotes.\n";
                return 1;
            }
            query_str = arg;
        }
    }

    if (query_str.empty()) {
        std::cerr << "Missing query string\n";
        print_usage();
        return 1;
    }

    auto start_time = std::chrono::high_resolution_clock::now();

    ParsedQuery parsed = parse_query(query_str);
    if (parsed.error) {
        std::cerr << "Query Error: " << *parsed.error << "\n";
        return 1;
    }

    sqlite3* db = nullptr;
    if (sqlite3_open_v2(db_path.c_str(), &db, SQLITE_OPEN_READONLY, nullptr) != SQLITE_OK) {
        std::cerr << "Error: Database file '" << db_path << "' not found or cannot be opened.\n";
        if (db) sqlite3_close(db);
        return 1;
    }

    sqlite3_busy_timeout(db, 1000); // 1000ms timeout for busy DB

    auto log_ids = execute_search(parsed, db);
    FilterResult res = apply_filters(db, log_ids, params);

    sqlite3_close(db);

    if (res.error) {
        std::cerr << "Filter Error: " << *res.error << "\n";
        return 1;
    }

    auto end_time = std::chrono::high_resolution_clock::now();
    double latency_ms = std::chrono::duration<double, std::milli>(end_time - start_time).count();

    if (json_output) {
        std::cout << "{\n";
        std::cout << "  \"latency_ms\": " << latency_ms << ",\n";
        std::cout << "  \"total_count\": " << res.total_count << ",\n";
        std::cout << "  \"results\": [\n";
        for (size_t i = 0; i < res.records.size(); ++i) {
            const auto& r = res.records[i];
            std::cout << "    {\n";
            std::cout << "      \"timestamp\": \"" << escape_json(r.timestamp) << "\",\n";
            std::cout << "      \"level\": \"" << escape_json(r.level) << "\",\n";
            std::cout << "      \"source\": \"" << escape_json(r.source) << "\",\n";
            std::cout << "      \"raw_message\": \"" << escape_json(r.raw_message) << "\"\n";
            std::cout << "    }" << (i + 1 < res.records.size() ? "," : "") << "\n";
        }
        std::cout << "  ]\n";
        std::cout << "}\n";
    } else {
        if (res.records.empty()) {
            std::cout << "No matches found.\n";
            std::cout << "\nFound 0 matches in " << latency_ms << " ms\n";
        } else {
            for (const auto& r : res.records) {
                std::cout << "[" << r.timestamp << "] [" << r.level << "] [" << r.source << "] " << r.raw_message << "\n";
            }
            std::cout << "\nFound " << res.total_count << " matches (showing limit " << params.limit << ") in " << latency_ms << " ms\n";
        }
    }

    return 0;
}

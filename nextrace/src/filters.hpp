#ifndef FILTERS_HPP
#define FILTERS_HPP

#include <string>
#include <vector>
#include <unordered_set>
#include <optional>
#include <sqlite3.h>

struct FilterParams {
    std::optional<std::string> since;
    std::optional<std::string> until;
    std::optional<std::string> source;
    std::optional<std::string> level;
    int limit = 100;
    int offset = 0;
};

struct LogRecord {
    int64_t id;
    std::string timestamp;
    std::string source;
    std::string level;
    std::string raw_message;
};

struct FilterResult {
    std::vector<LogRecord> records;
    int total_count = 0;
    std::optional<std::string> error;
};

FilterResult apply_filters(sqlite3* db, const std::unordered_set<int64_t>& log_ids, const FilterParams& filters);

#endif // FILTERS_HPP

#include "filters.hpp"
#include "posting_list.hpp" // For SQLiteStmt
#include <sstream>
#include <iomanip>
#include <algorithm>

static bool validate_date(const std::string& date_str) {
    std::tm t = {};
    std::istringstream ss(date_str);
    if (date_str.find('T') != std::string::npos) {
        ss >> std::get_time(&t, "%Y-%m-%dT%H:%M:%S");
    } else {
        ss >> std::get_time(&t, "%Y-%m-%d");
    }
    return !ss.fail() && ss.eof();
}

FilterResult apply_filters(sqlite3* db, const std::unordered_set<int64_t>& log_ids, const FilterParams& filters) {
    FilterResult res;
    if (log_ids.empty()) {
        return res;
    }

    if (filters.since && filters.until && *filters.since > *filters.until) {
        // returning empty result, not an error
        return res;
    }

    if (filters.since && !validate_date(*filters.since)) {
        res.error = "Malformed date format: " + *filters.since;
        return res;
    }
    if (filters.until && !validate_date(*filters.until)) {
        res.error = "Malformed date format: " + *filters.until;
        return res;
    }

    std::vector<int64_t> ids(log_ids.begin(), log_ids.end());
    const int chunk_size = 900; // safe under SQLite's parameter limit
    int num_chunks = (ids.size() + chunk_size - 1) / chunk_size;

    std::vector<LogRecord> all_chunk_results;

    for (int i = 0; i < num_chunks; ++i) {
        int start = i * chunk_size;
        int end = std::min((int)ids.size(), start + chunk_size);
        int current_chunk_size = end - start;

        std::string in_clause = "(";
        for (int j = 0; j < current_chunk_size; ++j) {
            in_clause += (j == 0 ? "?" : ",?");
        }
        in_clause += ")";

        std::string base_cond = " WHERE id IN " + in_clause;
        
        if (filters.since) base_cond += " AND timestamp >= ?";
        if (filters.until) base_cond += " AND timestamp <= ?";
        if (filters.source) base_cond += " AND source = ?";
        if (filters.level) base_cond += " AND level = ?";

        // Count query
        std::string count_sql = "SELECT COUNT(*) FROM Logs" + base_cond;
        sqlite3_stmt* count_stmt_ptr = nullptr;
        if (sqlite3_prepare_v2(db, count_sql.c_str(), -1, &count_stmt_ptr, nullptr) != SQLITE_OK) {
            res.error = "Database Error: Failed to prepare count statement";
            return res;
        }
        SQLiteStmt count_stmt(count_stmt_ptr);

        // CRITICAL: We use sqlite3_bind_* parameterized binding for every value 
        // (log_ids, since, until, source, level) — never string-concatenate user input into SQL. 
        // This is the injection-prevention boundary, matching the Python parameterized-query approach.
        int bind_idx = 1;
        for (int j = 0; j < current_chunk_size; ++j) {
            sqlite3_bind_int64(count_stmt, bind_idx++, ids[start + j]);
        }
        if (filters.since) sqlite3_bind_text(count_stmt, bind_idx++, filters.since->c_str(), -1, SQLITE_TRANSIENT);
        if (filters.until) sqlite3_bind_text(count_stmt, bind_idx++, filters.until->c_str(), -1, SQLITE_TRANSIENT);
        if (filters.source) sqlite3_bind_text(count_stmt, bind_idx++, filters.source->c_str(), -1, SQLITE_TRANSIENT);
        if (filters.level) sqlite3_bind_text(count_stmt, bind_idx++, filters.level->c_str(), -1, SQLITE_TRANSIENT);

        if (sqlite3_step(count_stmt) == SQLITE_ROW) {
            res.total_count += sqlite3_column_int(count_stmt, 0);
        }

        // Select query
        std::string select_sql = "SELECT id, timestamp, source, level, raw_message FROM Logs" + base_cond + " ORDER BY timestamp DESC, id ASC LIMIT ?";
        sqlite3_stmt* select_stmt_ptr = nullptr;
        if (sqlite3_prepare_v2(db, select_sql.c_str(), -1, &select_stmt_ptr, nullptr) != SQLITE_OK) {
            res.error = "Database Error: Failed to prepare select statement";
            return res;
        }
        SQLiteStmt select_stmt(select_stmt_ptr);

        bind_idx = 1;
        for (int j = 0; j < current_chunk_size; ++j) {
            sqlite3_bind_int64(select_stmt, bind_idx++, ids[start + j]);
        }
        if (filters.since) sqlite3_bind_text(select_stmt, bind_idx++, filters.since->c_str(), -1, SQLITE_TRANSIENT);
        if (filters.until) sqlite3_bind_text(select_stmt, bind_idx++, filters.until->c_str(), -1, SQLITE_TRANSIENT);
        if (filters.source) sqlite3_bind_text(select_stmt, bind_idx++, filters.source->c_str(), -1, SQLITE_TRANSIENT);
        if (filters.level) sqlite3_bind_text(select_stmt, bind_idx++, filters.level->c_str(), -1, SQLITE_TRANSIENT);
        
        sqlite3_bind_int(select_stmt, bind_idx++, filters.limit + filters.offset);

        while (sqlite3_step(select_stmt) == SQLITE_ROW) {
            LogRecord rec;
            rec.id = sqlite3_column_int64(select_stmt, 0);
            rec.timestamp = reinterpret_cast<const char*>(sqlite3_column_text(select_stmt, 1));
            rec.source = reinterpret_cast<const char*>(sqlite3_column_text(select_stmt, 2));
            rec.level = reinterpret_cast<const char*>(sqlite3_column_text(select_stmt, 3));
            rec.raw_message = reinterpret_cast<const char*>(sqlite3_column_text(select_stmt, 4));
            all_chunk_results.push_back(std::move(rec));
        }
    }

    // Merge and apply global offset and limit
    std::sort(all_chunk_results.begin(), all_chunk_results.end(), [](const LogRecord& a, const LogRecord& b) {
        if (a.timestamp != b.timestamp) {
            return a.timestamp > b.timestamp;
        }
        return a.id < b.id; // tie breaker: id ASC to match SQLite implicit rowid order
    });

    if (filters.offset >= all_chunk_results.size()) {
        res.records = {};
    } else {
        auto start_it = all_chunk_results.begin() + filters.offset;
        auto end_it = all_chunk_results.begin() + std::min(all_chunk_results.size(), (size_t)(filters.offset + filters.limit));
        res.records = std::vector<LogRecord>(start_it, end_it);
    }

    return res;
}

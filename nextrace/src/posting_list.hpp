#ifndef POSTING_LIST_HPP
#define POSTING_LIST_HPP

#include <string>
#include <vector>
#include <unordered_set>
#include <optional>
#include <sqlite3.h>
#include "query_parser.hpp"

// Utility class for RAII of SQLite statements
class SQLiteStmt {
public:
    sqlite3_stmt* stmt;
    SQLiteStmt(sqlite3_stmt* s = nullptr) : stmt(s) {}
    ~SQLiteStmt() {
        if (stmt) {
            sqlite3_finalize(stmt);
        }
    }
    sqlite3_stmt* operator*() const { return stmt; }
    operator sqlite3_stmt*() const { return stmt; }
};

std::optional<int64_t> get_term_id(sqlite3* db, const std::string& token);
std::unordered_set<int64_t> get_posting_list(sqlite3* db, int64_t term_id);

std::unordered_set<int64_t> intersect_sets(std::vector<std::unordered_set<int64_t>> sets);
std::unordered_set<int64_t> union_sets(const std::vector<std::unordered_set<int64_t>>& sets);

std::unordered_set<int64_t> execute_search(const ParsedQuery& query, sqlite3* db);

#endif // POSTING_LIST_HPP

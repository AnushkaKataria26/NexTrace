#include "posting_list.hpp"
#include <algorithm>
#include <iostream>

std::optional<int64_t> get_term_id(sqlite3* db, const std::string& token) {
    const char* sql = "SELECT term_id FROM Terms WHERE token = ?";
    sqlite3_stmt* stmt_ptr = nullptr;
    if (sqlite3_prepare_v2(db, sql, -1, &stmt_ptr, nullptr) != SQLITE_OK) {
        return std::nullopt;
    }
    SQLiteStmt stmt(stmt_ptr);

    sqlite3_bind_text(stmt, 1, token.c_str(), -1, SQLITE_TRANSIENT);

    if (sqlite3_step(stmt) == SQLITE_ROW) {
        return sqlite3_column_int64(stmt, 0);
    }
    return std::nullopt;
}

std::unordered_set<int64_t> get_posting_list(sqlite3* db, int64_t term_id) {
    std::unordered_set<int64_t> result;
    const char* sql = "SELECT log_id FROM PostingList WHERE term_id = ?";
    sqlite3_stmt* stmt_ptr = nullptr;
    if (sqlite3_prepare_v2(db, sql, -1, &stmt_ptr, nullptr) != SQLITE_OK) {
        return result;
    }
    SQLiteStmt stmt(stmt_ptr);

    sqlite3_bind_int64(stmt, 1, term_id);

    while (sqlite3_step(stmt) == SQLITE_ROW) {
        result.insert(sqlite3_column_int64(stmt, 0));
    }
    return result;
}

std::unordered_set<int64_t> intersect_sets(std::vector<std::unordered_set<int64_t>> sets) {
    if (sets.empty()) return {};

    for (const auto& s : sets) {
        if (s.empty()) return {};
    }

    std::sort(sets.begin(), sets.end(), [](const auto& a, const auto& b) {
        return a.size() < b.size();
    });

    std::unordered_set<int64_t> result = sets[0];
    for (size_t i = 1; i < sets.size(); ++i) {
        std::unordered_set<int64_t> next_result;
        for (auto val : result) {
            if (sets[i].find(val) != sets[i].end()) {
                next_result.insert(val);
            }
        }
        result = std::move(next_result);
        if (result.empty()) break;
    }

    return result;
}

std::unordered_set<int64_t> union_sets(const std::vector<std::unordered_set<int64_t>>& sets) {
    std::unordered_set<int64_t> result;
    for (const auto& s : sets) {
        for (auto val : s) {
            result.insert(val);
        }
    }
    return result;
}

std::unordered_set<int64_t> execute_search(const ParsedQuery& query, sqlite3* db) {
    if (query.terms.empty()) {
        return {};
    }

    std::vector<std::unordered_set<int64_t>> posting_lists;

    if (query.op == Operator::AND || query.op == Operator::NONE) {
        for (const auto& term : query.terms) {
            auto term_id = get_term_id(db, term);
            if (!term_id) {
                return {}; // Term never indexed -> empty result for AND
            }
            auto plist = get_posting_list(db, *term_id);
            if (plist.empty()) {
                return {};
            }
            posting_lists.push_back(std::move(plist));
        }
        return intersect_sets(std::move(posting_lists));
    } else if (query.op == Operator::OR) {
        for (const auto& term : query.terms) {
            auto term_id = get_term_id(db, term);
            if (term_id) {
                auto plist = get_posting_list(db, *term_id);
                posting_lists.push_back(std::move(plist));
            }
        }
        return union_sets(posting_lists);
    }

    return {};
}

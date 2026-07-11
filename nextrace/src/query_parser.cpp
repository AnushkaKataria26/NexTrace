#include "query_parser.hpp"
#include <sstream>
#include <algorithm>
#include <cctype>
#include <regex>
#include <iostream>

static std::vector<std::string> shlex_split(const std::string& s, std::optional<std::string>& error) {
    std::vector<std::string> tokens;
    bool in_quotes = false;
    std::string current_token;
    
    for (size_t i = 0; i < s.length(); ++i) {
        char c = s[i];
        if (c == '"' || c == '\'') {
            if (in_quotes) {
                in_quotes = false;
            } else {
                in_quotes = true;
            }
        } else if (std::isspace(c) && !in_quotes) {
            if (!current_token.empty()) {
                tokens.push_back(current_token);
                current_token.clear();
            }
        } else {
            current_token += c;
        }
    }
    
    if (in_quotes) {
        error = "No closing quotation";
    }
    if (!current_token.empty()) {
        tokens.push_back(current_token);
    }
    
    return tokens;
}

ParsedQuery parse_query(const std::string& query_str) {
    ParsedQuery res;
    res.raw_query = query_str;
    res.op = Operator::NONE;

    if (query_str.empty() || std::all_of(query_str.begin(), query_str.end(), [](unsigned char c){ return std::isspace(c); })) {
        res.error = "Query string cannot be empty.";
        return res;
    }

    std::optional<std::string> split_error;
    std::vector<std::string> raw_parts = shlex_split(query_str, split_error);
    if (split_error) {
        res.error = "Malformed query: " + *split_error;
        return res;
    }

    if (raw_parts.empty()) {
        res.error = "Query string cannot be empty.";
        return res;
    }

    std::regex token_pattern(R"(\w+)");
    bool expected_operator = false;
    bool has_operator = false;

    for (size_t i = 0; i < raw_parts.size(); ++i) {
        std::string part = raw_parts[i];
        std::string part_upper = part;
        std::transform(part_upper.begin(), part_upper.end(), part_upper.begin(), ::toupper);

        if (part_upper == "AND" || part_upper == "OR") {
            if (!expected_operator) {
                if (i == 0) {
                    res.error = "Malformed query: invalid operator placement '" + part + "'.";
                    return res;
                } else {
                    res.error = "Malformed query: consecutive operators.";
                    return res;
                }
            }

            Operator current_op = (part_upper == "AND") ? Operator::AND : Operator::OR;
            if (!has_operator) {
                res.op = current_op;
                has_operator = true;
            } else if (res.op != current_op) {
                res.error = "Mixed AND/OR queries are not supported in this phase.";
                return res;
            }

            expected_operator = false;
        } else {
            if (expected_operator) {
                res.error = "Malformed query: missing operator between terms.";
                return res;
            }

            std::string part_lower = part;
            std::transform(part_lower.begin(), part_lower.end(), part_lower.begin(), ::tolower);

            auto words_begin = std::sregex_iterator(part_lower.begin(), part_lower.end(), token_pattern);
            auto words_end = std::sregex_iterator();

            for (std::sregex_iterator k = words_begin; k != words_end; ++k) {
                std::string pt = k->str();
                if (pt.length() >= 2 || std::all_of(pt.begin(), pt.end(), ::isdigit)) {
                    res.terms.push_back(pt);
                }
            }

            expected_operator = true;
        }
    }

    if (!expected_operator) {
        res.error = "Malformed query: trailing operator.";
        return res;
    }

    if (res.terms.empty()) {
        res.error = "Query string contains no valid terms.";
        return res;
    }

    if (res.terms.size() > 1 && !has_operator) {
        res.op = Operator::AND;
    }

    // Deduplicate terms while preserving order
    std::vector<std::string> unique_terms;
    for (const auto& t : res.terms) {
        if (std::find(unique_terms.begin(), unique_terms.end(), t) == unique_terms.end()) {
            unique_terms.push_back(t);
        }
    }
    res.terms = unique_terms;

    return res;
}

#ifndef QUERY_PARSER_HPP
#define QUERY_PARSER_HPP

#include <string>
#include <vector>
#include <optional>

enum class Operator {
    AND,
    OR,
    NONE
};

struct ParsedQuery {
    std::vector<std::string> terms;
    Operator op;
    std::string raw_query;
    std::optional<std::string> error; // If set, parsing failed
};

ParsedQuery parse_query(const std::string& query_str);

#endif // QUERY_PARSER_HPP

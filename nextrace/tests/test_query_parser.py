import pytest
from nextrace.query_parser import parse_query

def test_single_term():
    res = parse_query("error")
    assert res["terms"] == ["error"]
    assert res["operator"] is None

def test_multi_term_and():
    res = parse_query("error AND timeout")
    assert res["terms"] == ["error", "timeout"]
    assert res["operator"] == "AND"

def test_multi_term_or():
    res = parse_query("error OR warning")
    assert res["terms"] == ["error", "warning"]
    assert res["operator"] == "OR"
    
def test_case_insensitivity_of_operators():
    res = parse_query("error and timeout")
    assert res["terms"] == ["error", "timeout"]
    assert res["operator"] == "AND"
    
    res = parse_query("error Or warning")
    assert res["terms"] == ["error", "warning"]
    assert res["operator"] == "OR"

def test_quoted_phrase():
    res = parse_query('"connection timeout"')
    assert res["terms"] == ["connection", "timeout"]
    assert res["operator"] == "AND"

def test_quoted_phrase_with_operator():
    res = parse_query('error AND "connection timeout"')
    assert res["terms"] == ["error", "connection", "timeout"]
    assert res["operator"] == "AND"
    
def test_mixed_and_or_rejected():
    with pytest.raises(ValueError, match="Mixed AND/OR queries are not supported"):
        parse_query("error AND warning OR timeout")

def test_leading_trailing_operator_rejected():
    with pytest.raises(ValueError, match="invalid operator placement"):
        parse_query("AND error")
    with pytest.raises(ValueError, match="trailing operator"):
        parse_query("error AND")

def test_consecutive_operators_rejected():
    with pytest.raises(ValueError, match="consecutive operators"):
        parse_query("error AND AND timeout")

def test_missing_operator_between_terms_rejected():
    with pytest.raises(ValueError, match="missing operator between terms"):
        parse_query("error timeout")
        
def test_empty_query_rejected():
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_query("")
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_query("   ")

def test_no_valid_terms_rejected():
    with pytest.raises(ValueError, match="contains no valid terms"):
        parse_query('"!" AND "?"')

def test_hyphenated_term():
    res = parse_query("api-gateway AND error")
    assert res["terms"] == ["api", "gateway", "error"]
    assert res["operator"] == "AND"

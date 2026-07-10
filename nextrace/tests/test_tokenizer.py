import time
import pytest
from nextrace.tokenizer import tokenize

def test_basic_tokenization():
    text = "Hello World! This is a TEST."
    tokens = tokenize(text)
    # Note: "is" and "a" should be filtered out because len < 2 for "a", 
    # but wait, "is" has len 2. Since filter_stopwords is False by default, "is" should stay.
    # "a" is length 1 and not numeric, so it should be dropped.
    assert set(tokens) == {"hello", "world", "this", "is", "test"}

def test_numeric_token_retention():
    text = "Error code 0 and status 1"
    tokens = tokenize(text)
    assert "0" in tokens
    assert "1" in tokens
    assert set(tokens) == {"error", "code", "0", "and", "status", "1"}

def test_stopword_filtering():
    text = "the quick brown fox and a dog"
    
    # Default (no filtering)
    tokens_no_filter = set(tokenize(text))
    assert "the" in tokens_no_filter
    assert "and" in tokens_no_filter
    
    # With filtering
    tokens_filtered = set(tokenize(text, filter_stopwords=True))
    assert "the" not in tokens_filtered
    assert "and" not in tokens_filtered
    assert "quick" in tokens_filtered
    assert "brown" in tokens_filtered
    assert "fox" in tokens_filtered
    assert "dog" in tokens_filtered

def test_empty_and_whitespace_input():
    assert tokenize("") == []
    assert tokenize("   \t\n  ") == []
    assert tokenize("!@#$%^&*()") == []

def test_json_fragment_input():
    text = '{"user_id": 123, "status": "failed"}'
    tokens = set(tokenize(text))
    assert tokens == {"user_id", "123", "status", "failed"}

def test_unicode_input():
    text = "Error in café サーバー returned 500"
    tokens = set(tokenize(text))
    # Unicode words should be extracted correctly
    assert tokens == {"error", "in", "café", "サーバー", "returned", "500"}

def test_long_string_performance():
    # Construct a 100KB+ string
    text = "log_entry " * 10000
    
    start_time = time.time()
    tokens = tokenize(text)
    end_time = time.time()
    
    # Should be extremely fast (way less than 1 second)
    assert end_time - start_time < 1.0
    assert set(tokens) == {"log_entry"}
    
    # Adversarial test (lots of punctuation)
    adversarial_text = "!@#$%^&*() " * 10000 + "token"
    start_time = time.time()
    tokens = tokenize(adversarial_text)
    end_time = time.time()
    
    assert end_time - start_time < 1.0
    assert set(tokens) == {"token"}

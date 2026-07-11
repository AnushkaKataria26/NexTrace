import shlex
import re

TOKEN_PATTERN = re.compile(r"\w+")

def parse_query(query_str: str) -> dict:
    """
    Parses a query string into a structured dictionary.
    
    Syntax supported:
    - Single term: `error`
    - Multi-term AND: `error AND timeout`
    - Multi-term OR: `error OR warning`
    
    Simplifications:
    - Quoted phrases (e.g., `"connection timeout"`) are tokenized into their constituent words. 
      If the query lacks an overarching operator, these words are treated as an implicit AND.
      However, if the overarching query uses OR (e.g., `error OR "connection timeout"`), 
      the constituent words are treated as part of the overarching OR query (i.e., `error OR connection OR timeout`),
      because mixed AND/OR operations are not supported in this phase.
    """
    if not query_str or not query_str.strip():
        raise ValueError("Query string cannot be empty.")
    
    try:
        raw_parts = shlex.split(query_str)
    except ValueError as e:
        raise ValueError(f"Malformed query: {e}")
        
    if not raw_parts:
        raise ValueError("Query string cannot be empty.")
        
    operator = None
    terms = []
    
    expected_operator = False
    
    for i, part in enumerate(raw_parts):
        part_upper = part.upper()
        if part_upper in ("AND", "OR"):
            if not expected_operator:
                if i == 0:
                    raise ValueError(f"Malformed query: invalid operator placement '{part}'.")
                else:
                    raise ValueError("Malformed query: consecutive operators.")
            
            if operator is None:
                operator = part_upper
            elif operator != part_upper:
                raise ValueError("Mixed AND/OR queries are not supported in this phase.")
            
            expected_operator = False
        else:
            if expected_operator:
                raise ValueError("Malformed query: missing operator between terms.")
            
            # Normalize and extract terms identical to tokenizer.py
            part_terms = TOKEN_PATTERN.findall(part.lower())
            for pt in part_terms:
                if len(pt) >= 2 or pt.isnumeric():
                    terms.append(pt)
            
            expected_operator = True
            
    if not expected_operator:
        raise ValueError("Malformed query: trailing operator.")
        
    if not terms:
        raise ValueError("Query string contains no valid terms.")
        
    # Default to AND if there are multiple terms but no operator was parsed
    # (e.g. a single quoted phrase with multiple words: `"connection timeout"`)
    if len(terms) > 1 and operator is None:
        operator = "AND"
        
    # Deduplicate terms while preserving order
    unique_terms = []
    for t in terms:
        if t not in unique_terms:
            unique_terms.append(t)
            
    return {
        "terms": unique_terms,
        "operator": operator,
        "raw_query": query_str
    }

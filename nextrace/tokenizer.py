import re

# Default stopwords list for log search, optional as log searches often want exact matches
DEFAULT_STOPWORDS = {"the", "and", "is", "at", "to", "a", "an", "of", "in", "on", "for"}

# re.UNICODE is default in Python 3, \w+ extracts alphanumeric sequences + underscores
# Using \w+ avoids catastrophic backtracking because it is simply a greedy match of a character class.
TOKEN_PATTERN = re.compile(r"\w+")

def tokenize(text: str, filter_stopwords: bool = False) -> list[str]:
    """
    Tokenizes a log message into a deduplicated list of terms.
    
    Args:
        text (str): The raw log message to tokenize.
        filter_stopwords (bool): Whether to filter out common English stopwords. 
                                 Default is False because log search typically 
                                 needs exact term matching, not NLP-style search.
                                 
    Returns:
        list[str]: A deduplicated list of tokens.
    """
    if not text:
        return []
        
    text = text.lower()
    
    # re.findall with \w+ extracts contiguous alphanumeric/underscore sequences.
    raw_tokens = TOKEN_PATTERN.findall(text)
    
    unique_tokens = set()
    
    for token in raw_tokens:
        # Keep numeric tokens even if single-character (e.g. "0", "1")
        if len(token) < 2 and not token.isnumeric():
            continue
            
        if filter_stopwords and token in DEFAULT_STOPWORDS:
            continue
            
        unique_tokens.add(token)
        
    return list(unique_tokens)

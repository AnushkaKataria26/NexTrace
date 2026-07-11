import sys
import datetime

def get_term_id(token: str, cursor) -> int | None:
    cursor.execute("SELECT term_id FROM Terms WHERE token = ?", (token,))
    row = cursor.fetchone()
    if row:
        return row[0]
    return None


def get_posting_list(term_id: int, cursor) -> set[int]:
    if term_id is None:
        return set()
    cursor.execute("SELECT log_id FROM PostingList WHERE term_id = ?", (term_id,))
    return {row[0] for row in cursor.fetchall()}


def intersect_posting_lists(sets: list[set[int]]) -> set[int]:
    if not sets:
        return set()
    
    # Optimize: sort sets by size ascending
    sets.sort(key=len)
    
    result = sets[0].copy()
    for s in sets[1:]:
        result.intersection_update(s)
        # Short-circuit if intersection becomes empty
        if not result:
            break
            
    return result


def execute_search(parsed_query: dict, cursor) -> set[int]:
    terms = parsed_query.get("terms", [])
    operator = parsed_query.get("operator")
    
    if not terms:
        return set()
        
    posting_lists = []
    
    if operator == "AND" or operator is None:
        # Default to AND for single terms or when operator is None
        for term in terms:
            term_id = get_term_id(term, cursor)
            if term_id is None:
                # Term never indexed -> empty result for AND
                return set()
            plist = get_posting_list(term_id, cursor)
            if not plist:
                return set()
            posting_lists.append(plist)
            
        return intersect_posting_lists(posting_lists)
        
    elif operator == "OR":
        result = set()
        for term in terms:
            term_id = get_term_id(term, cursor)
            if term_id is not None:
                plist = get_posting_list(term_id, cursor)
                result.update(plist)
        return result
        
    return set()


def validate_date(date_str: str):
    try:
        if "T" in date_str:
            datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
        else:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Malformed date format: {date_str}")


def apply_filters(
    log_ids: set[int], 
    since: str | None, 
    until: str | None, 
    source: str | None, 
    level: str | None, 
    cursor,
    limit: int = 100,
    offset: int = 0
) -> tuple[list[dict], int]:
    if not log_ids:
        return [], 0
        
    if since and until and since > until:
        print("Warning: 'since' > 'until' results in contradictory range.", file=sys.stderr)
        return [], 0

    # Use a temporary table to handle potentially huge IN clauses safely,
    # and to easily JOIN with Logs table for filtering and sorting.
    cursor.execute("CREATE TEMP TABLE IF NOT EXISTS temp_search_ids (log_id INTEGER PRIMARY KEY)")
    cursor.execute("DELETE FROM temp_search_ids")
    
    try:
        cursor.executemany("INSERT INTO temp_search_ids (log_id) VALUES (?)", [(i,) for i in log_ids])
        
        query = """
            SELECT timestamp, level, source, raw_message 
            FROM Logs 
            JOIN temp_search_ids ON Logs.id = temp_search_ids.log_id
            WHERE 1=1
        """
        params = []
        
        if since:
            validate_date(since)
            query += " AND timestamp >= ?"
            params.append(since)
            
        if until:
            validate_date(until)
            query += " AND timestamp <= ?"
            params.append(until)
            
        if source:
            query += " AND source = ?"
            params.append(source)
            
        if level:
            query += " AND level = ?"
            params.append(level)
            
        # Get total count before limit
        count_query = query.replace("SELECT timestamp, level, source, raw_message", "SELECT COUNT(*)", 1)
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]
            
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                "timestamp": row[0],
                "level": row[1],
                "source": row[2],
                "raw_message": row[3]
            })
        return results, total_count
        
    finally:
        # Clean up
        cursor.execute("DROP TABLE temp_search_ids")

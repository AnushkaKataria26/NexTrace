import sqlite3

conn = sqlite3.connect('nextrace/nextrace.db')
cursor = conn.cursor()

token = 'timeout'

cursor.execute("""
SELECT log_id FROM PostingList 
JOIN Terms USING(term_id) 
WHERE token = ? ORDER BY log_id
""", (token,))
indexed_ids = set([row[0] for row in cursor.fetchall()])

cursor.execute("""
SELECT id, raw_message FROM Logs
""")
like_ids = set()
for row in cursor.fetchall():
    # A simple regex to emulate the tokenizer finding 'timeout' as a whole word
    import re
    if 'timeout' in [t.lower() for t in re.findall(r"\w+", row[1])]:
        like_ids.add(row[0])

print(f"Indexed IDs count: {len(indexed_ids)}")
print(f"LIKE IDs count: {len(like_ids)}")
if indexed_ids == like_ids:
    print("Verification SUCCESS: Both sets match exactly.")
else:
    print("Verification FAILED: Sets do not match.")
    print("In indexed but not LIKE:", indexed_ids - like_ids)
    print("In LIKE but not indexed:", like_ids - indexed_ids)

conn.close()

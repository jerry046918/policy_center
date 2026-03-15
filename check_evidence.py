import sqlite3
import json

conn = sqlite3.connect('data/policy_center.db')
cursor = conn.cursor()

# Check column info
cursor.execute("PRAGMA table_info(review_queue)")
print("Columns:")
for col in cursor.fetchall():
    print(f"  {col[1]}: {col[2]}")

# Get latest review
cursor.execute("""
SELECT review_id, raw_evidence
FROM review_queue
ORDER BY submitted_at DESC
LIMIT 1
""")
row = cursor.fetchone()
if row:
    raw_str = row[0]
    print(f"\nReview ID: {row[0]}")
    print(f"raw_evidence type: {type(raw_str)}")
    print(f"raw_evidence content:\n{raw_str[:500]}")
    print("...")
else:
    print("No reviews found")

conn.close()

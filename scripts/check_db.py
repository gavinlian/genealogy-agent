# -*- coding: utf-8 -*-
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from main import DB_PATH, get_db  # noqa: E402

print("DB_PATH:", DB_PATH)
print("exists:", os.path.exists(DB_PATH))
if os.path.exists(DB_PATH):
    print("size_bytes:", os.path.getsize(DB_PATH))

t = time.time()
conn = sqlite3.connect(DB_PATH, timeout=3)
conn.row_factory = sqlite3.Row
c = conn.cursor()
print("families:", c.execute("SELECT COUNT(*) FROM families").fetchone()[0])
print("persons:", c.execute("SELECT COUNT(*) FROM persons").fetchone()[0])
print("relations:", c.execute("SELECT COUNT(*) FROM relations").fetchone()[0])
has_chat = c.execute(
    "SELECT COUNT(*) FROM sqlite_master WHERE name='family_ai_chat'"
).fetchone()[0]
print("family_ai_chat table:", has_chat)
if has_chat:
    for row in c.execute(
        "SELECT family_id, LENGTH(messages) AS msg_len, LENGTH(pending_plan) AS plan_len FROM family_ai_chat"
    ):
        print(" ai_chat:", dict(row))
conn.close()
print("direct query ok in", round(time.time() - t, 3), "s")

t = time.time()
conn2 = get_db()
rows = conn2.execute(
    """SELECT f.*, COUNT(p.id) as person_count FROM families f
        LEFT JOIN persons p ON p.family_id = f.id GROUP BY f.id ORDER BY f.created_at DESC"""
).fetchall()
conn2.close()
print("get_families query ok, rows:", len(rows), "in", round(time.time() - t, 3), "s")

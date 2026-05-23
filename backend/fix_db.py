import sqlite3
conn = sqlite3.connect('genealogy.db')
c = conn.cursor()

# Check current schema
c.execute('PRAGMA table_info(ai_config)')
print("Before:", c.fetchall())

# Add missing columns
try:
    c.execute('ALTER TABLE ai_config ADD COLUMN api_base TEXT DEFAULT ""')
except Exception as e:
    print("api_base:", e)
try:
    c.execute('ALTER TABLE ai_config ADD COLUMN vision_model TEXT DEFAULT ""')
except Exception as e:
    print("vision_model:", e)

conn.commit()

c.execute('PRAGMA table_info(ai_config)')
print("After:", c.fetchall())
conn.close()
print('done')
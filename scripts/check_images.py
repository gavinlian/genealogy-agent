import json
import os
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "backend", "genealogy.db")
UP = os.path.join(os.path.dirname(__file__), "..", "backend", "uploads")

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
upload_files = set(os.listdir(UP)) if os.path.isdir(UP) else set()
rows = conn.execute(
    "SELECT family_id, version_kind, note FROM family_source_versions WHERE note LIKE '%image:%'"
).fetchall()

missing = []
ok = []
for r in rows:
    note = r["note"] or ""
    img = ""
    for part in note.split("|"):
        if part.strip().startswith("image:"):
            img = part.strip()[6:]
    if not img:
        continue
    entry = {"family_id": r["family_id"], "kind": r["version_kind"], "image": img}
    if img in upload_files:
        ok.append(entry)
    else:
        missing.append(entry)

print(json.dumps({"ok": len(ok), "missing": missing, "orphan_uploads": []}, ensure_ascii=False, indent=2))

# uploads not referenced
referenced = set()
for r in rows:
    for part in (r["note"] or "").split("|"):
        if part.strip().startswith("image:"):
            referenced.add(part.strip()[6:])
orphans = sorted(upload_files - referenced)
print(f"\norphan files ({len(orphans)}):", orphans[:10])

# -*- coding: utf-8 -*-
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"


def main() -> int:
    fams = json.loads(urllib.request.urlopen(f"{BASE}/api/families", timeout=5).read())
    fid = next((f["id"] for f in fams if (f.get("person_count") or 0) == 0), fams[0]["id"])
    body = json.dumps(
        {
            "persist": True,
            "apply_mode": "replace",
            "plan": {
                "explanation": "api test",
                "new_persons": [{"name": "张三"}, {"name": "李四"}],
                "relations_add": [{"from": "张三", "to": "李四", "type": "parent_child"}],
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/families/{fid}/ai-organize",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        print(resp.read().decode("utf-8"))
        return 0
    except urllib.error.HTTPError as exc:
        print("HTTP", exc.code, exc.read().decode("utf-8", errors="replace")[:500])
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Talk to `8bms serve` (stdlib only). Start the server first: 8bms serve --port 8765"""
import json
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"


def post(path, body):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


print(post("/ops/compose", {"prompt": "chase scene", "bars": 8, "seed": 2, "_fields": "handle,score"}))
print(post("/ops/describe", {"src": "@last", "_fields": "summary"}))
print(post("/prompt", {"text": "/gen town 4"}))

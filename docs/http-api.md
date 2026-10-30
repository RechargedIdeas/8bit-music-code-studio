# HTTP API (`8bms serve`)

> **TL;DR** `8bms serve --port 8765` starts a local JSON API. `POST /ops/<op>` with the op's arguments as JSON runs it; `POST /prompt {"text": ...}` talks to a stateful studio. It binds to 127.0.0.1 only, has no auth, and is meant for local tools.

```sh
8bms serve --port 8765 &
curl -s localhost:8765/health
curl -s -X POST localhost:8765/ops/compose -H 'content-type: application/json' \
     -d '{"prompt": "chase scene", "bars": 8, "seed": 2, "_fields": "handle,score"}'
curl -s -X POST localhost:8765/ops/render -d '{"src": "@last", "out": "chase.wav"}'
curl -s -X POST localhost:8765/batch -d '{"jobs": [{"id": "a", "op": "compose", "args": {"context": "town", "seed": 2}}, {"op": "critique", "args": {"src": "$a"}, "fields": "score"}]}'
curl -s -X POST localhost:8765/prompt -d '{"text": "/gen town 4"}'
```

| Route | Body | Returns |
|---|---|---|
| `GET /health` | — | `{"ok": true, "version": …}` |
| `GET /ops` | — | ops with JSON Schemas |
| `GET /tools` | — | tool cards (same as `8bms tools --json`) |
| `GET /openapi.json` | — | OpenAPI 3.1 ([schemas/openapi.json](../schemas/openapi.json)) |
| `POST /ops/<name>` | the op's args (+ optional `_fields`) | the op's result, or `{"error": …}` with status 400 |
| `POST /batch` | `{"jobs": [{"id", "op", "args", "fields"}, …]}` (same shape as `jobs.jsonl`) | `{"results": [{"id", "ok", "result" \| "error"}, …]}` |
| `POST /prompt` | `{"text": "…"}` | `{"reply": "…"}` (one studio session per server) |

Paths are resolved relative to the server's working directory. Handles (`@last`) are shared with the CLI because they live in `~/.8bms/handles/`.
Python client (stdlib only): [examples/http_client.py](../examples/http_client.py).

Exposing the server beyond localhost (`--host 0.0.0.0`) lets anyone on the network write files as you, so put it behind your own auth proxy if you do.

# CLI reference (`8bms`)

> **TL;DR** `8bms <command> [args]`. Output is one terse `key=value` line by default; use `--json` for JSON, `--fields a,b` to keep only some keys, and `-q` for exit status only. Every song argument accepts a file, `demo`, `gen:style:bars:seed`, `-` (stdin) or a handle (`@id`, `@last`).

```sh
8bms --version
8bms                     # GUI (same as 8bms gui)
8bms --help              # all commands with examples
8bms tools               # every op as a one-line card; --json for full schemas
```

## Global flags
These can go anywhere on the command line.
| Flag | Effect |
|---|---|
| `--json` | print one JSON object (or list) |
| `--fields a,b` | keep only these result keys (also `_fields` in HTTP/MCP args and `"fields"` in batch jobs) |
| `-q`, `--quiet` | no output; exit status 0 = ok, 1 = error |
| `--no-plugins` | skip plugin discovery (or set `EIGHTBMS_NO_PLUGINS=1`) |

Errors print one line, `error: …`; score errors include `line N`.

## Song sources and handles
- A source can be `song.8bt`, `song.8bms`, `song.json`, `demo`, `gen:boss:16:3` or `-` (stdin).
- Ops that create a song store it and return `handle=@1a2b3c4d`. Pass `@1a2b3c4d` or `@last` wherever a song is expected; this avoids sending score text back and forth.
- Handles live in `~/.8bms/handles/` (`EIGHTBMS_HOME` moves the whole data dir).

## Core commands
| Command | What it does |
|---|---|
| `8bms gui [file]` | open the GUI (`--selftest --screenshot shot.png` for headless checks) |
| `8bms studio [file]` (alias `repl`) | [terminal studio](terminal-studio.md) |
| `8bms do "<text>" [--song f] [--save f]` | run studio input non-interactively (`;` or newlines separate) |
| `8bms play <src> [--loop]` | play through the speakers |
| `8bms show <src>` · `info` · `check` | print as `.8bt` / summarize / validate |
| `8bms batch jobs.jsonl [-o results.jsonl]` | run many ops; `"$prev"` / `"$<id>"` reference earlier handles |
| `8bms op <name> k=v …` | run any registered op, including plugin ops |
| `8bms tools [--json]` · `openapi` · `schema 8bt\|8bms\|plugin\|ops` | machine-readable descriptions |
| `8bms serve [--host 127.0.0.1] [--port 8765]` | [HTTP API](http-api.md) |
| `8bms mcp` · `8bms acp` | [MCP](mcp.md) / [ACP](acp.md) servers on stdio |
| `8bms midi [--port P] [--seconds N]` | list MIDI ports / monitor a controller ([midi-apc](midi-apc.md)) |
| `8bms plugin list\|info\|enable\|disable\|install\|uninstall\|new\|validate\|test\|build\|package` | [plugins](plugins/README.md) |

## Batch example
```jsonl
{"id": "theme", "op": "compose", "args": {"context": "space", "bars": 16, "seed": 1}, "fields": "handle,score"}
{"id": "loop", "op": "loopify", "args": {"src": "$theme", "wav": "out/space-loop.wav"}, "fields": "loop_seconds,wav"}
```
```sh
8bms batch jobs.jsonl            # one JSON result per line: {"id", "ok", "result" | "error"}
```

## Ops
This section is generated from the op registry by `python scripts/gen_docs.py`. Do not edit it by hand.

<!-- BEGIN GENERATED: ops -->
<!-- END GENERATED: ops -->

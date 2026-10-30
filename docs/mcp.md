# MCP server (`8bms mcp`)

> **TL;DR** Add `{"command": "8bms", "args": ["mcp"]}` to your MCP client. You get a stateful `studio` tool plus one tool per op (compose, remix, loopify, soundpack, render, export…), and plugin ops are added automatically.

## Client configs
Claude Desktop (`claude_desktop_config.json`) and Cursor (`.cursor/mcp.json`):
```json
{ "mcpServers": { "8bms": { "command": "8bms", "args": ["mcp"] } } }
```
opencode (`opencode.json`):
```json
{ "mcp": { "8bms": { "type": "local", "command": ["8bms", "mcp"], "enabled": true } } }
```
VS Code (`.vscode/mcp.json`):
```json
{ "servers": { "8bms": { "type": "stdio", "command": "8bms", "args": ["mcp"] } } }
```
If the client can't find `8bms`, use its absolute path:
- installer venv: `~/.8bms/venv/bin/8bms`
- Windows: `%USERPROFILE%\.8bms\venv\Scripts\8bms.exe`
- `which 8bms` / `where 8bms` shows the actual location.

Ready-made files are in [examples/mcp/](../examples/mcp/).

## Tools
- `studio {text}`: one persistent session per server. Accepts notes, `.8bt` statements, English and `/commands`, and returns a terse reply.
- `<op> {args}`: every op in [cli-reference](cli-reference.md#ops) (input schema = the op's JSON Schema). Add `"_fields": "handle,score"` to trim results.

## Tips for agents
- Chain with handles: `compose` → `{"handle": "@ab12cd34"}` → `loopify {"src": "@ab12cd34", "wav": "loop.wav"}`.
- Use `intent {"text": "make it spookier"}` to map a user request to an op call.
- `describe` and `critique` give a compact view of a song without reading the score.

Smoke test:
```sh
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"describe","arguments":{"src":"demo","_fields":"summary"}}}' | 8bms mcp
```
Implemented with the standard library: newline-delimited JSON-RPC 2.0, methods `initialize`, `tools/list`, `tools/call` and `ping`.

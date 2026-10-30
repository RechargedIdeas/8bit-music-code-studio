# ACP agent (`8bms acp`)

> **TL;DR** `8bms acp` makes the studio an Agent Client Protocol agent. Add `{"command": "8bms", "args": ["acp"]}` under `agent_servers` in Zed (or any ACP client) and chat music: notes, English, or slash commands. Renders and exports come back as file links.

Zed (`~/.config/zed/settings.json`):
```json
{ "agent_servers": { "8Bit Music Code Studio": { "command": "8bms", "args": ["acp"] } } }
```
Other ACP clients use the same command/args pair. A copy is in [examples/acp/zed-settings.json](../examples/acp/zed-settings.json).

## Protocol
- Newline-delimited JSON-RPC 2.0 over stdio, ACP protocol version 1, implemented with the standard library.
- Methods: `initialize`, `authenticate` (no auth), `session/new`, `session/load` (replays history; sessions persist in `~/.8bms/acp-sessions/`), `session/prompt`, `session/cancel`, `session/set_mode`.
- Updates streamed during a prompt:
  - `plan`
  - `agent_message_chunk`
  - `tool_call` and `tool_call_update` (with `resource_link`s to WAV/JS/… files)
  - `available_commands_update` (all slash commands, including intent ops and plugin commands)
  - `user_message_chunk` (on load)

## Example prompts
```
make a tense boss theme 16 bars
/variation amount=.3
critique this
make it loop
/render boss.wav --seamless
/export js boss.js
```
Debug: run `8bms acp` in a terminal. It waits for JSON on stdin; all logs go to stderr.

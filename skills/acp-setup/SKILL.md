---
name: acp-setup
description: Run 8bms as an Agent Client Protocol (ACP) agent inside Zed, JetBrains or other ACP clients, so you can chat music (notes, English, slash commands) in the editor. Use when asked to add 8bms to Zed or another ACP client.
---

# ACP setup

1. Install so `8bms` is on PATH (`8bms --version`).
2. Zed: add this to `~/.config/zed/settings.json` (also in `examples/acp/zed-settings.json`):
   ```json
   { "agent_servers": { "8Bit Music Code Studio": { "command": "8bms", "args": ["acp"] } } }
   ```
   Other ACP clients use the same pair: command `8bms`, args `["acp"]`.
3. Open the agent panel, pick "8Bit Music Code Studio" and try:
   - `make a mellow space song 16 bars`
   - `/remix style=chill`
   - `critique this`
   - `/render song.wav`
   - `/export js`
4. Sessions persist in `~/.8bms/acp-sessions/` (`session/load` resumes them). Rendered and exported files come back as `resource_link`s.

Troubleshooting: run `8bms acp` in a terminal. It should wait silently for JSON-RPC on stdin (Ctrl+C to quit). Logs go to stderr.
Docs: `docs/acp.md`.

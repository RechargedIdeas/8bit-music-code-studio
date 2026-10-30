---
name: mcp-setup
description: Connect 8bms to an MCP client (Claude Desktop, Cursor, opencode, VS Code, any stdio MCP host) so the agent gets compose/remix/soundpack/render tools. Use when asked to add 8bms as an MCP server or tool.
---

# MCP setup

1. Install so `8bms` is on PATH (see README "Install"); `8bms --version` must work in a new terminal.
2. Add the server. The command is always `8bms mcp` over stdio:
   - Claude Desktop / Cursor (`mcpServers`):
     ```json
     { "mcpServers": { "8bms": { "command": "8bms", "args": ["mcp"] } } }
     ```
   - opencode (`opencode.json`):
     ```json
     { "mcp": { "8bms": { "type": "local", "command": ["8bms", "mcp"], "enabled": true } } }
     ```
   - If `8bms` isn't on the client's PATH, use the absolute path (`~/.8bms/venv/bin/8bms`, or `%USERPROFILE%\.8bms\venv\Scripts\8bms.exe` on Windows).
3. Restart the client and check that the tools appear: `studio` (stateful: notes, English, slash commands) plus one tool per op (`compose`, `remix`, `soundpack`, `render`, `export`...).
4. Smoke test from a shell (prints the tool list):
   ```sh
   printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | 8bms mcp
   ```

Token tips for agents: pass `_fields` (for example `"handle,score"`) in tool arguments, and pass handles (`@last`) instead of song text.
Examples are in `examples/mcp/`. Docs: `docs/mcp.md`.

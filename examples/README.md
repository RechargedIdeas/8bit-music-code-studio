# Examples

> **TL;DR** Copy-paste starting points. Each one runs as-is from the repo root once `8bms` is installed.

| File | What it shows | Run |
|---|---|---|
| `hello.8bt` | smallest useful score | `8bms render examples/hello.8bt -o hello.wav` |
| `jobs.jsonl` | batch ops with `$id` handle references and `fields` | `8bms batch examples/jobs.jsonl` |
| `python_api.py` | compose → variation → critique → loop → JS export | `python examples/python_api.py out` |
| `http_client.py` | stdlib client for `8bms serve` | `8bms serve &` then `python examples/http_client.py` |
| `game_audio_pack.sh` / `.ps1` | a looped, mastered game kit + SFX | `sh examples/game_audio_pack.sh kit` / `.\examples\game_audio_pack.ps1 kit` |
| `mcp/*.json` | MCP client configs (Claude Desktop, Cursor, opencode) | merge into your client's config |
| `acp/zed-settings.json` | ACP agent entry for Zed | merge into `~/.config/zed/settings.json` |

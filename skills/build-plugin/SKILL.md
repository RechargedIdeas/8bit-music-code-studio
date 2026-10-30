---
name: build-plugin
description: Create, test and ship an 8Bit Music Code Studio (8bms) plugin: new instrument/wave, effect, generator style, op, exporter/importer, GUI panel, slash command, visualizer, MIDI mapping or ML backend.
---

# Build an 8bms plugin

1. Pick the type: `instrument effect style op exporter importer gui command visualizer midi ml`.
   - A new sound → instrument.
   - Audio processing → effect.
   - A song generator → style.
   - A new automation verb usable from CLI/MCP/ACP/HTTP → op.
2. Scaffold it, inside a project's `plugins/` folder or anywhere:
   `8bms plugin new <type> <name>` (name: lowercase, `-`/`_` allowed).
3. Edit `<module>/__init__.py` → `register(api)`. API reference: `docs/plugins/api.md`; per-type snippets: `docs/plugins/types.md`.
   - Keep numpy vectorized; waves get phase in cycles, effects get stereo `(n, 2)` float arrays.
   - Never import tkinter at module top (only in GUI factories).
   - Need network? Add `permissions = ["network"]` to plugin.toml.
4. Update `tests/test_plugin.py` and `example/example.8bt` to exercise the new behavior.
5. Loop until green:
   `8bms plugin validate <dir> && 8bms plugin test <dir>`
   On failure, read the one-line error; `8bms plugin info <name> --json` shows load/runtime errors.
6. Try it for real:
   `8bms plugin install <dir>`, then `8bms render <dir>/example/example.8bt -o /tmp/p.wav`. Ops become `8bms <op> --arg v`.
7. Ship it: bump the semver `version`, then run `8bms plugin build <dir>` (wheel) and/or `8bms plugin package <dir>` (zip). CI is already in `.github/workflows/ci.yml`.

Rules: one plugin = one `name`. Don't monkey-patch core; register through `api.*` so disable/unload works. Use `api.data_dir` for files.
Working examples: `plugins/examples/{wavetable,chorus,synthwave,mml}`.

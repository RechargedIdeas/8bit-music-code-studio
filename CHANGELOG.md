# Changelog

> **TL;DR** Notable changes per version. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

## [1.0.0] - first release (not yet published)
### Added
- **Studio:** Tk GUI (piano roll, keyboard, drum sequencer, patterns and arrangement, instruments, mixer, helpers, autosave), with a NumPy synth (pulse/triangle/noise/saw/sine/wavetable, ADSR, vibrato, arpeggio, slides, echo/low-pass/bitcrush).
- **Formats:** `.8bms` JSON projects and `.8bt` text scores with a compact note language.
  - Quoted track names (`track "Pulse 1"`).
  - `pat lead A:`, `pat lead.A:` and `bars=` header forms.
- **Export:** WAV/OGG/MP3/FLAC, seamless loops and stems; Python, JavaScript (Web Audio ES module) and JSON code.
- **Op registry** shared by the CLI, Python, HTTP, MCP and ACP.
  - **Intent ops:** compose, variation, extend, arrange, remix, loopify, humanize, soundpack, stems, master, describe, critique, diff, suggest, intent, library.
  - **Library:** 23 game contexts, 14 styles, 10 grooves, 25 presets, 26 SFX.
- **Token-thrifty I/O:** terse output, `--json`, `--fields`, handles (`@last`), `8bms batch` / `POST /batch` with `$prev`/`$id`, deterministic seeds, and `8bms tools --json`.
- **Tiny offline ML model** (`models/tiny-v1.json`, 43 KB): Markov melody, chord Viterbi, grooves, intent parser, critic, humanizer. Exposed as `compose --model tiny` and `8bms suggest`, with latency tests.
- **`8bms studio`:** a terminal studio with slash commands, Tab completion and visualizers (tracker, VU, scope, spectrum, roll, arrangement).
- **Protocols:** MCP server, ACP agent and HTTP API (`/ops`, `/tools`, `/batch`, `/prompt`, `/openapi.json`).
- **MIDI:** Akai APC mini/mk2/Key 25/APC40 mk2 and generic MIDI support.
- **Plugins:** 11 types, manifest schema, sandboxed tests, build/package, four examples.
- **Agent docs:** `skills/` (8 recipes), AGENTS.md, llms.txt / llms-full.txt, `schemas/` + OpenAPI, and full `docs/` with TL;DRs.
  - `scripts/gen_docs.py` regenerates them; a docs-sync test checks they stay current.
- **Installers:** `install.sh` (POSIX) and `install.ps1` (Windows), each preferring pipx, then uv, then a venv, with extras, upgrade and uninstall.
- **CI and packaging:**
  - CI on Ubuntu/macOS/Windows × Python 3.10–3.13, installer smoke tests, and package build + `twine check`.
  - A release workflow that builds artifacts only.

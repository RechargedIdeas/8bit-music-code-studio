# Changelog

> **TL;DR** Notable changes per version. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

## [1.1.0] - 2026-10-30
### Added
- **JS export parity:** the exported ES module now carries an exact renderer (`renderSamples`, `toWav`, `renderVoice`), a line-for-line port of the Python synth. Its output matches the app's render sample for sample, including **duty sweep** and **bitcrush**, and runs in Node/Deno/Bun as well as browsers.
  - `createPlayer(ctx, {mode})`: `"exact"` plays the exact render (seamless when looping); `"live"` schedules Web Audio notes; `"auto"` (default) picks exact when bitcrush is on.
  - Live mode plays duty-swept notes from exactly rendered buffers and applies bitcrush bit depth with a WaveShaper.
  - `renderOffline()` uses the exact renderer by default (`{mode: "live"}` renders the Web Audio graph).
  - New tests run the export in Node and compare it with the Python render (with and without bitcrush/duty sweep, seamless, WAV bytes, player modes).
- **Akai APC:** `8bms apc test`, a guided hardware check (LED sweep, press-the-lit-pad, faders/knobs, master, Play, scenes, keys) that prints or saves a Markdown report; `--virtual <model>` runs it against a simulated controller; `8bms apc models` lists mappings.
  - `VirtualApc`: an in-memory APC (MIDI backend + device model with LED state) that drives the real `MidiController`. Tests cover every pad, LED, fader, knob, scene and transport button of each model, and the GUI self-test drives pad → drum step → LED and fader → volume through it.
  - Optional loopback test over real python-rtmidi virtual ports where the OS allows them.
  - New mappings `apc-mini-mk2` and `apc-key25-mk2` (RGB LED palette, channel 6 brightness, mk2 scene/track button notes); APC Key 25 scene/track buttons.
  - Docs page [Testing with real APC hardware](docs/apc-hardware-testing.md) and a GitHub issue form for hardware reports.
### Changed
- Port detection picks the longest matching name (so "APC mini mk2" is no longer treated as an mk1), and the LED output port is paired with the input even when the OS names them differently (e.g. Windows `APC MINI 0` / `APC MINI 1`).
- `8bms gui --screenshot` now includes the menu bar; `screenshot.png` regenerated from the current UI.
- Plugin docs now describe the `plugin test` network block accurately: best effort over Python sockets (now also `connect_ex`), not a security sandbox; installed plugins are not sandboxed.
### Fixed
- APC Key 25: keys played on the keyboard channel could be mistaken for pads, scene or transport buttons when they shared a note number.
- APC mini mk2 / APC40 mkII LEDs used mk1 velocity colours (which show as dim grey on RGB pads).

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

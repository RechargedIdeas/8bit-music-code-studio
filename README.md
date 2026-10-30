# 8Bit Music Code Studio

A desktop chiptune studio in **one Python file**, `8BitMusicCodeStudio.py`. It has a Tkinter GUI, a NumPy synth, and every sound is synthesized (no samples).

- **Export:** music goes out as audio (WAV/OGG/MP3/FLAC) or as code: a Python script, a JavaScript Web Audio module, JSON, or a compact `.8bt` text score.
- **Interfaces:** the same engine also runs as a command-line tool (`8bms`), an Agent Client Protocol (ACP) agent, an MCP server and a local HTTP API.
- **Plugins:** a plugin system extends all of these.

![screenshot](screenshot.png)

## Install & run

Needs Python 3.10+ with tkinter (`sudo apt install python3-tk` on Debian/Ubuntu) and NumPy.

```sh
cd 8bit-music-code-studio
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt          # numpy, sounddevice (playback), pytest
python 8BitMusicCodeStudio.py            # opens the GUI (demo song on first launch)
```

To get the `8bms` command on PATH, use either of:
```sh
uv tool install --editable .             # or: pip install -e .
pip install -e ".[audio,midi,dev]"       # extras: sounddevice, mido+python-rtmidi, pytest+pillow
```

Playback order: `sounddevice` first, then `simpleaudio`, then a temporary WAV played with the OS player (aplay/paplay/afplay/start).
Without any audio library the app still opens, edits and exports.
OGG, MP3 and FLAC need `ffmpeg` on PATH; WAV never does.

## The GUI

| Area | What you can do |
|---|---|
| **Piano roll** | Click to add a note and drag to set its length; drag a note to move it; drag its right edge to resize; right-click or double-click to delete. Shift+click multi-selects and Ctrl+drag box-selects. The velocity lane is at the bottom. Snap options: 1/4, 1/8, 1/16, 1/32 and triplets. Scale highlight and snap-to-scale, chord stamp tool, copy/cut/paste, duplicate, quantize, transpose, undo/redo. |
| **Piano keyboard** | Click keys to audition notes. Ctrl+K plays from the computer keyboard (two rows, Z… and Q…, with −/= for octave). With **Record** on, what you play is written into the pattern. |
| **Drum sequencer** | Step grid for kick, snare, hat, open hat, clap, tom, crash and metal. Click toggles a step, right-click cycles accent/ghost/off, and dragging paints. |
| **Patterns & arrangement** | Each track has patterns A, B, C… with their own length. Drag patterns from the list onto the timeline, drag clips to move them, and drag on the ruler to set the loop region. |
| **Instruments** | Waves: pulse 1 and 2 (duty 12.5/25/50/75%), triangle, noise (long/short LFSR), saw, sine and a 4-bit wavetable. Each instrument has ADSR, volume, vibrato (rate/depth/delay), arpeggio, pitch slide/sweep and duty sweep. Includes about 30 presets; you can save or load your own (`~/.8bms/instruments/`). |
| **Mixer** | Per track: volume, pan, mute, solo. Also a master level, with echo, low-pass and bitcrush effects (plus any plugin effects). |
| **Helpers** | Arpeggiator, random melody, random drums, generator styles (boss, town, chill, dungeon…), metronome, tap tempo, swing, BPM and time signature. |
| **Transport** | Play/pause (Space), stop (Home), loop (L), follow playhead (F) and a moving playhead. |
| **Files** | `.8bms` JSON projects, recent files, autosave every 60 s with crash recovery on the next launch, and plugin panels as extra tabs. |
| **Export** | WAV 16-bit 44.1 kHz for the song, the loop, a seamless loop or stems; OGG/MP3/FLAC; Python, JS, JSON and `.8bt`. |

Press **F1** in the app for the full shortcut list. Tooltips are on every control and the status bar shows what happened.

### "Save as code"
- **Python (`--py`):** a standalone script needing only NumPy. It re-synthesizes the song and writes a WAV (`python song.py -o out.wav [--seamless]`). Its output is sample-identical to the app's render (covered by tests).
- **JavaScript (`--js`):** an ES module for the browser.
  - It exports `SONG`, `createPlayer(ctx, {loop})`, `renderOffline(sampleRate)`, `playNote(...)`, `createMixer(...)`, plus `STEP_EVENTS`, `STEPS` and `STEP_SECONDS` for step-sequencer/game engines (Luciverse-compatible).
  - Usage: `import {createPlayer} from './song.js'; createPlayer(new AudioContext()).start()`.
- **JSON (`--json`):** the fully resolved event list plus instruments.
- **`.8bt` (`--score`):** a compact, human/AI-editable text score that round-trips with the project.

## Command line (`8bms`)

```sh
8bms gen --style boss --bars 16 --seed 3 -o boss.8bt
8bms render boss.8bt -o boss.wav            # --loop, --seamless, --bars 5-8, --stems dir/
8bms export boss.8bt --js boss.js --py boss.py
8bms info demo --json        8bms show demo        8bms check song.8bt
8bms do "gen town 8; bpm 100; /render town.wav"
8bms play boss.8bt           8bms repl             8bms presets / styles / score-help
```
Output is one terse `key=value` line by default; `--json` and `-q/--quiet` work on every command.
[AGENTS.md](AGENTS.md) is the cheat-sheet, including the `.8bt` syntax.

### `.8bt` score example
```
title Tiny Tune
bpm 132; key C major
inst blip pulse duty=.125 a=.001 d=.08 s=.4 r=.05
track lead inst=blip
pat lead.A: o5 l8 c e g >c <b g e c
track bass inst=bass
pat bass.A: l4 c3 c3 g2 g2
track drums drum
pat drums.A: kick=x...x...x...x... snare=....x.......x... hat=x.x.x.x.x.x.x.x.
```

## Agents: ACP, MCP, HTTP

### ACP (Agent Client Protocol), for Zed, opencode and others
`8bms acp` speaks ACP JSON-RPC over stdio, using newline-delimited messages and protocol version 1. Supported methods:
- `initialize` and `authenticate` (no auth needed).
- `session/new`, `session/load` (sessions persist to `~/.8bms/acp-sessions/`) and `session/prompt`.
- `session/cancel` and `session/set_mode`.

While a prompt runs, the server streams `session/update` notifications: `plan`, `agent_message_chunk`, `tool_call` / `tool_call_update` (with `resource_link`s to rendered or exported files), and `available_commands_update` (slash commands, including plugin ops).
Prompts are interpreted as music:
- note language (`o5 l8 c e g >c`),
- `.8bt` statements,
- plain English (`make a chill song 8 bars, faster, add drums, render`),
- slash commands (`/render`, `/export js`, `/gen boss 16`).

No ACP SDK is needed; the protocol is implemented with the standard library.

**Zed** (`~/.config/zed/settings.json`):
```json
{
  "agent_servers": {
    "8Bit Music Code Studio": { "command": "8bms", "args": ["acp"] }
  }
}
```
If `8bms` isn't on PATH, use `"command": "/path/to/.venv/bin/python", "args": ["/path/to/8BitMusicCodeStudio.py", "acp"]`.

**opencode** (`opencode.json`): opencode itself is an ACP *agent*, so you normally use 8bms from opencode as an MCP server:
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": { "8bms": { "type": "local", "command": ["8bms", "mcp"], "enabled": true } }
}
```
ACP clients that launch external agents (Zed, JetBrains, `acp` clients, and others) use the same `{"command": "8bms", "args": ["acp"]}` entry.

### MCP
`8bms mcp` is a stdio MCP server. It exposes the tool `studio`, a stateful session that takes notes, English or slash commands, plus one tool per op (`render`, `export`, `gen`, `info`, `check`, …), including ops added by plugins.

### HTTP
`8bms serve --port 8765` listens on localhost only. Routes: `GET /health`, `GET /ops`, `POST /ops/<name>` with a JSON body of args, and `POST /prompt` with `{"text": "..."}`.

## Akai APC / MIDI controllers (optional)
Install `mido` and `python-rtmidi` (`pip install -e ".[midi]"`). The GUI's **MIDI** menu connects to a port; `8bms midi` lists ports and monitors one.

Built-in mappings:
- **APC mini / mk2:** the 8×8 pads edit drum steps (with LED feedback and a playhead), faders set track volumes, fader 9 sets master, and the scene buttons select patterns.
- **APC Key 25:** pads and the keyboard (played notes are recorded when Record is on).
- **APC40 mk2:** clip grid, faders, master, and play/stop/record.
- **Generic:** any MIDI keyboard.

Plugins can add more mappings.

## Plugins
Plugin types:
- instruments/waves and effects,
- generator styles/grooves,
- **ops** (automatically exposed in the CLI, HTTP, MCP and ACP),
- exporters/importers,
- GUI panels,
- slash commands and visualizers,
- MIDI mappings and ML/composer backends.

Discovery: `~/.8bms/plugins`, `plugins/` in the current folder, `$EIGHTBMS_PLUGIN_PATH`, and the Python entry-point group `eightbit_studio.plugins`.
Each plugin has a `plugin.toml` manifest validated against a JSON Schema, with semver API compatibility (`api_version = "^1.0"`).
Errors are isolated: a crashing plugin is reported and rolled back, and a failing wave or effect falls back so renders still work.
Permissions are declared; network access is off in the test sandbox unless granted.

```sh
8bms plugin new effect my-fx          # scaffold (11 templates) with tests, example, CI workflow
8bms plugin validate my-fx && 8bms plugin test my-fx && 8bms plugin build my-fx
8bms plugin list | info | enable | disable | install | uninstall | package
python scripts/new_plugin.py op my-op   ;   python scripts/build_all_plugins.py
```
Examples in `plugins/examples/`: **wavetable** (wave + 3 presets), **chorus** (effect), **synthwave** (style + groove) and **mml** (MML exporter).
Docs: [docs/plugins/](docs/plugins/README.md). Agent skill: [skills/build-plugin/SKILL.md](skills/build-plugin/SKILL.md).

## Development
```sh
make test          # pytest (synth, timing, loops, round-trips, WAV, code exports, CLI, ACP, MCP/HTTP, plugins, GUI under xvfb)
make screenshot    # xvfb-run … gui --selftest --screenshot screenshot.png
make demo          # renders demo.wav
make plugins       # validate + test + build the example plugins
```
Architecture: everything above `launch_gui()` in `8BitMusicCodeStudio.py` is the GUI-free engine. The engine covers the model, synth, sequencer, mixer, exports, score language, ops, ACP/MCP/HTTP and plugins.
`import eightbit_studio as bms` (the small shim package) exposes the engine. The GUI imports tkinter lazily.

## Limitations
- The JS export approximates the synth with Web Audio oscillators. It ignores duty sweep and bitcrush, and plugin waves/effects aren't embedded in code exports (the Python export falls back to built-ins).
- Without `sounddevice`, the playhead is estimated and loop playback restarts a rendered buffer.
- APC mappings follow Akai's published note/CC maps but haven't been tested on real hardware here.
- The plugin "filesystem" permission is advisory. Only network is enforced, and only in `plugin test`; plugins run in-process with full Python rights, so install only plugins you trust.
- `.8bt` velocities are stored as 7-bit MIDI values or 3-decimal numbers.

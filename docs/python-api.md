# Python API

> **TL;DR** `import eightbit_studio as bms`, then `bms.run_op("compose", prompt="...", bars=8)` runs any op exactly like the CLI. Use `bms.load_any`, `bms.parse_score`, `bms.render_song` and `bms.export_audio` for direct control. Everything lives in one module.

```python
import eightbit_studio as bms

res = bms.run_op("compose", prompt="calm town at dusk", bars=8, seed=4, _fields="handle,score")
song = bms.load_any(res["handle"])           # Song object (also: path, "demo", "gen:boss:16:3")
song.bpm = 96
audio = bms.render_song(song)                # float stereo array, shape (n, 2), 44.1 kHz
bms.export_audio("town.ogg", audio)          # .wav always; .ogg/.mp3/.flac via ffmpeg
bms.op_export(song, "js", "town.js")         # any exporter: js, py, json, score, project, plugins
print(bms.song_to_score(song))               # .8bt text
```
A runnable tour is in [examples/python_api.py](../examples/python_api.py).

## Main entry points
| Function | Purpose |
|---|---|
| `run_op(name, _fields=None, **args)` | run a registered op (same args as CLI/HTTP/MCP); returns a dict |
| `OPS` · `op_tools()` · `openapi_spec()` | the registry, tool cards, OpenAPI spec |
| `run_batch(lines)` | iterate results for `jobs.jsonl` lines |
| `load_any(src)` · `parse_score(text)` · `song_to_score(song)` | load and convert songs |
| `load_project(path)` · `save_project(song, path)` | `.8bms` / `.8bt` files |
| `new_song()` · `demo_song()` · `generate_song(style, bars, seed, key, bpm)` | create songs |
| `apply_score(song, text)` · `parse_notes(text)` | apply statements / parse the note language |
| `render_song(song, start_bar=0, end_bar=None, seamless=False, stems=False)` | synthesize |
| `write_wav(path, data)` · `export_audio(path, data)` · `export_code(song, kind, path)` | write files |
| `critique_song(song)` · `suggest_next(song, ti, pname, k)` · `humanize_song(song, amount, seed)` · `song_chords(song)` | ML helpers ([ml](ml.md)) |
| `register_op(name, help, **params)` | add your own op (a decorator) |
| `load_plugins()` | discover plugins (run automatically by the CLI) |

## Data model
`Song(title, bpm, time_sig, swing, key, scale, master, tracks, arrangement, instruments, effects, loop_start, loop_end)`
- `Track(name, instrument, volume, pan, mute, solo, drum, kind, patterns: {name: Pattern})`
- `Pattern(name, bars, notes)`; `Note(start, length, pitch, velocity, inst)`. Ticks use PPQ 96, so a 16th note is 24 ticks.
- `Instrument(name, wave, duty, attack, decay, sustain, release, volume, vibrato…, arp, slide…)`

## Your own op
```python
import eightbit_studio as bms

@bms.register_op("octave_up", "Transpose every melodic track up an octave.",
                 src={"type": "string", "required": True, "pos": True, "help": "song"},
                 out={"type": "string", "help": "save to .8bt/.8bms"})
def octave_up(src, out=None):
    s = bms.load_any(src).copy()
    for t in s.tracks:
        if not t.drum:
            for p in t.patterns.values():
                for n in p.notes:
                    n.pitch += 12
    return bms._finish(s, out)        # stores a handle and returns {"handle", "title", ...}
```
Ship it as a plugin (type `op`) and it appears in the CLI, HTTP, MCP and ACP automatically ([plugins](plugins/README.md)).

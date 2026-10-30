# PluginAPI reference

`register(api)` receives a `PluginAPI`:

| member | purpose |
|---|---|
| `api.version` | host API version string (`"1.0.0"`) |
| `api.name` | your plugin name |
| `api.core` | the engine module (`load_any`, `new_song`, `generate_song`, `render_song`, `parse_notes`, `PRESETS`, …) |
| `api.Instrument, Note, Pattern, Track, Song, Clip` | model classes |
| `api.data_dir` | `~/.8bms/plugin-data/<name>/` (created on demand) |
| `api.log(msg)` | prints `[name] msg` to stderr |
| `api.guard(fn, fallback=None)` | wrap your own callbacks with the same error isolation |

## Extension points
| method | signature of what you pass |
|---|---|
| `add_wave(name, fn)` | `fn(phase_cycles: ndarray, t_seconds: ndarray, inst: dict) -> ndarray[-1..1]` |
| `add_instrument(inst)` | `Instrument` or dict (`name, wave, duty, attack, decay, sustain, release, volume, vib_rate, vib_depth, arp, slide, duty_sweep, …`) |
| `add_effect(name, fn, params)` | `fn(x: ndarray (n,2), sr, **params) -> ndarray (n,2)`; `params = {"mix": (min, max, default)}` |
| `add_style(name, spec_or_fn)` | dict like core `STYLES` entries, or `fn(rng, bars, key) -> Song` |
| `add_groove(name, rows)` | `{"kick": "x...x...", "snare": "....x...", ...}` (16 steps per bar) |
| `add_op(name, fn, help, **params)` | `fn(**kwargs) -> dict`; params as `name=int` / `name="float"` or `name={"type": "str", "required": True, "default": .., "help": ..}`. Defaults come from fn's signature. |
| `add_exporter(name, ext, fn)` | `fn(song) -> str|bytes`; usable as `8bms export song --to name -o f.ext` and in the GUI's Export menu |
| `add_importer(ext, fn)` | `fn(text) -> Song`; `load_any("x.ext")` and Open use it |
| `add_gui_panel(title, factory)` | `factory(parent, app) -> tk widget`, added as a notebook tab; `app.song`, `app.set_bpm`, `app.refresh_all()` … |
| `add_command(name, fn, help)` | `fn(interp, args: list[str]) -> str` → `/name` in repl/do/ACP/MCP studio |
| `add_visualizer(name, fn)` | `fn(song) -> str` → `/viz name` |
| `add_midi_mapping(name, mapping)` | see types.md#midi |
| `add_ml_backend(name, backend)` | object with `generate(prompt, song, **kw) -> Song | ".8bt text"` → `/ml name prompt` |

Everything registered is undone by `unload`/`disable`; if a key shadowed a built-in, the built-in is restored.

## Using ops everywhere
An op registered with `add_op("shout", fn, text=str, times=int)` becomes all of these:
- Python: `bms.run_op("shout", text="hi")`
- CLI: `8bms shout --text hi --times 3` and `8bms op shout text=hi`
- HTTP: `POST /ops/shout {"text": "hi"}`; listed in `GET /ops`
- MCP: tool `shout` with a JSON Schema built from the params
- ACP / repl: `/shout text=hi`, advertised in `available_commands_update`

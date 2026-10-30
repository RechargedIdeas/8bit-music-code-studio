# Plugin types

> **TL;DR** One section per plugin type, each with the snippet its `8bms plugin new <type> <name>` template generates.

Each type has a template: `8bms plugin new <type> <name>`. The snippets below are what the templates generate (shortened).

## instrument
```python
def register(api):
    def fat(phase, t, inst):
        f = phase % 1.0
        return np.round((np.where(f < .5, 1., -1.) * .6 + np.where((f * 2) % 1 < .25, 1., -1.) * .4) * 7.5) / 7.5
    api.add_wave("fat", fat)
    api.add_instrument({"name": "fat_lead", "wave": "fat", "attack": .005, "sustain": .6, "volume": .5})
```
Use it in a score with `inst x fat …` or `track lead inst=fat_lead`. Example plugin: `plugins/examples/wavetable`.

## effect
`api.add_effect("widen", fn, {"width": (0, 3, 1.5)})`, then use it in a score with `fx widen width=2`. It also appears in the GUI mixer. Example: `chorus`.

## style
Add a spec dict (bpm range, scale, keys, progressions, lead/harm/bass instruments, groove, density, swing, fx) or a function. Use it with `8bms gen --style name`. Example: `synthwave`.

## op
`api.add_op(name, fn, help, **params)` makes the op available in the CLI, HTTP, MCP and ACP (see api.md).

## exporter / importer
`api.add_exporter("mml", ".mml", song_to_mml)` adds `8bms export song.8bt --to mml -o song.mml`.
`api.add_importer(".txt", parse)` makes `8bms render tune.txt -o x.wav` work. Example: `mml`.

## gui
`api.add_gui_panel("My Panel", factory)` adds a tab in the bottom notebook. Keep imports of tkinter inside the factory so the plugin also loads headless.

## command / visualizer
- `/name args…` in repl, `do`, ACP and the MCP `studio` tool. Return a short string.
- Visualizers return text (`/viz name`). They're handy in terminals and ACP chats.

## midi
```python
api.add_midi_mapping("launchpad", {
    "match": ["Launchpad"],                         # substrings of the port name
    "grid": {"notes": [...64 notes...], "rows": 8, "cols": 8, "origin": "bottom"},
    "faders": {"48": 0, "49": 1},                   # CC -> track index (volume)
    "master_cc": 56,
    "transport": {"play": 91, "stop": 92, "record": 93},
    "keys_channel": 1,                              # notes on this channel = keyboard
    "led": {"off": 0, "on": 1, "accent": 5, "playhead": 3},
})
```
The grid toggles drum steps of the current pattern; LEDs echo the pattern and playhead.

## ml
```python
class Backend:
    def generate(self, prompt, song, **kw):
        return api.core.generate_song("boss", 8, seed=1)   # or return ".8bt" text
api.add_ml_backend("mymodel", Backend())
```
Use it with `/ml mymodel a sad dungeon theme`. Declare `permissions = ["network"]` if you call a remote API.

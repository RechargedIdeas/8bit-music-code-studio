# MIDI and Akai APC controllers

> **TL;DR** Install the `midi` extra (`--midi` in the installer, or `pip install "eightbit-music-code-studio[midi]"`), plug in the controller, then use **MIDI ▸ Connect** in the GUI. `8bms midi` lists ports and `8bms midi --port "APC mini" --seconds 10` shows incoming messages. `8bms apc test` checks a controller end to end and prints a report.

| Controller | Mapping id | Mapping |
|---|---|---|
| APC mini (mk1) | `apc-mini` | 8×8 pads = drum steps (LED feedback); faders 1–8 = track volume; fader 9 = master; scene buttons = select pattern / drum page |
| APC mini mk2 | `apc-mini-mk2` | same as the mk1; RGB LEDs (palette colours on channel 6), scene buttons 112–119 |
| APC Key 25 (mk1) | `apc-key25` | 5×8 pads = drum steps; knobs 1–8 = track volume; Play/Record; keys (channel 2) play and record notes |
| APC Key 25 mk2 | `apc-key25-mk2` | as the mk1, with RGB pad LEDs |
| APC40 mkII | `apc40` | 5×8 clip grid, track faders, master, Play/Stop/Record, scene buttons |
| any keyboard | `generic` | notes play the current instrument and record into the pattern |

The mapping is picked from the port name (the longest match wins, so "APC mini mk2" is not treated as an mk1). `8bms apc models` lists them; `--model` forces one.

## Check a controller: `8bms apc test`

```sh
8bms apc test                          # finds the first APC, sweeps every LED, then asks you to press/move controls
8bms apc test --report apc-report.md   # also saves a Markdown report to attach to a hardware-report issue
8bms apc test --virtual apc40          # no hardware: runs the same check against a simulated APC40 mkII
```

See [Testing with real APC hardware](apc-hardware-testing.md) for the full walk-through and what the results mean.

Notes:
- Dependencies: `mido` and `python-rtmidi`. Without them the MIDI menu explains what to install, and nothing else is affected.
- On Linux, ALSA MIDI needs the `snd-seq` kernel module; on Windows the controller must not be open in another app.
- Mappings follow Akai's published note/CC maps. They are tested end to end against a simulated APC (every pad, LED, fader, knob, scene and transport button) but not yet on real hardware; reports from owners are welcome ([how](apc-hardware-testing.md)).
- The original APC40 (mk1) uses a different grid layout and is not supported yet.
- Plugins of type `midi` can add mappings for other controllers ([plugins/types](plugins/types.md)).

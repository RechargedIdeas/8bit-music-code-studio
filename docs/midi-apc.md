# MIDI and Akai APC controllers

> **TL;DR** Install the `midi` extra (`--midi` in the installer, or `pip install "eightbit-music-code-studio[midi]"`), plug in the controller, then use **MIDI ▸ Connect** in the GUI. `8bms midi` lists ports and `8bms midi --port "APC mini" --seconds 10` shows incoming messages.

| Controller | Mapping |
|---|---|
| APC mini / mk2 | 8×8 pads = drum steps (LED feedback and playhead); faders 1–8 = track volume; fader 9 = master; scene buttons = select pattern |
| APC Key 25 | pads plus keyboard; played notes are recorded when Record is on |
| APC40 mk2 | clip grid, faders, master, play/stop/record |
| any keyboard | notes play the current instrument and record into the pattern |

Notes:
- Dependencies: `mido` and `python-rtmidi`. Without them the MIDI menu explains what to install, and nothing else is affected.
- On Linux, ALSA MIDI needs the `snd-seq` kernel module; on Windows the controller must not be open in another app.
- Mappings follow Akai's published note/CC maps but have not been tested on real hardware here.
- Plugins of type `midi` can add mappings for other controllers ([plugins/types](plugins/types.md)).

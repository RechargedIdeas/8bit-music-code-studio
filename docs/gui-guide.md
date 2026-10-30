# GUI guide

> **TL;DR** Run `8bms` (or `8bms gui`). Draw notes in the piano roll, paint drums in the step grid, drag patterns onto the timeline, press Space to play, and use **AI ▸ Compose** or **Ctrl+Space** for help. Press F1 for every shortcut.

![8Bit Music Code Studio](../screenshot.png)

## Layout
| Area | What it does |
|---|---|
| Toolbar / transport | Play/pause (Space), stop (Home), loop (L), follow (F), BPM, time signature, swing, metronome, tap tempo |
| Tracks (left) | Add/rename tracks, pick an instrument, volume, pan, mute, solo |
| Piano roll | Click to add a note, drag to move it, drag its right edge to resize; right-click/double-click deletes. Shift-click multi-selects; Ctrl-drag box-selects. A velocity lane is at the bottom. Snap 1/4 to 1/32 and triplets; scale highlight and snap-to-scale; chord stamp |
| Piano keyboard | Click to audition notes; Ctrl+K plays from the computer keyboard (Z… and Q… rows, −/= changes octave). With **Record** on, played notes are written into the pattern |
| Drum grid | Kick, snare, hat, open hat, clap, tom, crash, metal. Click toggles a step; right-click cycles accent / ghost / off; drag paints |
| Patterns & arrangement | Patterns A, B, C… per track, each with its own length. Drag a pattern onto the timeline, drag clips to move them, drag on the ruler to set the loop |
| Instrument editor | Waves: pulse (12.5/25/50/75 %), triangle, noise (long/short), saw, sine and a 4-bit wavetable. ADSR, vibrato, arpeggio, pitch slide, duty sweep. 25 presets; save your own to `~/.8bms/instruments/` |
| Mixer / FX | Master level, echo, low-pass, bitcrush, plus plugin effects |

## Menus
- **File:** new, open, open recent, save, save as. Autosave runs every 60 s, with crash recovery on the next launch.
- **Save as Code:** Python, JavaScript, JSON or `.8bt` score. Audio export covers the song, loop, seamless loop or stems as WAV/OGG/MP3/FLAC.
- **Edit:** undo/redo, copy/cut/paste, duplicate, quantize, transpose.
- **Tools:** arpeggiator, random melody/drums, generate in a style, chord stamp.
- **AI** (tiny offline model, see [ml](ml.md)):
  - Compose (tiny model)…
  - Suggest Next Note (**Ctrl+Space**; press again to cycle alternatives)
  - Variation, Extend +8 bars, Humanize, Auto-arrange, Make Seamless Loop
  - Critique, Describe, Chords of this Pattern

  Every AI edit is one undo step.
- **Plugins:** manage plugins and open plugin panels (they appear as extra tabs).
- **MIDI:** connect an Akai APC or any MIDI keyboard ([midi-apc](midi-apc.md)).
- **Help:** shortcuts (F1) and about.

## Recipes
- **Loop for a game:** drag on the ruler over bars 1–8, then *Save as Code ▸ Seamless loop WAV*.
- **Start from an idea:** *AI ▸ Compose*, type "sneaky stealth level", then use *Variation* until you like it.
- **Hand it to code:** *Save as Code ▸ JavaScript* and `import {createPlayer} from './song.js'`.

## Headless check
`8bms gui --selftest --screenshot shot.png` opens the real window, drives every menu handler (including the AI menu) and saves a screenshot. CI runs it under xvfb.

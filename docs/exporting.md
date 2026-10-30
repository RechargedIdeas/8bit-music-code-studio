# Exporting: audio and code

> **TL;DR** `8bms render song.8bt -o song.wav` makes audio (also `.ogg/.mp3/.flac` with ffmpeg); `--seamless` gives a gapless loop. `8bms export song.8bt --js song.js` (or `--py --json --score --project`) saves the song as code that rebuilds the music.

## Audio
```sh
8bms render song.8bt -o song.wav                  # 16-bit 44.1 kHz stereo
8bms render song.8bt -o loop.ogg --seamless       # loop region with the release tail folded back: gapless
8bms render song.8bt -o part.wav --bars 5-8       # a bar range (--loop = loop region without folding)
8bms stems song.8bt -o stems/                     # one WAV per track + mix.wav
8bms master song.8bt -o song.ogg --target-db -16  # loudness: gain, soft limiter, optional fades
8bms soundpack platformer -o sfx/                 # SFX WAVs + manifest.json + Howler sprite
```
OGG, MP3 and FLAC need `ffmpeg` on PATH; WAV never does. Rough sizes for a 16-bar loop: WAV 3–7 MB, OGG about 0.8 MB, JS module about 60 KB.

## Code
| Kind | Flag | Result |
|---|---|---|
| Python | `--py song.py` | standalone NumPy script: `python song.py -o out.wav [--seamless]`, sample-identical to the app |
| JavaScript | `--js song.js` | ES module: `SONG`, `createPlayer(ctx, {loop})`, `renderOffline(sampleRate)`, `playNote`, `createMixer`, `STEP_EVENTS`/`STEPS`/`STEP_SECONDS` |
| JSON | `--json song.json` | resolved event list plus instruments |
| Score | `--score song.8bt` | text score ([score-format](score-format.md)) |
| Project | `--project song.8bms` | lossless JSON project |
| Plugins | `--to <kind> -o path` | e.g. `--to mml` from the example plugin |

```js
import { createPlayer } from "./song.js";
const player = createPlayer(new AudioContext(), { loop: true });
document.querySelector("#play").onclick = () => player.start();
```

## Limits
- The JS export approximates the synth with Web Audio oscillators. It ignores duty sweep and bitcrush.
- Plugin waves and effects are not embedded in code exports; the Python export falls back to built-ins.

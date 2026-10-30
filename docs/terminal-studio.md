# Terminal studio (`8bms studio`)

> **TL;DR** `8bms studio` is a REPL: type notes, `.8bt` lines, plain English or `/slash` commands. Tab completes commands, op arguments and ML next-note ideas. `/watch` shows a live tracker, VU meters, oscilloscope and spectrum while the song plays.

```text
$ 8bms studio
8bms> make a mellow space song 16 bars
ok composed 'Space #1' (critique 98) ...
8bms> /watch 10
8bms> o5 l8 c e g > c
8bms> /suggest
8bms> /render space.wav
8bms> /quit
```

## What you can type
| Input | Example |
|---|---|
| notes (appended to the current track/pattern) | `o5 l8 c e g >c` · `{Am}/1 {F}/1` |
| statements | `bpm 120` · `key A minor` · `track bass inst=bass` · `pat bass.A: l8 c2 c2 g2 c2` |
| English | `make a boss theme 16 bars`, `faster`, `transpose up 2`, `add drums`, `make it loop`, `critique this`, `render` |
| slash commands | see below |

## Slash commands
Editing and files:
`/new /demo /gen <style> [bars] [seed] /load <f> /save <f> /show /info /track <name> /pat <name> /bpm N /key C minor /transpose N /clear /undo`

Output:
`/render [f] [--loop] [--seamless]  /stems [dir]  /export <js|py|json|score|project> [f]  /presets /styles`

Intent ops (they act on the current song):
`/compose <prompt> [context=boss bars=16 seed=1]  /variation [amount=.3]  /extend [bars=8]  /remix style=<s>  /loopify  /humanize  /arrange  /describe  /critique  /suggest [kind=next|chords|groove]  /master [out=f.wav]  /soundpack <names|set>  /library <what>  /intent <text>  /op <op> k=v`

Studio-only:
| Command | Shows |
|---|---|
| `/play [--loop]` · `/stop` | playback (sounddevice → simpleaudio → winsound → OS player) |
| `/watch [secs]` | live dashboard: tracker playhead, VU, scope, spectrum (Ctrl+C stops) |
| `/dashboard [bar]` | one dashboard frame (default: loudest moment) |
| `/tracker [bar]` · `/vu` · `/scope` · `/spectrum` | single views |
| `/viz roll` · `/viz arrangement` | ASCII piano roll / arrangement |
| `/suggest` | ML next-note ideas (Tab inserts them) |

## Visualizations
Seven visualizers ship: `tracker`, `vu`, `scope`, `spectrum`, `dashboard`, `roll`, `arrangement`. Plugins can add more (type `visualizer`).
They use Unicode blocks when the terminal supports them and fall back to ASCII. On Windows, ANSI colors are enabled automatically (VT mode).

## Non-interactive
```sh
8bms do "gen town 8; bpm 100; /render town.wav" --save town.8bt
echo "/describe" | 8bms studio song.8bt
```

# The `.8bt` score format

> **TL;DR** `.8bt` is a line-based text score: `title`, `bpm`, `key`, `inst`, `track`, `pat <track> <name>: <notes>`, `arr <track>: A A B A`. It round-trips with the project file and is the cheapest format for people and AIs to read or write. Validate with `8bms check song.8bt`.

```
title Boss Theme
bpm 150; time 4/4; swing 0; key A minor; master .8
loop 1-8
fx echo time=.3 feedback=.3 mix=.2
inst zap pulse duty=.125 a=.001 d=.1 s=.5 r=.05 vib=.2 arp=0,4,7 slide=-12
track lead inst=zap vol=.7 pan=-.2
pat lead A: o5 l8 c e g > c < b g e c
pat lead B bars=2: (a g)x4 f/2. r/4
arr lead: A A B - A*2
track drums drum
pat drums A: kick=x...x...x...x... snare=....x.......x... hat=x.x.x.x.x.x.x.x.
```

## Statements
One per line; `;` also separates. Indented lines continue the previous line. A `#` followed by a space starts a comment (`title Boss #3` stays intact).

| Statement | Meaning |
|---|---|
| `title <text>` | song title |
| `bpm <n>` · `time 3/4` · `swing 0..1` | tempo, meter, swing |
| `key <root> <scale>` | e.g. `key F# dorian` (major, minor, dorian, phrygian, lydian, mixolydian, harmonic_minor, pentatonic, minor_pentatonic, blues, chromatic) |
| `master <0..1>` | master volume |
| `loop <a>-<b>` | loop region in bars, 1-based and inclusive |
| `fx <echo\|lowpass\|bitcrush> k=v…` | master effects (`time feedback mix`, `cutoff`, `bits downsample`) |
| `inst <name> <wave> k=v…` | define an instrument: `duty a d s r vol vib vibrate vibdelay arp slide slidetime noise=long\|short` |
| `track <name> [drum] [inst=..] [vol=..] [pan=..] [mute] [solo]` | create or select a track |
| `pat <track> <name> [bars=N] [o=4] [l=8] [steps=16]: <body>` | a pattern; `pat <track>.<name>:` also works |
| `play <track>: <notes>` | shorthand for pattern A, arranged once |
| `arr <track>: A A B - A*2` | arrangement: `-` is an empty slot, `*N` repeats. Without `arr`, patterns play in order |

Pattern bodies are written in the [note language](note-language.md). A drum track can also use grid rows: `kick=x...x...` with `x` hit, `X` accent, `o` ghost and `.` rest, 16 steps per bar (`steps=` changes this).

## Round-trip and tools
- `8bms show song.8bt` prints the normalized score; `8bms check song.8bt` prints `ok=True bars=8 notes=229`, or an error with `line N`.
- `.8bms` is the JSON project format (lossless and larger). Use `8bms export x.8bms --score x.8bt` to convert.
- JSON Schemas: [schemas/8bt.schema.json](../schemas/8bt.schema.json) (statement patterns) and [schemas/8bms.schema.json](../schemas/8bms.schema.json).
- Every command accepts `-` for stdin: `cat song.8bt | 8bms render - -o song.wav`.

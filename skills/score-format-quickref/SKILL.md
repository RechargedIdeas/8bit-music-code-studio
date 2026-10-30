---
name: score-format-quickref
description: Read or write 8bms .8bt text scores (statements, tracks, patterns, arrangement, drum grids, note language) correctly the first time. Use whenever editing music as text, writing a score by hand, or fixing an `8bms check` error.
---

# .8bt quick reference

```
title Boss Theme            # '#'+space starts a comment
bpm 150; time 4/4; swing 0; key A minor; master .8
loop 1-8                    # bars, 1-based inclusive
fx echo time=.3 feedback=.3 mix=.2      # also: lowpass cutoff=  bitcrush bits= downsample=
inst zap pulse duty=.125 a=.001 d=.1 s=.5 r=.05 vib=.2 arp=0,4,7 slide=-12
track lead inst=zap vol=.7 pan=-.2
pat lead A: o5 l8 c e g > c < b g e c     # or 'pat lead.A:'
pat lead B bars=2 o=5: (a g)x4 f/2. r/4  # header k=v: bars= o= (octave, default 4) l= (default length)
arr lead: A A B - A*2       # '-' empty slot, '*N' repeat; no arr line = patterns in order
track drums drum
pat drums A: kick=x...x...x...x... snare=....x.......x... hat=x.x.x.x.x.x.x.x.
```

Note language (inside `pat` bodies):
- Pitch `c4 c#4 db4`, or bare `c` (current octave `o5`); `>` `<` move the octave.
- Length: `l8` sets the default; per note `c/4 c/8. c/16t` (dot, triplet), `c%36` (ticks), `c*2` (scale). `_` or `_/4` extends (ties) the previous note.
- Rest `r` or `r/4`; chord `[c e g]/2`; chord symbols `{Am}/1 {G7} {Fmaj7}` (also m dim aug sus2 sus4 m7 ...).
- Velocity: default `v100` or `v.8`; per note `c!.6` / `c!110`.
- Repeat `( ... )x4`; `|` is a visual bar line; `@192` jumps to an absolute tick (PPQ 96, 16th = 24); `@b3` jumps to bar 3.
- Drum hits as notes in a drum track: `kick/8 snare/8 hat/16`; grid rows use `x` hit, `X` accent, `o` ghost, `.` rest (16 steps per bar; `steps=` on the header).

Workflow: write, then `8bms check song.8bt` (it reports `line N` for errors), then `8bms show song.8bt` to normalize, then render.
Every song command accepts `-` for stdin: `8bms render - -o x.wav < song.8bt`.
Schema: `schemas/8bt.schema.json`. Full docs: `docs/score-format.md` and `docs/note-language.md`.

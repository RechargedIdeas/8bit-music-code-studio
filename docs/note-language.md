# Note language

> **TL;DR** Inside `pat` bodies, the studio and `8bms do`, you write `o5 l8 c e g > c` style notes: letters with an optional octave, `/len` for length, `!vel` for velocity, `r` for rests, `[c e g]` chords, `{Am}` chord symbols, and `( … )x4` repeats.

| Write | Means |
|---|---|
| `c4 c#4 db4` | a pitch with an octave (`c4` is middle C, MIDI 60) |
| `c` | a pitch in the current octave |
| `o5` · `>` · `<` | set the octave / up one / down one |
| `l8` · `l16t` · `l4.` | default length: eighth, sixteenth triplet, dotted quarter |
| `c/4` · `c/8.` · `c/16t` | per-note length |
| `c%36` | length in ticks (PPQ 96: a 16th is 24 ticks) |
| `c*2` | scale the length (×2) |
| `_` · `_/4` | tie: extend the previous note(s) by the default length / by a quarter |
| `r` · `r/4` · `rest` | rest |
| `[c e g]/2` | chord (any pitches) |
| `{Am}/1` `{G7}` `{Fmaj7}` `{Csus4}` | chord symbol (maj, m/min, dim, aug, sus2, sus4, 7, maj7, m7…), voiced in the current octave |
| `v100` · `v.8` | default velocity (0–127 or 0–1) |
| `c!.6` · `c!110` | per-note velocity |
| `( c d e )x4` | repeat a group |
| `\|` | bar line (visual only) |
| `@192` · `@b3` | jump to tick 192 / to bar 3 of the pattern |
| `kick/8 snare hat/16` | drum hits by name (in drum tracks) |

Examples:
```
o5 l8 c e g > c < b g e c            # arpeggio up and back
l4 {C} {Am} {F} {G7}                 # I-vi-IV-V7 block chords
o4 l16 (c e g e)x4 | f/2 _/4 r/4     # repeated figure, then a held note
kick/4 snare/4 kick/8 kick/8 snare/4 # a drum bar written as notes
```

Try it live: `8bms do "o5 l8 c e g >c" --save t.8bt`, or type the notes into `8bms studio` (Tab completes, and `/suggest` proposes the next note).

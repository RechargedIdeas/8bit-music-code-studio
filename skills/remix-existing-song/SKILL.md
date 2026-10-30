---
name: remix-existing-song
description: Remix, vary, extend or re-style an existing 8bms song (.8bt/.8bms/demo/@handle) while keeping its melody, then compare with diff. Use when asked to rework, redo, restyle, make a variation of, or lengthen a song.
---

# Remix an existing song

1. Understand it first: `8bms describe song.8bt` (form, chords, mood, range) and `8bms critique song.8bt`.
2. Pick the op:
   | Want | Command |
   |---|---|
   | new style/tempo, same melody | `8bms remix song.8bt --style chill` or `--context underwater` |
   | similar but fresh | `8bms variation song.8bt --amount 0.3 --seed 2` (0 = identical, 1 = new melody) |
   | longer | `8bms extend song.8bt --bars 8` |
   | new backing, same melody | `8bms arrange song.8bt --style town` |
   | less robotic | `8bms humanize song.8bt --amount 0.4` |
   Every op returns a `handle`; chain with `@last` or the handle and save with `-o out.8bt`.
3. Compare: `8bms diff song.8bt @last` lists settings, track and note changes.
4. Render: `8bms render @last -o remix.wav` (or `master @last -o remix.ogg`).

Plain English works in the studio, MCP `studio` tool and ACP: "remix this as a boss theme", "make it sound like a dungeon", "add 8 more bars".
`8bms intent "<text>"` shows the op it maps to. Keep `--seed` fixed for reproducible results.

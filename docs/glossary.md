# Glossary

> **TL;DR** Quick definitions of the words used across the docs and the CLI.

| Term | Meaning |
|---|---|
| **8bms** | the command-line program, and the `.8bms` JSON project format |
| **.8bt** | the text score format ([score-format](score-format.md)) |
| **ACP** | Agent Client Protocol: editors such as Zed talk to agents over stdio ([acp](acp.md)) |
| **MCP** | Model Context Protocol: AI clients call tools over stdio ([mcp](mcp.md)) |
| **op** | a registered operation (compose, render, …) exposed in every front-end |
| **handle** | `@` plus 8 hex chars naming a stored song result; `@last` is the latest |
| **context** | a game situation (boss, town, space…) that picks style, length and loop/jingle |
| **style** | a generator recipe: scale, tempo, instruments, groove, density |
| **groove** | a drum pattern template (four, rock, shuffle…) |
| **preset** | a named instrument (lead, bass, snare, coin…) |
| **pattern** | a block of notes on one track (A, B, C…) with its own length |
| **arrangement** | the order of patterns per track over the bars |
| **seamless loop** | a render whose release tail is folded back into the start so it repeats without a gap or click |
| **stems** | one audio file per track |
| **PPQ** | pulses per quarter note; 96 here (a 16th note = 24 ticks) |
| **duty** | the pulse-wave width (12.5/25/50/75 %), which sets the NES-like timbre |
| **LFSR noise** | the noise channel's shift-register generator (long = hiss, short = metallic) |
| **critique** | a rule-based 0–100 score with tips; also used to rerank compose candidates |
| **tiny model** | the bundled 43 KB statistical model ([ml](ml.md)) |
| **sprite** | one WAV holding all SFX plus a JSON map of offsets (Howler.js format) |

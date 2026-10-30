# Agent framework

> **TL;DR** Every capability is an **op** in one registry. The same op is a CLI subcommand, a `POST /ops/<name>` route, an MCP tool, an ACP/studio slash command and a Python call. Ops take small JSON args, return small JSON results, are deterministic for a seed, and pass songs around as **handles** (`@last`), so agents spend few tokens.

## The intent ops
| Op | Use it to | Key args | Returns |
|---|---|---|---|
| `compose` | make a new song from a prompt and/or game context | `prompt context style bars key bpm seed model candidates loop` | `handle score style context bars bpm key notes title` |
| `variation` | same form and harmony, fresh melody/rhythm | `src amount seed` | `handle changed` |
| `extend` | add N bars | `src bars seed` | `handle added_bars` |
| `arrange` | keep the melody, rebuild chords/bass/drums | `src style seed` | `handle` |
| `remix` | new style or context, same melody | `src style context bpm seed` | `handle style` |
| `loopify` | seamless loop | `src bars out wav` | `loop_bars loop_seconds loop_samples wav seam` |
| `humanize` | timing/velocity feel | `src amount seed` | `handle` |
| `soundpack` | SFX pack | `names out variants seed sprite sr` | `dir count manifest sprite` |
| `stems` | one WAV per track | `src out seamless` | `dir stems mix` |
| `master` | loudness, limiter, fades (songs or WAVs) | `src out target_db ceiling_db fade_in fade_out loop` | `path rms_db peak_db gain_db` |
| `describe` | one-paragraph summary | `src` | `summary mood form chords lead_range score` |
| `critique` | 0–100 score + tips | `src` | `score metrics parts tips` |
| `diff` | structural diff of two songs | `a b` | `same changes` |
| `suggest` | ML next notes / chords / groove | `src kind track pattern k seed` | list of suggestions |
| `intent` | English → op call | `text` | `op args confidence alternatives` |
| `library` | styles, contexts, grooves, presets, SFX | `what` | lists |

Utility ops: `render`, `export`, `gen`, `info`, `check`, `presets`, `styles`, `score_help`, `ml`. The full generated list is in the [CLI reference](cli-reference.md#ops).

## Token-thrifty I/O
- **Handles** instead of score text: every song-producing op returns `handle`. `@last` is always the latest.
- **`--fields` / `_fields`**: `8bms compose ... --fields handle,score` → `handle=@ab12cd34 score=98`.
- **Terse default output**: one `key=value` line. Ask for `--json` only when you need structure.
- **Batch**: `8bms batch jobs.jsonl` runs a whole plan in one call (`"$prev"`, `"$<id>"`).
- **Determinism**: the same args and `seed` give byte-identical songs and audio. You can retry without surprises and cache results.
- **Self-description**: `8bms tools` (one line per op), `8bms tools --json`, `GET /tools`, MCP `tools/list`, `8bms schema ops`.

## Library
- **14 styles:** boss, chase, chill, credits, dungeon, gameover, mellow-space, puzzle, stealth, title, town, underwater, upbeat, victory.
- **23 game contexts:** title-screen, menu, overworld, town, shop, forest, dungeon, cave, castle, battle, boss, final-boss, chase, puzzle, stealth, underwater, space, lofi-break, credits, victory, level-clear, game-over, cutscene-sad. Each maps to a style, a length and loop-or-jingle.
- **Other sets:** 10 grooves, 25 instrument presets, and 26 SFX in 4 sets (platformer, shooter, ui, rpg).

See them with `8bms library <styles|contexts|grooves|presets|sfx>`.

## Skills
Task recipes for agents live in [skills/](../skills/):
- `compose-game-soundtrack`
- `make-sfx-pack`
- `loop-for-web`
- `remix-existing-song`
- `score-format-quickref`
- `mcp-setup`
- `acp-setup`
- `build-plugin`

## A typical agent plan
```sh
8bms intent "spooky cave level, short loop"                 # -> op=compose args={context: cave, ...}
8bms compose "spooky cave" --context cave --seed 3 --fields handle,score
8bms critique @last --fields score,tips
8bms loopify @last --wav cave.ogg --fields loop_seconds,wav
```

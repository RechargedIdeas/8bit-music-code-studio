# CLI reference (`8bms`)

> **TL;DR** `8bms <command> [args]`. Output is one terse `key=value` line by default; use `--json` for JSON, `--fields a,b` to keep only some keys, and `-q` for exit status only. Every song argument accepts a file, `demo`, `gen:style:bars:seed`, `-` (stdin) or a handle (`@id`, `@last`).

```sh
8bms --version
8bms                     # GUI (same as 8bms gui)
8bms --help              # all commands with examples
8bms tools               # every op as a one-line card; --json for full schemas
```

## Global flags
These can go anywhere on the command line.
| Flag | Effect |
|---|---|
| `--json` | print one JSON object (or list) |
| `--fields a,b` | keep only these result keys (also `_fields` in HTTP/MCP args and `"fields"` in batch jobs) |
| `-q`, `--quiet` | no output; exit status 0 = ok, 1 = error |
| `--no-plugins` | skip plugin discovery (or set `EIGHTBMS_NO_PLUGINS=1`) |

Errors print one line, `error: …`; score errors include `line N`.

## Song sources and handles
- A source can be `song.8bt`, `song.8bms`, `song.json`, `demo`, `gen:boss:16:3` or `-` (stdin).
- Ops that create a song store it and return `handle=@1a2b3c4d`. Pass `@1a2b3c4d` or `@last` wherever a song is expected; this avoids sending score text back and forth.
- Handles live in `~/.8bms/handles/` (`EIGHTBMS_HOME` moves the whole data dir).

## Core commands
| Command | What it does |
|---|---|
| `8bms gui [file]` | open the GUI (`--selftest --screenshot shot.png` for headless checks) |
| `8bms studio [file]` (alias `repl`) | [terminal studio](terminal-studio.md) |
| `8bms do "<text>" [--song f] [--save f]` | run studio input non-interactively (`;` or newlines separate) |
| `8bms play <src> [--loop]` | play through the speakers |
| `8bms show <src>` · `info` · `check` | print as `.8bt` / summarize / validate |
| `8bms batch jobs.jsonl [-o results.jsonl]` | run many ops; `"$prev"` / `"$<id>"` reference earlier handles |
| `8bms op <name> k=v …` | run any registered op, including plugin ops |
| `8bms tools [--json]` · `openapi` · `schema 8bt\|8bms\|plugin\|ops` | machine-readable descriptions |
| `8bms serve [--host 127.0.0.1] [--port 8765]` | [HTTP API](http-api.md) |
| `8bms mcp` · `8bms acp` | [MCP](mcp.md) / [ACP](acp.md) servers on stdio |
| `8bms midi [--port P] [--seconds N]` | list MIDI ports / monitor a controller ([midi-apc](midi-apc.md)) |
| `8bms apc test [--port P] [--model M] [--virtual [M]] [--report FILE]` | guided Akai APC check with a Markdown report ([apc-hardware-testing](apc-hardware-testing.md)); `8bms apc models` lists mappings |
| `8bms plugin list\|info\|enable\|disable\|install\|uninstall\|new\|validate\|test\|build\|package` | [plugins](plugins/README.md) |

## Batch example
```jsonl
{"id": "theme", "op": "compose", "args": {"context": "space", "bars": 16, "seed": 1}, "fields": "handle,score"}
{"id": "loop", "op": "loopify", "args": {"src": "$theme", "wav": "out/space-loop.wav"}, "fields": "loop_seconds,wav"}
```
```sh
8bms batch jobs.jsonl            # one JSON result per line: {"id", "ok", "result" | "error"}
```

## Ops
This section is generated from the op registry by `python scripts/gen_docs.py`. Do not edit it by hand.

<!-- BEGIN GENERATED: ops -->
<a id="ops"></a>

25 ops, generated from the registry (`8bms tools --json` has full input schemas). Every op also takes `_fields` (CLI `--fields`) to trim its result.

### `render`

Render a song to audio (wav/ogg/mp3/flac).

```sh
8bms render <src> [-o out.wav] [--loop] [--seamless] [--bars 1-8] [--stems DIR]
```

| arg | type | default | help |
|---|---|---|---|
| `src` | string | required | file .8bt/.8bms, 'demo' or gen:style:bars:seed |
| `out` | string | `"out.wav"` | output file (extension picks format) |
| `loop` | boolean | `false` | render only the loop region |
| `seamless` | boolean | `false` | gapless loop file: loop region (or --bars) with the tail folded into the start |
| `bars` | string |  | bar range like 1-8 |
| `stems` | string |  | also write per-track stems into this folder |

### `export`

Export a song as code/data: js, py, json, score (.8bt), project (.8bms) or plugin formats.

```sh
8bms export <src> [--js|--py|--json|--score|--project PATH] [--to KIND -o PATH]
```

| arg | type | default | help |
|---|---|---|---|
| `src` | string | required | song source |
| `kind` | string | required | exporter name |
| `out` | string |  | output path (default from title) |

### `gen`

Generate a song in a style. Returns score text, or writes it to out (.8bt/.8bms).

```sh
8bms gen [--style S] [--bars N] [--seed N] [--key K] [--bpm N] [-o out.8bt] [--wav out.wav]
```

| arg | type | default | help |
|---|---|---|---|
| `style` | string | `"mellow-space"` | style name |
| `bars` | integer | `16` | length in bars |
| `seed` | integer |  | random seed |
| `key` | string |  | key like C, F#, Bb |
| `bpm` | number |  | tempo |
| `out` | string |  | write score/project here |
| `wav` | string |  | also render a WAV |

### `info`

Summarize a song.

```sh
8bms info <src>
```

| arg | type | default | help |
|---|---|---|---|
| `src` | string | required | song source |

### `check`

Validate a score/project; returns ok or the first error.

```sh
8bms check <src>
```

| arg | type | default | help |
|---|---|---|---|
| `src` | string | required | file |

### `presets`

List instrument presets (and user instruments).

```sh
8bms presets
```

| arg | type | default | help |
|---|---|---|---|

### `styles`

List generator styles.

```sh
8bms styles
```

| arg | type | default | help |
|---|---|---|---|

### `score_help`

Show the .8bt score syntax.

```sh
8bms score-help
```

| arg | type | default | help |
|---|---|---|---|

### `compose`

Compose a new song from a prompt and/or game context; reranks candidates by critique score.

```sh
8bms compose <prompt> [--context] [--style] [--bars] [--key] [--bpm] [--seed] [--model] [--candidates] [--loop] [--out] [--wav]
```

| arg | type | default | help |
|---|---|---|---|
| `prompt` | string | `""` | free text, e.g. 'tense boss fight 16 bars in E' |
| `context` | string |  | game context: title-screen, menu, overworld, town, shop, forest, dungeon, cave, castle, battle, boss, final-boss, chase, puzzle, stealth, underwater, space, lofi-break, credits, victory, level-clear, game-over, cutscene-sad |
| `style` | string |  | style (overrides context) |
| `bars` | integer |  | length in bars |
| `key` | string |  | key like C, F#, Bb |
| `bpm` | number |  | tempo |
| `seed` | integer | `0` | seed (same args + seed = same result) |
| `model` | string | `"tiny"` | tiny (Markov+rules, default) \| rules \| <ml plugin> |
| `candidates` | integer | `4` | generate N and keep the best by critique score |
| `loop` | boolean |  | make it a seamless loop (default: from context) |
| `out` | string |  | also save the song (.8bt/.8bms) |
| `wav` | string |  | also render audio (wav/ogg/mp3/flac) |

### `variation`

Make a variation: same form and harmony, re-voiced melody/rhythm details.

```sh
8bms variation <src> [--amount] [--seed] [--out] [--wav]
```

| arg | type | default | help |
|---|---|---|---|
| `src` | string | required | song: file .8bt/.8bms, @handle, @last, demo or gen:style:bars:seed |
| `amount` | number | `0.3` | 0..1 how much to change |
| `seed` | integer | `0` | seed (same args + seed = same result) |
| `out` | string |  | also save the song (.8bt/.8bms) |
| `wav` | string |  | also render audio (wav/ogg/mp3/flac) |

### `extend`

Extend a song by N bars: new melody over the existing accompaniment, ending with a fill.

```sh
8bms extend <src> [--bars] [--seed] [--model] [--out] [--wav]
```

| arg | type | default | help |
|---|---|---|---|
| `src` | string | required | song: file .8bt/.8bms, @handle, @last, demo or gen:style:bars:seed |
| `bars` | integer | `8` | bars to add |
| `seed` | integer | `0` | seed (same args + seed = same result) |
| `model` | string | `"tiny"` | tiny \| rules |
| `out` | string |  | also save the song (.8bt/.8bms) |
| `wav` | string |  | also render audio (wav/ogg/mp3/flac) |

### `arrange`

Auto-arrange: keep the melody, add chords (Viterbi), bass and a groove in a style.

```sh
8bms arrange <src> [--style] [--seed] [--out] [--wav]
```

| arg | type | default | help |
|---|---|---|---|
| `src` | string | required | song: file .8bt/.8bms, @handle, @last, demo or gen:style:bars:seed |
| `style` | string |  | style (default: guessed from tempo/scale) |
| `seed` | integer | `0` | seed (same args + seed = same result) |
| `out` | string |  | also save the song (.8bt/.8bms) |
| `wav` | string |  | also render audio (wav/ogg/mp3/flac) |

### `remix`

Remix in another style or context: keeps the melody, new tempo/instruments/harmony/groove.

```sh
8bms remix <src> [--style] [--context] [--bpm] [--seed] [--out] [--wav]
```

| arg | type | default | help |
|---|---|---|---|
| `src` | string | required | song: file .8bt/.8bms, @handle, @last, demo or gen:style:bars:seed |
| `style` | string |  | target style |
| `context` | string |  | or a game context |
| `bpm` | number |  | tempo |
| `seed` | integer | `0` | seed (same args + seed = same result) |
| `out` | string |  | also save the song (.8bt/.8bms) |
| `wav` | string |  | also render audio (wav/ogg/mp3/flac) |

### `loopify`

Make a seamless loop: set the loop region, smooth the seam, optionally render a gapless file.

```sh
8bms loopify <src> [--bars] [--out] [--wav]
```

| arg | type | default | help |
|---|---|---|---|
| `src` | string | required | song: file .8bt/.8bms, @handle, @last, demo or gen:style:bars:seed |
| `bars` | integer |  | loop length (default: whole song) |
| `out` | string |  | also save the song (.8bt/.8bms) |
| `wav` | string |  | render the gapless loop (wav/ogg) |

### `soundpack`

Render a retro SFX pack (WAV files + manifest.json + Howler-style sprite).

```sh
8bms soundpack <names> [--out] [--variants] [--seed] [--sprite] [--sr]
```

| arg | type | default | help |
|---|---|---|---|
| `names` | string | `"all"` | comma list of sfx and/or sets (platformer, shooter, ui, rpg) or 'all' |
| `out` | string | `"sfx"` | output folder |
| `variants` | integer | `1` | variants per sound (deterministic) |
| `seed` | integer | `0` | seed (same args + seed = same result) |
| `sprite` | boolean | `true` | also write sprite.wav + sprite.json |
| `sr` | integer | `44100` | sample rate |

### `stems`

Render one WAV per track (plus mix.wav) into a folder.

```sh
8bms stems <src> [--out] [--seamless]
```

| arg | type | default | help |
|---|---|---|---|
| `src` | string | required | song: file .8bt/.8bms, @handle, @last, demo or gen:style:bars:seed |
| `out` | string | `"stems"` | folder |
| `seamless` | boolean | `false` | loop region, tails folded (gapless) |

### `master`

Master to a loudness target: gain to RMS target, soft limiter, fades; renders a file.

```sh
8bms master <src> [--out] [--target-db] [--ceiling-db] [--fade-in] [--fade-out] [--loop]
```

| arg | type | default | help |
|---|---|---|---|
| `src` | string | required | song (file/@handle/demo) or an existing .wav |
| `out` | string | `"master.wav"` | output file |
| `target_db` | number | `-14.0` | target RMS dBFS (~LUFS for chiptune) |
| `ceiling_db` | number | `-1.0` | peak ceiling dBFS |
| `fade_in` | number | `0.0` | seconds |
| `fade_out` | number | `0.0` | seconds |
| `loop` | boolean | `false` | seamless loop render (no fades) |

### `describe`

Describe a song in one paragraph plus key facts (form, chords, range, mood, score).

```sh
8bms describe <src>
```

| arg | type | default | help |
|---|---|---|---|
| `src` | string | required | song: file .8bt/.8bms, @handle, @last, demo or gen:style:bars:seed |

### `critique`

Score a song 0-100 with metrics and concrete tips (also used to rerank compose).

```sh
8bms critique <src>
```

| arg | type | default | help |
|---|---|---|---|
| `src` | string | required | song: file .8bt/.8bms, @handle, @last, demo or gen:style:bars:seed |

### `diff`

Structural diff of two songs: settings, tracks, notes added/removed, arrangement.

```sh
8bms diff <a> <b>
```

| arg | type | default | help |
|---|---|---|---|
| `a` | string | required | first song |
| `b` | string | required | second song |

### `suggest`

ML suggestions: next notes for a pattern, chords per bar, or a groove.

```sh
8bms suggest <src> [--kind] [--track] [--pattern] [--k] [--seed]
```

| arg | type | default | help |
|---|---|---|---|
| `src` | string | required | song: file .8bt/.8bms, @handle, @last, demo or gen:style:bars:seed |
| `kind` | string | `"next"` | next \| chords \| groove |
| `track` | string |  | track name or index (default: lead) |
| `pattern` | string |  | pattern name |
| `k` | integer | `3` | how many |
| `seed` | integer | `0` | seed (same args + seed = same result) |

### `humanize`

Humanize timing and velocity (deterministic per seed).

```sh
8bms humanize <src> [--amount] [--seed] [--out] [--wav]
```

| arg | type | default | help |
|---|---|---|---|
| `src` | string | required | song: file .8bt/.8bms, @handle, @last, demo or gen:style:bars:seed |
| `amount` | number | `0.3` | 0..1 |
| `seed` | integer | `0` | seed (same args + seed = same result) |
| `out` | string |  | also save the song (.8bt/.8bms) |
| `wav` | string |  | also render audio (wav/ogg/mp3/flac) |

### `intent`

Parse plain English into an op call {op, args, confidence} (no side effects).

```sh
8bms intent <text>
```

| arg | type | default | help |
|---|---|---|---|
| `text` | string | required | request in plain English |

### `library`

List the style/preset library: styles, game contexts, grooves, presets, SFX and SFX sets.

```sh
8bms library <what>
```

| arg | type | default | help |
|---|---|---|---|
| `what` | string | `"all"` | all \| styles \| contexts \| grooves \| presets \| sfx |

### `ml`

Tiny ML model: info \| train \| bench (sizes, provenance, latency).

```sh
8bms ml <action> [--out]
```

| arg | type | default | help |
|---|---|---|---|
| `action` | string | `"info"` | info \| train \| bench |
| `out` | string |  | train: where to write the model JSON |
<!-- END GENERATED: ops -->

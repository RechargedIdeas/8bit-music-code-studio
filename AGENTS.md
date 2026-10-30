# AGENTS.md: guide for coding and music agents

> **TL;DR** Run `8bms tools` to list every op. Call ops as `8bms <op> … --fields a,b`, pass songs by handle (`@last`), and chain them with `8bms batch jobs.jsonl`. Every op is deterministic for a `--seed`. The same ops are MCP tools (`8bms mcp`), ACP slash commands (`8bms acp`) and HTTP routes (`8bms serve`). Short index: [llms.txt](llms.txt); everything in one file: [llms-full.txt](llms-full.txt).

Install: see the README ([Install](README.md#install)). If `8bms` isn't on PATH, `python -m eightbit_studio <args>` or `python 8BitMusicCodeStudio.py <args>` work from a checkout.

## Output contract
- Default output is one `key=value` line. Use `--json` for one JSON object, `--fields a,b` to keep only some keys, `-q` for none.
- Exit status is 0 on success and 1 on error. Errors are one line, `error: …` (with `line N` for score errors).
- Flags may go anywhere. `--no-plugins` skips plugin loading.
- Song sources: `file.8bt`, `file.8bms`, `.json`, `demo`, `gen:<style>:<bars>:<seed>`, `-` (stdin), `@<handle>`, `@last`.

## Repo map
| Path | What |
|---|---|
| `8BitMusicCodeStudio.py` | the whole app. The engine is everything above `launch_gui`; then the GUI and the CLI (`build_parser`/`main`) |
| `eightbit_studio/` | import shim: `import eightbit_studio as bms`, plus the `8bms` entry point |
| `models/tiny-v1.json` | 43 KB offline ML model ([docs/ml.md](docs/ml.md)) |
| `schemas/` | JSON Schemas (8bt, 8bms, plugin, ops) and `openapi.json`; generated |
| `docs/` | user and agent docs; `cli-reference.md` ops section is generated |
| `skills/` | agent task recipes (`SKILL.md` with frontmatter) |
| `examples/` | batch jobs, Python/HTTP clients, MCP/ACP configs, game-audio scripts |
| `samples/` | small generated loop and SFX packs |
| `plugins/examples/` | wavetable, chorus, synthwave, mml example plugins |
| `scripts/` | `gen_docs.py` (regenerate docs; `--check`), `new_plugin.py`, `build_all_plugins.py` |
| `tests/` | pytest suite, including `test_docs_sync.py` |
| `install.sh`, `install.ps1` | one-line installers (pipx → uv → venv) |
| `.github/workflows/` | CI matrix + installer smoke tests; release build (no publish) |

## Ops
Generated from the registry by `python scripts/gen_docs.py`. Details and args: [docs/cli-reference.md](docs/cli-reference.md#ops) or `8bms <op> --help`.

<!-- BEGIN GENERATED: ops -->
| op | what it does | CLI |
|---|---|---|
| `render` | Render a song to audio (wav/ogg/mp3/flac). | `8bms render <src> [-o out.wav] [--loop] [--seamless] [--bars 1-8] [--stems DIR]` |
| `export` | Export a song as code/data: js, py, json, score (.8bt), project (.8bms) or plugin formats. | `8bms export <src> [--js\|--py\|--json\|--score\|--project PATH] [--to KIND -o PATH]` |
| `gen` | Generate a song in a style. Returns score text, or writes it to out (.8bt/.8bms). | `8bms gen [--style S] [--bars N] [--seed N] [--key K] [--bpm N] [-o out.8bt] [--wav out.wav]` |
| `info` | Summarize a song. | `8bms info <src>` |
| `check` | Validate a score/project; returns ok or the first error. | `8bms check <src>` |
| `presets` | List instrument presets (and user instruments). | `8bms presets` |
| `styles` | List generator styles. | `8bms styles` |
| `score_help` | Show the .8bt score syntax. | `8bms score-help` |
| `compose` | Compose a new song from a prompt and/or game context; reranks candidates by critique score. | `8bms compose <prompt> [--context] [--style] [--bars] [--key] [--bpm] [--seed] [--model] [--candidates] [--loop] [--out] [--wav]` |
| `variation` | Make a variation: same form and harmony, re-voiced melody/rhythm details. | `8bms variation <src> [--amount] [--seed] [--out] [--wav]` |
| `extend` | Extend a song by N bars: new melody over the existing accompaniment, ending with a fill. | `8bms extend <src> [--bars] [--seed] [--model] [--out] [--wav]` |
| `arrange` | Auto-arrange: keep the melody, add chords (Viterbi), bass and a groove in a style. | `8bms arrange <src> [--style] [--seed] [--out] [--wav]` |
| `remix` | Remix in another style or context: keeps the melody, new tempo/instruments/harmony/groove. | `8bms remix <src> [--style] [--context] [--bpm] [--seed] [--out] [--wav]` |
| `loopify` | Make a seamless loop: set the loop region, smooth the seam, optionally render a gapless file. | `8bms loopify <src> [--bars] [--out] [--wav]` |
| `soundpack` | Render a retro SFX pack (WAV files + manifest.json + Howler-style sprite). | `8bms soundpack <names> [--out] [--variants] [--seed] [--sprite] [--sr]` |
| `stems` | Render one WAV per track (plus mix.wav) into a folder. | `8bms stems <src> [--out] [--seamless]` |
| `master` | Master to a loudness target: gain to RMS target, soft limiter, fades; renders a file. | `8bms master <src> [--out] [--target-db] [--ceiling-db] [--fade-in] [--fade-out] [--loop]` |
| `describe` | Describe a song in one paragraph plus key facts (form, chords, range, mood, score). | `8bms describe <src>` |
| `critique` | Score a song 0-100 with metrics and concrete tips (also used to rerank compose). | `8bms critique <src>` |
| `diff` | Structural diff of two songs: settings, tracks, notes added/removed, arrangement. | `8bms diff <a> <b>` |
| `suggest` | ML suggestions: next notes for a pattern, chords per bar, or a groove. | `8bms suggest <src> [--kind] [--track] [--pattern] [--k] [--seed]` |
| `humanize` | Humanize timing and velocity (deterministic per seed). | `8bms humanize <src> [--amount] [--seed] [--out] [--wav]` |
| `intent` | Parse plain English into an op call {op, args, confidence} (no side effects). | `8bms intent <text>` |
| `library` | List the style/preset library: styles, game contexts, grooves, presets, SFX and SFX sets. | `8bms library <what>` |
| `ml` | Tiny ML model: info \| train \| bench (sizes, provenance, latency). | `8bms ml <action> [--out]` |
<!-- END GENERATED: ops -->

## Recipes
```sh
8bms compose "tense boss fight" --context boss --seed 7 --fields handle,score
8bms remix @last --style chase --fields handle
8bms loopify @last --wav boss-loop.ogg --fields loop_seconds,wav
8bms soundpack platformer -o sfx/ --fields count,manifest
8bms master boss.wav --out boss-master.wav --target-db -14 --fields rms_db,peak_db
8bms critique song.8bt --fields score,tips      8bms describe @last --fields summary
8bms intent "make it spookier and loop it"      # -> which op + args to call
8bms export @last --js song.js                  # ES module: SONG, createPlayer, renderOffline, STEP_EVENTS
8bms do "gen town 8; bpm 100; transpose 2; /render t.wav" --save t.8bt
```
Skills with step-by-step plans:
- [compose-game-soundtrack](skills/compose-game-soundtrack/SKILL.md)
- [make-sfx-pack](skills/make-sfx-pack/SKILL.md)
- [loop-for-web](skills/loop-for-web/SKILL.md)
- [remix-existing-song](skills/remix-existing-song/SKILL.md)
- [score-format-quickref](skills/score-format-quickref/SKILL.md)
- [mcp-setup](skills/mcp-setup/SKILL.md)
- [acp-setup](skills/acp-setup/SKILL.md)
- [build-plugin](skills/build-plugin/SKILL.md)

## .8bt score (the cheapest way to write music)
```
title Boss Theme            # '#'+space starts a comment ("Boss #3" stays intact)
bpm 150; time 4/4; swing 0; key A minor; master .8
loop 1-8                    # bars, 1-based inclusive
fx echo time=.3 feedback=.3 mix=.2     # also lowpass cutoff=, bitcrush bits= downsample=
inst zap pulse duty=.125 a=.001 d=.1 s=.5 r=.05 vib=.2 arp=0,4,7 slide=-12
track lead inst=zap vol=.7 pan=-.2
pat lead A: o5 l8 c e g >c <b g e c        # pat <track> <name> [bars=N]:  (also lead.A, "Pulse 1" A)
pat lead B bars=2: (a g)x4 f/2. r/4
arr lead: A A B -*1 A                      # '-' empty bar, '*N' repeat
track drums drum
pat drums A: kick=x...x...x...x... snare=....x.......x... hat=x.x.x.x.x.x.x.x.  # X = accent
```
Note language:
- Notes: `c4 c#4 db4`, or a bare `c` (uses the current octave, `o5`). `>` / `<` shift the octave.
- Lengths: `l8` sets the default; per note `/4 /8. /16t` (dotted `.`, triplet `t`); a standalone `_` token ties (extends the previous note by the default length).
- Rests and chords: `r/4` is a rest, `[c e g]/2` is a chord, `{Am}/1` `{G7}` `{Fmaj7}` are chord symbols.
- Velocity: `v100` / `v.8` sets the default; per note `c!.6` or `c!110`.
- Repeats: `( … )x4`. `@192` jumps to an absolute tick (PPQ = 96).

Instruments: `8bms presets`. Waves: pulse (duty .125/.25/.5/.75), triangle, noise (`noise_mode=short`), saw, sine, wave (4-bit table), plus plugin waves.

## Agent front-ends
- **MCP:** `8bms mcp`, with tool `studio` plus one tool per op ([docs/mcp.md](docs/mcp.md)).
- **ACP:** `8bms acp`, for Zed and JetBrains; prompts can be music, English or slash commands ([docs/acp.md](docs/acp.md)).
- **HTTP:** `8bms serve --port 8765`, with `GET /tools`, `POST /ops/<name>`, `POST /batch` and `POST /prompt` ([docs/http-api.md](docs/http-api.md)).
- **Terminal studio:** `8bms studio`; one-shot `8bms do "…"`.

## Plugins (short)
```sh
8bms plugin list | info <name> | enable <name> | disable <name>
8bms plugin new <type> <name>      # types: instrument effect style op exporter importer gui command visualizer midi ml
8bms plugin validate <dir> && 8bms plugin test <dir> && 8bms plugin build <dir>   # build = wheel; package = zip
8bms plugin install <dir|zip|wheel|git-url|pip-spec>    8bms plugin uninstall <name>
```
- Search order: `~/.8bms/plugins`, `plugins/` in the cwd (examples load only when run from the repo), `$EIGHTBMS_PLUGIN_PATH`, then entry points `eightbit_studio.plugins`.
- Op plugins become CLI subcommands (`8bms <op> --arg v`), MCP tools, HTTP routes and ACP slash commands automatically.
- Full guide: `docs/plugins/`. Skill: `skills/build-plugin/SKILL.md`. Examples: `plugins/examples/{wavetable,chorus,synthwave,mml}`.

## Working on this repo
- Run `pytest -q` before committing. Tests cover the engine, ops, ML latency budgets, protocols, plugins, the GUI (skipped without Tk/display) and docs sync.
- After changing an op, a schema or a doc, run `python scripts/gen_docs.py`. `tests/test_docs_sync.py` fails when generated files are stale.
- Keep the engine free of tkinter imports, keep every random choice seeded, and use `pathlib` + UTF-8 (CI runs on Windows).
- Do not commit large binaries. Samples stay small and must be regenerable (see `samples/README.md`).

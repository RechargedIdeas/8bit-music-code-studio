# AGENTS.md: 8bms cheat-sheet (for assistants)

`8bms` is on PATH (`/usr/local/bin/8bms` → `~/.local/bin/8bms`, uv tool, editable install of this repo).
Fallback: `python3 /workspace/8bit-music-code-studio/8BitMusicCodeStudio.py <args>`.

Output is a single `key=value` line by default. Use `--json` for one JSON object or `-q` for no output.
Exit status is 0 on success and 1 on error; errors print one line, `error: …` (with `line N` for score errors).
Use `--no-plugins` to skip plugin loading. Flags may go anywhere in argv.

## Most-used commands
```sh
8bms gen --style boss --bars 16 --seed 3 -o boss.8bt     # styles: 8bms styles
8bms render boss.8bt -o boss.wav                        # also .ogg/.mp3/.flac (needs ffmpeg)
8bms render boss.8bt -o loop.wav --seamless             # loop region, tail folded back = gapless
8bms render boss.8bt -o x.wav --bars 5-8 | --loop | --stems stems/
8bms export boss.8bt --js boss.js                       # ES module: SONG, createPlayer, renderOffline, playNote, STEP_EVENTS
8bms export boss.8bt --py boss.py --json boss.json --score out.8bt --project out.8bms
8bms info boss.8bt [--json]     8bms show demo     8bms check song.8bt
8bms do "gen town 8; bpm 100; transpose 2; /render t.wav" --save t.8bt
8bms render - -o x.wav < song.8bt                       # score from stdin
```
Song sources work anywhere a file is accepted: `file.8bt`, `file.8bms`, `.json`, `demo`, `gen:<style>:<bars>:<seed>`, `-` (stdin).

For Luciverse-style JS, use `8bms export song.8bt --js out.js`, then `import {createPlayer} from './out.js'; createPlayer(new AudioContext()).start()`.
Also exported: `STEP_EVENTS`, `STEPS`, `STEP_SECONDS` for step-based engines, and `SONG` (default export).

## .8bt score (the cheapest way to write music)
```
title Boss Theme            # '#'+space starts a comment ("Boss #3" stays intact)
bpm 150; time 4/4; swing 0; key A minor; master .8
loop 1-8                    # bars, 1-based inclusive
fx echo time=.3 feedback=.3 mix=.2     # also lowpass cutoff=, bitcrush bits= downsample=
inst zap pulse duty=.125 a=.001 d=.1 s=.5 r=.05 vib=.2 arp=0,4,7 slide=-12
track lead inst=zap vol=.7 pan=-.2
pat lead.A: o5 l8 c e g >c <b g e c        # pat <track>.<name> [bars=N]:
pat lead.B bars=2: (a g)x4 f/2. r/4
arr lead: A A B -*1 A                      # '-' empty bar, '*N' repeat
track drums drum
pat drums.A: kick=x...x...x...x... snare=....x.......x... hat=x.x.x.x.x.x.x.x.  # X = accent
```
Note language:
- Notes: `c4 c#4 db4`, or a bare `c` (uses the current octave, `o5`). `>` / `<` shift the octave.
- Lengths: `l8` sets the default; per note `/4 /8. /16t` (dotted `.`, triplet `t`); a standalone `_` token ties (extends the previous note by the default length).
- Rests and chords: `r/4` is a rest, `[c e g]/2` is a chord, `{Am}/1` `{G7}` `{Fmaj7}` are chord symbols.
- Velocity: `v100` / `v.8` sets the default; per note `c!.6` or `c!110`.
- Repeats: `( … )x4`. `@192` jumps to an absolute tick (PPQ = 96).

Instruments: `8bms presets`. Waves: pulse (duty .125/.25/.5/.75), triangle, noise (`noise_mode=short`), saw, sine, wave (4-bit table), plus plugin waves.

## Agent front-ends
- **ACP:** `8bms acp` (Zed and opencode; prompts are music/English/slash commands).
- **MCP:** `8bms mcp` (tool `studio` plus one tool per op).
- **HTTP:** `8bms serve --port 8765` (`GET /ops`, `POST /ops/<name>`, `POST /prompt`).
- **Terminal studio:** `8bms repl`. One-shot: `8bms do "…"`.

Studio language (repl/do/ACP/MCP `studio`):
- Notes are appended to the current track.
- Statements work the same as in .8bt.
- English: "make a mellow space song 16 bars", "faster", "transpose up 2", "add drums", "render".
- Slash commands: `/gen /render /export js /show /info /undo /viz roll /op <op> k=v /ml <backend> <prompt>`.

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

## Dev
`make test` (pytest), `make screenshot` (xvfb), `make demo`, `make plugins` (validate+test+build examples).
Engine = everything above `launch_gui` in `8BitMusicCodeStudio.py`; `import eightbit_studio as bms` exposes it.

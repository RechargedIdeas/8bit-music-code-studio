---
name: compose-game-soundtrack
description: Compose a set of looping chiptune tracks for a game (title, overworld, dungeon, boss, victory...) with 8bms, check quality, and export audio plus code. Use when asked for game music, a soundtrack, BGM or level themes.
---

# Compose a game soundtrack

1. List the scenes the game needs and map each to a context: `8bms library contexts`
   (title-screen, menu, overworld, town, forest, cave, dungeon, castle, underwater, space, stealth, chase, battle, boss, final-boss, shop, puzzle, victory, level-clear, game-over, cutscene-sad, credits, lofi-break).
2. Compose each one. Fix `--seed` so reruns are identical, and keep output small with `--fields`:
   ```sh
   8bms compose "heroic overworld" --context overworld --bars 16 --seed 1 --loop -o music/overworld.8bt --fields handle,score,style
   ```
   No context fits? Describe it in the prompt instead (`"slow sad piano-like cutscene"`); `8bms intent "<text>"` shows how it will be read.
3. Check each track: `8bms critique music/overworld.8bt`. Below 80, try `--seed 2..5` or `8bms variation <file> --amount 0.3`; `compose --candidates 6` reranks more drafts by critique score.
4. Keep a family sound: `8bms remix music/overworld.8bt --context dungeon -o music/dungeon.8bt` reuses the melody in a new style.
5. Make loops gapless and mastered:
   ```sh
   8bms loopify music/overworld.8bt -o music/overworld.8bt
   8bms master music/overworld.8bt --loop --target-db -16 -o audio/overworld.ogg
   ```
6. Export code for engines: `8bms export music/overworld.8bt --js web/overworld.js` (Web Audio) or `--py`.

Many tracks at once: put one `compose` line per scene in `jobs.jsonl` and run `8bms batch jobs.jsonl` (see `examples/jobs.jsonl`).
Checks: every file passes `8bms check`, and `critique` is >= 80. Seamless renders have `loop_samples` == file frames.

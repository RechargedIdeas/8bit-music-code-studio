---
name: make-sfx-pack
description: Generate retro sound effects (jump, coin, laser, explosion, UI clicks...) as WAV files plus a manifest and an audio sprite with 8bms soundpack. Use when asked for game SFX, UI sounds or a sound pack.
---

# Make an SFX pack

1. See what exists: `8bms library sfx` lists the 26 effects and the sets `platformer`, `shooter`, `ui`, `rpg`.
2. Render a set or a list (positional, comma or space separated):
   ```sh
   8bms soundpack platformer -o sfx/                       # a whole set
   8bms soundpack jump coin powerup -o sfx/ --variants 3   # 3 pitch/timing variants each
   8bms soundpack ui -o sfx-ui/ --no-sprite                 # skip sprite.wav
   ```
3. Output: `<name>.wav` (16-bit 44.1 kHz), `manifest.json` (name -> file, ms, desc; seed and license), and `sprite.wav` + `sprite.json`. The sprite map uses Howler.js format: `{"sprite": {"jump": [startMs, durMs]}}`.
4. Use it on the web:
   ```js
   const sfx = new Howl({ src: ["sfx/sprite.wav"], sprite: (await (await fetch("sfx/sprite.json")).json()).sprite });
   sfx.play("coin");
   ```
5. Too loud or quiet? `8bms master sfx/jump.wav --target-db -18 -o sfx/jump.wav` works on any WAV.

Determinism: the same `--seed` gives byte-identical files. A sample pack ships in `samples/sfx-platformer/` and `samples/sfx-ui/`.

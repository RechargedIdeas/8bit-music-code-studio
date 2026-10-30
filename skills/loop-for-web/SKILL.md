---
name: loop-for-web
description: Turn a song into a gapless background loop for a website or browser game (OGG/WAV plus an optional Web Audio JS module). Use when asked for looping background music, ambient loops or audio for a web page.
---

# Loop for the web

1. Start from any song: a file, `demo`, a `@handle`, or compose one:
   `8bms compose "calm ambient space" --context space --bars 16 --seed 1 --fields handle`
2. Make the seam clean and render the loop region only:
   ```sh
   8bms loopify @last -o bg.8bt --wav bg.wav --fields loop_seconds,loop_samples,wav
   8bms master bg.8bt --loop --target-db -18 -o bg.ogg   # OGG needs ffmpeg; WAV never does
   ```
   `--seamless`/`--loop` fold the release tail back into the start, so the file length is exactly the loop length and repeats with no click.
3. Play it:
   ```html
   <audio src="bg.ogg" loop autoplay muted></audio>
   ```
   Or tiny and code-only, synthesized in the browser (no audio file):
   ```sh
   8bms export bg.8bt --js bg.js
   ```
   ```js
   import { createPlayer } from "./bg.js";
   document.onclick = () => createPlayer(new AudioContext(), { loop: true }).start();
   ```
4. Check: `8bms describe bg.8bt` (length, tempo) and `8bms critique bg.8bt`.

Size tip: a 16-bar OGG at q6 is about 0.8 MB; the JS export is about 60 KB. A ready-made example is in `samples/mellow-space-loop/`.

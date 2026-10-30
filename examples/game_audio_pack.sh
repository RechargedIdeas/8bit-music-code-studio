#!/usr/bin/env sh
# Make a small game audio kit: title, overworld, boss (looped + mastered) and SFX.
set -e
OUT=${1:-game-audio}
mkdir -p "$OUT"
for ctx in title-screen overworld boss; do
  8bms compose --context "$ctx" --bars 16 --seed 1 --loop -o "$OUT/$ctx.8bt" -q
  8bms master "$OUT/$ctx.8bt" --loop -o "$OUT/$ctx.wav" -q
done
8bms soundpack platformer -o "$OUT/sfx" -q
8bms soundpack ui -o "$OUT/sfx-ui" --no-sprite -q
echo "done: $OUT"

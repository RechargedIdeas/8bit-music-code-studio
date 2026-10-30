# Make a small game audio kit (PowerShell). Usage: .\examples\game_audio_pack.ps1 [outdir]
param([string]$Out = "game-audio")
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
foreach ($ctx in "title-screen", "overworld", "boss") {
    8bms compose --context $ctx --bars 16 --seed 1 --loop -o "$Out/$ctx.8bt" -q
    8bms master "$Out/$ctx.8bt" --loop -o "$Out/$ctx.wav" -q
}
8bms soundpack platformer -o "$Out/sfx" -q
8bms soundpack ui -o "$Out/sfx-ui" --no-sprite -q
Write-Host "done: $Out"

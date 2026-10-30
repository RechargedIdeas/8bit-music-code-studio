# Getting started

> **TL;DR** One line installs `8bms`; then `8bms` opens the GUI, `8bms studio` opens the terminal studio and `8bms compose "..." --wav out.wav` makes music from a sentence.

## 1. Install

| System | One line |
|---|---|
| Linux / macOS | `curl -fsSL https://raw.githubusercontent.com/RechargedIdeas/8bit-music-code-studio/main/install.sh \| sh` |
| Windows (PowerShell) | `irm https://raw.githubusercontent.com/RechargedIdeas/8bit-music-code-studio/main/install.ps1 \| iex` |

What the installer does:
1. Finds Python 3.10+ (preferring one with Tk for the GUI). If none is found, it prints the exact `winget` / `brew` / `apt` / `dnf` / `pacman` command to run.
2. Installs with **pipx**, else **uv tool**, else a private venv at `~/.8bms/venv`. It runs pipx and uv through your Python (`python -m pipx`), installs them for your user if they are missing or broken, and moves on to the next method if one fails.
3. Puts `8bms` on your PATH (`~/.local/bin` or `~/.8bms/bin`; on Windows, your *user* PATH). It never uses sudo or admin rights.
4. Warns if `tkinter` is missing (Linux: `sudo apt-get install python3-tk`); everything except the GUI still works.

Options:
```sh
curl -fsSL .../install.sh | sh -s -- --all            # extras: --all --audio --midi --mcp --acp --ml
sh install.sh --uninstall                             # add --purge to also delete ~/.8bms (handles, plugins)
```
```powershell
$env:EIGHTBMS_EXTRAS = "all"; irm .../install.ps1 | iex
irm .../install.ps1 -OutFile install.ps1; .\install.ps1 -All      # or -Uninstall [-Purge]
```
Re-running the installer upgrades in place. Each run starts with `installer <version> (app commit <sha>)`.

Right after an update, `raw.githubusercontent.com` may serve the previous script for up to 5 minutes (a `?query` string does not help). The script detects that and switches to the current version. To bypass the cache anyway:
```powershell
irm https://api.github.com/repos/RechargedIdeas/8bit-music-code-studio/contents/install.ps1 -Headers @{Accept='application/vnd.github.raw'} | iex
```
```sh
curl -fsSL -H "Accept: application/vnd.github.raw" https://api.github.com/repos/RechargedIdeas/8bit-music-code-studio/contents/install.sh | sh
```
Something failing? Run with `$env:EIGHTBMS_DEBUG = "1"` (Windows) or `sh -s -- --verbose` and paste the output into an issue.

> The raw.githubusercontent.com one-liners work once the repository is public. Until then, clone the repo and run `sh install.sh --source .` (or `.\install.ps1 -Source .`).

### Manual installs
```sh
pipx install "git+https://github.com/RechargedIdeas/8bit-music-code-studio"
uv tool install "eightbit-music-code-studio[all] @ git+https://github.com/RechargedIdeas/8bit-music-code-studio"
pip install "eightbit-music-code-studio[midi] @ git+https://github.com/RechargedIdeas/8bit-music-code-studio"
```
Extras:
- `audio`: sounddevice, for live playback with an accurate playhead.
- `midi`: mido + python-rtmidi, for Akai APC and other controllers.
- `mcp`, `acp`, `ml`: currently empty (stdlib/numpy only). They are kept so install commands stay stable.
- `all`: everything above.
- `dev`: pytest, pillow, build, twine.

From a clone (for development):
```sh
git clone https://github.com/RechargedIdeas/8bit-music-code-studio && cd 8bit-music-code-studio
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```
No install at all: `python 8BitMusicCodeStudio.py <args>` works anywhere NumPy is installed.

## 2. First five minutes

```sh
8bms                                         # GUI; the demo song loads on first launch
8bms compose "mellow space exploration" --bars 16 --seed 1 --wav space.wav
8bms describe @last                          # what did it make?
8bms loopify @last --wav space-loop.wav      # gapless loop
8bms soundpack platformer -o sfx/            # 10 retro SFX + sprite
8bms export @last --js space.js              # Web Audio module: no audio file needed
8bms studio                                  # terminal studio with live meters
```
`@last` is the handle of the most recent result; every song-making command prints one (`handle=@1a2b3c4d`).

## 3. Where next
- Making music by hand: [gui-guide](gui-guide.md), [score-format](score-format.md), [note-language](note-language.md).
- Automating: [cli-reference](cli-reference.md), [python-api](python-api.md), [http-api](http-api.md).
- AI agents: [agent-framework](agent-framework.md), [mcp](mcp.md), [acp](acp.md).
- Shipping audio: [exporting](exporting.md). Problems: [faq](faq.md).

# FAQ and troubleshooting

> **TL;DR** Most problems are a missing optional piece: Tk (GUI), ffmpeg (OGG/MP3/FLAC), sounddevice (playback) or `~/.local/bin` not on PATH. Each case has a one-line fix below.

**`8bms: command not found` after installing.**
Open a new terminal. The installer adds `~/.local/bin` (or `~/.8bms/bin`, or your Windows user PATH) and prints the line it added.
Check with `ls ~/.local/bin/8bms` or `where 8bms`. You can always run `python -m eightbit_studio` or `python 8BitMusicCodeStudio.py` instead.

**The GUI doesn't open: `No module named tkinter`.**
- Debian/Ubuntu: `sudo apt-get install python3-tk`
- Fedora: `sudo dnf install python3-tkinter`
- Arch: `sudo pacman -S tk`
- macOS (Homebrew): `brew install python-tk@3.12`
- Windows: reinstall Python from python.org with "tcl/tk" ticked.

Everything except the GUI works without Tk.

**`error: ffmpeg not found` for .ogg/.mp3/.flac.**
Install ffmpeg (`winget install Gyan.FFmpeg`, `brew install ffmpeg`, `sudo apt-get install ffmpeg`) or export `.wav`.

**No sound when playing.**
`pip install sounddevice` (or the `audio` extra). Without it, playback falls back to simpleaudio, then winsound (Windows), then the OS player (aplay/paplay/afplay).
Rendering to files always works.

**The `midi` extra fails to install.**
`python-rtmidi` has no prebuilt wheel for some Python/OS combinations. The installer then installs the core app without it.
Install a C++ compiler (or use Python 3.12) and re-run with `--midi`.

**Windows shows garbled boxes in the terminal studio.**
Use Windows Terminal or PowerShell 7. The studio enables ANSI (VT) mode itself, and falls back to ASCII meters when the console can't print Unicode. Setting `PYTHONUTF8=1` also helps.

**`irm … | iex` with options?**
`$env:EIGHTBMS_EXTRAS="all"; irm …/install.ps1 | iex`, or download the script and run `.\install.ps1 -All`. Scripts blocked? Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

**The Windows installer says "The system cannot find the path specified."**
That message comes from `cmd.exe`, for example from a leftover `pipx`/`uv` launcher of a Python that was removed, or from a cmd.exe *AutoRun* entry pointing at a missing file. Installer 1.1.1 and later never use those launchers: they run `python -m pipx`, reinstall pipx if it is broken, and fall back to uv and then a plain venv. If you still see the old behaviour, you got a cached copy of the old script (see the first output line, `installer <version>`); run `irm https://api.github.com/repos/RechargedIdeas/8bit-music-code-studio/contents/install.ps1 -Headers @{Accept='application/vnd.github.raw'} | iex`. If it still fails, set `$env:EIGHTBMS_DEBUG = "1"` and paste the output into an issue.

**How do I uninstall?**
`sh install.sh --uninstall` or `.\install.ps1 -Uninstall`. Add `--purge` / `-Purge` to delete `~/.8bms`, which holds handles, sessions, plugins and instruments.

**Same command, different song?**
Pass `--seed`. With a seed, every op is deterministic. Without one, `compose` uses seed 0 and `gen` picks a random seed.

**Where are my handles and settings?**
In `~/.8bms/`: `handles/`, `acp-sessions/`, `plugins/`, `instruments/`, `recent.json`. Set `EIGHTBMS_HOME` to move them.

**Is anything sent over the network?**
No. The app, the ML model and every front-end work offline. `8bms serve` binds to 127.0.0.1. Plugin tests block network access unless the plugin's manifest grants it.

**A test is slow on my machine.**
Latency tests honour `EIGHTBMS_BUDGET_SCALE=4`.

# Contributing

> **TL;DR** Fork the repo and run `pip install -e ".[dev]"`, then make your change. Run `pytest -q` and `python scripts/gen_docs.py`, then open a PR. CI must pass on Linux, macOS and Windows.

## Setup
```sh
git clone https://github.com/RechargedIdeas/8bit-music-code-studio && cd 8bit-music-code-studio
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"                           # + ".[all]" for playback/MIDI
pytest -q                                         # GUI tests skip without Tk or a display (use xvfb-run on Linux)
```

## Where things go
- **Engine features** (synth, score language, ops) go above `launch_gui` in `8BitMusicCodeStudio.py` and must not import tkinter.
- **New ops** use `@register_op(...)` with typed params and help text. This makes the op appear in the CLI, HTTP, MCP, ACP and the docs automatically. Add a test in `tests/test_agent_ops.py`.
- **Instruments, styles, effects and exporters** usually fit better as a plugin: `8bms plugin new <type> <name>`. See [docs/plugins](docs/plugins/README.md).
- **Docs:** each page starts with a `> **TL;DR**` line and has copy-paste examples. After changing ops, schemas or docs, run `python scripts/gen_docs.py`. `tests/test_docs_sync.py` checks generated files, links, skills frontmatter and CLI examples.

## Rules of thumb
- Determinism: every random choice takes a seed, so the same args give the same output.
- Cross-platform: use `pathlib`, UTF-8 I/O, no symlinks or shell-isms in Python, and test Windows paths.
- Agent-friendly output: one terse line by default, JSON with `--json`, small results (handles, not score text).
- Performance budgets live in `tests/test_ml.py`. Don't loosen them without a reason in the PR.
- No large binaries. Samples must be small and regenerable (`samples/README.md`); prefer Vorbis q0 for demo audio.
- No secrets, tokens or personal paths in code, docs or examples.

## Commits and PRs
- Keep PRs focused. Describe what changed and how you tested it, and add a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md).
- Installer changes: run `shellcheck -s sh install.sh` and test `install.ps1` with PowerShell 7 (`pwsh`). CI smoke-tests both.

## Releasing (maintainers)
1. Bump `version` in `pyproject.toml` and `APP_VERSION`, then update the CHANGELOG.
2. Tag `vX.Y.Z` and push. The `release` workflow builds the sdist and wheel, runs `twine check`, verifies the version matches the tag, and uploads them as artifacts.
3. Publishing to PyPI is a separate, manual decision. The workflow does not publish.

By contributing you agree your contributions are licensed under the [MIT License](LICENSE).

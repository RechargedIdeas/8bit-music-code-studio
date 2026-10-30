# Testing, building, publishing

> **TL;DR** Run `validate`, then `test` (sandboxed), then `build` (wheel) and `package` (zip). Share the zip, a git URL, or a PyPI package that uses the `eightbit_studio.plugins` entry point.

```sh
8bms plugin validate <dir>   # schema + api_version + import + dry-run register + declared types
8bms plugin test <dir>       # pytest in a sandbox: temp EIGHTBMS_HOME, other plugins off, network blocked*
8bms plugin build <dir>      # dist/eightbit_studio_plugin_<name>-<ver>-py3-none-any.whl (entry point included)
8bms plugin package <dir>    # dist/<name>-<ver>.zip (installable with `8bms plugin install x.zip`)
python scripts/build_all_plugins.py [dirs…]   # validate+test+build+package all of plugins/**
```
\* Network stays blocked unless the manifest grants `network`.

Tests import the host as `import eightbit_studio as bms` and load the plugin with `bms.load_plugin_dir(<plugin root>)`. See any template's `tests/test_plugin.py`.

## Versioning
- Bump `version` in plugin.toml (and pyproject.toml if you keep one) using semver.
- Widen `api_version` only after testing against the new host.

## Distribution
- **Folder / zip:** `8bms plugin install ./my-fx` or `install my-fx-1.0.0.zip`. This copies the plugin to `~/.8bms/plugins/`.
- **Git:** `8bms plugin install https://github.com/you/my-fx.git`.
- **Wheel / PyPI:** `pip install eightbit-studio-plugin-my-fx`. It's discovered via the `eightbit_studio.plugins` entry point.
- **Project-local:** commit it under `plugins/` in your music project.

## CI
Every scaffold ships `.github/workflows/ci.yml`; the same file is also at `templates/plugin-ci.yml`. It checks out 8bms, installs it, then runs validate, test, build and package, and uploads `dist/`.
The main repo's workflow builds the example plugins too (`make plugins`).

# 8bms plugins: overview

A plugin is a folder (or an installed Python package) containing a `plugin.toml` manifest and a module with `register(api)`.
`register` calls `api.add_*` methods; every registration is tracked so the plugin can be unloaded or disabled cleanly.

```
my-fx/
  plugin.toml            # manifest (see manifest.md)
  bms_my_fx/__init__.py  # def register(api): ...
  tests/test_plugin.py   # run by `8bms plugin test`
  example/example.8bt    # a song that uses the plugin
  pyproject.toml         # optional: lets pip build/install it
  .github/workflows/ci.yml
  README.md
```

## Lifecycle
1. **Discover**, first match per name wins:
   1. `~/.8bms/plugins/` (where `8bms plugin install` puts things; override the home with `EIGHTBMS_HOME`),
   2. `./plugins/` (current project; nested one level, e.g. `plugins/examples/*`),
   3. `$EIGHTBMS_PLUGIN_PATH` (os.pathsep-separated),
   4. entry points in group **`eightbit_studio.plugins`** (pip-installed wheels).
2. **Validate**: the manifest is checked against the [JSON Schema](plugin.schema.json), and `api_version` must accept the host API (currently 1.0.0).
3. **Load**: import the entry, then call `register(PluginAPI)`. If either raises, the plugin is marked with its error and anything it registered is rolled back. The host keeps going.
4. **Run**: plugin callables are wrapped by `api.guard`. Exceptions are recorded in `plugin info <name>`; waves fall back to a square and effects to pass-through, so a render never dies.
5. **Disable/enable**: `8bms plugin disable <name>`, stored in `~/.8bms/plugins.json`. `EIGHTBMS_NO_PLUGINS=1` or `--no-plugins` skips all plugins.

## Quick start
```sh
8bms plugin new effect my-fx      # or: python scripts/new_plugin.py effect my-fx
cd my-fx && $EDITOR bms_my_fx/__init__.py
8bms plugin validate . && 8bms plugin test .
8bms render example/example.8bt -o /tmp/try.wav     # run from a folder whose plugins/ contains it, or install it:
8bms plugin install .
8bms plugin build .               # dist/*.whl (entry point included)   ;   8bms plugin package . -> dist/*.zip
```

More detail:
- [api.md](api.md): the `PluginAPI` reference.
- [types.md](types.md): every plugin type with examples.
- [manifest.md](manifest.md): `plugin.toml`, semver and permissions.
- [publishing.md](publishing.md): testing, building, CI and distribution.

# Mml (exporter plugin)

A `exporter` plugin for [8Bit Music Code Studio](https://github.com/RechargedIdeas/8bit-music-code-studio).

```bash
8bms plugin validate .     # manifest + API compatibility + dry load
8bms plugin test .         # sandboxed pytest
8bms plugin install .      # copy into ~/.8bms/plugins
8bms plugin build .        # dist/*.whl  (pip-installable, entry point group eightbit_studio.plugins)
8bms plugin package .      # dist/*.zip  (8bms plugin install dist/x.zip)
```

See `example/example.8bt` for a song that uses it.

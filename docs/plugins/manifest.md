# plugin.toml

> **TL;DR** `plugin.toml` declares name, semver version, `api_version`, entry module, types and permissions. `8bms plugin validate` checks it against `schemas/plugin.schema.json`.

```toml
name = "my-fx"                  # ^[a-z][a-z0-9_-]{1,40}$, unique
version = "1.2.0"               # semver MAJOR.MINOR.PATCH[-pre][+build]
api_version = "^1.0"            # host API range this plugin works with
types = ["effect"]              # one or more of the types below
entry = "bms_my_fx:register"    # module[.sub]:function (function defaults to register)
description = "Stereo widener"  # 3-120 chars
permissions = []                # filesystem | network | midi | audio | subprocess
author = "you"                  # optional: author, license, homepage, tags
license = "MIT"
```
`types`: `instrument effect style op exporter importer gui command visualizer midi ml`.
The machine-readable schema is in [plugin.schema.json](plugin.schema.json). Unknown keys are rejected.
`8bms plugin validate` also checks that every declared type actually registered something.

## api_version ranges
| spec | meaning |
|---|---|
| `^1.0` | >=1.0.0 and <2.0.0 (recommended) |
| `~1.2` | >=1.2.0 and <1.3.0 |
| `>=1.0,<2` | comma = AND |
| `1.x`, `1` | major 1 |
| `==1.0.0`, `1.0.0` | exact |
| `*` | anything |

The host API follows semver. Additive changes bump the minor version; breaking changes bump the major.

## Permissions
These declare what a plugin needs; they appear in `plugin list/info` and in the install output.
- `network`: without it, `8bms plugin test` runs the plugin's tests with sockets blocked (enforced in the sandbox).
- `filesystem`, `midi`, `audio`, `subprocess`: currently advisory. They document intent, and reviewers and users see them.

Plugins run in-process with normal Python rights, so install only plugins you trust.

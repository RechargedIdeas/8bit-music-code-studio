#!/usr/bin/env python3
"""Scaffold a new 8Bit Music Code Studio plugin (same as `8bms plugin new`).

    python scripts/new_plugin.py effect my-fx [--dir plugins]
    then: 8bms plugin validate plugins/my-fx && 8bms plugin test plugins/my-fx
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import eightbit_studio as bms  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("type", choices=bms.PLUGIN_TYPES)
    ap.add_argument("name")
    ap.add_argument("--dir", default="plugins")
    a = ap.parse_args()
    root = bms.scaffold_plugin(a.type, a.name, Path(a.dir))
    res = bms.validate_plugin(root)
    print(f"created {root} ({'valid' if res['ok'] else 'INVALID: ' + '; '.join(res['errors'])})")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

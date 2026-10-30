#!/usr/bin/env python3
"""Validate, test, build (.whl) and package (.zip) every plugin under the given
folders (default: plugins/examples and plugins/). Exits non-zero on any failure.

    python scripts/build_all_plugins.py [--no-test] [--out dist/plugins] [DIR ...]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import eightbit_studio as bms  # noqa: E402


def find(dirs):
    seen = []
    for d in dirs:
        for mf in sorted(Path(d).rglob("plugin.toml")):
            if "dist" in mf.parts or "templates" in mf.parts:
                continue
            if mf.parent not in seen:
                seen.append(mf.parent)
    return seen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="*", default=["plugins"])
    ap.add_argument("--no-test", action="store_true")
    ap.add_argument("--out", default="dist/plugins")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    bad = 0
    for root in find(a.dirs):
        v = bms.validate_plugin(root)
        line = f"{v['name']:14} validate={'ok' if v['ok'] else 'FAIL'}"
        if v["ok"] and not a.no_test:
            t = bms.test_plugin(root)
            line += f" test={'ok' if t['ok'] else 'FAIL'} ({t['summary']})"
            v["ok"] = t["ok"]
            if not t["ok"]:
                print(t["output"])
        if v["ok"]:
            whl = bms.build_plugin_wheel(root, out)
            z = bms.package_plugin_zip(root, out)
            line += f" -> {whl.name}, {z.name}"
        else:
            line += "  " + "; ".join(v["errors"])
            bad += 1
        print(line)
    print(f"{'FAILED: ' + str(bad) if bad else 'all plugins ok'} -> {out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

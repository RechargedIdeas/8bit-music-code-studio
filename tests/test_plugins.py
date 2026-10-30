import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

import eightbit_studio as bms
from conftest import APP

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "plugins" / "examples"


def write_plugin(root: Path, name: str, body: str, types=("op",), perms=(), version="1.0.0", api="^1.0"):
    d = root / name
    d.mkdir(parents=True)
    (d / "plugin.toml").write_text(
        f'name = "{name}"\nversion = "{version}"\napi_version = "{api}"\ntypes = {json.dumps(list(types))}\n'
        f'entry = "plug:register"\npermissions = {json.dumps(list(perms))}\ndescription = "test plugin {name}"\n')
    (d / "plug.py").write_text(body)
    return d


GOOD = '''
def register(api):
    def shout(text="hi", times=2):
        "Repeat text."
        return {"out": " ".join([text.upper()] * int(times))}
    api.add_op("shout", shout, help="shout text", text=str, times=int)
'''


@pytest.fixture
def manager(tmp_path):
    made = []

    def make(paths):
        pm = bms.PluginManager(search_paths=paths, use_entry_points=False, include_defaults=False)
        pm.load_all()
        made.append(pm)
        return pm
    yield make
    for pm in made:
        for n in list(pm.plugins):
            pm.unload(n)


@pytest.mark.parametrize("spec,ver,ok", [
    ("^1.0", "1.4.2", True), ("^1.0", "2.0.0", False), ("^0.3", "0.4.0", False), ("~1.2", "1.2.9", True),
    ("~1.2", "1.3.0", False), (">=1.0,<2", "1.9.9", True), (">=1.0,<2", "2.0.0", False), ("1.x", "1.0.5", True),
    ("*", "9.9.9", True), ("==1.0.0", "1.0.0", True), ("1", "2.0.0", False)])
def test_semver(spec, ver, ok):
    assert bms.version_satisfies(spec, ver) is ok


def test_manifest_schema():
    good = {"name": "abc", "version": "1.2.3", "api_version": "^1.0", "types": ["op"], "entry": "m:register", "description": "fine"}
    assert bms.validate_manifest(good) == []
    for bad in ({**good, "name": "Bad Name"}, {**good, "version": "1.0"}, {**good, "types": ["laser"]},
                {**good, "permissions": ["root"]}, {**good, "extra": 1}, {k: v for k, v in good.items() if k != "entry"},
                {**good, "api_version": "^9.0"}):
        assert bms.validate_manifest(bad), bad
    schema = json.loads(subprocess.run([sys.executable, str(APP), "plugin", "schema"], capture_output=True, text=True).stdout or "{}") \
        if False else bms.MANIFEST_SCHEMA
    assert schema["required"] and "network" in schema["properties"]["permissions"]["items"]["enum"]


def test_discovery_examples_and_shadowing(tmp_path, manager):
    write_plugin(tmp_path, "wavetable", GOOD)          # same name as example -> shadowed (first path wins)
    pm = manager([EXAMPLES, tmp_path])
    names = {p.name for p in pm.plugins.values()}
    assert {"wavetable", "chorus", "synthwave", "mml"} <= names
    assert any("shadowed" in p for p in pm.problems)
    assert all(p.loaded and not p.error for p in pm.plugins.values())
    assert "wavetable" in bms.EXTRA_WAVES and "chorus" in bms.EXTRA_FX
    assert "synthwave" in bms.STYLES and "mml" in bms.EXPORTERS


def test_examples_produce_audio(manager):
    manager([EXAMPLES])
    song = bms.generate_song("synthwave", bars=2, seed=3)
    song.effects.append({"type": "chorus", "params": {"mix": 0.5}})
    song.tracks[0].instrument = "wt_glass"
    y = bms.render_song(song)
    assert y.shape[1] == 2 and np.abs(y).max() > 0.05
    ext, fn = bms.EXPORTERS["mml"]
    assert ext == ".mml" and "t" in fn(song).lower()


def test_isolation_of_broken_plugins(tmp_path, manager):
    write_plugin(tmp_path, "boom", "raise RuntimeError('import time crash')\n")
    write_plugin(tmp_path, "badreg", "def register(api):\n    api.add_op('half', lambda: 1)\n    raise ValueError('nope')\n")
    write_plugin(tmp_path, "oldapi", GOOD, api="^0.1")
    write_plugin(tmp_path, "badwave", "def register(api):\n    api.add_wave('explode', lambda ph, t, inst: 1/0)\n", types=("instrument",))
    write_plugin(tmp_path, "good", GOOD)
    pm = manager([tmp_path])
    p = pm.plugins
    assert "import time crash" in p["boom"].error and not p["boom"].loaded
    assert "nope" in p["badreg"].error and "half" not in bms.OPS          # partial registration rolled back
    assert "not compatible" in (p["oldapi"].error or "")
    assert p["good"].loaded and "shout" in bms.OPS
    # runtime failure inside a wave falls back instead of crashing the render
    inst = bms.Instrument(name="x", wave="explode")
    y = bms.render_note_preview(inst, 60, 0.1)
    assert np.isfinite(y).all() and p["badwave"].errors
    pm.unload("good")
    assert "shout" not in bms.OPS


def test_ops_auto_exposed_everywhere(tmp_path, manager):
    write_plugin(tmp_path, "good", GOOD)
    manager([tmp_path])
    assert bms.run_op("shout", text="yo", times=3) == {"out": "YO YO YO"}
    out = io.StringIO()
    bms.run_mcp(io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
                            + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "shout", "arguments": {"text": "a"}}}) + "\n"), out)
    lines = [json.loads(l) for l in out.getvalue().splitlines()]
    tool = next(t for t in lines[0]["result"]["tools"] if t["name"] == "shout")
    assert tool["inputSchema"]["properties"]["times"]["type"] == "integer"
    assert "A A" in lines[1]["result"]["content"][0]["text"]
    it = bms.Interpreter(bms.new_song())
    assert "B B" in it.execute("/op shout text=b")
    # CLI subcommand + ACP/HTTP use the same registry; check the CLI in a fresh process
    env = {**os.environ, "EIGHTBMS_NO_PLUGINS": "0", "EIGHTBMS_PLUGIN_PATH": str(tmp_path)}
    r = subprocess.run([sys.executable, str(APP), "shout", "--text", "cli", "--times", "2"], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode == 0 and "CLI CLI" in r.stdout, r.stderr


def test_enable_disable_cli(tmp_path):
    write_plugin(tmp_path / "pl", "good", GOOD)
    env = {**os.environ, "EIGHTBMS_NO_PLUGINS": "0", "EIGHTBMS_PLUGIN_PATH": str(tmp_path / "pl"), "EIGHTBMS_HOME": str(tmp_path / "home")}

    def cli(*a):
        return subprocess.run([sys.executable, str(APP), *a], capture_output=True, text=True, env=env, cwd=tmp_path)
    lst = json.loads(cli("--json", "plugin", "list").stdout)
    assert any(p["name"] == "good" and p["enabled"] for p in lst["plugins"])
    assert cli("plugin", "disable", "good").returncode == 0
    assert cli("shout").returncode != 0
    assert cli("plugin", "enable", "good").returncode == 0
    assert "HI HI" in cli("shout").stdout


def test_install_uninstall_folder(tmp_path):
    env = {**os.environ, "EIGHTBMS_NO_PLUGINS": "0", "EIGHTBMS_HOME": str(tmp_path / "home")}
    r = subprocess.run([sys.executable, str(APP), "plugin", "install", str(EXAMPLES / "chorus")], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "home" / "plugins" / "chorus" / "plugin.toml").exists()
    r = subprocess.run([sys.executable, str(APP), "plugin", "uninstall", "chorus"], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode == 0 and not (tmp_path / "home" / "plugins" / "chorus").exists()


def test_sandbox_blocks_network(tmp_path):
    d = write_plugin(tmp_path, "netty", GOOD)
    (d / "tests").mkdir()
    (d / "tests" / "test_net.py").write_text(
        "import socket, pytest\n\ndef test_no_net():\n    with pytest.raises(PermissionError):\n"
        "        socket.create_connection(('1.1.1.1', 80), timeout=1)\n")
    assert bms.test_plugin(d, timeout=120)["ok"]


@pytest.mark.parametrize("ptype", bms.PLUGIN_TYPES)
def test_scaffold_build_validate_test_roundtrip(tmp_path, ptype):
    root = bms.scaffold_plugin(ptype, f"my-{ptype}", tmp_path)
    v = bms.validate_plugin(root)
    assert v["ok"], v
    t = bms.test_plugin(root, timeout=300)
    assert t["ok"], t
    whl = bms.build_plugin_wheel(root)
    with zipfile.ZipFile(whl) as z:
        names = z.namelist()
        assert any(n.endswith("entry_points.txt") for n in names)
        ep = z.read(next(n for n in names if n.endswith("entry_points.txt"))).decode()
        assert bms.EP_GROUP in ep
        assert any(n.endswith("/plugin.toml") for n in names)
    zp = bms.package_plugin_zip(root)
    assert zp.exists() and zipfile.is_zipfile(zp)


@pytest.mark.parametrize("name", ["wavetable", "chorus", "synthwave", "mml"])
def test_examples_validate(name):
    assert bms.validate_plugin(EXAMPLES / name)["ok"]

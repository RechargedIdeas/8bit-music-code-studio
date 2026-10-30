"""Intent ops: one registry -> Python, CLI, MCP, HTTP. Handles, --fields, batch, determinism."""
import json
import subprocess
import sys
import wave

import eightbit_studio as bms
from conftest import APP

INTENT_OPS = ["compose", "variation", "extend", "remix", "loopify", "soundpack", "stems", "master", "describe", "diff", "critique"]


def cli(*args, inp=None, cwd=None):
    return subprocess.run([sys.executable, str(APP), *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          input=inp, cwd=cwd, timeout=180)


def test_registry_has_intent_ops():
    for n in INTENT_OPS + ["suggest", "humanize", "arrange", "intent", "library", "ml"]:
        assert n in bms.OPS, n
        sch = bms.OPS[n].json_schema()
        assert sch["type"] == "object" and "_fields" in sch["properties"]


def test_compose_deterministic_and_handle():
    a = bms.run_op("compose", prompt="tense boss fight", bars=8, seed=3)
    b = bms.run_op("compose", prompt="tense boss fight", bars=8, seed=3)
    assert a["handle"] == b["handle"] and a["handle"].startswith("@")
    assert a["style"] == "boss" and a["bars"] == 8 and 0 <= a["score"] <= 100
    c = bms.run_op("compose", prompt="tense boss fight", bars=8, seed=4)
    assert c["handle"] != a["handle"]
    song = bms.load_any(a["handle"])
    assert song.length_bars() == 8
    assert bms.load_any("@last").to_dict() == bms.load_any(c["handle"]).to_dict()


def test_every_context_composes():
    for ctx in bms.GAME_CONTEXTS:
        r = bms.run_op("compose", context=ctx, bars=4, seed=1, candidates=1, _fields="handle,context,style")
        assert r["context"] == ctx and r["style"] in bms.STYLES, ctx


def test_op_chain(tmp_path):
    a = bms.run_op("compose", prompt="calm town", bars=8, seed=1)["handle"]
    v = bms.run_op("variation", src=a, amount=0.3, seed=2)
    assert v["bars"] == 8 and v["changed"] > 0
    e = bms.run_op("extend", src=v["handle"], bars=4)
    assert e["bars"] == 12 and e["added_bars"] == 4
    r = bms.run_op("remix", src=a, style="chill")
    assert r["style"] == "chill" and r["handle"] != a
    lp = bms.run_op("loopify", src=e["handle"], wav=str(tmp_path / "l.wav"))
    with wave.open(lp["wav"]) as w:
        assert w.getnframes() == lp["loop_samples"]
    d = bms.run_op("describe", src=a)
    assert d["summary"] and d["bars"] == 8 and d["chords"]
    c = bms.run_op("critique", src=a)
    assert 0 <= c["score"] <= 100 and c["tips"]
    df = bms.run_op("diff", a=a, b=v["handle"])
    assert df["same"] is False and df["changes"]
    assert bms.run_op("diff", a=a, b=a)["same"] is True


def test_soundpack_master_stems(tmp_path):
    sp = bms.run_op("soundpack", names="jump,coin,select,confirm", out=str(tmp_path / "sfx"))
    man = json.loads(open(sp["manifest"], encoding="utf-8").read())
    assert {"jump", "coin", "select", "confirm"} <= set(man["sounds"]) and sp["count"] == len(man["sounds"])
    assert (tmp_path / "sfx" / "sprite.wav").exists()
    st = bms.run_op("stems", src="demo", out=str(tmp_path / "stems"))
    assert len(st["stems"]) >= 3
    m = bms.run_op("master", src="demo", out=str(tmp_path / "m.wav"), target_db=-14)
    assert abs(m["rms_db"] + 14) < 1.5 and m["peak_db"] <= -0.5
    m2 = bms.run_op("master", src=str(tmp_path / "m.wav"), out=str(tmp_path / "m2.wav"))   # an existing .wav
    assert m2["seconds"] > 1


def test_fields_trim_output():
    r = bms.run_op("compose", prompt="chase", bars=4, seed=1, _fields="handle,score")
    assert set(r) == {"handle", "score"}


def test_cli_positionals_fields_and_json(tmp_path):
    env_home = str(tmp_path / "home")
    import os
    env = dict(os.environ, EIGHTBMS_HOME=env_home)
    r = subprocess.run([sys.executable, str(APP), "compose", "tense", "boss", "fight", "--bars", "4", "--seed", "7",
                        "--json", "--fields", "handle,style"], capture_output=True, text=True, encoding="utf-8", env=env, timeout=180)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert set(d) == {"handle", "style"} and d["style"] == "boss"
    r = subprocess.run([sys.executable, str(APP), "describe", "@last"], capture_output=True, text=True, encoding="utf-8", env=env, timeout=180)
    assert r.returncode == 0 and "4-bar" in r.stdout
    r = subprocess.run([sys.executable, str(APP), "soundpack", "jump", "coin", "-o", str(tmp_path / "s"), "--fields", "count"],
                       capture_output=True, text=True, encoding="utf-8", env=env, timeout=180)
    assert r.returncode == 0 and "count=2" in r.stdout


def test_tools_and_openapi():
    tools = bms.op_tools()
    names = {t["name"] for t in tools}
    assert set(INTENT_OPS) <= names
    for t in tools:
        assert t["cli"].startswith("8bms ") and t["http"].startswith("POST /ops/") and t["inputSchema"]["type"] == "object"
    spec = bms.openapi_spec()
    assert spec["openapi"].startswith("3.1")
    for n in INTENT_OPS:
        assert f"/ops/{n}" in spec["paths"]
    r = cli("tools", "compose", "--json")
    assert r.returncode == 0 and json.loads(r.stdout)["name"] == "compose"


def test_batch_jobs(tmp_path):
    jobs = tmp_path / "jobs.jsonl"
    jobs.write_text("\n".join([
        json.dumps({"id": "a", "op": "compose", "args": {"prompt": "calm town", "bars": 4, "seed": 1}, "fields": "handle"}),
        json.dumps({"id": "b", "op": "extend", "args": {"src": "$a", "bars": 4}, "fields": "bars"}),
        json.dumps({"id": "c", "op": "loopify", "args": {"src": "$prev", "wav": str(tmp_path / "x.wav")}, "fields": "loop_bars"}),
        json.dumps({"id": "d", "op": "nope"}),
    ]), encoding="utf-8")
    r = cli("batch", str(jobs), "-o", str(tmp_path / "res.jsonl"))
    assert r.returncode == 1  # one job failed
    res = [json.loads(x) for x in (tmp_path / "res.jsonl").read_text(encoding="utf-8").splitlines()]
    by = {x["id"]: x for x in res}
    assert by["b"]["result"] == {"bars": 8} and by["c"]["result"] == {"loop_bars": 8}
    assert by["d"]["ok"] is False and "unknown op" in by["d"]["error"]


def test_mcp_lists_intent_ops():
    import io
    out = io.StringIO()
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "compose", "arguments": {"prompt": "chase", "bars": 4, "_fields": "handle"}}}]
    bms.run_mcp(io.StringIO("".join(json.dumps(m) + "\n" for m in msgs)), out)
    res = {m["id"]: m for m in map(json.loads, out.getvalue().splitlines())}
    names = {t["name"] for t in res[2]["result"]["tools"]}
    assert set(INTENT_OPS) <= names
    body = json.loads(res[3]["result"]["content"][0]["text"])
    assert list(body) == ["handle"]


def test_interpreter_english_routes_to_ops():
    it = bms.Interpreter(bms.new_song())
    out = it.execute("make a boss theme 8 bars")
    assert out.startswith("ok @") and it.song.length_bars() == 8
    assert "score=" in it.execute("critique this")
    assert "loop" in it.execute("make it loop").lower()
    assert it.execute("/describe")

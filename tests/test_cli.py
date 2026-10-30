import json
import subprocess
import sys
import wave

import pytest

from conftest import APP


def run(*args, cwd=None, inp=None):
    r = subprocess.run([sys.executable, str(APP), *args], capture_output=True, text=True, cwd=cwd, input=inp, timeout=180)
    return r


def test_version_and_help():
    assert "8Bit Music Code Studio" in run("--version").stdout
    h = run("--help").stdout
    for cmd in ("render", "export", "gen", "acp", "mcp", "plugin"):
        assert cmd in h


def test_gen_render_export_terse(tmp_path):
    r = run("gen", "--style", "town", "--bars", "4", "--seed", "1", "-o", "t.8bt", cwd=tmp_path)
    assert r.returncode == 0 and r.stdout.count("\n") == 1 and "path=" in r.stdout
    r = run("render", "t.8bt", "-o", "t.wav", cwd=tmp_path)
    assert r.returncode == 0 and r.stdout.startswith("path=")
    with wave.open(str(tmp_path / "t.wav")) as w:
        assert w.getframerate() == 44100 and w.getsampwidth() == 2
    r = run("export", "t.8bt", "--js", "t.js", "--py", "t.py", "--json", "t.json", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert all((tmp_path / f).exists() for f in ("t.js", "t.py", "t.json"))


def test_json_and_quiet_modes(tmp_path):
    r = run("--json", "info", "demo")
    d = json.loads(r.stdout)
    assert d["bars"] >= 8 and d["tracks"]
    r = run("render", "demo", "-o", str(tmp_path / "q.wav"), "--bars", "1-1", "--quiet")
    assert r.returncode == 0 and r.stdout == ""
    r = run("--json", "check", str(tmp_path / "missing.8bt"))
    assert r.returncode == 1 and json.loads(r.stdout)["ok"] is False


def test_errors_are_one_line(tmp_path):
    (tmp_path / "bad.8bt").write_text("track a\npat a.A: c4 h9\n")
    r = run("check", "bad.8bt", cwd=tmp_path)
    assert r.returncode == 1 and r.stderr.strip().count("\n") == 0 and "line 2" in r.stderr


def test_gen_prints_score_to_stdout():
    r = run("gen", "--style", "boss", "--bars", "2", "--seed", "5")
    assert r.returncode == 0 and r.stdout.lstrip().startswith("#") and "track" in r.stdout


def test_do_and_stdin(tmp_path):
    r = run("do", "bpm 100; c4 e g; /render x.wav", "--save", "x.8bt", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "x.wav").exists() and (tmp_path / "x.8bt").exists()
    r = run("render", "-", "-o", str(tmp_path / "s.wav"), inp="bpm 120\ntrack a\npat a.A: c d e f\n")
    assert r.returncode == 0, r.stderr


def test_op_and_presets():
    assert "lead" in run("presets").stdout.split()
    assert "boss" in run("styles").stdout.split()
    r = run("--json", "op", "info", "src=demo")
    assert json.loads(r.stdout)["title"]


@pytest.mark.skipif(sys.platform == "win32", reason="posix")
def test_score_help():
    assert "pat" in run("score-help").stdout

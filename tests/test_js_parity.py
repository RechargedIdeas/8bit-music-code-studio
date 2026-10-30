"""JS export parity: the exported ES module's pure-JS renderer (renderSamples) must
match the Python render, including duty sweep and bitcrush. Runs the module in node."""
import json
import shutil
import subprocess

import numpy as np
import pytest

import eightbit_studio as bms

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
SR = 22050

FAKE_AUDIO = """
const param = () => ({ value: 0, setValueAtTime(){}, linearRampToValueAtTime(){}, exponentialRampToValueAtTime(){}, setTargetAtTime(){}, cancelScheduledValues(){}, setValueCurveAtTime(){} });
globalThis.__started = 0; globalThis.__buffers = 0; globalThis.__shapers = 0;
const node = () => ({ connect(x){ return x || this; }, disconnect(){}, start(){ globalThis.__started++; }, stop(){}, gain: param(), frequency: param(), detune: param(), pan: param(), delayTime: param(), Q: param(), buffer: null, loop: false, type: '', curve: null, setPeriodicWave(){}, playbackRate: param() });
globalThis.AudioContext = class { constructor(){ this.currentTime = 0; this.sampleRate = 22050; this.destination = node(); }
  createOscillator(){ return node(); } createGain(){ return node(); } createStereoPanner(){ return node(); } createBiquadFilter(){ return node(); }
  createDelay(){ return node(); } createWaveShaper(){ globalThis.__shapers++; return node(); } createBufferSource(){ return node(); }
  createBuffer(c, n, sr){ globalThis.__buffers++; const ch = Array.from({length: c}, () => new Float32Array(n)); return { getChannelData(i){ return ch[i]; }, length: n, sampleRate: sr, numberOfChannels: c }; }
  createPeriodicWave(){ return {}; } };
globalThis.OfflineAudioContext = class extends AudioContext { constructor(c, n, sr){ super(); this.length = n; this.sampleRate = sr; } startRendering(){ return Promise.resolve({ length: this.length }); } };
"""


def make_song(bitcrush=True, sweep=True):
    s = bms.demo_song()
    for f in s.effects:
        f["enabled"] = f["type"] != "bitcrush" or bitcrush
    if sweep:
        s.tracks[0].instrument = "pad"      # duty_sweep +0.15/s
        s.tracks[1].instrument = "laser"    # duty_sweep -1.5/s, pitch slide
    s.arrangement = [c for c in s.arrangement if c.bar < 2]
    return s


def js_song(tmp_path, song):
    js = bms.export_js(song)
    p = tmp_path / "song.mjs"
    p.write_text(js, encoding="utf-8")
    line = next(ln for ln in js.splitlines() if ln.startswith("export const SONG = "))
    return p, json.loads(line[len("export const SONG = "):].rstrip(";"))


def node(tmp_path, body, *args):
    h = tmp_path / "h.mjs"
    h.write_text(FAKE_AUDIO + body, encoding="utf-8")
    r = subprocess.run(["node", str(h), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, r.stderr
    return r.stdout


def js_render(tmp_path, mod, seamless=False):
    out = tmp_path / "o.bin"
    node(tmp_path, f"""import fs from 'fs';
const m = await import(process.argv[2]); const r = m.renderSamples({SR}, {{ seamless: {str(seamless).lower()} }});
const a = new Float64Array(r.length * 2); for (let i = 0; i < r.length; i++) {{ a[2*i] = r.left[i]; a[2*i+1] = r.right[i]; }}
fs.writeFileSync(process.argv[3], Buffer.from(a.buffer));""", mod.as_uri(), str(out))
    return np.fromfile(out, dtype="<f8").reshape(-1, 2)


def py_render(S, seamless=False):
    n_exact = int(round(S["seconds"] * SR))
    n = n_exact + int((2.0 if seamless else 1.5) * SR)
    out = bms.mix_events(S["events"], S["instruments"], S["tracks"], S["effects"], n, SR, S["master"])
    if not seamless:
        return out
    body = out[:n_exact].copy()
    for k in range(n_exact, n, n_exact):
        seg = out[k:k + n_exact]
        body[: len(seg)] += seg
    return body


def assert_close(a, b):
    assert a.shape == b.shape
    d = np.abs(a - b)
    # float rounding (libm sin/pow) may flip a rare pulse edge; everything else must agree
    assert np.mean(d > 1e-6) < 1e-4, f"{np.mean(d > 1e-6):.2e} of samples differ"
    assert float(np.sqrt(np.mean(d ** 2))) < 1e-4


@pytest.mark.parametrize("bitcrush,sweep", [(True, True), (False, True), (True, False)])
def test_js_render_matches_python(tmp_path, bitcrush, sweep):
    mod, S = js_song(tmp_path, make_song(bitcrush, sweep))
    assert any(f["type"] == "bitcrush" for f in S["effects"]) == bitcrush
    if sweep:
        assert any(i.get("duty_sweep") for i in S["instruments"].values())
    py = py_render(S)
    assert np.abs(py).max() > 0.1
    assert_close(js_render(tmp_path, mod), py)


def test_js_seamless_render_matches_python(tmp_path):
    mod, S = js_song(tmp_path, make_song())
    assert_close(js_render(tmp_path, mod, seamless=True), py_render(S, seamless=True))


def test_effects_are_audible_in_js(tmp_path):
    """Bitcrush and duty sweep actually change the JS output (not silently ignored)."""
    mod, S = js_song(tmp_path, make_song())
    crushed = js_render(tmp_path, mod)
    S2 = json.loads(json.dumps(S))
    S2["effects"] = [f for f in S2["effects"] if f["type"] != "bitcrush"]
    for i in S2["instruments"].values():
        i["duty_sweep"] = 0.0
    out = tmp_path / "plain.bin"
    (tmp_path / "s2.json").write_text(json.dumps(S2), encoding="utf-8")
    node(tmp_path, f"""import fs from 'fs';
const m = await import(process.argv[2]); const song = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
const r = m.renderSamples({SR}, {{ song }}); fs.writeFileSync(process.argv[3], Buffer.from(Float64Array.from(r.left).buffer));""",
         mod.as_uri(), str(out), str(tmp_path / "s2.json"))
    plain = np.fromfile(out, dtype="<f8")
    assert np.mean(np.abs(plain - crushed[:, 0]) > 1e-3) > 0.1
    bc = next(f for f in S["effects"] if f["type"] == "bitcrush")["params"]
    left = crushed[: int(S["seconds"] * SR), 0]
    assert len(np.unique(np.round(left, 12))) <= 2 ** bc["bits"] + 1          # bit depth
    ds = int(bc["downsample"])
    m = len(left) // ds * ds
    assert np.array_equal(left[:m:ds], left[1:m:ds]) if ds > 1 else True     # sample-and-hold


def test_js_voice_duty_sweep_matches_python(tmp_path):
    inst = bms.PRESETS["laser"].to_dict()
    mod, _ = js_song(tmp_path, make_song())
    out = node(tmp_path, f"""const m = await import(process.argv[2]);
const inst = {json.dumps(inst)}; const v = m.renderVoice(inst, 81, 0.25, 0.9, {SR});
const flat = m.renderVoice({{ ...inst, duty_sweep: 0 }}, 81, 0.25, 0.9, {SR});
console.log(JSON.stringify({{ v: Array.from(v), diff: v.some((x, i) => Math.abs(x - flat[i]) > 1e-3) }}));""", mod.as_uri())
    d = json.loads(out)
    assert d["diff"]
    py = bms.render_voice(inst, 81, 0.25, 0.9, SR)
    assert_close(np.array(d["v"])[:, None], py[:, None])


def test_wav_bytes_match_python_within_1lsb(tmp_path):
    mod, S = js_song(tmp_path, make_song())
    wav = tmp_path / "js.wav"
    node(tmp_path, f"""import fs from 'fs'; const m = await import(process.argv[2]);
fs.writeFileSync(process.argv[3], m.toWav(m.renderSamples({SR})));""", mod.as_uri(), str(wav))
    a, sr = bms.read_wav(wav)
    assert sr == SR
    b = bms.to_int16(py_render(S)).astype(np.int32)
    a16 = np.round(a * 32768).astype(np.int32) if a.dtype != np.int16 else a.astype(np.int32)
    assert a16.shape == b.shape and np.abs(a16 - b).max() <= 1


def test_player_modes_and_live_paths(tmp_path):
    crushed, _ = js_song(tmp_path, make_song(bitcrush=True))
    out = node(tmp_path, """const m = await import(process.argv[2]);
const ctx = new AudioContext(); const p = m.createPlayer(ctx, { loop: true }); p.start(); p.stop();
const live = m.createPlayer(ctx, { mode: 'live' }); live.start(); live.stop();
const b = await m.renderOffline(22050); const lb = await m.renderOffline(22050, m.SONG, { mode: 'live' });
console.log(JSON.stringify({ mode: p.mode, live: live.mode, shapers: globalThis.__shapers, buffers: globalThis.__buffers,
  started: globalThis.__started, exact: b.length, need: m.needsExactRender() }));""", crushed.as_uri())
    d = json.loads(out.strip().splitlines()[-1])
    assert d["mode"] == "exact" and d["live"] == "live" and d["need"] is True
    assert d["shapers"] >= 1          # live bit-depth quantizer
    assert d["buffers"] >= 2          # exact loop buffer + per-note duty-sweep buffers
    assert d["exact"] > 0 and d["started"] > 0
    plain, _ = js_song(tmp_path, make_song(bitcrush=False, sweep=False))
    out = node(tmp_path, """const m = await import(process.argv[2]);
console.log(m.createPlayer(new AudioContext()).mode, m.needsExactRender());""", plain.as_uri())
    assert out.split() == ["live", "false"]

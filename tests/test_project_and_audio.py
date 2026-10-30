import json
import shutil
import subprocess
import sys
import wave

import numpy as np
import pytest

import eightbit_studio as bms


def test_project_roundtrip(tmp_path, song):
    p = bms.save_project(song, tmp_path / "x.8bms")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["format"].startswith("8bms") or "song" in data
    back = bms.load_project(p)
    assert back.to_dict() == song.to_dict()


def test_score_roundtrip_is_sample_identical(tmp_path):
    for style in ("boss", "town", "chill"):
        s = bms.generate_song(style, 8, 3)
        s2 = bms.parse_score(bms.song_to_score(s))
        assert np.array_equal(bms.to_int16(bms.render_song(s)), bms.to_int16(bms.render_song(s2))), style


def test_wav_is_valid_16bit_44k(tmp_path, song):
    out = bms.op_render(song, str(tmp_path / "d.wav"), bars="1-2")
    with wave.open(out["path"]) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (2, 2, 44100)
        frames = w.readframes(w.getnframes())
    a = np.frombuffer(frames, "<i2")
    assert a.size > 44100 and np.abs(a).max() > 1000
    data, sr = bms.read_wav(out["path"])
    assert sr == 44100 and data.shape[1] == 2


def test_stems_and_loop_export(tmp_path, song):
    res = bms.op_render(song, str(tmp_path / "loop.wav"), seamless=True, stems=str(tmp_path / "stems"))
    stems = sorted((tmp_path / "stems").glob("*.wav"))
    assert len(stems) == len(song.tracks)
    a, b = song.loop_range()
    assert res["seconds"] == pytest.approx((b - a) * song.ticks_per_bar * song.tick_seconds(), abs=0.01)


@pytest.mark.skipif(not bms.ffmpeg_available(), reason="ffmpeg not installed")
def test_ffmpeg_formats(tmp_path, song):
    for ext in ("ogg", "mp3", "flac"):
        p = bms.op_render(song, str(tmp_path / f"x.{ext}"), bars="1-1")["path"]
        assert (tmp_path / f"x.{ext}").stat().st_size > 1000, p


def test_python_export_runs_and_matches(tmp_path, song):
    py = bms.op_export(song, "py", str(tmp_path / "song.py"))["path"]
    r = subprocess.run([sys.executable, py, "-o", str(tmp_path / "fromcode.wav")], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, r.stderr
    a, _ = bms.read_wav(tmp_path / "fromcode.wav")
    b = bms.render_song(song, tail=1.5)
    assert np.array_equal(bms.to_int16(a), bms.to_int16(b))


def test_python_export_seamless(tmp_path, song):
    py = bms.op_export(song, "py", str(tmp_path / "song.py"))["path"]
    r = subprocess.run([sys.executable, py, str(tmp_path / "s.wav"), "--seamless"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, r.stderr
    a, _ = bms.read_wav(tmp_path / "s.wav")
    b = bms.render_song(song, seamless=True)
    assert len(a) == len(b)


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_export_passes_node_check(tmp_path, song):
    js = bms.op_export(song, "js", str(tmp_path / "song.js"))["path"]
    r = subprocess.run(["node", "--check", js], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    text = (tmp_path / "song.js").read_text(encoding="utf-8")
    assert "AudioContext" in text or "OfflineAudioContext" in text


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_export_schedules_notes_in_node(tmp_path, song):
    """Import the module in node with a fake Web Audio API and count scheduled oscillators."""
    js = tmp_path / "song.mjs"
    js.write_text(bms.export_js(song), encoding="utf-8")
    harness = tmp_path / "h.mjs"
    harness.write_text("""
let started = 0;
const param = () => ({ value: 0, setValueAtTime(){}, linearRampToValueAtTime(){}, exponentialRampToValueAtTime(){}, setTargetAtTime(){}, cancelScheduledValues(){}, setValueCurveAtTime(){} });
const node = () => ({ connect(){ return this; }, disconnect(){}, start(){ started++; }, stop(){}, gain: param(), frequency: param(), detune: param(), pan: param(), delayTime: param(), Q: param(), buffer: null, loop: false, type: '', curve: null, setPeriodicWave(){}, playbackRate: param() });
globalThis.AudioContext = class { constructor(){ this.currentTime = 0; this.sampleRate = 44100; this.destination = node(); this.state='running'; }
  createOscillator(){ return node(); } createGain(){ return node(); } createStereoPanner(){ return node(); } createBiquadFilter(){ return node(); }
  createDelay(){ return node(); } createWaveShaper(){ return node(); } createBufferSource(){ return node(); } createDynamicsCompressor(){ const n=node(); n.threshold=param(); n.ratio=param(); n.knee=param(); n.attack=param(); n.release=param(); return n; }
  createBuffer(c, n, sr){ return { getChannelData(){ return new Float32Array(n); }, length: n, sampleRate: sr, numberOfChannels: c }; }
  createPeriodicWave(){ return {}; } resume(){ return Promise.resolve(); } close(){ return Promise.resolve(); } };
globalThis.OfflineAudioContext = class extends AudioContext { constructor(c, n, sr){ super(); this.length = n; } startRendering(){ return Promise.resolve({ length: this.length }); } };
const m = await import(process.argv[2]);
const buf = await m.renderOffline(44100);   // exact (pure-JS) render
if (!(buf.length > m.SONG.seconds * 44100)) throw new Error('short render');
const live = await m.renderOffline(44100, m.SONG, { mode: 'live' });   // Web Audio graph
if (!(live.length > m.SONG.seconds * 44100)) throw new Error('short live render');
if (!(m.STEP_EVENTS.length === m.SONG.events.length)) throw new Error('step events mismatch');
console.log(started);
""", encoding="utf-8")
    r = subprocess.run(["node", str(harness), js.as_uri()], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert r.returncode == 0, r.stderr
    assert int(r.stdout.strip().splitlines()[-1]) >= song.note_count() // 2


def test_json_export(tmp_path, song):
    p = bms.op_export(song, "json", str(tmp_path / "s.json"))["path"]
    d = json.loads(open(p).read())
    assert d and isinstance(d, dict)


def test_user_instrument_save_load(tmp_path):
    inst = bms.Instrument(name="mine", wave="pulse", duty=0.125, arp=[0, 3, 7])
    p = bms.save_instrument(inst, tmp_path / "mine.json")
    assert bms.load_instrument(p) == inst

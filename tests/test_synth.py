import numpy as np
import pytest

import eightbit_studio as bms

SR = 44100


def dominant_freq(x, sr=SR):
    x = x - x.mean()
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    f = np.fft.rfftfreq(len(x), 1 / sr)
    return f[np.argmax(spec)]


def test_a4_is_440():
    assert bms.midi_to_freq(69) == pytest.approx(440.0)
    assert bms.midi_to_freq(81) == pytest.approx(880.0)
    assert bms.note_name(69) == "A4" and bms.parse_note_name("A4") == 69 and bms.parse_note_name("c#4") == 61


@pytest.mark.parametrize("wave,duty", [("pulse", 0.125), ("pulse", 0.25), ("pulse", 0.5), ("pulse", 0.75), ("triangle", 0.5), ("saw", 0.5)])
def test_rendered_pitch_matches_a4(wave, duty):
    inst = bms.Instrument(name="t", wave=wave, duty=duty, attack=0.001, decay=0.01, sustain=1.0, release=0.01).to_dict()
    y = bms.render_voice(inst, 69, 0.5, 1.0)
    f = dominant_freq(y[: SR // 2])
    # narrow pulses have strong harmonics: the fundamental or an integer multiple must dominate
    assert min(abs(f / 440 - round(f / 440)), 1) < 0.02 and round(f / 440) >= 1
    if wave in ("triangle", "saw") or duty == 0.5:
        assert f == pytest.approx(440, abs=3)


@pytest.mark.parametrize("duty", [0.125, 0.25, 0.5, 0.75])
def test_pulse_duty_cycle(duty):
    phase = np.linspace(0, 10, 10000, endpoint=False)
    y = bms.osc("pulse", phase, phase / 440, {"duty": duty})
    assert set(np.unique(y)) == {-1.0, 1.0}
    assert (y > 0).mean() == pytest.approx(duty, abs=0.01)


def test_triangle_is_4bit_stepped():
    phase = np.linspace(0, 1, 5000, endpoint=False)
    y = bms.osc("triangle", phase, phase, {})
    assert len(np.unique(np.round(y, 6))) == 16
    assert y.max() == pytest.approx(1.0) and y.min() == pytest.approx(-1.0)


def test_noise_lfsr_periods():
    long_, short = bms.lfsr_sequence(False), bms.lfsr_sequence(True)
    assert len(long_) == 32767 and len(short) == 93
    assert set(np.unique(long_)) == {-1.0, 1.0}
    assert abs(long_.mean()) < 0.01


def test_adsr_shape():
    sr = 1000
    env = bms.adsr_env(500, 700, sr, attack=0.1, decay=0.1, sustain=0.5, release=0.2)
    assert env[0] == 0 and env[100] == pytest.approx(1.0, abs=0.02)
    assert env[300] == pytest.approx(0.5)
    assert env[499] == pytest.approx(0.5)
    assert env[-1] == pytest.approx(0.0, abs=0.01)
    assert np.all(np.diff(env[500:]) <= 1e-12)          # release only falls
    assert np.all(np.diff(env[:100]) > 0)                # attack only rises


def test_vibrato_arp_slide_change_pitch():
    base = bms.Instrument(name="b", wave="pulse", duty=0.5, sustain=1, attack=0.001, release=0.01).to_dict()
    plain = bms.render_voice(base, 69, 0.4, 1)
    slide = bms.render_voice(dict(base, slide=12, slide_time=0.05), 69, 0.4, 1)
    assert dominant_freq(slide[SR // 10: SR // 10 * 4]) == pytest.approx(880, abs=6)
    arp = bms.render_voice(dict(base, arp=[0, 12], arp_speed=10), 69, 0.4, 1)
    assert not np.allclose(plain, arp)
    vib = bms.render_voice(dict(base, vib_depth=0.5, vib_rate=6), 69, 0.4, 1)
    assert not np.allclose(plain, vib)


def test_effects_are_finite_and_shape_preserving():
    x = np.random.default_rng(1).uniform(-0.5, 0.5, (SR // 2, 2))
    for fn in (bms.fx_echo, bms.fx_lowpass, bms.fx_bitcrush):
        y = fn(x, SR)
        assert y.shape == x.shape and np.isfinite(y).all()
    lp = bms.fx_lowpass(x, SR, cutoff=500)
    assert np.abs(np.diff(lp[:, 0])).mean() < np.abs(np.diff(x[:, 0])).mean() / 3
    crushed = bms.fx_bitcrush(x, SR, bits=3, downsample=1)
    assert len(np.unique(crushed[:, 0])) <= 9


def test_all_presets_render():
    for name, inst in bms.PRESETS.items():
        y = bms.render_note_preview(inst, 60, 0.15)
        assert np.isfinite(y).all() and np.abs(y).max() > 0.01, name

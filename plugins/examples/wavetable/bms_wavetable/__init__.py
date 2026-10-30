"""Wavetable: a morphing 32x4-bit wavetable oscillator for 8Bit Music Code Studio.

Adds the wave ``wavetable`` and presets ``wt_glass``, ``wt_growl``, ``wt_organ``.
An instrument's ``table`` (32 values 0..15) is the start shape; the oscillator
morphs towards a built-in end shape at ``duty_sweep`` cycles/second (0 = static).
"""
import numpy as np

STEPS = 32
SHAPES = {
    "sine": [8, 10, 11, 13, 14, 15, 15, 15, 15, 15, 14, 13, 11, 10, 8, 7, 7, 5, 4, 2, 1, 0, 0, 0, 0, 0, 1, 2, 4, 5, 7, 7],
    "saw": [int(i * 15 / 31) for i in range(STEPS)],
    "organ": [8, 12, 14, 12, 9, 11, 15, 13, 8, 6, 9, 7, 3, 5, 7, 4, 8, 11, 8, 10, 12, 9, 7, 8, 4, 2, 5, 3, 1, 3, 6, 4],
}


def _table(values):
    t = np.asarray(values if values else SHAPES["sine"], dtype=float)
    if t.size != STEPS:  # resample any length to 32 steps
        t = np.interp(np.linspace(0, t.size, STEPS, endpoint=False), np.arange(t.size), t)
    return np.clip(np.round(t), 0, 15) / 7.5 - 1.0


def wavetable_wave(phase, t, inst):
    start = _table(inst.get("table"))
    end = _table(SHAPES["saw"] if inst.get("name", "").endswith("growl") else SHAPES["organ"])
    idx = (np.floor((phase % 1.0) * STEPS).astype(int)) % STEPS
    rate = float(inst.get("duty_sweep") or 0.0)
    mix = np.clip(np.abs(np.sin(np.pi * rate * t)), 0, 1) if rate else 0.0
    v = start[idx] * (1 - mix) + end[idx] * mix
    return np.round(v * 7.5) / 7.5  # keep it 4-bit


def register(api):
    api.add_wave("wavetable", wavetable_wave)
    common = {"wave": "wavetable"}
    api.add_instrument({"name": "wt_glass", **common, "table": SHAPES["sine"], "attack": 0.002, "decay": 0.4,
                        "sustain": 0.3, "release": 0.3, "volume": 0.5, "vib_depth": 0.08, "vib_rate": 5.0})
    api.add_instrument({"name": "wt_growl", **common, "table": SHAPES["sine"], "attack": 0.01, "decay": 0.1,
                        "sustain": 0.8, "release": 0.08, "volume": 0.45, "duty_sweep": 3.0})
    api.add_instrument({"name": "wt_organ", **common, "table": SHAPES["organ"], "attack": 0.01, "decay": 0.05,
                        "sustain": 0.9, "release": 0.12, "volume": 0.4})

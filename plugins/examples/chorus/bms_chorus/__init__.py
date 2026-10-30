"""Chorus: stereo modulated-delay chorus effect for 8Bit Music Code Studio.

Use in a score:   fx chorus rate=0.8 depth=4 mix=0.4 width=1
Params: rate (Hz), depth (ms), delay (ms base), mix (0..1), width (0..1 stereo spread).
"""
import numpy as np


def chorus(x, sr, rate=0.8, depth=4.0, delay=12.0, mix=0.4, width=1.0):
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n == 0 or mix <= 0:
        return x
    t = np.arange(n) / sr
    out = np.empty_like(x)
    base, dep = delay * sr / 1000.0, depth * sr / 1000.0
    for ch in range(x.shape[1]):
        phase = np.pi * width * ch  # right channel LFO in anti-phase
        d = base + dep * 0.5 * (1 + np.sin(2 * np.pi * rate * t + phase))
        pos = np.arange(n) - d
        i0 = np.floor(pos).astype(int)
        frac = pos - i0
        valid = i0 >= 0
        i0c = np.clip(i0, 0, n - 1)
        i1c = np.clip(i0 + 1, 0, n - 1)
        wet = np.where(valid, x[i0c, ch] * (1 - frac) + x[i1c, ch] * frac, 0.0)
        out[:, ch] = x[:, ch] * (1 - mix * 0.5) + wet * mix
    return out


def register(api):
    api.add_effect("chorus", chorus, params={"rate": (0.1, 5.0, 0.8), "depth": (0.5, 10.0, 4.0), "delay": (5.0, 30.0, 12.0),
                                             "mix": (0.0, 1.0, 0.4), "width": (0.0, 1.0, 1.0)})

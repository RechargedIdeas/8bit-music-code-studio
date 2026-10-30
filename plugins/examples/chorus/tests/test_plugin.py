from pathlib import Path

import numpy as np

import eightbit_studio as bms

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_is_valid():
    assert bms.validate_manifest(bms.manifest_from_file(ROOT / "plugin.toml")) == []


def test_chorus_widens_and_is_finite():
    info = bms.load_plugin_dir(ROOT)
    assert info.loaded, info.error
    try:
        sr = 44100
        t = np.arange(sr) / sr
        mono = np.sin(2 * np.pi * 440 * t) * 0.5
        x = np.stack([mono, mono], axis=1)
        y = bms.EXTRA_FX["chorus"](x, sr, mix=0.5)
        assert y.shape == x.shape and np.isfinite(y).all()
        assert np.abs(y[:, 0] - y[:, 1]).max() > 0.01   # stereo spread
        assert bms.EXTRA_FX["chorus"](x, sr, mix=0).tolist() == x.tolist()
        song = bms.parse_score((ROOT / "example" / "example.8bt").read_text(encoding="utf-8"))
        audio = bms.render_song(song)
        assert np.isfinite(audio).all() and np.abs(audio).max() > 0.05
    finally:
        info._manager.unload(info.name)

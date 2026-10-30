from pathlib import Path

import numpy as np

import eightbit_studio as bms

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_is_valid():
    assert bms.validate_manifest(bms.manifest_from_file(ROOT / "plugin.toml")) == []


def test_wave_is_4bit_and_pitched():
    info = bms.load_plugin_dir(ROOT)
    assert info.loaded, info.error
    try:
        assert {"wt_glass", "wt_growl", "wt_organ"} <= set(bms.PRESETS)
        y = bms.render_note_preview(bms.PRESETS["wt_organ"], 69, 0.5)
        assert np.isfinite(y).all() and np.abs(y).max() > 0.05
        # dominant period ~ 440 Hz
        mono = y[:, 0] if y.ndim == 2 else y
        seg = mono[2000:2000 + 44100 // 4]
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        f = np.fft.rfftfreq(len(seg), 1 / 44100)
        fund = f[np.argmax(spec * (f > 200) * (f < 2000))]
        assert abs(fund - 440) < 20 or abs(fund - 880) < 30
        raw = bms.EXTRA_WAVES["wavetable"](np.linspace(0, 4, 400), np.linspace(0, 0.01, 400), {"table": None})
        assert len(np.unique(np.round(raw, 6))) <= 16
    finally:
        info._manager.unload(info.name)
    assert "wt_glass" not in bms.PRESETS  # unload restores the registry

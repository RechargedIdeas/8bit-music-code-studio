from pathlib import Path

import numpy as np

import eightbit_studio as bms

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_is_valid():
    assert bms.validate_manifest(bms.manifest_from_file(ROOT / "plugin.toml")) == []


def test_style_generates_deterministically():
    info = bms.load_plugin_dir(ROOT)
    assert info.loaded, info.error
    try:
        assert "synthwave" in bms.style_names()
        a = bms.generate_song("synthwave", 8, 7)
        b = bms.generate_song("synthwave", 8, 7)
        assert bms.song_to_score(a) == bms.song_to_score(b)
        assert 96 <= a.bpm <= 112 and a.scale == "minor" and a.note_count() > 20
        audio = bms.render_song(a, 0, 2)
        assert np.isfinite(audio).all() and np.abs(audio).max() > 0.05
    finally:
        info._manager.unload(info.name)
    assert "synthwave" not in bms.style_names()

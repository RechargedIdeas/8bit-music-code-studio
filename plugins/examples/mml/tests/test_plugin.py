from pathlib import Path

import eightbit_studio as bms

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_is_valid():
    assert bms.validate_manifest(bms.manifest_from_file(ROOT / "plugin.toml")) == []


def test_mml_export(tmp_path):
    info = bms.load_plugin_dir(ROOT)
    assert info.loaded, info.error
    try:
        song = bms.parse_score("bpm 150\ntrack lead inst=lead\npat lead.A: o4 l8 c d e/4 r [c e g]/2 >c/4.")
        out = bms.op_export(song, "mml", str(tmp_path / "x.mml"))
        text = Path(out["path"]).read_text(encoding="utf-8")
        line = next(l for l in text.splitlines() if l.startswith("A "))
        assert "t150" in line and "o4" in line
        assert " c d e4 r g2 > c4." in line.replace(" v12", ""), line
        demo = bms.EXPORTERS["mml"][1](bms.demo_song())
        assert demo.count("\n") >= 5
    finally:
        info._manager.unload(info.name)

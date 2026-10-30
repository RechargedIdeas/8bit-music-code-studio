"""Terminal studio: visualizers, completion and scripted slash commands (headless)."""
import io

import numpy as np

import eightbit_studio as bms


def test_visualizers_shapes():
    song = bms.demo_song()
    buf = bms.render_song(song, 0, 2)
    fr = bms._frame_at(buf, 1.0)
    vu = bms.viz_vu(fr, 30, uni=False)
    assert vu.count("\n") == 1 and "dB" in vu
    sc = bms.viz_scope(fr, 40, 7, uni=False).split("\n")
    assert len(sc) == 7 and all(len(r) == 40 for r in sc)
    sp = bms.viz_spectrum(fr, 32, 6, uni=True).split("\n")
    assert len(sp) == 7
    tr = bms.viz_tracker(song, bms.PPQ * 4, rows=8)
    assert ">" in tr and "Lead" in tr
    frame = bms.studio_frame(song, buf, 1.0, uni=False)
    assert "bpm" in frame and "spectrum" in frame
    silent = bms.viz_vu(np.zeros((2048, 2)), 10, uni=False)
    assert "-96.0" in silent


def test_viz_registry():
    for k in ("tracker", "vu", "scope", "spectrum", "dashboard"):
        assert k in bms.VISUALIZERS
        assert bms.VISUALIZERS[k](bms.generate_song("town", 4, 1))


def test_completions():
    it = bms.Interpreter(bms.demo_song())
    assert "/compose" in bms.studio_completions(it, "/comp", "/comp")
    assert "context=dungeon" in bms.studio_completions(it, "context=dun", "/compose context=dun")
    assert "bars=" in bms.studio_completions(it, "ba", "/compose ba")
    notes = bms.studio_completions(it, "", "")
    assert notes and all(isinstance(n, str) for n in notes)


def test_run_studio_scripted():
    out = io.StringIO()
    script = ["/compose calm town 4 bars", "/tracker", "/vu", "/suggest", "c5 d5", "/critique", "/describe", "/help", "/quit"]
    assert bms.run_studio(None, inp=iter(script), out=out) == 0
    text = out.getvalue()
    assert "ok @" in text and "next:" in text and "score=" in text and "/watch" in text

import pytest

import eightbit_studio as bms

PPQ = bms.PPQ


def test_note_language_basics():
    notes, end = bms.parse_notes("c4 e4/8 g4/8. r/4 [c4 e4 g4]/2 {Am}/1", deflen=PPQ)
    assert [n.pitch for n in notes[:3]] == [60, 64, 67]
    assert notes[1].length == PPQ // 2 and notes[2].length == PPQ * 3 // 4
    chord = [n for n in notes if n.start == notes[3].start]
    assert sorted(n.pitch for n in chord) == [60, 64, 67] and chord[0].length == PPQ * 2
    am = notes[-3:]
    assert sorted(n.pitch % 12 for n in am) == [0, 4, 9] and am[0].length == PPQ * 4
    assert end == PPQ + PPQ // 2 + PPQ * 3 // 4 + PPQ + PPQ * 2 + PPQ * 4


def test_octave_length_velocity_repeat_tie():
    notes, end = bms.parse_notes("o5 l16 v64 c >c <c (d e)x2 f!127 _ g/4")
    assert [n.pitch for n in notes[:3]] == [72, 84, 72]
    assert all(n.length == PPQ // 4 for n in notes[:3])
    assert notes[0].velocity == pytest.approx(64 / 127)
    assert [n.pitch for n in notes[3:7]] == [74, 76, 74, 76]
    f = notes[7]
    assert f.velocity == 1.0 and f.length == PPQ // 2          # tied 16th + 16th
    assert notes[8].start == f.start + f.length


def test_triplets_and_absolute_positions():
    notes, _ = bms.parse_notes("c/8t c/8t c/8t @192 e")
    assert [n.start for n in notes] == [0, PPQ // 3, 2 * PPQ // 3, 192]


def test_bad_notes_raise():
    with pytest.raises(bms.NoteSyntaxError):
        bms.parse_notes("c4 h4")
    with pytest.raises(bms.ScoreError):
        bms.parse_score("track a\npat a.A: c4 (d e")


def test_notes_to_text_roundtrip_and_compression():
    src = "l16 (a2 a2 a2 a2)x8 r/4 [c4 e4 g4]/2 b3!100"
    notes, _ = bms.parse_notes(src)
    text = bms.notes_to_text(notes)
    back, _ = bms.parse_notes(text)
    key = lambda ns: sorted((n.start, n.length, n.pitch, round(n.velocity, 4)) for n in ns)
    assert key(back) == key(notes)
    assert ")x" in text and len(text) < len(" ".join(["a2"] * 32))


def test_score_features():
    s = bms.parse_score("""
# comment
title My #1 Song
bpm 140; time 3/4; swing 0.1; key D minor; master 0.7
loop 2-3
fx echo time=.2 feedback=.2 mix=.1
inst zap2 pulse duty=.125 a=.001 slide=-12 arp=0,4,7
track lead inst=zap2 vol=.6 pan=-.3
pat lead.A: o5 l8 d f a
pat lead.B bars=2: d/2.
  e/2.
arr lead: A B -*1 A
track drums drum
pat drums.A: kick=x..x.. snare=...x..
""")
    assert s.title == "My #1 Song" and s.bpm == 140 and s.time_sig == (3, 4) and s.swing == 0.1
    assert (s.key, s.scale) == ("D", "minor") and s.loop_range() == (1, 3)
    z = s.get_instrument("zap2")
    assert z.duty == 0.125 and z.slide == -12 and z.arp == [0, 4, 7]
    lead = s.tracks[s.track_index("lead")]
    assert lead.volume == 0.6 and lead.pan == -0.3
    assert len(lead.patterns["B"].notes) == 2                  # continuation line joined
    assert sorted(c.bar for c in s.arrangement if c.track == 0) == [0, 1, 4]
    assert s.tracks[1].drum and len(s.tracks[1].patterns["A"].notes) == 3
    again = bms.parse_score(bms.song_to_score(s))
    assert bms.song_to_score(again) == bms.song_to_score(s)


def test_load_any_sources(tmp_path):
    assert bms.load_any("demo").title
    g = bms.load_any("gen:boss:4:2")
    assert g.length_bars() == 4
    p = tmp_path / "x.8bt"
    p.write_text("bpm 99\ntrack a\npat a.A: c d e", encoding="utf-8")
    assert bms.load_any(str(p)).bpm == 99


def test_interpreter_language():
    it = bms.Interpreter(bms.new_song())
    it.execute("bpm 90")
    assert it.song.bpm == 90
    it.execute("c4 e4 g4 >c")
    assert it.song.note_count() == 4
    it.execute("transpose 2")
    it.execute("/undo")
    out = it.execute("make a boss song 4 bars")
    assert it.song.length_bars() == 4 and it.song.note_count() > 10, out
    assert "/export" in it.execute("/help")
    assert "?" in it.execute("florbnicate the zorp") or "understand" in it.execute("florbnicate the zorp")

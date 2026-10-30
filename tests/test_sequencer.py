import numpy as np
import pytest

import eightbit_studio as bms

SR = 44100


def one_note_song(bpm=120, start=0, length=None):
    s = bms.parse_score(f"bpm {bpm}\ninst click pulse a=0 d=0 s=1 r=0.001\ntrack a inst=click\npat a.A bars=2: @{start} c4/4")
    s.effects = []
    return s


def first_onset(x, thresh=1e-6):
    return int(np.argmax(np.abs(x[:, 0]) > thresh))


def test_tick_math():
    s = one_note_song(120)
    assert s.ticks_per_bar == bms.PPQ * 4
    assert s.tick_seconds() == pytest.approx(0.5 / bms.PPQ)
    s.time_sig = (3, 4)
    assert s.ticks_per_bar == bms.PPQ * 3
    s.time_sig = (6, 8)
    assert s.ticks_per_bar == bms.PPQ * 3


def test_note_starts_at_the_right_sample():
    s = one_note_song(120, start=bms.PPQ)              # beat 2 = 0.5 s
    x = bms.render_song(s, tail=0)
    assert first_onset(x) == pytest.approx(SR // 2, abs=2)
    assert len(x) == SR * 4                            # 2 bars @120 = 4 s exactly


def test_bpm_scales_timing():
    a = first_onset(bms.render_song(one_note_song(120, bms.PPQ * 4), tail=0))
    b = first_onset(bms.render_song(one_note_song(60, bms.PPQ * 4), tail=0))
    assert b == pytest.approx(2 * a, abs=3)


def test_loop_range_render_is_exact_length(song):
    a, b = song.loop_range()
    x = bms.render_song(song, a, b, seamless=True)
    exact = int(round((b - a) * song.ticks_per_bar * song.tick_seconds() * SR))
    assert len(x) == exact


def test_seamless_loop_has_no_gap(song):
    a, b = song.loop_range()
    plain = bms.render_song(song, a, b, tail=0)
    seam = bms.render_song(song, a, b, seamless=True)
    assert len(plain) == len(seam)
    # the tail folded onto the start makes the beginning differ (release/echo carried over)
    assert not np.allclose(plain[:2000], seam[:2000])
    # and the end-to-start jump is small (no click)
    jump = np.abs(seam[0] - seam[-1]).max()
    assert jump < 0.5


def test_loop_boundaries_exclude_outside_notes():
    s = bms.parse_score("bpm 120\ntrack a inst=lead\npat a.A bars=4: @0 c4/4 @384 e4/4 @768 g4/4 @1152 c5/4")
    evs = bms.compile_events(s, 1, 3)
    assert [e["midi"] for e in evs] == [64, 67]
    assert evs[0]["t"] == pytest.approx(0.0)
    assert evs[1]["t"] == pytest.approx(2.0)


def test_swing_delays_offbeat_sixteenths():
    six = bms.PPQ // 4
    assert bms.swing_offset(0, 0.5) == 0
    assert bms.swing_offset(six, 0.5) == six // 2
    assert bms.swing_offset(2 * six, 0.5) == 0


def test_arrangement_places_patterns():
    s = bms.parse_score("track a inst=lead\npat a.A bars=1: c4\npat a.B bars=1: e4\narr a: A B -*2 A")
    bars = sorted((c.bar, c.pattern) for c in s.arrangement)
    assert bars == [(0, "A"), (1, "B"), (4, "A")]
    assert s.length_bars() == 5


def test_mute_solo(song):
    solo = bms.track_dicts(song)
    song.tracks[0].solo = True
    x = bms.render_song(song, 4, 5, effects=False, stems=True, tail=0)
    assert np.abs(x[0]).max() > 0 and all(np.abs(s).max() == 0 for s in x[1:])
    assert solo  # unchanged copy


def test_generators_are_deterministic():
    for style in bms.style_names():
        a = bms.song_to_score(bms.generate_song(style, 4, 11))
        b = bms.song_to_score(bms.generate_song(style, 4, 11))
        assert a == b, style


def test_quantize_and_arpeggiate():
    notes = [bms.Note(5, 40, 60), bms.Note(50, 40, 64)]
    bms.quantize(notes, bms.PPQ // 2)
    assert [n.start for n in notes] == [0, 48]
    arp = bms.arpeggiate([bms.Note(0, bms.PPQ, p) for p in (60, 64, 67)], rate=bms.PPQ // 4)
    assert [n.pitch for n in arp] == [60, 64, 67, 60] and all(n.length == bms.PPQ // 4 for n in arp)


def test_scale_helpers():
    assert bms.in_scale(64, 60, "major") and not bms.in_scale(63, 60, "major")
    assert bms.snap_to_scale(61, 60, "major") in (60, 62)
    assert bms.diatonic_chord(60, "major", 0) == [60, 64, 67]
    assert bms.diatonic_chord(60, "major", 1) == [62, 65, 69]

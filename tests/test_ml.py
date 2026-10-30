"""Tiny offline ML: determinism, provenance, quality floors and latency budgets (CPU only)."""
import json
import os
import time

import numpy as np
import pytest

import eightbit_studio as bms
from conftest import ROOT

# Budgets are deliberately generous (CI machines vary ~5x); typical numbers are in docs/ml.md.
SLOW = float(os.environ.get("EIGHTBMS_BUDGET_SCALE", "1"))


def timed(fn, *a, **k):
    t = time.perf_counter()
    r = fn(*a, **k)
    return r, (time.perf_counter() - t) * 1000


def best_of(n, fn, *a, **k):
    return min(timed(fn, *a, **k)[1] for _ in range(n))


def test_shipped_model_matches_training():
    shipped = json.loads((ROOT / "models" / "tiny-v1.json").read_text(encoding="utf-8"))
    fresh, ms = timed(bms.train_tiny_model)
    assert ms < 3000 * SLOW
    assert shipped["provenance"]["corpus_sha256"] == fresh["provenance"]["corpus_sha256"], \
        "models/tiny-v1.json is stale: run `8bms ml train --out models/tiny-v1.json`"
    assert shipped["provenance"]["deterministic"] is True
    assert "self-generated" in shipped["provenance"]["corpus"]
    assert len(json.dumps(shipped)) < 200_000


def test_compose_budget_and_determinism():
    bms.load_tiny_model()
    a, ms = timed(bms.run_op, "compose", prompt="mellow space", bars=16, seed=5, candidates=3)
    b = bms.run_op("compose", prompt="mellow space", bars=16, seed=5, candidates=3)
    assert a["handle"] == b["handle"]
    assert ms < 1500 * SLOW
    assert a["score"] >= 70


def test_tiny_melody_constraints():
    song = bms.load_any(bms.run_op("compose", style="town", bars=8, seed=2, model="tiny")["handle"])
    li = bms.lead_track(song)
    root = bms.key_root(song.key)
    scale = {(root + iv) % 12 for iv in bms.SCALES[song.scale]}
    notes = [n for p in song.tracks[li].patterns.values() for n in p.notes]
    assert notes and all(n.pitch % 12 in scale for n in notes)


def test_suggest_budget():
    song = bms.demo_song()
    sug = bms.suggest_next(song, k=3)
    assert 1 <= len(sug) <= 3 and all({"note", "p", "midi", "ticks", "at"} <= set(x) for x in sug)
    assert best_of(5, bms.suggest_next, song, None, None, 3) < 50 * SLOW
    drums = bms.suggest_next(song, next(i for i, t in enumerate(song.tracks) if t.drum), k=2)
    assert drums and drums[0]["note"] in bms.DRUM_ROWS


def test_chords_critique_humanize_budgets():
    song = bms.generate_song("town", 8, 1)
    assert best_of(3, bms.run_op, "suggest", src=song, kind="chords") < 200 * SLOW
    c = bms.critique_song(song)
    assert 0 <= c["score"] <= 100
    assert best_of(3, bms.critique_song, song) < 200 * SLOW
    h = bms.humanize_song(song, 0.5, seed=1)
    h2 = bms.humanize_song(song, 0.5, seed=1)
    assert h.to_dict() == h2.to_dict() and h.to_dict() != song.to_dict()
    g = bms.groove_drums("four", 2, song.ticks_per_bar, seed=3)
    assert g and all(n.inst for n in g)


@pytest.mark.parametrize("text,op", [("make a tense boss fight theme 16 bars", "compose"), ("make it loop", "loopify"),
                                     ("critique this", "critique"), ("make jump and coin sounds", "soundpack"),
                                     ("add 8 more bars", "extend"), ("describe the song", "describe")])
def test_intent_parser(text, op):
    r = bms.parse_intent(text)
    assert r["op"] == op, r
    assert best_of(5, bms.parse_intent, text) < 10 * SLOW


@pytest.mark.parametrize("text", ["remix this as a boss theme", "redo it as underwater music", "turn this into credits music",
                                  "make it sound like a dungeon"])
def test_intent_remix_phrases(text):
    assert bms.parse_intent(text)["op"] == "remix"


def test_render_cache_speedup_and_equality(monkeypatch):
    song = bms.generate_song("chill", 4, 9)
    monkeypatch.setenv("EIGHTBMS_NO_CACHE", "1")
    cold = bms.render_song(song)
    monkeypatch.delenv("EIGHTBMS_NO_CACHE")
    a, t1 = timed(bms.render_song, song)
    b, t2 = timed(bms.render_song, song)
    assert np.array_equal(cold, a) and np.array_equal(a, b)
    assert t2 < t1


def test_adaptive_blocksize_and_bench():
    bs = bms.adaptive_blocksize()
    assert bs in (128, 256, 512, 1024, 2048, 4096)
    r = bms.run_op("ml", action="bench")
    for k in ("compose16_ms", "suggest_ms", "critique_ms", "intent_ms", "render_cold_ms"):
        assert r[k] >= 0

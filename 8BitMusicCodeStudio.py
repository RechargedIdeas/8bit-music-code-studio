#!/usr/bin/env python3
"""
8Bit Music Code Studio (8BitMusicCodeStudio.py)
================================================

A beginner-friendly but fully capable chiptune studio in one file.

* Synth engine: 2 pulse channels (12.5/25/50/75 % duty), triangle, noise
  (long/short LFSR), plus saw / sine / 4-bit wavetable voices; ADSR, vibrato,
  arpeggio, pitch slide, duty sweep. Everything is synthesized - no samples.
* Piano roll, drum step sequencer, pattern arrangement, mixer, effects.
* Save projects (.8bms JSON), compact text scores (.8bt), export WAV (+ stems,
  loops, seamless loops), OGG/MP3/FLAC via ffmpeg, and "save as code"
  (Python script, JavaScript Web Audio module, JSON data).
* CLI (`8bms ...`), Agent Client Protocol server (`8bms acp`), MCP server
  (`8bms mcp`), local HTTP API (`8bms serve`), terminal studio (`8bms repl`).
* Plugins: instruments, effects, styles, ops, exporters/importers, GUI panels,
  slash commands, visualizers, MIDI mappings and ML backends.

Engine code is GUI-free and importable headless; the tkinter GUI is only
imported when the GUI is launched.

Run:  python 8BitMusicCodeStudio.py            (GUI)
      python 8BitMusicCodeStudio.py --help     (CLI)
"""
from __future__ import annotations

import argparse
import base64
import copy
import dataclasses
import hashlib
import importlib
import importlib.util
import io
import json
import math
import os
import random
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import wave
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np

# Make sure plugins importing ``eightbit_studio`` get *this* module instance.
sys.modules.setdefault("eightbit_studio_core", sys.modules[__name__])
if __name__ == "__main__":  # run as a plain script: let plugins `import eightbit_studio` too
    sys.modules.setdefault("eightbit_studio", sys.modules[__name__])

APP_NAME = "8Bit Music Code Studio"
APP_VERSION = "1.0.0"
API_VERSION = "1.0.0"          # plugin API (semver)
SR = 44100                      # sample rate
PPQ = 96                        # ticks per quarter note (divisible by 3 for triplets)
FILE_EXT = ".8bms"
SCORE_EXT = ".8bt"


def home_dir() -> Path:
    """Per-user data folder (~/.8bms, override with EIGHTBMS_HOME)."""
    p = Path(os.environ.get("EIGHTBMS_HOME") or (Path.home() / ".8bms"))
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Music theory
# ---------------------------------------------------------------------------
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_LETTER = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}

SCALES: Dict[str, List[int]] = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "pentatonic": [0, 2, 4, 7, 9],
    "minor_pentatonic": [0, 3, 5, 7, 10],
    "blues": [0, 3, 5, 6, 7, 10],
    "chromatic": list(range(12)),
}

CHORDS: Dict[str, List[int]] = {
    "maj": [0, 4, 7], "min": [0, 3, 7], "m": [0, 3, 7], "dim": [0, 3, 6],
    "aug": [0, 4, 8], "sus2": [0, 2, 7], "sus4": [0, 5, 7], "7": [0, 4, 7, 10],
    "maj7": [0, 4, 7, 11], "m7": [0, 3, 7, 10], "min7": [0, 3, 7, 10],
    "add9": [0, 4, 7, 14], "5": [0, 7], "oct": [0, 12],
}


def midi_to_freq(m: float) -> float:
    """Equal temperament, A4 (MIDI 69) = 440 Hz."""
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


def note_name(m: int) -> str:
    return f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"


def parse_note_name(s: str) -> int:
    """'C4' -> 60, 'A4' -> 69, 'Eb3', 'f#5'."""
    mm = re.fullmatch(r"([a-gA-G])([#b]?)(-?\d+)", s.strip())
    if not mm:
        raise ValueError(f"bad note name {s!r}")
    v = _LETTER[mm.group(1).lower()] + (1 if mm.group(2) == "#" else -1 if mm.group(2) == "b" else 0)
    return v + (int(mm.group(3)) + 1) * 12


def key_root(key: str) -> int:
    """'C', 'F#', 'Bb' -> pitch class."""
    k = key.strip()
    v = _LETTER[k[0].lower()]
    if len(k) > 1 and k[1] == "#":
        v += 1
    elif len(k) > 1 and k[1] == "b":
        v -= 1
    return v % 12


def in_scale(m: int, root: int, scale: str) -> bool:
    return ((m - root) % 12) in SCALES.get(scale, SCALES["chromatic"])


def snap_to_scale(m: int, root: int, scale: str) -> int:
    for d in (0, -1, 1, -2, 2):
        if in_scale(m + d, root, scale):
            return m + d
    return m


def scale_note(root_midi: int, scale: str, degree: int) -> int:
    """0-based scale degree (may be negative / > len) above root_midi."""
    sc = SCALES.get(scale, SCALES["major"])
    o, i = divmod(degree, len(sc))
    return root_midi + 12 * o + sc[i]


def diatonic_chord(root_midi: int, scale: str, degree: int, size: int = 3) -> List[int]:
    return [scale_note(root_midi, scale, degree + 2 * k) for k in range(size)]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Instrument:
    name: str = "lead"
    wave: str = "pulse"          # pulse|triangle|saw|sine|noise|wave|<plugin wave>
    duty: float = 0.5            # pulse duty 0.125/0.25/0.5/0.75
    noise_mode: str = "long"     # long|short
    attack: float = 0.005
    decay: float = 0.08
    sustain: float = 0.7
    release: float = 0.08
    volume: float = 0.8
    vib_depth: float = 0.0       # semitones
    vib_rate: float = 5.5        # Hz
    vib_delay: float = 0.0       # seconds before vibrato starts
    arp: List[int] = field(default_factory=list)  # semitone offsets cycled
    arp_speed: float = 30.0      # steps per second
    slide: float = 0.0           # semitones over slide_time (negative = down)
    slide_time: float = 0.1
    duty_sweep: float = 0.0      # duty change per second
    fixed_note: Optional[int] = None  # drums: ignore note pitch
    noise_rate: float = 1.0      # noise clock multiplier
    table: List[int] = field(default_factory=lambda: [8, 11, 13, 14, 15, 14, 13, 11, 8, 5, 3, 2, 1, 2, 3, 5] * 2)
    transpose: int = 0

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Instrument":
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: copy.deepcopy(v) for k, v in d.items() if k in names})


@dataclass
class Note:
    start: int                   # ticks from pattern start
    length: int                  # ticks
    pitch: int = 60              # MIDI note
    velocity: float = 0.8        # 0..1
    inst: Optional[str] = None   # per-note instrument override (drums)

    def to_dict(self) -> dict:
        d = {"start": self.start, "length": self.length, "pitch": self.pitch, "velocity": round(self.velocity, 4)}
        if self.inst:
            d["inst"] = self.inst
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Note":
        return cls(int(d["start"]), int(d["length"]), int(d.get("pitch", 60)), float(d.get("velocity", 0.8)), d.get("inst"))

    @property
    def end(self) -> int:
        return self.start + self.length


@dataclass
class Pattern:
    name: str = "A"
    bars: int = 1
    notes: List[Note] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "bars": self.bars, "notes": [n.to_dict() for n in sorted(self.notes, key=lambda n: (n.start, n.pitch))]}

    @classmethod
    def from_dict(cls, d: dict) -> "Pattern":
        return cls(d.get("name", "A"), int(d.get("bars", 1)), [Note.from_dict(n) for n in d.get("notes", [])])


CHANNEL_KINDS = ["pulse1", "pulse2", "triangle", "noise", "extra"]


@dataclass
class Track:
    name: str = "Lead"
    kind: str = "pulse1"         # pulse1|pulse2|triangle|noise|extra (informational / colour)
    instrument: str = "lead"
    volume: float = 0.8
    pan: float = 0.0             # -1..1
    mute: bool = False
    solo: bool = False
    drum: bool = False           # use drum sequencer rows
    patterns: Dict[str, Pattern] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "instrument": self.instrument, "volume": self.volume,
                "pan": self.pan, "mute": self.mute, "solo": self.solo, "drum": self.drum,
                "patterns": {k: p.to_dict() for k, p in self.patterns.items()}}

    @classmethod
    def from_dict(cls, d: dict) -> "Track":
        t = cls(d.get("name", "Track"), d.get("kind", "pulse1"), d.get("instrument", "lead"), float(d.get("volume", 0.8)),
                float(d.get("pan", 0.0)), bool(d.get("mute")), bool(d.get("solo")), bool(d.get("drum")))
        t.patterns = {k: Pattern.from_dict(p) for k, p in d.get("patterns", {}).items()}
        return t


@dataclass
class Clip:
    track: int
    pattern: str
    bar: int

    def to_dict(self) -> dict:
        return {"track": self.track, "pattern": self.pattern, "bar": self.bar}


DEFAULT_EFFECTS = [
    {"type": "echo", "enabled": False, "params": {"time": 0.3, "feedback": 0.35, "mix": 0.25}},
    {"type": "lowpass", "enabled": False, "params": {"cutoff": 6000.0}},
    {"type": "bitcrush", "enabled": False, "params": {"bits": 6, "downsample": 2}},
]


@dataclass
class Song:
    title: str = "Untitled"
    bpm: float = 120.0
    time_sig: Tuple[int, int] = (4, 4)
    swing: float = 0.0           # 0..0.5 (fraction of a 16th the off-16ths are delayed)
    key: str = "C"
    scale: str = "major"
    master: float = 0.8
    tracks: List[Track] = field(default_factory=list)
    instruments: Dict[str, Instrument] = field(default_factory=dict)
    arrangement: List[Clip] = field(default_factory=list)
    loop_start: int = 0          # bars
    loop_end: int = 0            # bars (0 = song end)
    effects: List[dict] = field(default_factory=lambda: copy.deepcopy(DEFAULT_EFFECTS))
    meta: Dict[str, Any] = field(default_factory=dict)

    # -- timing -----------------------------------------------------------
    @property
    def ticks_per_bar(self) -> int:
        n, d = self.time_sig
        return int(PPQ * 4 * n / d)

    def tick_seconds(self) -> float:
        return 60.0 / (self.bpm * PPQ)

    def length_bars(self) -> int:
        end = 0
        for c in self.arrangement:
            p = self.pattern_of(c)
            if p is not None:
                end = max(end, c.bar + p.bars)
        return max(end, 1)

    def loop_range(self) -> Tuple[int, int]:
        end = self.loop_end if self.loop_end > self.loop_start else self.length_bars()
        return self.loop_start, end

    def pattern_of(self, clip: Clip) -> Optional[Pattern]:
        if 0 <= clip.track < len(self.tracks):
            return self.tracks[clip.track].patterns.get(clip.pattern)
        return None

    def get_instrument(self, name: Optional[str]) -> Instrument:
        if name and name in self.instruments:
            return self.instruments[name]
        if name and name in PRESETS:
            return PRESETS[name]
        return PRESETS["lead"]

    def track_index(self, name: str) -> int:
        for i, t in enumerate(self.tracks):
            if t.name.lower() == name.lower():
                return i
        raise KeyError(f"no track {name!r}")

    def note_count(self) -> int:
        return sum(len(p.notes) for t in self.tracks for p in t.patterns.values())

    # -- (de)serialisation -------------------------------------------------
    def to_dict(self) -> dict:
        return {"format": "8bms", "version": 1, "app": APP_VERSION, "title": self.title, "bpm": self.bpm,
                "time_sig": list(self.time_sig), "swing": self.swing, "key": self.key, "scale": self.scale,
                "master": self.master, "tracks": [t.to_dict() for t in self.tracks],
                "instruments": {k: v.to_dict() for k, v in self.instruments.items()},
                "arrangement": [c.to_dict() for c in self.arrangement], "loop_start": self.loop_start,
                "loop_end": self.loop_end, "effects": copy.deepcopy(self.effects), "meta": copy.deepcopy(self.meta)}

    @classmethod
    def from_dict(cls, d: dict) -> "Song":
        s = cls()
        s.title = d.get("title", "Untitled")
        s.bpm = float(d.get("bpm", 120))
        s.time_sig = tuple(d.get("time_sig", (4, 4)))  # type: ignore[assignment]
        s.swing = float(d.get("swing", 0))
        s.key = d.get("key", "C")
        s.scale = d.get("scale", "major")
        s.master = float(d.get("master", 0.8))
        s.tracks = [Track.from_dict(t) for t in d.get("tracks", [])]
        s.instruments = {k: Instrument.from_dict(v) for k, v in d.get("instruments", {}).items()}
        s.arrangement = [Clip(int(c["track"]), c["pattern"], int(c["bar"])) for c in d.get("arrangement", [])]
        s.loop_start = int(d.get("loop_start", 0))
        s.loop_end = int(d.get("loop_end", 0))
        s.effects = d.get("effects", copy.deepcopy(DEFAULT_EFFECTS))
        s.meta = d.get("meta", {})
        return s

    def copy(self) -> "Song":
        return Song.from_dict(self.to_dict())


# ---------------------------------------------------------------------------
# Instrument presets
# ---------------------------------------------------------------------------
def _I(name, **kw) -> Instrument:
    return Instrument(name=name, **kw)


PRESETS: Dict[str, Instrument] = {i.name: i for i in [
    _I("lead", wave="pulse", duty=0.25, attack=0.005, decay=0.12, sustain=0.6, release=0.1, volume=0.55, vib_depth=0.15, vib_rate=5.5, vib_delay=0.15),
    _I("lead50", wave="pulse", duty=0.5, attack=0.005, decay=0.1, sustain=0.65, release=0.08, volume=0.5),
    _I("thin", wave="pulse", duty=0.125, attack=0.004, decay=0.1, sustain=0.5, release=0.08, volume=0.5),
    _I("bass", wave="triangle", attack=0.003, decay=0.05, sustain=0.9, release=0.05, volume=0.9),
    _I("pulsebass", wave="pulse", duty=0.5, attack=0.003, decay=0.15, sustain=0.5, release=0.04, volume=0.45),
    _I("pad", wave="pulse", duty=0.5, attack=0.25, decay=0.3, sustain=0.6, release=0.5, volume=0.3, vib_depth=0.1, vib_rate=4.0, duty_sweep=0.15),
    _I("arp", wave="pulse", duty=0.125, attack=0.002, decay=0.08, sustain=0.4, release=0.05, volume=0.4, arp=[0, 4, 7, 12], arp_speed=24),
    _I("arpminor", wave="pulse", duty=0.25, attack=0.002, decay=0.08, sustain=0.4, release=0.05, volume=0.4, arp=[0, 3, 7, 12], arp_speed=24),
    _I("blip", wave="pulse", duty=0.25, attack=0.001, decay=0.06, sustain=0.0, release=0.02, volume=0.45),
    _I("bell", wave="wave", attack=0.002, decay=0.4, sustain=0.2, release=0.3, volume=0.5),
    _I("saw", wave="saw", attack=0.01, decay=0.2, sustain=0.6, release=0.15, volume=0.35),
    _I("flute", wave="sine", attack=0.06, decay=0.1, sustain=0.8, release=0.15, volume=0.5, vib_depth=0.2, vib_rate=5.0, vib_delay=0.2),
    _I("kick", wave="triangle", attack=0.001, decay=0.12, sustain=0.0, release=0.03, volume=1.0, slide=-30, slide_time=0.09, fixed_note=52),
    _I("snare", wave="noise", noise_mode="long", attack=0.001, decay=0.14, sustain=0.0, release=0.05, volume=0.6, fixed_note=72),
    _I("hat", wave="noise", noise_mode="long", attack=0.001, decay=0.035, sustain=0.0, release=0.01, volume=0.35, fixed_note=96, noise_rate=2.0),
    _I("ohat", wave="noise", noise_mode="long", attack=0.001, decay=0.2, sustain=0.1, release=0.1, volume=0.3, fixed_note=96, noise_rate=2.0),
    _I("clap", wave="noise", noise_mode="long", attack=0.002, decay=0.09, sustain=0.0, release=0.04, volume=0.5, fixed_note=80, arp=[0, -2, 0], arp_speed=60),
    _I("tom", wave="triangle", attack=0.001, decay=0.18, sustain=0.0, release=0.05, volume=0.9, slide=-12, slide_time=0.15, fixed_note=57),
    _I("crash", wave="noise", noise_mode="long", attack=0.002, decay=0.7, sustain=0.0, release=0.3, volume=0.3, fixed_note=100, noise_rate=1.5),
    _I("metal", wave="noise", noise_mode="short", attack=0.001, decay=0.08, sustain=0.0, release=0.04, volume=0.35, fixed_note=84),
    _I("laser", wave="pulse", duty=0.5, attack=0.001, decay=0.2, sustain=0.0, release=0.05, volume=0.45, slide=-36, slide_time=0.2, duty_sweep=-1.5),
    _I("coin", wave="pulse", duty=0.5, attack=0.001, decay=0.25, sustain=0.0, release=0.05, volume=0.45, arp=[0, 5], arp_speed=14),
    _I("powerup", wave="pulse", duty=0.25, attack=0.001, decay=0.4, sustain=0.2, release=0.1, volume=0.4, slide=24, slide_time=0.35),
    _I("explosion", wave="noise", noise_mode="long", attack=0.001, decay=0.6, sustain=0.0, release=0.2, volume=0.6, slide=-24, slide_time=0.5, fixed_note=70),
    _I("zap", wave="noise", noise_mode="short", attack=0.001, decay=0.15, sustain=0.0, release=0.05, volume=0.4, slide=-24, slide_time=0.15),
]}

DRUM_ROWS = ["kick", "snare", "hat", "ohat", "clap", "tom", "crash", "metal"]
WAVE_TYPES = ["pulse", "triangle", "saw", "sine", "noise", "wave"]


def user_instrument_dir() -> Path:
    p = home_dir() / "instruments"
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_instrument(inst: Instrument, path: Optional[Path] = None) -> Path:
    path = Path(path) if path else user_instrument_dir() / f"{inst.name}.json"
    path.write_text(json.dumps(inst.to_dict(), indent=2))
    return path


def load_instrument(path: Path) -> Instrument:
    return Instrument.from_dict(json.loads(Path(path).read_text()))


def user_instruments() -> Dict[str, Instrument]:
    out = {}
    for f in sorted(user_instrument_dir().glob("*.json")):
        try:
            i = load_instrument(f)
            out[i.name] = i
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# Synth engine.  Functions in this block work on plain dicts / numpy only and
# are copied verbatim into exported Python scripts (see export_python).
# ---------------------------------------------------------------------------
_LFSR_CACHE = {}


def lfsr_sequence(short=False):
    """NES-style 15-bit LFSR noise as +-1 values. long period 32767, short 93."""
    key = bool(short)
    if key in _LFSR_CACHE:
        return _LFSR_CACHE[key]
    reg, tap = 1, (6 if short else 1)
    out = []
    period = 93 if short else 32767
    for _ in range(period):
        bit = (reg ^ (reg >> tap)) & 1
        reg = (reg >> 1) | (bit << 14)
        out.append(1.0 if reg & 1 else -1.0)
    arr = np.array(out, dtype=np.float64)
    _LFSR_CACHE[key] = arr
    return arr


def adsr_env(n_gate, n_total, sr, attack, decay, sustain, release):
    """ADSR envelope: gate for n_gate samples, then release to zero."""
    i = np.arange(n_total, dtype=np.float64)
    a = max(int(attack * sr), 1)
    d = max(int(decay * sr), 1)
    env = np.full(n_total, float(sustain))
    env = np.where(i < a, i / a, env)
    dm = (i >= a) & (i < a + d)
    env = np.where(dm, 1.0 - (1.0 - sustain) * (i - a) / d, env)
    if n_total > n_gate:
        g = max(n_gate - 1, 0)
        if g < a:
            lvl = g / a
        elif g < a + d:
            lvl = 1.0 - (1.0 - sustain) * (g - a) / d
        else:
            lvl = sustain
        r = max(n_total - n_gate, 1)
        rel = lvl * (1.0 - (i - n_gate) / r)
        env = np.where(i >= n_gate, np.maximum(rel, 0.0), env)
    return env


def osc(wave_name, phase, t, inst, waves=None):
    """Oscillator: phase = cumulative cycles (float array)."""
    frac = phase - np.floor(phase)
    if waves and wave_name in waves:
        return waves[wave_name](phase, t, inst)
    if wave_name == "triangle":
        v = 1.0 - 4.0 * np.abs(frac - 0.5)
        return np.round((v + 1.0) * 7.5) / 7.5 - 1.0          # 4-bit stepped triangle
    if wave_name == "saw":
        return np.round(frac * 15.0) / 7.5 - 1.0
    if wave_name == "sine":
        return np.sin(2 * np.pi * frac)
    if wave_name == "wave":
        tab = np.asarray(inst.get("table") or [8] * 32, dtype=np.float64)
        idx = np.floor(frac * len(tab)).astype(np.int64) % len(tab)
        return tab[idx] / 7.5 - 1.0
    if wave_name == "noise":
        seq = lfsr_sequence(inst.get("noise_mode") == "short")
        idx = np.floor(phase * 8.0 * inst.get("noise_rate", 1.0)).astype(np.int64) % len(seq)
        return seq[idx]
    duty = np.clip(inst.get("duty", 0.5) + inst.get("duty_sweep", 0.0) * t, 0.05, 0.95)
    return np.where(frac < duty, 1.0, -1.0)


def render_voice(inst, midi, dur, vel, sr=44100, waves=None):
    """Render one note (mono float64) incl. release tail."""
    n_gate = max(int(dur * sr), 1)
    n = n_gate + int(inst.get("release", 0.05) * sr)
    t = np.arange(n, dtype=np.float64) / sr
    if inst.get("fixed_note") is not None:
        midi = inst["fixed_note"]
    semis = np.zeros(n)
    vd = inst.get("vib_depth", 0.0)
    if vd:
        on = np.clip((t - inst.get("vib_delay", 0.0)) * 10.0, 0.0, 1.0)
        semis += vd * on * np.sin(2 * np.pi * inst.get("vib_rate", 5.5) * t)
    arp = inst.get("arp") or []
    if arp:
        idx = np.floor(t * inst.get("arp_speed", 30.0)).astype(np.int64) % len(arp)
        semis += np.asarray(arp, dtype=np.float64)[idx]
    sl = inst.get("slide", 0.0)
    if sl:
        semis += sl * np.clip(t / max(inst.get("slide_time", 0.1), 1e-4), 0.0, 1.0)
    freq = 440.0 * 2.0 ** ((midi + inst.get("transpose", 0) - 69 + semis) / 12.0)
    phase = np.cumsum(freq) / sr
    sig = osc(inst.get("wave", "pulse"), phase, t, inst, waves)
    env = adsr_env(n_gate, n, sr, inst.get("attack", 0.005), inst.get("decay", 0.1),
                   inst.get("sustain", 0.7), inst.get("release", 0.05))
    return sig * env * inst.get("volume", 0.8) * vel


def fx_echo(x, sr, time=0.3, feedback=0.35, mix=0.25):
    d = max(int(time * sr), 1)
    y = x.copy()
    g, k = mix, 1
    while g > 0.004 and d * k < len(x):
        y[d * k:] += g * x[:-d * k]
        g *= feedback
        k += 1
    return y


def fx_lowpass(x, sr, cutoff=6000.0):
    fc = min(max(cutoff, 50.0), sr * 0.45) / sr
    taps = 63
    m = np.arange(taps) - (taps - 1) / 2
    h = np.sinc(2 * fc * m) * np.hamming(taps)
    h /= h.sum()
    return np.stack([np.convolve(x[:, c], h, mode="same") for c in range(x.shape[1])], axis=1)


def fx_bitcrush(x, sr, bits=6, downsample=2):
    ds = max(int(downsample), 1)
    if ds > 1:
        held = x[::ds]
        x = np.repeat(held, ds, axis=0)[: len(x)] if len(x) else x
    levels = 2 ** max(int(bits), 1) / 2
    return np.round(x * levels) / levels


BUILTIN_FX = {"echo": fx_echo, "lowpass": fx_lowpass, "bitcrush": fx_bitcrush}


def apply_effects(x, sr, effects, fx_table=None):
    table = dict(BUILTIN_FX)
    if fx_table:
        table.update(fx_table)
    for fx in effects or []:
        if fx.get("enabled", True) and fx.get("type") in table:
            x = table[fx["type"]](x, sr, **fx.get("params", {}))
    return x


def mix_events(events, instruments, tracks, effects, n_samples, sr=44100, master=0.8,
               waves=None, fx_table=None, stems=False):
    """Mix compiled note events into a stereo float buffer (or per-track stems).

    events: dicts {t, dur, midi, vel, inst, track}; instruments: name -> dict;
    tracks: dicts {volume, pan, mute, solo}.
    """
    bufs = [np.zeros(n_samples) for _ in tracks]
    for ev in events:
        inst = instruments.get(ev["inst"]) or instruments.get("lead") or {}
        v = render_voice(inst, ev["midi"], ev["dur"], ev["vel"], sr, waves)
        s0 = int(round(ev["t"] * sr))
        if s0 >= n_samples:
            continue
        v = v[: n_samples - s0]
        bufs[ev["track"]][s0:s0 + len(v)] += v
    any_solo = any(t.get("solo") for t in tracks)
    outs = []
    for b, t in zip(bufs, tracks):
        audible = not t.get("mute") and (t.get("solo") or not any_solo)
        g = t.get("volume", 0.8) * (1.0 if audible else 0.0)
        p = (t.get("pan", 0.0) + 1) * np.pi / 4
        outs.append(np.stack([b * g * np.cos(p), b * g * np.sin(p)], axis=1) * np.sqrt(2) * 0.5)
    if stems:
        return [apply_effects(o, sr, effects, fx_table) * master for o in outs]
    mix = np.sum(outs, axis=0) if outs else np.zeros((n_samples, 2))
    mix = apply_effects(mix, sr, effects, fx_table) * master
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > 0.99:
        mix = mix * (0.99 / peak)
    return mix
# --- end of exportable synth block ---


# Registries that plugins extend ------------------------------------------------
EXTRA_WAVES: Dict[str, Callable] = {}
EXTRA_FX: Dict[str, Callable] = {}
FX_PARAMS: Dict[str, Dict[str, Tuple[float, float, float]]] = {   # name -> param -> (min,max,default)
    "echo": {"time": (0.02, 1.0, 0.3), "feedback": (0.0, 0.9, 0.35), "mix": (0.0, 1.0, 0.25)},
    "lowpass": {"cutoff": (200.0, 16000.0, 6000.0)},
    "bitcrush": {"bits": (2, 12, 6), "downsample": (1, 8, 2)},
}


def instrument_dicts(song: Song) -> Dict[str, dict]:
    d = {k: v.to_dict() for k, v in PRESETS.items()}
    d.update({k: v.to_dict() for k, v in song.instruments.items()})
    return d


def swing_offset(tick: int, swing: float) -> int:
    six = PPQ // 4
    if swing and tick % six == 0 and (tick // six) % 2 == 1:
        return int(round(swing * six))
    return 0


def compile_events(song: Song, start_bar: int = 0, end_bar: Optional[int] = None) -> List[dict]:
    """Flatten arrangement into timed events relative to start_bar."""
    tpb = song.ticks_per_bar
    end_bar = song.length_bars() if end_bar is None else end_bar
    t0, t1 = start_bar * tpb, end_bar * tpb
    spt = song.tick_seconds()
    evs = []
    for c in song.arrangement:
        pat = song.pattern_of(c)
        if pat is None:
            continue
        tr = song.tracks[c.track]
        base = c.bar * tpb
        plen = pat.bars * tpb
        for n in pat.notes:
            if n.start >= plen:
                continue
            at = base + n.start
            if at < t0 or at >= t1:
                continue
            at += swing_offset(n.start, song.swing)
            ln = min(n.length, plen - n.start)
            evs.append({"t": (at - t0) * spt, "dur": max(ln, 1) * spt, "midi": n.pitch,
                        "vel": n.velocity, "inst": n.inst or tr.instrument, "track": c.track})
    evs.sort(key=lambda e: e["t"])
    return evs


def track_dicts(song: Song) -> List[dict]:
    return [{"name": t.name, "volume": t.volume, "pan": t.pan, "mute": t.mute, "solo": t.solo} for t in song.tracks]


class Cancelled(Exception):
    pass


def render_song(song: Song, start_bar: int = 0, end_bar: Optional[int] = None, sr: int = SR,
                tail: float = 2.0, seamless: bool = False, stems: bool = False, effects: bool = True):
    """Render bars [start_bar, end_bar). Returns stereo float array (n,2) or list of stems.

    seamless=True folds the release/echo tail back onto the start so the
    result loops without a click or gap (length == exact loop length).
    """
    end_bar = song.length_bars() if end_bar is None else end_bar
    secs = (end_bar - start_bar) * song.ticks_per_bar * song.tick_seconds()
    n_exact = int(round(secs * sr))
    n = n_exact + int((tail if (tail or seamless) else 0) * sr)
    if seamless and tail == 0:
        n = n_exact + int(2.0 * sr)
    evs = compile_events(song, start_bar, end_bar)
    fx = song.effects if effects else []
    out = mix_events(evs, instrument_dicts(song), track_dicts(song), fx, n, sr, song.master,
                     EXTRA_WAVES, EXTRA_FX, stems)

    def fold(buf):
        if not seamless:
            return buf
        body = buf[:n_exact].copy()
        rest = buf[n_exact:]
        k = 0
        while k < len(rest) and n_exact > 0:
            seg = rest[k:k + n_exact]
            body[: len(seg)] += seg
            k += n_exact
        return body
    if stems:
        return [fold(b) for b in out]
    return fold(out)


def render_note_preview(inst: Instrument, pitch: int = 60, dur: float = 0.35, vel: float = 0.8, sr: int = SR):
    v = render_voice(inst.to_dict(), pitch, dur, vel, sr, EXTRA_WAVES)
    return np.stack([v, v], axis=1) * 0.7


def click_track(song: Song, bars: int, sr: int = SR) -> np.ndarray:
    """Metronome clicks (accent on beat 1)."""
    n_beats = bars * song.time_sig[0]
    beat_s = 60.0 / song.bpm * 4 / song.time_sig[1]
    n = int(bars * song.ticks_per_bar * song.tick_seconds() * sr) + sr // 10
    out = np.zeros(n)
    blip = Instrument(wave="pulse", duty=0.5, attack=0.001, decay=0.03, sustain=0, release=0.01, volume=0.35)
    for b in range(n_beats):
        v = render_voice(blip.to_dict(), 96 if b % song.time_sig[0] == 0 else 84, 0.03, 1.0, sr)
        s = int(b * beat_s * sr)
        v = v[: n - s]
        out[s:s + len(v)] += v
    return np.stack([out, out], axis=1)


# ---------------------------------------------------------------------------
# Audio file IO
# ---------------------------------------------------------------------------
def to_int16(x: np.ndarray) -> np.ndarray:
    return (np.clip(x, -1.0, 1.0) * 32767).astype("<i2")


def write_wav(path, data: np.ndarray, sr: int = SR) -> Path:
    """16-bit PCM WAV (stereo if data is (n,2))."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if data.ndim == 1:
        data = data[:, None]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(to_int16(data).tobytes())
    return path


def read_wav(path) -> Tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
        ch, sr = w.getnchannels(), w.getframerate()
    a = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32767
    return a.reshape(-1, ch), sr


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def export_audio(path, data: np.ndarray, sr: int = SR) -> Path:
    """Write WAV, or OGG/MP3/FLAC via ffmpeg when the extension asks for it."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext in ("", ".wav"):
        return write_wav(path if ext else path.with_suffix(".wav"), data, sr)
    if ext not in (".ogg", ".mp3", ".flac"):
        raise ValueError(f"unsupported audio format {ext}")
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg not found on PATH (needed for OGG/MP3/FLAC); export WAV instead")
    with tempfile.TemporaryDirectory() as td:
        tmp = write_wav(Path(td) / "x.wav", data, sr)
        codec = {".ogg": ["-c:a", "libvorbis", "-q:a", "6"], ".mp3": ["-c:a", "libmp3lame", "-q:a", "2"], ".flac": ["-c:a", "flac"]}[ext]
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp), *codec, str(path)], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f"ffmpeg failed: {r.stderr.strip()[:300]}")
    return path


# ---------------------------------------------------------------------------
# Note language  (compact text for melodies; used by .8bt scores, ACP, REPL)
#
#   c4 e4/8 g4/8. bb3/16t  r/4  [c4 e4 g4]/2  {Am7}/1  (c5 d5)x4  _  @192
#   o5 > <  l16  v100   c4%36 (ticks)  c4*3 (3x default length)  e4!.5 (vel)
#   drum names (kick snare hat ...) are notes for that drum instrument.
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"\(|\)(?:[x*]\d+)?|\[[^\]]*\]\S*|\{[^}]*\}\S*|[<>]|[^\s()\[\]{}|<>]+|\|")
_SUFFIX_RE = re.compile(r"^(?:/(\d+)(t?))?(\.?)(?:%(\d+))?(?:\*(\d+(?:\.\d+)?))?(?:!(\d*\.?\d+))?$")
_PITCH_RE = re.compile(r"^([a-gA-G])([#b]?)(-?\d+)?")


class NoteSyntaxError(ValueError):
    pass


def _len_from(den: str, trip: str, dot: str, ticks: str, mul: str, deflen: int) -> int:
    ln = deflen
    if den:
        ln = int(PPQ * 4 / int(den))
        if trip:
            ln = ln * 2 // 3
    if ticks:
        ln = int(ticks)
    if dot:
        ln = ln * 3 // 2
    if mul:
        ln = int(round(ln * float(mul)))
    return max(ln, 1)


def _vel(v: Optional[str], default: float) -> float:
    if not v:
        return default
    f = float(v)
    return max(0.0, min(1.0, f / 127 if f > 1 else f))


def parse_length_token(s: str) -> int:
    """'8' -> eighth, '16t' -> sixteenth triplet, '4.' -> dotted quarter."""
    mm = re.fullmatch(r"(\d+)(t?)(\.?)", s)
    if not mm:
        raise NoteSyntaxError(f"bad length {s!r}")
    return _len_from(mm.group(1), mm.group(2), mm.group(3), "", "", PPQ)


def parse_notes(text: str, octave: int = 4, deflen: int = PPQ // 2, velocity: float = 0.8,
                start: int = 0, tpb: int = PPQ * 4) -> Tuple[List[Note], int]:
    """Parse note-language text. Returns (notes, end_tick)."""
    toks = _TOKEN_RE.findall(text)
    st = {"o": octave, "l": deflen, "v": velocity, "cur": start, "last": []}
    notes: List[Note] = []

    def pitch_of(tok: str) -> Tuple[int, str]:
        m = _PITCH_RE.match(tok)
        if not m:
            raise NoteSyntaxError(f"bad note {tok!r}")
        p = _LETTER[m.group(1).lower()] + (1 if m.group(2) == "#" else -1 if m.group(2) == "b" else 0)
        o = int(m.group(3)) if m.group(3) is not None else st["o"]
        return p + (o + 1) * 12, tok[m.end():]

    def suffix(rest: str, tok: str) -> Tuple[int, float]:
        m = _SUFFIX_RE.match(rest)
        if not m:
            raise NoteSyntaxError(f"bad length/velocity in {tok!r}")
        return _len_from(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), st["l"]), _vel(m.group(6), st["v"])

    def emit(pitches: List[Tuple[int, Optional[str]]], ln: int, vel: float):
        made = [Note(st["cur"], ln, p, vel, inst) for p, inst in pitches]
        notes.extend(made)
        st["last"] = made
        st["cur"] += ln

    def run(tokens: List[str]):
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            i += 1
            if tok == "|":
                continue
            if tok == "(":
                depth, j = 1, i
                while j < len(tokens) and depth:
                    if tokens[j] == "(":
                        depth += 1
                    elif tokens[j].startswith(")"):
                        depth -= 1
                    j += 1
                if depth:
                    raise NoteSyntaxError("unclosed '('")
                close = tokens[j - 1]
                reps = int(close[2:]) if len(close) > 2 else 1
                for _ in range(reps):
                    run(tokens[i:j - 1])
                i = j
                continue
            if tok.startswith(")"):
                raise NoteSyntaxError("unmatched ')'")
            low = tok.lower()
            if tok.startswith("["):
                inner, rest = tok[1:].split("]", 1)
                ps = [pitch_of(x)[0] for x in inner.split()]
                ln, vel = suffix(rest, tok)
                emit([(p, None) for p in ps], ln, vel)
            elif tok.startswith("{"):
                inner, rest = tok[1:].split("}", 1)
                m = re.fullmatch(r"([A-Ga-g][#b]?)(.*)", inner.strip())
                if not m:
                    raise NoteSyntaxError(f"bad chord {tok!r}")
                q = m.group(2) or "maj"
                if q not in CHORDS:
                    raise NoteSyntaxError(f"unknown chord quality {q!r} (try {', '.join(CHORDS)})")
                root = key_root(m.group(1)) + (st["o"] + 1) * 12
                ln, vel = suffix(rest, tok)
                emit([(root + iv, None) for iv in CHORDS[q]], ln, vel)
            elif low in ("r", "rest") or (low.startswith("r") and low[1:2] in ("/", "%", "*", ".")):
                ln, _ = suffix(tok[1:] if low != "rest" else "", tok)
                st["cur"] += ln
                st["last"] = []
            elif low.startswith("_") or low.startswith("~"):
                ln, _ = suffix(tok[1:], tok)
                for n in st["last"]:
                    n.length += ln
                st["cur"] += ln
            elif low in (">", "<"):
                st["o"] += 1 if low == ">" else -1
            elif re.fullmatch(r"o-?\d+", low):
                st["o"] = int(low[1:])
            elif re.fullmatch(r"l\d+t?\.?", low):
                st["l"] = parse_length_token(low[1:])
            elif re.fullmatch(r"v(\d+(\.\d+)?|\.\d+)", low):
                st["v"] = _vel(low[1:], st["v"])
            elif re.fullmatch(r"@\d+", low):
                st["cur"] = start + int(low[1:])
            elif re.fullmatch(r"@b\d+(\.\d+)?", low):
                st["cur"] = start + int(round((float(low[2:]) - 1) * tpb))
            else:
                dm = re.match(r"^([a-z][a-z0-9_]*)", low)
                if dm and (dm.group(1) in DRUM_ROWS or (dm.group(1) in PRESETS and PRESETS[dm.group(1)].fixed_note is not None)):
                    ln, vel = suffix(tok[dm.end():], tok)
                    emit([(60, dm.group(1))], ln, vel)
                    continue
                p, rest = pitch_of(tok)
                ln, vel = suffix(rest, tok)
                emit([(p, None)], ln, vel)
    run(toks)
    return notes, st["cur"]


def _len_suffix(ticks: int, deflen: int) -> str:
    if ticks == deflen:
        return ""
    for den in (1, 2, 4, 8, 16, 32, 64):
        base = PPQ * 4 // den
        if ticks == base:
            return f"/{den}"
        if ticks == base * 3 // 2 and base % 2 == 0:
            return f"/{den}."
        if ticks == base * 2 // 3 and (base * 2) % 3 == 0:
            return f"/{den}t"
    return f"%{ticks}"


def _vel_str(v: float) -> str:
    """Velocity as 1-127 when exact (MIDI style), else a short decimal like .65."""
    m = v * 127
    if abs(m - round(m)) < 0.02 and round(m) > 1:
        return str(int(round(m)))
    return (f"{v:.3f}".rstrip("0").rstrip(".") or "0").lstrip("0") or "0"


def _compress_tokens(toks: List[str]) -> List[str]:
    """Run-length fold repeated motifs: 'a2 a2 a2 a2' -> '( a2 )x4'."""
    out: List[str] = []
    i, n = 0, len(toks)
    while i < n:
        best = (0, 1, 1)                      # (saved, period, reps)
        for p in range(1, min(16, (n - i) // 2) + 1):
            unit = toks[i:i + p]
            if any(t.startswith("@") for t in unit):
                break
            k = 1
            while toks[i + k * p:i + (k + 1) * p] == unit:
                k += 1
            saved = p * (k - 1) - 2
            if k > 1 and saved > best[0]:
                best = (saved, p, k)
        _, p, k = best
        if k > 1:
            out += ["(", *toks[i:i + p], f")x{k}"]
            i += p * k
        else:
            out.append(toks[i])
            i += 1
    return out


def notes_to_text(notes: List[Note], deflen: Optional[int] = None, default_vel: Optional[float] = None) -> str:
    """Serialize notes back to note language (round-trips through parse_notes).
    Picks the most common length/velocity as defaults and folds repeats."""
    from collections import Counter
    if deflen is None:
        lens = Counter(n.length for n in notes if _len_suffix(n.length, -1).startswith("/") and "." not in _len_suffix(n.length, -1))
        deflen = lens.most_common(1)[0][0] if lens else PPQ // 2
    if not _len_suffix(deflen, -1).startswith("/"):
        deflen = PPQ // 2
    out = [f"l{_len_suffix(deflen, -1)[1:]}"]
    if default_vel is None:
        vels = Counter(round(n.velocity, 4) for n in notes)
        default_vel = vels.most_common(1)[0][0] if vels else 0.8
    if abs(default_vel - 0.8) >= 1e-4:
        out.append(f"v{_vel_str(default_vel)}")
    groups: Dict[Tuple[int, int, float, Optional[str]], List[Note]] = {}
    order = []
    for n in sorted(notes, key=lambda n: (n.start, n.length, n.pitch)):
        k = (n.start, n.length, round(n.velocity, 4), n.inst)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(n)
    toks: List[str] = []
    cur = 0
    for k in order:
        start, ln, vel, inst = k
        if start > cur:
            toks.append("r" + (_len_suffix(start - cur, deflen) or ""))
        elif start < cur:
            toks.append(f"@{start}")
        vs = "" if abs(vel - default_vel) < 1e-4 else f"!{_vel_str(vel)}"
        sfx = _len_suffix(ln, deflen) + vs
        g = groups[k]
        if inst:
            toks.append(f"{inst}{sfx}")
        elif len(g) == 1:
            toks.append(note_name(g[0].pitch).lower() + sfx)
        else:
            toks.append("[" + " ".join(note_name(n.pitch).lower() for n in g) + "]" + sfx)
        cur = start + ln
    return " ".join(out + _compress_tokens(toks))


# ---------------------------------------------------------------------------
# .8bt compact score format
# ---------------------------------------------------------------------------
SCORE_HELP = """\
.8bt score (one statement per line; indented lines continue; ';' separates; # comments)
  title My Song        bpm 120     time 4/4     swing 0.1     key C minor
  master 0.8           loop 1-8    fx echo time=.3 feedback=.3 mix=.2
  inst lead pulse duty=.25 a=.01 d=.1 s=.6 r=.1 vib=.15 arp=0,4,7 slide=-12
  track lead inst=lead vol=.7 pan=-.2        track drums drum
  pat lead A: o5 l8 c e g > c < g e c r      (note language)
  pat drums A: kick=x...x...x...x... snare=....x.......x... hat=x.x.x.x.x.x.x.x.
  arr lead: A A B A -*2 A*2                  (no arr line = patterns in order)
"""

_INST_KEYS = {"a": "attack", "d": "decay", "s": "sustain", "r": "release", "vol": "volume", "vib": "vib_depth",
              "vibrate": "vib_rate", "vibdelay": "vib_delay", "arpspeed": "arp_speed", "slidetime": "slide_time",
              "sweep": "duty_sweep", "note": "fixed_note", "noise": "noise_mode", "rate": "noise_rate"}


def _kv(parts: Iterable[str]) -> Tuple[Dict[str, str], List[str]]:
    kv, pos = {}, []
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            kv[k.lower()] = v
        else:
            pos.append(p)
    return kv, pos


def _num(v: str) -> float:
    return float(v)


def apply_inst_kv(inst: Instrument, kv: Dict[str, str]) -> Instrument:
    for k, v in kv.items():
        k = _INST_KEYS.get(k, k)
        if k in ("arp", "table"):
            setattr(inst, k, [int(x) for x in re.split(r"[,\s]+", v) if x])
        elif k in ("wave", "noise_mode", "name"):
            setattr(inst, k, v)
        elif k == "fixed_note":
            inst.fixed_note = None if v in ("none", "") else (int(v) if v.lstrip("-").isdigit() else parse_note_name(v))
        elif k == "transpose":
            inst.transpose = int(v)
        elif hasattr(inst, k):
            setattr(inst, k, _num(v))
        else:
            raise ValueError(f"unknown instrument field {k!r}")
    return inst


def _strip_comment(line: str) -> str:
    m = re.search(r"^\s*#|\s#(?=\s|$)", line)
    return line[: m.start()] if m else line


def score_statements(text: str) -> List[Tuple[int, str]]:
    stmts: List[Tuple[int, str]] = []
    for ln, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        if raw[:1] in (" ", "\t") and stmts:
            stmts[-1] = (stmts[-1][0], stmts[-1][1] + " " + line.strip())
            continue
        for part in line.split(";"):
            if part.strip():
                stmts.append((ln, part.strip()))
    return stmts


class ScoreError(ValueError):
    pass


def apply_score(song: Song, text: str) -> Song:
    """Apply .8bt statements to a song (used for whole files and live commands)."""
    arranged: Dict[str, List[str]] = {}
    for ln, st in score_statements(text):
        try:
            _apply_statement(song, st, arranged)
        except (ValueError, KeyError, NoteSyntaxError) as e:
            raise ScoreError(f"line {ln}: {e}  [{st[:60]}]") from None
    # tracks with arr lines get explicit placement; tracks without get patterns in order
    touched = song.meta.pop("_touched", [])
    for ti, t in enumerate(song.tracks):
        if t.name in arranged:
            seq = arranged[t.name]
        elif t.name in touched and not any(c.track == ti for c in song.arrangement):
            seq = list(t.patterns)
        else:
            continue
        song.arrangement = [c for c in song.arrangement if c.track != ti]
        bar = 0
        for item in seq:
            if item.startswith("-"):
                bar += int(item.lstrip("-*") or 1)
                continue
            if item not in t.patterns:
                raise ScoreError(f"arr {t.name}: no pattern {item!r}")
            song.arrangement.append(Clip(ti, item, bar))
            bar += t.patterns[item].bars
    return song


def _expand_arr(items: List[str]) -> List[str]:
    out = []
    for it in items:
        m = re.fullmatch(r"(.+?)\*(\d+)", it)
        if m and not it.startswith("-"):
            out.extend([m.group(1)] * int(m.group(2)))
        else:
            out.append(it)
    return out


def _apply_statement(song: Song, st: str, arranged: Dict[str, List[str]]):
    head, _, rest = st.partition(" ")
    kw = head.rstrip(":").lower()
    rest = rest.strip()
    if kw == "title":
        song.title = rest.strip('"')
    elif kw in ("bpm", "tempo"):
        song.bpm = max(20.0, min(400.0, float(rest)))
    elif kw == "time":
        n, d = rest.split("/")
        song.time_sig = (int(n), int(d))
    elif kw == "swing":
        song.swing = max(0.0, min(0.5, float(rest)))
    elif kw == "key":
        parts = rest.split()
        k = parts[0]
        if re.fullmatch(r"[A-Ga-g][#b]?m", k):
            song.key, song.scale = k[:-1].upper()[:1] + k[1:-1], "minor"
        else:
            song.key = k
        if len(parts) > 1:
            song.scale = parts[1].lower()
        key_root(song.key)
        if song.scale not in SCALES:
            raise ValueError(f"unknown scale {song.scale!r}")
    elif kw == "scale":
        if rest.lower() not in SCALES:
            raise ValueError(f"unknown scale {rest!r}")
        song.scale = rest.lower()
    elif kw == "master":
        song.master = float(rest)
    elif kw == "loop":
        a, b = rest.replace(" ", "").split("-")
        song.loop_start, song.loop_end = int(a) - 1, int(b)
    elif kw == "fx":
        parts = rest.split()
        if parts and parts[0] == "off":
            for f in song.effects:
                f["enabled"] = False
            return
        kv, pos = _kv(parts[1:])
        name = parts[0]
        fx = next((f for f in song.effects if f["type"] == name), None)
        if fx is None:
            if name not in BUILTIN_FX and name not in EXTRA_FX:
                raise ValueError(f"unknown effect {name!r}")
            fx = {"type": name, "enabled": True, "params": {}}
            song.effects.append(fx)
        fx["enabled"] = "off" not in pos
        fx["params"].update({k: float(v) for k, v in kv.items()})
    elif kw == "inst":
        parts = rest.split()
        name = parts[0]
        kv, pos = _kv(parts[1:])
        base = None
        for p in pos:
            if p in PRESETS or p in song.instruments:
                base = copy.deepcopy(song.get_instrument(p))
            elif p in WAVE_TYPES or p in EXTRA_WAVES:
                base = base or Instrument()
                base.wave = p
            elif p in ("short", "long"):
                base = base or Instrument(wave="noise")
                base.noise_mode = p
            else:
                raise ValueError(f"unknown preset or wave {p!r}")
        inst = base or copy.deepcopy(song.instruments.get(name) or PRESETS.get(name) or Instrument())
        inst.name = name
        song.instruments[name] = apply_inst_kv(inst, kv)
    elif kw == "track":
        parts = rest.split()
        name = parts[0]
        kv, pos = _kv(parts[1:])
        try:
            t = song.tracks[song.track_index(name)]
        except KeyError:
            t = Track(name=name, patterns={})
            t.drum = "drum" in pos or name.lower() in ("drums", "drum", "perc", "noise")
            t.instrument = "snare" if t.drum else (name if name in PRESETS else "lead")
            song.tracks.append(t)
        if "drum" in pos:
            t.drum = True
        t.instrument = kv.get("inst", t.instrument)
        t.volume = float(kv.get("vol", t.volume))
        t.pan = float(kv.get("pan", t.pan))
        t.mute = kv.get("mute", str(t.mute)).lower() in ("1", "true", "yes")
        t.solo = kv.get("solo", str(t.solo)).lower() in ("1", "true", "yes")
        default_kind = "noise" if t.drum else {"triangle": "triangle", "noise": "noise"}.get(song.get_instrument(t.instrument).wave, "pulse1")
        if default_kind == "pulse1" and any(x.kind == "pulse1" for x in song.tracks if x is not t):
            default_kind = "pulse2" if not any(x.kind == "pulse2" for x in song.tracks if x is not t) else "extra"
        t.kind = kv.get("kind", t.kind if "kind" not in kv and t.kind != "pulse1" else default_kind)
    elif kw in ("pat", "pattern", "play"):
        header, sep, body = rest.partition(":")
        if not sep:
            raise ValueError("pattern needs ':' before the notes")
        hp = header.split()
        if kw == "play":
            tname, pname, kvp = hp[0], "A", hp[1:]
        elif "." in hp[0]:
            tname, pname = hp[0].split(".", 1)
            kvp = hp[1:]
        else:
            tname, pname, kvp = hp[0], hp[1], hp[2:]
        kv, _ = _kv(kvp)
        try:
            t = song.tracks[song.track_index(tname)]
        except KeyError:
            _apply_statement(song, f"track {tname}", arranged)
            t = song.tracks[song.track_index(tname)]
        tpb = song.ticks_per_bar
        notes: List[Note] = []
        end = 0
        rows = re.findall(r"([A-Za-z_][\w]*)[=:]([xXo.\-|]+)", body)
        if t.drum and rows and not re.sub(r"([A-Za-z_][\w]*)[=:]([xXo.\-|]+)", "", body).strip():
            res = int(kv.get("steps", 16))
            step = tpb // res if tpb % res == 0 else PPQ // 4
            for inst, cells in rows:
                cells = cells.replace("|", "")
                for i, ch in enumerate(cells):
                    if ch in "xXo":
                        notes.append(Note(i * step, step, 60, {"x": 0.8, "X": 1.0, "o": 0.45}[ch], inst))
                end = max(end, len(cells) * step)
        else:
            notes, end = parse_notes(body, octave=int(kv.get("o", 4)),
                                     deflen=parse_length_token(kv.get("l", "8")), tpb=tpb)
        bars = int(kv.get("bars", 0)) or max(1, math.ceil(end / tpb))
        t.patterns[pname] = Pattern(pname, bars, notes)
        song.meta.setdefault("_touched", []).append(t.name)
        if kw == "play":
            arranged[t.name] = ["A"]
    elif kw in ("arr", "arrange"):
        tname, _, seq = rest.partition(":")
        if not _:
            p = rest.split()
            tname, seq = p[0], " ".join(p[1:])
        t = song.tracks[song.track_index(tname.strip())]
        arranged[t.name] = _expand_arr(seq.split())
    else:
        raise ValueError(f"unknown statement {kw!r}")


def parse_score(text: str) -> Song:
    s = Song(title="Untitled", effects=copy.deepcopy(DEFAULT_EFFECTS))
    s.meta["source"] = "8bt"
    return apply_score(s, text)


def _inst_line(inst: Instrument) -> str:
    base = PRESETS.get(inst.name)
    ref = base if base else Instrument()
    rev = {v: k for k, v in _INST_KEYS.items()}
    parts = [f"inst {inst.name}"]
    if not base:
        parts.append(inst.wave)
    for f in dataclasses.fields(Instrument):
        if f.name in ("name",) or (not base and f.name == "wave"):
            continue
        v, rv = getattr(inst, f.name), getattr(ref, f.name)
        if v == rv:
            continue
        key = rev.get(f.name, f.name)
        if isinstance(v, list):
            sv = ",".join(str(x) for x in v)
        elif isinstance(v, float):
            sv = f"{v:g}"
        else:
            sv = str(v)
        parts.append(f"{key}={sv}")
    return " ".join(parts)


def song_to_score(song: Song) -> str:
    L = [f"# {APP_NAME} score", f"title {song.title}",
         f"bpm {song.bpm:g}; time {song.time_sig[0]}/{song.time_sig[1]}; swing {song.swing:g}; key {song.key} {song.scale}; master {song.master:g}"]
    if song.loop_end > song.loop_start:
        L.append(f"loop {song.loop_start + 1}-{song.loop_end}")
    for fx in song.effects:
        if fx.get("enabled"):
            L.append(f"fx {fx['type']} " + " ".join(f"{k}={v:g}" for k, v in fx.get("params", {}).items()))
    for inst in song.instruments.values():
        L.append(_inst_line(inst))
    tpb = song.ticks_per_bar
    for ti, t in enumerate(song.tracks):
        extras = (" drum" if t.drum else "") + (" mute=1" if t.mute else "") + (" solo=1" if t.solo else "")
        L.append(f"track {t.name} inst={t.instrument} vol={t.volume:g} pan={t.pan:g} kind={t.kind}{extras}")
        for p in t.patterns.values():
            drum_ok = t.drum and p.notes and all(n.inst and n.length == PPQ // 4 and n.start % (PPQ // 4) == 0 and n.velocity in (0.8, 1.0, 0.45) for n in p.notes)
            if drum_ok:
                steps = p.bars * tpb // (PPQ // 4)
                rows = {}
                for n in p.notes:
                    r = rows.setdefault(n.inst, ["."] * steps)
                    if n.start // (PPQ // 4) < steps:
                        r[n.start // (PPQ // 4)] = {0.8: "x", 1.0: "X", 0.45: "o"}[n.velocity]
                body = " ".join(f"{k}={''.join(v)}" for k, v in rows.items())
            else:
                body = notes_to_text(p.notes)
            L.append(f"pat {t.name}.{p.name} bars={p.bars}: {body}")
        clips = sorted((c for c in song.arrangement if c.track == ti), key=lambda c: c.bar)
        seq, bar = [], 0
        for c in clips:
            if c.bar > bar:
                seq.append(f"-*{c.bar - bar}")
            elif c.bar < bar:
                continue  # overlapping clips cannot be expressed; skipped
            seq.append(c.pattern)
            bar = c.bar + t.patterns[c.pattern].bars if c.pattern in t.patterns else c.bar + 1
        L.append(f"arr {t.name}: " + (" ".join(seq) if seq else "-"))
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# Generators: styles, random melody / drums, chord stamp, arpeggiator
# ---------------------------------------------------------------------------
GROOVES: Dict[str, Dict[str, str]] = {
    "four": {"kick": "x...x...x...x...", "snare": "....x.......x...", "hat": "..x...x...x...x."},
    "rock": {"kick": "x.......x.x.....", "snare": "....x.......x...", "hat": "x.x.x.x.x.x.x.x."},
    "soft": {"kick": "x.......x.......", "hat": "..x...x...x...x."},
    "half": {"kick": "x...............", "snare": "........x.......", "hat": "x...x...x...x..."},
    "drive": {"kick": "x..x..x.x..x..x.", "snare": "....x.......x..x", "hat": "xxxxxxxxxxxxxxxx"},
    "bounce": {"kick": "x.....x...x.....", "snare": "....x.......x...", "hat": "x.xxx.xxx.xxx.xx"},
    "none": {},
}
FILL = {"snare": "........x.x.xxxx", "kick": "x.......x......."}

STYLES: Dict[str, dict] = {
    "mellow-space": {"bpm": (88, 100), "scale": "major", "keys": ["D", "F", "G", "C"], "prog": [[0, 5, 3, 4], [0, 4, 5, 3], [5, 3, 0, 4]],
                     "lead": "flute", "harm": "arp", "bass": "bass", "bass_style": "half", "groove": "soft", "density": 0.45, "swing": 0.0, "fx": {"echo": {"time": 0.35, "feedback": 0.4, "mix": 0.3}}},
    "upbeat": {"bpm": (128, 144), "scale": "major", "keys": ["C", "G", "A", "E"], "prog": [[0, 4, 5, 3], [3, 4, 0, 0], [0, 3, 4, 3]],
               "lead": "lead", "harm": "arp", "bass": "bass", "bass_style": "octave", "groove": "four", "density": 0.75, "swing": 0.0, "fx": {}},
    "boss": {"bpm": (150, 170), "scale": "harmonic_minor", "keys": ["E", "D", "A"], "prog": [[0, 5, 3, 4], [0, 0, 5, 4], [0, 1, 0, 4]],
             "lead": "lead50", "harm": "arpminor", "bass": "bass", "bass_style": "drive", "groove": "drive", "density": 0.85, "swing": 0.0, "fx": {"bitcrush": {"bits": 7, "downsample": 1}}},
    "town": {"bpm": (100, 116), "scale": "major", "keys": ["F", "C", "Bb"], "prog": [[0, 3, 4, 0], [0, 5, 1, 4], [3, 4, 2, 5]],
             "lead": "lead", "harm": "blip", "bass": "bass", "bass_style": "walk", "groove": "bounce", "density": 0.6, "swing": 0.15, "fx": {}},
    "chill": {"bpm": (76, 90), "scale": "dorian", "keys": ["D", "A", "E"], "prog": [[0, 3, 0, 3], [0, 6, 5, 3]],
              "lead": "flute", "harm": "pad", "bass": "bass", "bass_style": "half", "groove": "half", "density": 0.35, "swing": 0.2, "fx": {"echo": {"time": 0.4, "feedback": 0.35, "mix": 0.25}, "lowpass": {"cutoff": 5000}}},
    "chase": {"bpm": (160, 180), "scale": "minor", "keys": ["A", "C", "G"], "prog": [[0, 5, 6, 4], [0, 6, 5, 6]],
              "lead": "lead", "harm": "arpminor", "bass": "pulsebass", "bass_style": "drive", "groove": "rock", "density": 0.8, "swing": 0.0, "fx": {}},
    "dungeon": {"bpm": (84, 96), "scale": "phrygian", "keys": ["E", "C"], "prog": [[0, 1, 0, 6], [0, 5, 1, 0]],
                "lead": "thin", "harm": "pad", "bass": "bass", "bass_style": "half", "groove": "half", "density": 0.4, "swing": 0.0, "fx": {"echo": {"time": 0.45, "feedback": 0.45, "mix": 0.3}}},
    "victory": {"bpm": (132, 140), "scale": "major", "keys": ["C", "D", "Bb"], "prog": [[0, 3, 4, 0], [3, 4, 0, 0]],
                "lead": "lead50", "harm": "arp", "bass": "bass", "bass_style": "octave", "groove": "four", "density": 0.7, "swing": 0.0, "fx": {}},
}
STYLE_FUNCS: Dict[str, Callable[..., Song]] = {}   # plugins: name -> fn(rng, bars, key) -> Song

_RHYTHMS = [  # in 16ths per bar (sum 16)
    [4, 4, 4, 4], [2, 2, 4, 2, 2, 4], [6, 2, 4, 4], [4, 2, 2, 8], [2, 2, 2, 2, 4, 4], [8, 4, 4], [3, 3, 2, 4, 4],
    [2, 2, 2, 2, 2, 2, 2, 2], [4, 4, 2, 2, 4], [12, 4]]


def gen_melody(rng: random.Random, root_midi: int, scale: str, prog: List[int], bars: int, tpb: int,
               density: float = 0.6, lo: int = 0, hi: int = 9) -> List[Note]:
    six = PPQ // 4
    notes: List[Note] = []
    deg = rng.randint(lo + 2, hi - 2)
    for b in range(bars):
        chord_deg = prog[b % len(prog)]
        chord = {(chord_deg + k) % 7 for k in (0, 2, 4)}
        pool = [r for r in _RHYTHMS if (len(r) <= 4) == (density < 0.5)] or _RHYTHMS
        rhythm = rng.choice(pool if rng.random() < 0.8 else _RHYTHMS)
        pos = 0
        for i, ln in enumerate(rhythm):
            if pos * six >= tpb:
                break
            if rng.random() > 0.35 + density * 0.6 and i:
                pos += ln
                continue
            step = rng.choice([-2, -1, -1, 0, 1, 1, 2, 3, -3])
            deg = max(lo, min(hi, deg + step))
            if (pos % 8 == 0) and (deg % 7) not in chord:
                cands = [d for d in range(lo, hi + 1) if d % 7 in chord]
                deg = min(cands, key=lambda d: abs(d - deg))
            ln_t = min(ln * six, tpb - pos * six)
            notes.append(Note(b * tpb + pos * six, ln_t, scale_note(root_midi, scale, deg), rng.choice([0.7, 0.8, 0.85])))
            pos += ln
    if notes:  # land on the tonic family
        notes[-1].pitch = snap_to_scale(notes[-1].pitch, root_midi % 12, scale)
    return notes


def gen_bass(root_midi: int, scale: str, prog: List[int], bars: int, tpb: int, style: str = "root8") -> List[Note]:
    out: List[Note] = []
    e = PPQ // 2
    for b in range(bars):
        r = scale_note(root_midi, scale, prog[b % len(prog)])
        while r > root_midi + 7:
            r -= 12
        fifth = scale_note(root_midi, scale, prog[b % len(prog)] + 4)
        while fifth > r + 12:
            fifth -= 12
        base = b * tpb
        if style == "half":
            out += [Note(base, tpb // 2, r, 0.85), Note(base + tpb // 2, tpb // 2, fifth if fifth < r + 12 else r, 0.8)]
        elif style == "octave":
            out += [Note(base + i * e, e, r + (12 if i % 2 else 0), 0.85) for i in range(tpb // e)]
        elif style == "walk":
            seq = [r, scale_note(root_midi, scale, prog[b % len(prog)] + 2) - (12 if r < root_midi + 7 - 12 else 0), fifth, r + 12]
            out += [Note(base + i * PPQ, PPQ, seq[i % 4] if seq[i % 4] <= r + 12 else seq[i % 4] - 12, 0.85) for i in range(tpb // PPQ)]
        elif style == "drive":
            out += [Note(base + i * (PPQ // 4), PPQ // 4, r, 0.9 if i % 4 == 0 else 0.7) for i in range(tpb // (PPQ // 4))]
        else:
            out += [Note(base + i * e, e, r, 0.85) for i in range(tpb // e)]
    return out


def gen_arp(root_midi: int, scale: str, prog: List[int], bars: int, tpb: int, mode: str = "up", rate: int = PPQ // 4) -> List[Note]:
    out: List[Note] = []
    for b in range(bars):
        ch = diatonic_chord(root_midi, scale, prog[b % len(prog)], 3)
        ch = ch + [ch[0] + 12]
        seq = ch if mode == "up" else ch + ch[-2:0:-1]
        for i in range(tpb // rate):
            out.append(Note(b * tpb + i * rate, rate, seq[i % len(seq)], 0.65))
    return out


def gen_pad(root_midi: int, scale: str, prog: List[int], bars: int, tpb: int) -> List[Note]:
    return [Note(b * tpb, tpb, p, 0.6) for b in range(bars) for p in diatonic_chord(root_midi, scale, prog[b % len(prog)], 3)]


def gen_drums(groove: str, bars: int, tpb: int, fill_last: bool = False, rng: Optional[random.Random] = None) -> List[Note]:
    g = GROOVES.get(groove, GROOVES["four"])
    step = PPQ // 4
    out: List[Note] = []
    for b in range(bars):
        rows = dict(g)
        if fill_last and b == bars - 1:
            rows.update(FILL)
        for inst, cells in rows.items():
            for i, ch in enumerate(cells):
                if i * step >= tpb:
                    break
                hit = ch == "x"
                if rng and inst == "hat" and not hit and rng.random() < 0.08:
                    hit = True
                if hit:
                    out.append(Note(b * tpb + i * step, step, 60, 1.0 if (i == 0 and inst == "kick") else 0.8, inst))
    return out


def style_names() -> List[str]:
    return sorted(set(STYLES) | set(STYLE_FUNCS))


def generate_song(style: str = "mellow-space", bars: int = 16, seed: Optional[int] = None, key: Optional[str] = None,
                  bpm: Optional[float] = None) -> Song:
    """Compose a complete, loopable song in a style. Deterministic for a seed."""
    rng = random.Random(seed)
    if style in STYLE_FUNCS:
        s = STYLE_FUNCS[style](rng, bars, key)
        if bpm:
            s.bpm = bpm
        return s
    if style not in STYLES:
        raise ValueError(f"unknown style {style!r}; try: {', '.join(style_names())}")
    sp = STYLES[style]
    s = Song(title=f"{style.replace('-', ' ').title()} #{seed if seed is not None else rng.randint(1, 999)}")
    s.bpm = bpm or rng.randint(*sp["bpm"])
    s.key = key or rng.choice(sp["keys"])
    s.scale = sp["scale"]
    s.swing = sp["swing"]
    for f in s.effects:
        if f["type"] in sp["fx"]:
            f["enabled"] = True
            f["params"].update(sp["fx"][f["type"]])
    tpb = s.ticks_per_bar
    pb = min(4, bars)
    root = key_root(s.key)
    lead_root = 60 + root + (0 if root < 6 else -12) + 12
    bass_root = 36 + root + (12 if root < 5 else 0)
    harm_root = 48 + root + (12 if root < 5 else 0)
    progA = rng.choice(sp["prog"])
    progB = rng.choice(sp["prog"])
    s.tracks = [Track("Lead", "pulse1", sp["lead"], 0.75, -0.15), Track("Harmony", "pulse2", sp["harm"], 0.55, 0.2),
                Track("Bass", "triangle", sp["bass"], 0.9, 0.0), Track("Drums", "noise", "snare", 0.75, 0.0, drum=True)]
    for name, prog, fill in (("A", progA, False), ("B", progB, True)):
        lead = gen_melody(rng, lead_root, s.scale, prog, pb, tpb, sp["density"])
        if sp["harm"] == "pad":
            harm = gen_pad(harm_root, s.scale, prog, pb, tpb)
        elif sp["harm"] in ("blip",):
            harm = gen_arp(harm_root, s.scale, prog, pb, tpb, "updown", PPQ // 2)
        else:
            harm = [Note(b * tpb + i * PPQ, PPQ, diatonic_chord(harm_root, s.scale, prog[b % len(prog)])[i % 3], 0.6)
                    for b in range(pb) for i in range(tpb // PPQ)]
        s.tracks[0].patterns[name] = Pattern(name, pb, lead)
        s.tracks[1].patterns[name] = Pattern(name, pb, harm)
        s.tracks[2].patterns[name] = Pattern(name, pb, gen_bass(bass_root, s.scale, prog, pb, tpb, sp["bass_style"]))
        s.tracks[3].patterns[name] = Pattern(name, pb, gen_drums(sp["groove"], pb, tpb, fill, rng))
    nblocks = max(1, math.ceil(bars / pb))
    for i in range(nblocks):
        name = "B" if (i % 4 == 2 or (i == nblocks - 1 and nblocks > 2 and i % 4 == 3)) else "A"
        for ti in range(4):
            if ti == 0 and i == 0 and nblocks > 2:
                continue  # intro without lead
            s.arrangement.append(Clip(ti, name, i * pb))
    s.loop_start, s.loop_end = 0, nblocks * pb
    s.meta["generator"] = {"style": style, "bars": bars, "seed": seed}
    return s


def arpeggiate(notes: List[Note], rate: int = PPQ // 4, mode: str = "up") -> List[Note]:
    """Turn chords (notes sharing a start) into arpeggios."""
    by: Dict[int, List[Note]] = {}
    for n in notes:
        by.setdefault(n.start, []).append(n)
    out: List[Note] = []
    for st, grp in sorted(by.items()):
        if len(grp) < 2:
            out.extend(grp)
            continue
        ps = sorted(n.pitch for n in grp)
        seq = {"up": ps, "down": ps[::-1], "updown": ps + ps[-2:0:-1]}.get(mode, ps)
        ln = max(n.length for n in grp)
        for i in range(max(1, ln // rate)):
            out.append(Note(st + i * rate, rate, seq[i % len(seq)], grp[0].velocity))
    return out


def chord_stamp(root_pitch: int, quality: str, start: int, length: int, song: Optional[Song] = None,
                diatonic: bool = False, vel: float = 0.75) -> List[Note]:
    if diatonic and song is not None:
        r = key_root(song.key)
        p = snap_to_scale(root_pitch, r, song.scale)
        deg = SCALES[song.scale].index((p - r) % 12) if (p - r) % 12 in SCALES[song.scale] else 0
        base = p - SCALES[song.scale][deg]
        pitches = [scale_note(base, song.scale, deg + 2 * k) for k in range(3)]
    else:
        pitches = [root_pitch + iv for iv in CHORDS.get(quality, CHORDS["maj"])]
    return [Note(start, length, p, vel) for p in pitches]


def quantize(notes: List[Note], grid: int, strength: float = 1.0, lengths: bool = False):
    for n in notes:
        q = int(round(n.start / grid) * grid)
        n.start = int(round(n.start + (q - n.start) * strength))
        if lengths:
            n.length = max(grid, int(round(n.length / grid) * grid))


# ---------------------------------------------------------------------------
# Demo song (written in the .8bt score language)
# ---------------------------------------------------------------------------
DEMO_SCORE = """\
# Neon Orbit - demo song for 8Bit Music Code Studio (original composition)
title Neon Orbit
bpm 112; time 4/4; swing 0; key C major; master 0.85
loop 5-16
fx echo time=0.32 feedback=0.3 mix=0.18
track Lead inst=lead vol=0.75 pan=-0.15
track Arp inst=thin vol=0.45 pan=0.25
track Bass inst=bass vol=0.9
track Drums drum vol=0.7
pat Lead.A: e5/8 g5/8 c6/4 b5/8 g5/8 e5/4 | a5/8 c6/8 e6/4 d6/8 c6/8 a5/4
            f5 a5 c6 a5 g5 f5 e5 f5 | g5/4. d5/8 g5/4 r/4
pat Lead.B: a5/4 c6/8 a5/8 g5/4 f5/4 | g5/8 a5/8 b5/8 d6/8 c6/4 b5/4
            c6/8 b5/8 g5/8 e5/8 g5/4 c6/4 | d6/2 r/4 g5/8 b5/8
pat Arp.A: l16 (c4 e4 g4 c5)x4 (a3 c4 e4 a4)x4 (f3 a3 c4 f4)x4 (g3 b3 d4 g4)x4
pat Arp.B: l16 (f3 a3 c4 f4)x4 (g3 b3 d4 g4)x4 (c4 e4 g4 c5)x4 (g3 b3 d4 g4)x4
pat Bass.A: l8 (c3 c3 g2 c3)x2 (a2 a2 e2 a2)x2 (f2 f2 c3 f2)x2 (g2 g2 d3 g2)x2
pat Bass.B: l8 (f2 f2 c3 f2)x2 (g2 g2 d3 g2)x2 (c3 c3 g2 c3)x2 (g2 g2 d3 b2)x2
pat Drums.A: kick=x...x...x...x...|x...x...x...x...|x...x...x...x...|x...x...x...x...
             snare=....x.......x...|....x.......x...|....x.......x...|....x.......x...
             hat=..x...x...x...x.|..x...x...x...x.|..x...x...x...x.|..x...x...x.x.x.
pat Drums.B: kick=x...x...x...x...|x...x...x...x...|x...x...x...x...|x...x...x.x.x...
             snare=....x.......x...|....x.......x...|....x.......x...|....x...x.xXxXXX
             ohat=..x...x...x...x.|..x...x...x...x.|..x...x...x...x.|..x...x.........
arr Lead: -*4 A B A
arr Arp: A A B A
arr Bass: A A B A
arr Drums: A A B A
"""


def demo_song() -> Song:
    return parse_score(DEMO_SCORE)


def new_song() -> Song:
    s = Song(title="Untitled")
    s.tracks = [Track("Pulse 1", "pulse1", "lead", 0.75, -0.15, patterns={"A": Pattern("A", 4)}),
                Track("Pulse 2", "pulse2", "arp", 0.5, 0.2, patterns={"A": Pattern("A", 4)}),
                Track("Triangle", "triangle", "bass", 0.9, 0.0, patterns={"A": Pattern("A", 4)}),
                Track("Noise", "noise", "snare", 0.7, 0.0, drum=True, patterns={"A": Pattern("A", 4)})]
    s.arrangement = [Clip(i, "A", 0) for i in range(4)]
    return s


# ---------------------------------------------------------------------------
# "Save as code" exporters
# ---------------------------------------------------------------------------
_EXPORT_FUNCS = ["lfsr_sequence", "adsr_env", "osc", "render_voice", "fx_echo", "fx_lowpass", "fx_bitcrush",
                 "apply_effects", "mix_events"]


def _song_payload(song: Song, start_bar: int = 0, end_bar: Optional[int] = None) -> dict:
    a, b = (start_bar, end_bar if end_bar is not None else song.length_bars())
    used = {e["inst"] for e in compile_events(song, a, b)}
    insts = instrument_dicts(song)
    return {"title": song.title, "bpm": song.bpm, "timeSig": list(song.time_sig), "key": song.key, "scale": song.scale,
            "seconds": (b - a) * song.ticks_per_bar * song.tick_seconds(), "master": song.master,
            "loopStartBar": a, "loopEndBar": b,
            "instruments": {k: v for k, v in insts.items() if k in used or k == "lead"},
            "tracks": track_dicts(song), "effects": [f for f in song.effects if f.get("enabled")],
            "events": compile_events(song, a, b)}   # full float precision -> sample-identical re-render


def export_python(song: Song, seamless: bool = False) -> str:
    """Standalone Python script (numpy only) that regenerates the song as WAV."""
    import inspect
    data = _song_payload(song)
    src = "\n\n".join(inspect.getsource(globals()[f]) for f in _EXPORT_FUNCS)
    return f'''#!/usr/bin/env python3
"""{song.title} - generated by {APP_NAME} {APP_VERSION}.

Regenerates the song as a 16-bit 44.1 kHz stereo WAV using only numpy:
    python {re.sub(r"[^A-Za-z0-9_]+", "_", song.title).strip("_").lower() or "song"}.py [out.wav] [--seamless]
"""
import json
import sys
import wave

import numpy as np

SONG = json.loads(r"""{json.dumps(data, separators=(",", ":"))}""")

_LFSR_CACHE = {{}}

{src}

BUILTIN_FX = {{"echo": fx_echo, "lowpass": fx_lowpass, "bitcrush": fx_bitcrush}}


def render(sr=44100, seamless={seamless!r}):
    n_exact = int(round(SONG["seconds"] * sr))
    n = n_exact + int((2.0 if seamless else 1.5) * sr)
    out = mix_events(SONG["events"], SONG["instruments"], SONG["tracks"], SONG["effects"], n, sr, SONG["master"])
    if not seamless:
        return out
    body = out[:n_exact].copy()
    tail = out[n_exact:]
    for k in range(0, len(tail), n_exact):
        seg = tail[k:k + n_exact]
        body[: len(seg)] += seg
    return body


def main():
    argv = sys.argv[1:]
    path = "song.wav"
    for i, a in enumerate(argv):
        if a in ("-o", "--out") and i + 1 < len(argv):
            path = argv[i + 1]
        elif not a.startswith("-") and (i == 0 or argv[i - 1] not in ("-o", "--out")):
            path = a
    data = render(seamless="--seamless" in sys.argv or {seamless!r})
    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(pcm.tobytes())
    print(path)


if __name__ == "__main__":
    main()
'''


_DRUM_MAP = {"kick": "kick", "tom": "kick", "snare": "snare", "clap": "snare", "hat": "hat", "ohat": "hat", "crash": "hat", "metal": "hat"}

JS_PLAYER = r"""
// ---- tiny Web Audio chiptune player (no dependencies) ----------------------
const _waves = new Map();
function _pulseWave(ctx, duty) {
  const key = 'p' + duty;
  if (_waves.has(key)) return _waves.get(key);
  const N = 64, re = new Float32Array(N), im = new Float32Array(N);
  for (let n = 1; n < N; n++) { re[n] = (2 / (n * Math.PI)) * Math.sin(2 * Math.PI * n * duty); im[n] = (2 / (n * Math.PI)) * (1 - Math.cos(2 * Math.PI * n * duty)); }
  const w = ctx.createPeriodicWave(re, im); _waves.set(key, w); return w;
}
function _tableWave(ctx, table) {
  const key = 't' + table.join(',');
  if (_waves.has(key)) return _waves.get(key);
  const L = table.length, N = Math.min(32, Math.floor(L / 2)), re = new Float32Array(N + 1), im = new Float32Array(N + 1);
  for (let k = 1; k <= N; k++) for (let i = 0; i < L; i++) { const v = table[i] / 7.5 - 1, a = 2 * Math.PI * k * i / L; re[k] += v * Math.cos(a) / L; im[k] += v * Math.sin(a) / L; }
  const w = ctx.createPeriodicWave(re, im); _waves.set(key, w); return w;
}
const _noise = new Map();
function _noiseBuffer(ctx, short) {
  if (_noise.has(short)) return _noise.get(short);
  const len = short ? 93 : 32767, buf = ctx.createBuffer(1, len * 8, ctx.sampleRate), d = buf.getChannelData(0);
  let reg = 1; const tap = short ? 6 : 1;
  for (let i = 0; i < len; i++) { const bit = (reg ^ (reg >> tap)) & 1; reg = (reg >> 1) | (bit << 14); const v = (reg & 1) ? 1 : -1; for (let j = 0; j < 8; j++) d[i * 8 + j] = v; }
  _noise.set(short, buf); return buf;
}
const midiHz = (m) => 440 * Math.pow(2, (m - 69) / 12);

/** Schedule one note event at absolute AudioContext time `when`. */
export function playNote(ctx, dest, inst, ev, when) {
  const midi = (inst.fixed_note ?? ev.midi) + (inst.transpose || 0);
  const hz = midiHz(midi), end = when + ev.dur, stop = end + (inst.release || 0.05) + 0.02;
  let src, pitchParam;
  if (inst.wave === 'noise') {
    src = ctx.createBufferSource(); src.buffer = _noiseBuffer(ctx, inst.noise_mode === 'short'); src.loop = true;
    src.playbackRate.value = (hz * 8 * (inst.noise_rate || 1)) / ctx.sampleRate * 8; pitchParam = src.detune;
  } else {
    src = ctx.createOscillator(); pitchParam = src.detune;
    if (inst.wave === 'triangle') src.type = 'triangle';
    else if (inst.wave === 'saw') src.type = 'sawtooth';
    else if (inst.wave === 'sine') src.type = 'sine';
    else if (inst.wave === 'wave') src.setPeriodicWave(_tableWave(ctx, inst.table || [8]));
    else src.setPeriodicWave(_pulseWave(ctx, inst.duty ?? 0.5));
    src.frequency.value = hz;
  }
  const g = ctx.createGain(), peak = (inst.volume ?? 0.8) * ev.vel * 0.5, a = Math.max(inst.attack || 0.005, 0.001), d = Math.max(inst.decay || 0.1, 0.001);
  g.gain.setValueAtTime(0, when); g.gain.linearRampToValueAtTime(peak, when + a);
  g.gain.linearRampToValueAtTime(peak * (inst.sustain ?? 0.7), when + a + d);
  g.gain.setValueAtTime(peak * (inst.sustain ?? 0.7), Math.max(end, when + a + d)); g.gain.linearRampToValueAtTime(0, stop - 0.02);
  if (inst.slide) { pitchParam.setValueAtTime(0, when); pitchParam.linearRampToValueAtTime(inst.slide * 100, when + (inst.slide_time || 0.1)); }
  if (inst.arp && inst.arp.length) { const step = 1 / (inst.arp_speed || 30); let i = 0; for (let t = when; t < stop; t += step, i++) pitchParam.setValueAtTime(inst.arp[i % inst.arp.length] * 100 + (inst.slide || 0) * 0, t); }
  if (inst.vib_depth) { const lfo = ctx.createOscillator(), lg = ctx.createGain(); lfo.frequency.value = inst.vib_rate || 5.5; lg.gain.setValueAtTime(0, when); lg.gain.linearRampToValueAtTime(inst.vib_depth * 100, when + (inst.vib_delay || 0) + 0.1); lfo.connect(lg).connect(pitchParam); lfo.start(when); lfo.stop(stop); }
  src.connect(g).connect(dest); src.start(when); src.stop(stop);
  return src;
}

/** Build the mixer graph (per-track gain + pan, echo, low-pass) into `destination`. */
export function createMixer(ctx, destination = ctx.destination, song = SONG) {
  const master = ctx.createGain(); master.gain.value = song.master;
  let out = master;
  const lp = song.effects.find((f) => f.type === 'lowpass');
  if (lp) { const f = ctx.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = lp.params.cutoff || 6000; master.connect(f); out = f; }
  out.connect(destination);
  const echo = song.effects.find((f) => f.type === 'echo');
  const bus = ctx.createGain(); bus.connect(master);
  if (echo) { const dl = ctx.createDelay(2), fb = ctx.createGain(), wet = ctx.createGain(); dl.delayTime.value = echo.params.time || 0.3; fb.gain.value = echo.params.feedback || 0.3; wet.gain.value = echo.params.mix || 0.25; bus.connect(dl); dl.connect(fb).connect(dl); dl.connect(wet).connect(master); }
  const solo = song.tracks.some((t) => t.solo);
  const tracks = song.tracks.map((t) => { const g = ctx.createGain(); g.gain.value = (t.mute || (solo && !t.solo)) ? 0 : t.volume; let n = g; if (ctx.createStereoPanner) { const p = ctx.createStereoPanner(); p.pan.value = t.pan; g.connect(p); n = p; } n.connect(bus); return g; });
  return { master, tracks };
}

/**
 * createPlayer(ctx, {destination, loop}) -> {start(), stop(), playing, position()}
 * Look-ahead scheduler; loops the whole song (seamless) when loop is true.
 */
export function createPlayer(ctx, opts = {}) {
  const song = opts.song || SONG, loop = opts.loop ?? true, ahead = 0.15;
  let timer = null, t0 = 0, idx = 0, cycle = 0, mixer = null;
  const tick = () => {
    const horizon = ctx.currentTime + ahead;
    for (;;) {
      if (idx >= song.events.length) { if (!loop) { if (ctx.currentTime > t0 + song.seconds) api.stop(); return; } idx = 0; cycle++; }
      const ev = song.events[idx], when = t0 + cycle * song.seconds + ev.t;
      if (when > horizon) return;
      if (when >= ctx.currentTime - 0.01) playNote(ctx, mixer.tracks[ev.track], song.instruments[ev.inst] || song.instruments.lead, ev, when);
      idx++;
    }
  };
  const api = {
    playing: false,
    start() { if (api.playing) return; mixer = createMixer(ctx, opts.destination || ctx.destination, song); t0 = ctx.currentTime + 0.05; idx = 0; cycle = 0; api.playing = true; tick(); timer = setInterval(tick, 25); },
    stop() { api.playing = false; if (timer) clearInterval(timer); timer = null; if (mixer) { try { mixer.master.disconnect(); } catch (e) { /* ignore */ } } mixer = null; },
    position() { return api.playing ? (ctx.currentTime - t0) % song.seconds : 0; },
  };
  return api;
}

/** Render to an AudioBuffer offline (browser OfflineAudioContext). */
export async function renderOffline(sampleRate = 44100, song = SONG) {
  const ctx = new OfflineAudioContext(2, Math.ceil((song.seconds + 2) * sampleRate), sampleRate);
  const mixer = createMixer(ctx, ctx.destination, song);
  for (const ev of song.events) playNote(ctx, mixer.tracks[ev.track], song.instruments[ev.inst] || song.instruments.lead, ev, ev.t);
  return ctx.startRendering();
}
"""


def export_js(song: Song) -> str:
    """ES module: song data + a dependency-free Web Audio player."""
    data = _song_payload(song)
    step_sec = 60.0 / song.bpm / 4
    for e in data["events"]:
        e["t"], e["dur"] = round(e["t"], 6), round(e["dur"], 6)
        e["step"] = round(e["t"] / step_sec, 4)
        e["len"] = round(e["dur"] / step_sec, 4)
        e["voice"] = song.tracks[e["track"]].name
    lv = []
    for e in data["events"]:
        d = {"voice": e["voice"], "step": e["step"], "len": e["len"], "vel": e["vel"]}
        if e["inst"] in _DRUM_MAP and song.get_instrument(e["inst"]).fixed_note is not None:
            d["drum"] = _DRUM_MAP[e["inst"]]
        else:
            d["midi"] = e["midi"]
        lv.append(d)
    return (f"// {song.title} - generated by {APP_NAME} {APP_VERSION}\n"
            "// ES module. Usage:\n"
            "//   import SONG, { createPlayer } from './song.js';\n"
            "//   const ctx = new AudioContext(); const p = createPlayer(ctx, { loop: true }); p.start();\n"
            f"export const SONG = {json.dumps(data, separators=(',', ':'))};\n"
            f"/** Events in 16th-note steps ({{voice, step, len, midi|drum, vel}}) for step sequencers. */\n"
            f"export const STEP_EVENTS = {json.dumps(lv, separators=(',', ':'))};\n"
            f"export const STEPS = {round(data['seconds'] / step_sec)};\n"
            f"export const STEP_SECONDS = {step_sec!r};\n"
            + JS_PLAYER + "\nexport default SONG;\n")


def export_json(song: Song) -> str:
    d = song.to_dict()
    d["compiled"] = _song_payload(song)
    return json.dumps(d, indent=1)


# Exporter/importer registries (plugins add more): name -> (extension, fn(song)->str|bytes)
EXPORTERS: Dict[str, Tuple[str, Callable[[Song], Any]]] = {
    "py": (".py", export_python), "js": (".js", export_js), "json": (".json", export_json),
    "score": (".8bt", song_to_score), "project": (".8bms", lambda s: json.dumps(s.to_dict(), indent=1)),
}
IMPORTERS: Dict[str, Callable[[str], Song]] = {}   # extension -> fn(text) -> Song


def export_code(song: Song, kind: str, path) -> Path:
    if kind not in EXPORTERS:
        raise ValueError(f"unknown exporter {kind!r}; have {', '.join(EXPORTERS)}")
    data = EXPORTERS[kind][1](song)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data)
    return path


# ---------------------------------------------------------------------------
# Project IO, recent files, autosave
# ---------------------------------------------------------------------------
def save_project(song: Song, path) -> Path:
    path = Path(path)
    if path.suffix.lower() == SCORE_EXT:
        path.write_text(song_to_score(song))
    else:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(song.to_dict(), indent=1))
        os.replace(tmp, path)
    add_recent(path)
    return path


def load_project(path) -> Song:
    path = Path(path)
    ext = path.suffix.lower()
    text = path.read_text()
    if ext == SCORE_EXT:
        return parse_score(text)
    if ext in IMPORTERS:
        return IMPORTERS[ext](text)
    d = json.loads(text)
    if "tracks" not in d:
        raise ValueError("not an 8bms project")
    return Song.from_dict(d)


def load_any(src: str) -> Song:
    """Path to .8bms/.8bt/.json, 'demo', or 'gen:<style>[:bars[:seed]]'."""
    if src == "demo":
        return demo_song()
    if src.startswith("gen:"):
        p = src.split(":")
        return generate_song(p[1], int(p[2]) if len(p) > 2 else 16, int(p[3]) if len(p) > 3 else None)
    if src == "-":
        return parse_score(sys.stdin.read())
    return load_project(src)


def recent_files() -> List[str]:
    f = home_dir() / "recent.json"
    try:
        return [p for p in json.loads(f.read_text()) if Path(p).exists()][:10]
    except Exception:
        return []


def add_recent(path) -> None:
    f = home_dir() / "recent.json"
    lst = [str(Path(path).resolve())] + [p for p in recent_files() if p != str(Path(path).resolve())]
    try:
        f.write_text(json.dumps(lst[:10]))
    except OSError:
        pass


def autosave_path() -> Path:
    return home_dir() / "autosave.8bms"


# ---------------------------------------------------------------------------
# Ops registry: one definition -> CLI, Python API, HTTP, MCP and ACP
# ---------------------------------------------------------------------------
@dataclass
class Op:
    name: str
    fn: Callable[..., dict]
    help: str = ""
    params: Dict[str, dict] = field(default_factory=dict)   # name -> {type, default, help, required}
    owner: str = "core"

    def json_schema(self) -> dict:
        tmap = {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "path": "string"}
        props = {k: {"type": tmap.get(v.get("type", "str"), "string"), "description": v.get("help", "")} for k, v in self.params.items()}
        req = [k for k, v in self.params.items() if v.get("required")]
        return {"type": "object", "properties": props, "required": req}

    def coerce(self, kwargs: dict) -> dict:
        out = {}
        for k, spec in self.params.items():
            if k in kwargs and kwargs[k] is not None:
                v, t = kwargs[k], spec.get("type", "str")
                if t == "int":
                    v = int(v)
                elif t == "float":
                    v = float(v)
                elif t == "bool":
                    v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")
                out[k] = v
            elif spec.get("required"):
                raise ValueError(f"{self.name}: missing parameter {k!r}")
            elif "default" in spec:
                out[k] = spec["default"]
        return out

    def __call__(self, **kwargs) -> dict:
        return self.fn(**self.coerce(kwargs))


OPS: Dict[str, Op] = {}


def register_op(name: str, help: str = "", owner: str = "core", **params):
    def deco(fn):
        OPS[name] = Op(name, fn, help, params, owner)
        return fn
    return deco


def run_op(name: str, **kwargs) -> dict:
    if name not in OPS:
        raise KeyError(f"unknown op {name!r}; have {', '.join(sorted(OPS))}")
    return OPS[name](**kwargs)


def _parse_bars(bars: Optional[str], song: Song) -> Tuple[int, int]:
    if not bars:
        return 0, song.length_bars()
    a, _, b = str(bars).partition("-")
    return int(a) - 1, int(b or a)


@register_op("render", "Render a song to audio (wav/ogg/mp3/flac).",
             src={"type": "str", "required": True, "help": "file .8bt/.8bms, 'demo' or gen:style:bars:seed"},
             out={"type": "path", "default": "out.wav", "help": "output file (extension picks format)"},
             loop={"type": "bool", "default": False, "help": "render only the loop region"},
             seamless={"type": "bool", "default": False, "help": "gapless loop file: loop region (or --bars) with the tail folded into the start"},
             bars={"type": "str", "default": None, "help": "bar range like 1-8"},
             stems={"type": "path", "default": None, "help": "also write per-track stems into this folder"})
def op_render(src, out="out.wav", loop=False, seamless=False, bars=None, stems=None):
    song = load_any(src) if isinstance(src, str) else src
    a, b = song.loop_range() if (loop or (seamless and not bars)) else _parse_bars(bars, song)
    data = render_song(song, a, b, seamless=seamless, tail=0 if seamless else 1.5)
    p = export_audio(out, data)
    res = {"path": str(Path(p).resolve()), "seconds": round(len(data) / SR, 2), "bars": f"{a + 1}-{b}"}
    if stems:
        d = Path(stems)
        d.mkdir(parents=True, exist_ok=True)
        res["stems"] = []
        for t, st in zip(song.tracks, render_song(song, a, b, seamless=seamless, stems=True, tail=0 if seamless else 1.5)):
            res["stems"].append(str(write_wav(d / f"{re.sub(r'[^A-Za-z0-9_-]+', '_', t.name)}.wav", st).resolve()))
    return res


@register_op("export", "Export a song as code/data: js, py, json, score (.8bt), project (.8bms) or plugin formats.",
             src={"type": "str", "required": True, "help": "song source"},
             kind={"type": "str", "required": True, "help": "exporter name"},
             out={"type": "path", "default": None, "help": "output path (default from title)"})
def op_export(src, kind, out=None):
    song = load_any(src) if isinstance(src, str) else src
    if kind not in EXPORTERS:
        raise ValueError(f"unknown exporter {kind!r}; have {', '.join(EXPORTERS)}")
    ext = EXPORTERS[kind][0]
    out = out or (re.sub(r"[^A-Za-z0-9_]+", "_", song.title).strip("_").lower() or "song") + ext
    p = export_code(song, kind, out)
    return {"path": str(p.resolve()), "kind": kind, "bytes": p.stat().st_size}


@register_op("gen", "Generate a song in a style. Returns score text, or writes it to out (.8bt/.8bms).",
             style={"type": "str", "default": "mellow-space", "help": "style name"},
             bars={"type": "int", "default": 16, "help": "length in bars"},
             seed={"type": "int", "default": None, "help": "random seed"},
             key={"type": "str", "default": None, "help": "key like C, F#, Bb"},
             bpm={"type": "float", "default": None, "help": "tempo"},
             out={"type": "path", "default": None, "help": "write score/project here"},
             wav={"type": "path", "default": None, "help": "also render a WAV"})
def op_gen(style="mellow-space", bars=16, seed=None, key=None, bpm=None, out=None, wav=None):
    song = generate_song(style, bars, seed, key, bpm)
    res: Dict[str, Any] = {"title": song.title, "bpm": song.bpm, "key": f"{song.key} {song.scale}", "bars": song.length_bars()}
    if out:
        res["path"] = str(save_project(song, out).resolve())
    else:
        res["score"] = song_to_score(song)
    if wav:
        res["wav"] = op_render(song, wav)["path"]
    return res


@register_op("info", "Summarize a song.", src={"type": "str", "required": True, "help": "song source"})
def op_info(src):
    s = load_any(src) if isinstance(src, str) else src
    a, b = s.loop_range()
    return {"title": s.title, "bpm": s.bpm, "time": f"{s.time_sig[0]}/{s.time_sig[1]}", "key": f"{s.key} {s.scale}",
            "bars": s.length_bars(), "seconds": round(s.length_bars() * s.ticks_per_bar * s.tick_seconds(), 2),
            "loop": f"{a + 1}-{b}", "notes": s.note_count(),
            "tracks": [f"{t.name}({t.instrument},{'drum,' if t.drum else ''}{len(t.patterns)}p)" for t in s.tracks]}


@register_op("check", "Validate a score/project; returns ok or the first error.", src={"type": "str", "required": True, "help": "file"})
def op_check(src):
    s = load_any(src)
    return {"ok": True, "bars": s.length_bars(), "notes": s.note_count()}


@register_op("presets", "List instrument presets (and user instruments).")
def op_presets():
    return {"presets": sorted(PRESETS), "user": sorted(user_instruments())}


@register_op("styles", "List generator styles.")
def op_styles():
    return {"styles": style_names()}


@register_op("score_help", "Show the .8bt score syntax.")
def op_score_help():
    return {"text": SCORE_HELP}


# ---------------------------------------------------------------------------
# Interpreter: prompts -> studio operations (shared by ACP, REPL, HTTP)
# ---------------------------------------------------------------------------
SCORE_KEYWORDS = {"title", "bpm", "tempo", "time", "swing", "key", "scale", "master", "loop", "fx", "inst", "track",
                  "pat", "pattern", "play", "arr", "arrange"}
SLASH_COMMANDS: Dict[str, Tuple[Callable, str]] = {}      # plugins: name -> (fn(interp, args)->str, help)
VISUALIZERS: Dict[str, Callable[[Song], str]] = {}
ML_BACKENDS: Dict[str, Any] = {}                           # name -> object with generate(prompt, song, **kw)

STYLE_WORDS = [("mellow-space", ["space", "mellow", "orbit", "galaxy", "ambient", "star"]), ("boss", ["boss", "battle", "fight"]),
               ("town", ["town", "village", "shop", "city"]), ("chase", ["chase", "run", "race", "escape"]),
               ("chill", ["chill", "lofi", "relax"]), ("dungeon", ["dungeon", "cave", "spooky", "dark"]),
               ("victory", ["victory", "win", "fanfare"]), ("upbeat", ["upbeat", "happy", "fast", "energetic", "dance"])]


def ascii_roll(song: Song, track: int = 0, pattern: Optional[str] = None, width: int = 64) -> str:
    if not song.tracks:
        return "(no tracks)"
    t = song.tracks[track]
    p = t.patterns.get(pattern or next(iter(t.patterns), ""), None)
    if not p or not p.notes:
        return f"{t.name}: (empty)"
    step = PPQ // 4
    cols = min(width, p.bars * song.ticks_per_bar // step)
    if t.drum:
        rows = sorted({n.inst or "?" for n in p.notes}, key=lambda r: DRUM_ROWS.index(r) if r in DRUM_ROWS else 99)
        lines = []
        for r in rows:
            cells = ["."] * cols
            for n in p.notes:
                if (n.inst or "?") == r and n.start // step < cols:
                    cells[n.start // step] = "x"
            lines.append(f"{r:>6} |" + "".join(cells))
        return f"{t.name}.{p.name}\n" + "\n".join(lines)
    hi, lo = max(n.pitch for n in p.notes), min(n.pitch for n in p.notes)
    lines = []
    for pitch in range(hi, lo - 1, -1):
        cells = ["-" if in_scale(pitch, key_root(song.key), song.scale) else " "] * cols
        for n in p.notes:
            if n.pitch == pitch:
                for c in range(n.start // step, min(cols, (n.start + n.length) // step)):
                    cells[c] = "#" if c == n.start // step else "="
        lines.append(f"{note_name(pitch):>4} |" + "".join(cells))
    return f"{t.name}.{p.name}\n" + "\n".join(lines)


VISUALIZERS["roll"] = lambda s: "\n\n".join(ascii_roll(s, i) for i in range(len(s.tracks)))
VISUALIZERS["arrangement"] = lambda s: "\n".join(
    f"{t.name:>10} |" + "".join(next((c.pattern[0] for c in s.arrangement if c.track == ti and c.bar <= b < c.bar + (t.patterns[c.pattern].bars if c.pattern in t.patterns else 1)), ".")
                                for b in range(s.length_bars())) for ti, t in enumerate(s.tracks))


class Interpreter:
    """Turns text (slash commands, .8bt statements, note language, simple
    English) into studio operations. emit(kind, **data) streams progress."""

    def __init__(self, song: Optional[Song] = None, cwd: Optional[str] = None, emit: Optional[Callable[..., None]] = None):
        self.song = song or new_song()
        self.cwd = Path(cwd or os.getcwd())
        self.track = 0
        self.pattern = "A"
        self.undo: List[dict] = []
        self.cancelled = False
        self.emit = emit or (lambda _ev, **d: None)
        self._tool_n = 0

    # helpers -------------------------------------------------------------
    def path(self, p: Optional[str], default: str) -> Path:
        pp = Path(os.path.expanduser(p or default))
        return pp if pp.is_absolute() else (self.cwd / pp)

    def snapshot(self):
        self.undo.append(self.song.to_dict())
        self.undo = self.undo[-50:]

    def summary(self) -> str:
        s = self.song
        cur = s.tracks[self.track].name if s.tracks and self.track < len(s.tracks) else "-"
        return (f"'{s.title}' {s.bpm:g}bpm {s.key} {s.scale}, {len(s.tracks)} tracks, {s.length_bars()} bars, "
                f"{s.note_count()} notes; editing {cur}.{self.pattern}")

    def tool(self, title: str, kind: str, fn: Callable[[], dict], raw: Optional[dict] = None) -> dict:
        self._tool_n += 1
        tid = f"call_{self._tool_n}"
        self.emit("tool_start", id=tid, title=title, kind=kind, input=raw or {})
        if self.cancelled:
            self.emit("tool_end", id=tid, status="failed", text="cancelled")
            raise Cancelled()
        try:
            res = fn()
        except Cancelled:
            raise
        except Exception as e:
            self.emit("tool_end", id=tid, status="failed", text=str(e))
            raise
        paths = [v for k, v in res.items() if k in ("path", "wav") and isinstance(v, str)] + list(res.get("stems", []))
        self.emit("tool_end", id=tid, status="completed", text=_terse(res), paths=paths, output=res)
        return res

    # main entry ------------------------------------------------------------
    def execute(self, text: str) -> str:
        """Run every line of text; returns a combined reply."""
        replies = []
        for line in [l for l in text.splitlines() if l.strip()] or [""]:
            if self.cancelled:
                raise Cancelled()
            replies.append(self.execute_line(line.strip()))
        return "\n".join(r for r in replies if r)

    def execute_line(self, line: str) -> str:
        if not line:
            return HELP_TEXT
        if line.startswith("/"):
            return self.slash(line[1:])
        word = line.split()[0].rstrip(":").lower()
        if word in SCORE_KEYWORDS:
            self.snapshot()
            apply_score(self.song, line)
            if word in ("track",):
                self.track = self.song.track_index(line.split()[1])
            if word in ("pat", "pattern", "play"):
                hdr = line.split(":", 1)[0].split()[1:]
                tn = hdr[0].split(".")[0] if hdr else None
                if tn:
                    self.track = self.song.track_index(tn)
                    self.pattern = hdr[0].split(".", 1)[1] if "." in hdr[0] else (hdr[1] if len(hdr) > 1 and "=" not in hdr[1] else "A")
            return "ok " + self.summary()
        nl = self.natural(line)
        if nl is not None:
            return nl
        try:
            notes, end = parse_notes(line, tpb=self.song.ticks_per_bar)
        except NoteSyntaxError as e:
            return f"? couldn't understand: {e}. Type /help for commands."
        self.snapshot()
        return self.append_notes(notes, end)

    def append_notes(self, notes: List[Note], end: int) -> str:
        s = self.song
        if not s.tracks:
            apply_score(s, "track Lead inst=lead")
        t = s.tracks[self.track]
        p = t.patterns.setdefault(self.pattern, Pattern(self.pattern, 1))
        off = max((n.end for n in p.notes), default=0)
        for n in notes:
            n.start += off
        p.notes.extend(notes)
        p.bars = max(p.bars, math.ceil((off + end) / s.ticks_per_bar))
        ti = self.track
        if not any(c.track == ti and c.pattern == p.name for c in s.arrangement):
            bar = max((c.bar + (t.patterns[c.pattern].bars if c.pattern in t.patterns else 1) for c in s.arrangement if c.track == ti), default=0)
            s.arrangement.append(Clip(ti, p.name, bar))
        return f"+{len(notes)} notes -> {t.name}.{p.name} ({p.bars} bars). " + self.summary()

    def natural(self, line: str) -> Optional[str]:
        low = line.lower()
        bars_m = re.search(r"(\d+)\s*bars?", low)
        bpm_m = re.search(r"(\d{2,3})\s*bpm", low)
        if re.search(r"\b(make|generate|compose|create|write|gen)\b", low) and re.search(r"\b(song|track|tune|loop|music|beat|theme|soundtrack)\b", low):
            style = next((st for st, words in STYLE_WORDS if any(w in low for w in words)), "upbeat")
            style = next((st for st in style_names() if st in low), style)
            seed_m = re.search(r"seed\s*(\d+)", low)
            key_m = re.search(r"\bin ([a-g][#b]?)\b", low)
            return self.slash(f"gen {style} {bars_m.group(1) if bars_m else 16} {seed_m.group(1) if seed_m else ''} "
                              f"{('key=' + key_m.group(1).upper()) if key_m else ''} {('bpm=' + bpm_m.group(1)) if bpm_m else ''}")
        if re.fullmatch(r"(make it |a bit |much )*(faster|speed up)!?", low):
            self.snapshot(); self.song.bpm = min(300, self.song.bpm + 10); return "ok " + self.summary()
        if re.fullmatch(r"(make it |a bit |much )*(slower|slow down)!?", low):
            self.snapshot(); self.song.bpm = max(30, self.song.bpm - 10); return "ok " + self.summary()
        if bpm_m and re.search(r"\b(tempo|set|bpm)\b", low):
            self.snapshot(); self.song.bpm = float(bpm_m.group(1)); return "ok " + self.summary()
        m = re.search(r"transpose (up|down)?\s*(-?\d+)", low)
        if m:
            return self.slash(f"transpose {('-' if m.group(1) == 'down' else '') + m.group(2).lstrip('-')}")
        if re.search(r"\b(louder|quieter|softer)\b", low):
            self.snapshot(); self.song.master = max(0.1, min(1.0, self.song.master + (0.1 if "louder" in low else -0.1)))
            return f"ok master {self.song.master:.1f}"
        m = re.search(r"\bexport\b.*\b(js|javascript|python|py|json|score|8bt|project)\b", low)
        if m:
            kind = {"javascript": "js", "python": "py", "8bt": "score"}.get(m.group(1), m.group(1))
            return self.slash(f"export {kind}")
        if re.search(r"\b(render|bounce|export)\b", low):
            return self.slash("render" + (" --loop" if "loop" in low else "") + (" --seamless" if "seamless" in low else ""))
        if re.search(r"\badd (some )?drums\b", low):
            self.snapshot()
            s = self.song
            if not any(t.drum for t in s.tracks):
                apply_score(s, "track Drums drum")
            ti = next(i for i, t in enumerate(s.tracks) if t.drum)
            bars = s.length_bars()
            s.tracks[ti].patterns["A"] = Pattern("A", bars, gen_drums("four", bars, s.ticks_per_bar))
            s.arrangement = [c for c in s.arrangement if c.track != ti] + [Clip(ti, "A", 0)]
            return "ok drums added. " + self.summary()
        if re.fullmatch(r"(show|print|display)( the)?( score| song)?", low):
            return self.slash("show")
        if low in ("help", "?", "commands"):
            return HELP_TEXT
        return None

    def slash(self, cmd: str) -> str:
        parts = cmd.split()
        if not parts:
            return HELP_TEXT
        name, args = parts[0].lower(), parts[1:]
        kv, pos = _kv(args)
        flags = {a[2:] for a in pos if a.startswith("--")}
        pos = [a for a in pos if not a.startswith("--")]
        s = self.song
        if name in ("help", "h", "?"):
            return HELP_TEXT
        if name in SLASH_COMMANDS:
            return str(SLASH_COMMANDS[name][0](self, args))
        if name == "new":
            self.snapshot()
            self.song, self.track, self.pattern = new_song(), 0, "A"
            if pos:
                self.song.title = " ".join(pos)
            return "ok new song. " + self.summary()
        if name == "demo":
            self.snapshot(); self.song = demo_song(); return "ok demo loaded. " + self.summary()
        if name == "gen":
            style = pos[0] if pos else "upbeat"
            bars = int(pos[1]) if len(pos) > 1 else int(kv.get("bars", 16))
            seed = int(pos[2]) if len(pos) > 2 else (int(kv["seed"]) if "seed" in kv else None)
            self.snapshot()
            self.song = self.tool(f"Generate {style} ({bars} bars)", "other",
                                  lambda: {"song": generate_song(style, bars, seed, kv.get("key"), float(kv["bpm"]) if "bpm" in kv else None)},
                                  {"style": style, "bars": bars, "seed": seed})["song"]
            self.track, self.pattern = 0, "A"
            return "ok generated. " + self.summary()
        if name in ("load", "open"):
            p = self.path(pos[0] if pos else None, "song.8bms")
            self.snapshot()
            self.song = self.tool(f"Load {p.name}", "read", lambda: {"song": load_project(p), "path": str(p)}, {"path": str(p)})["song"]
            return "ok loaded. " + self.summary()
        if name == "save":
            p = self.path(pos[0] if pos else None, "song.8bms")
            self.tool(f"Save {p.name}", "edit", lambda: {"path": str(save_project(s, p))}, {"path": str(p)})
            return f"saved {p}"
        if name in ("show", "score"):
            return song_to_score(s)
        if name == "info":
            return _terse(op_info(s))
        if name in ("bpm", "tempo") and pos:
            self.snapshot(); s.bpm = float(pos[0]); return "ok " + self.summary()
        if name == "key" and pos:
            self.snapshot(); apply_score(s, "key " + " ".join(pos)); return "ok " + self.summary()
        if name == "track":
            if not pos:
                return "tracks: " + ", ".join(f"{i}:{t.name}" for i, t in enumerate(s.tracks))
            try:
                self.track = s.track_index(pos[0])
            except KeyError:
                self.snapshot(); apply_score(s, "track " + " ".join(args)); self.track = s.track_index(pos[0])
            self.pattern = next(iter(s.tracks[self.track].patterns), "A")
            return "ok " + self.summary()
        if name in ("pat", "pattern") and pos:
            self.pattern = pos[0]; return "ok " + self.summary()
        if name == "clear":
            self.snapshot()
            t = s.tracks[self.track]
            if self.pattern in t.patterns:
                t.patterns[self.pattern].notes.clear()
            return "ok cleared. " + self.summary()
        if name == "undo":
            if not self.undo:
                return "nothing to undo"
            self.song = Song.from_dict(self.undo.pop()); return "ok undone. " + self.summary()
        if name == "transpose" and pos:
            self.snapshot()
            n = int(pos[0])
            for t in s.tracks:
                if not t.drum:
                    for p in t.patterns.values():
                        for nn in p.notes:
                            nn.pitch = max(0, min(127, nn.pitch + n))
            return f"ok transposed {n:+d}. " + self.summary()
        if name == "render":
            p = self.path(pos[0] if pos else None, "8bms-out/" + _slug(s.title) + (".loop" if "loop" in flags else "") + ".wav")
            res = self.tool(f"Render {p.name}", "execute", lambda: op_render(s, str(p), loop="loop" in flags or "seamless" in flags,
                                                                            seamless="seamless" in flags, bars=kv.get("bars")),
                            {"out": str(p), "flags": sorted(flags)})
            return f"rendered {res['path']} ({res['seconds']}s)"
        if name == "stems":
            d = self.path(pos[0] if pos else None, "8bms-out/" + _slug(s.title) + "-stems")
            res = self.tool("Render stems", "execute", lambda: op_render(s, str(d / "mix.wav"), stems=str(d)), {"dir": str(d)})
            return "stems: " + " ".join(res["stems"])
        if name == "export":
            kind = pos[0] if pos else "js"
            if kind not in EXPORTERS:
                return f"unknown exporter {kind}; have {', '.join(EXPORTERS)}"
            p = self.path(pos[1] if len(pos) > 1 else None, "8bms-out/" + _slug(s.title) + EXPORTERS[kind][0])
            res = self.tool(f"Export {kind} -> {p.name}", "edit", lambda: op_export(s, kind, str(p)), {"kind": kind, "out": str(p)})
            return f"exported {res['path']}"
        if name in ("instruments", "presets"):
            return "presets: " + " ".join(sorted(PRESETS)) + ("\ncustom: " + " ".join(s.instruments) if s.instruments else "")
        if name == "styles":
            return "styles: " + " ".join(style_names())
        if name in ("roll", "viz"):
            vname = (pos[0] if name == "viz" and pos else "roll")
            if name == "roll":
                return ascii_roll(s, self.track, self.pattern)
            if vname not in VISUALIZERS:
                return f"visualizers: {', '.join(VISUALIZERS)}"
            return VISUALIZERS[vname](s)
        if name == "op" and pos:
            res = self.tool(f"Op {pos[0]}", "other", lambda: run_op(pos[0], **kv), kv)
            return _terse(res)
        if name == "ml" and pos:
            be = ML_BACKENDS.get(pos[0])
            if not be:
                return f"ml backends: {', '.join(ML_BACKENDS) or '(none installed)'}"
            self.snapshot()
            out = be.generate(" ".join(pos[1:]), s)
            if isinstance(out, Song):
                self.song = out
            elif isinstance(out, str):
                apply_score(s, out)
            return "ok " + self.summary()
        if name in OPS:
            res = self.tool(f"Op {name}", "other", lambda: run_op(name, **({"src": s} if "src" in OPS[name].params and "src" not in kv else {}), **kv), kv)
            return _terse(res)
        return f"unknown command /{name}. Type /help."


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_").lower() or "song"


def _terse(res: Any) -> str:
    if isinstance(res, dict):
        if "text" in res and len(res) == 1:
            return res["text"]
        if "score" in res:
            return res["score"]
        parts = []
        for k, v in res.items():
            if isinstance(v, Song):
                v = f"<song {v.title}>"
            elif isinstance(v, (list, tuple)):
                v = ",".join(map(str, v))
            parts.append(f"{k}={v}")
        return " ".join(parts)
    return str(res)


HELP_TEXT = """\
Type music directly:
  notes      c4 e4 g4/4 [c4 e4 g4]/2 {Am}/1 (c5 d5)x4 r/8 o5 l16 > <   -> appended to current track
  statements bpm 120 | key A minor | track bass inst=bass | pat bass.A: l8 c2 c2 g2 c2 | arr bass: A A B A
  english    "make a mellow space song 16 bars", faster, slower, transpose up 2, add drums, render, export js
Slash commands:
  /new /demo /gen <style> [bars] [seed] /load <f> /save <f> /show /info /track <name> /pat <name>
  /bpm N /key C minor /transpose N /clear /undo /render [f] [--loop] [--seamless] /stems [dir]
  /export <js|py|json|score|project> [f] /presets /styles /roll /viz <name> /op <op> k=v /ml <backend> <prompt>
"""


# ---------------------------------------------------------------------------
# Plugin system
# ---------------------------------------------------------------------------
PLUGIN_TYPES = ["instrument", "effect", "style", "op", "exporter", "importer", "gui", "command", "visualizer", "midi", "ml"]
PLUGIN_PERMISSIONS = ["filesystem", "network", "midi", "audio", "subprocess"]
EP_GROUP = "eightbit_studio.plugins"
GUI_PANELS: List[Tuple[str, Callable, str]] = []       # (title, factory(parent, app) -> widget, owner)
MIDI_MAPPINGS: Dict[str, dict] = {}

MANIFEST_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "8bms plugin.toml",
    "type": "object",
    "required": ["name", "version", "api_version", "types", "entry", "description"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "pattern": r"^[a-z][a-z0-9_-]{1,40}$"},
        "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+([-+][0-9A-Za-z.-]+)?$"},
        "api_version": {"type": "string", "minLength": 1},
        "types": {"type": "array", "minItems": 1, "items": {"type": "string", "enum": PLUGIN_TYPES}},
        "entry": {"type": "string", "pattern": r"^[A-Za-z_][\w.]*(:[A-Za-z_]\w*)?$"},
        "permissions": {"type": "array", "items": {"type": "string", "enum": PLUGIN_PERMISSIONS}},
        "description": {"type": "string", "minLength": 3, "maxLength": 120},
        "author": {"type": "string"}, "license": {"type": "string"}, "homepage": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}


def validate_schema(data: Any, schema: dict, path: str = "$") -> List[str]:
    """Tiny JSON-Schema subset validator (type, required, properties,
    additionalProperties, enum, pattern, items, minItems, minLength, maxLength).
    Uses the real `jsonschema` package when it is installed."""
    try:
        import jsonschema  # type: ignore
        v = jsonschema.Draft202012Validator(schema)
        return [f"{'/'.join(map(str, e.absolute_path)) or '$'}: {e.message}" for e in v.iter_errors(data)]
    except ImportError:
        pass
    errs: List[str] = []
    tmap = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool}
    t = schema.get("type")
    if t and not isinstance(data, tmap[t]):
        return [f"{path}: expected {t}"]
    if "enum" in schema and data not in schema["enum"]:
        errs.append(f"{path}: {data!r} not one of {schema['enum']}")
    if isinstance(data, str):
        if "pattern" in schema and not re.search(schema["pattern"], data):
            errs.append(f"{path}: {data!r} does not match {schema['pattern']}")
        if len(data) < schema.get("minLength", 0):
            errs.append(f"{path}: too short")
        if "maxLength" in schema and len(data) > schema["maxLength"]:
            errs.append(f"{path}: too long (max {schema['maxLength']})")
    if isinstance(data, list):
        if len(data) < schema.get("minItems", 0):
            errs.append(f"{path}: needs at least {schema['minItems']} item(s)")
        for i, it in enumerate(data):
            errs += validate_schema(it, schema.get("items", {}), f"{path}[{i}]")
    if isinstance(data, dict):
        for r in schema.get("required", []):
            if r not in data:
                errs.append(f"{path}: missing required '{r}'")
        props = schema.get("properties", {})
        for k, v in data.items():
            if k in props:
                errs += validate_schema(v, props[k], f"{path}.{k}")
            elif schema.get("additionalProperties") is False:
                errs.append(f"{path}: unknown key '{k}'")
    return errs


def parse_version(v: str) -> Tuple[int, int, int]:
    m = re.match(r"^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", v)
    if not m:
        raise ValueError(f"bad version {v!r}")
    return int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0)


def version_satisfies(spec: str, version: str = API_VERSION) -> bool:
    """Semver ranges: '^1.0', '~1.2', '>=1.0,<2', '1.x', '1', '*', '==1.0.0'."""
    v = parse_version(version)
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        if part in ("*", "x"):
            continue
        if part.startswith("^"):
            b = parse_version(part[1:])
            ok = v >= b and (v[0] == b[0] if b[0] > 0 else v[:2] == b[:2])
        elif part.startswith("~"):
            b = parse_version(part[1:])
            ok = v >= b and v[:2] == b[:2]
        elif re.match(r"^(>=|<=|>|<|==|=)", part):
            op = re.match(r"^(>=|<=|>|<|==|=)", part).group(1)
            b = parse_version(part[len(op):])
            ok = {">=": v >= b, "<=": v <= b, ">": v > b, "<": v < b, "==": v == b, "=": v == b}[op]
        elif part.endswith((".x", ".*")) or re.fullmatch(r"\d+", part):
            nums = [int(x) for x in part.replace(".x", "").replace(".*", "").split(".")]
            ok = list(v[: len(nums)]) == nums
        else:
            ok = v == parse_version(part)
        if not ok:
            return False
    return True


def _load_toml(path: Path) -> dict:
    try:
        import tomllib  # py3.11+
    except ImportError:  # pragma: no cover
        try:
            import tomli as tomllib  # type: ignore
        except ImportError:
            return _mini_toml(path.read_text())
    with open(path, "rb") as f:
        return tomllib.load(f)


def _mini_toml(text: str) -> dict:  # pragma: no cover - only for 3.10 without tomli
    out: Dict[str, Any] = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line and not line.startswith("["):
            k, v = [x.strip() for x in line.split("=", 1)]
            out[k] = json.loads(v.replace("'", '"'))
    return out


class PluginError(RuntimeError):
    pass


_plugin_ctx = threading.local()
_orig_connect = socket.socket.connect


def _guarded_connect(self, *a, **kw):
    stack = getattr(_plugin_ctx, "stack", [])
    if stack and "network" not in stack[-1].permissions:
        raise PermissionError(f"plugin '{stack[-1].name}' has no 'network' permission")
    return _orig_connect(self, *a, **kw)


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]


@dataclass
class PluginInfo:
    name: str
    version: str = "0.0.0"
    api_version: str = "^1.0"
    types: List[str] = field(default_factory=list)
    entry: str = "plugin:register"
    permissions: List[str] = field(default_factory=list)
    description: str = ""
    path: Optional[str] = None
    source: str = "folder"            # folder | entrypoint
    enabled: bool = True
    loaded: bool = False
    error: Optional[str] = None
    errors: List[str] = field(default_factory=list)   # runtime errors caught later
    provides: List[str] = field(default_factory=list)
    _undo: List[Tuple[dict, str, Any]] = field(default_factory=list, repr=False)
    _obj: Any = field(default=None, repr=False)

    def summary(self) -> dict:
        return {"name": self.name, "version": self.version, "types": self.types, "enabled": self.enabled,
                "loaded": self.loaded, "error": self.error, "errors": self.errors[-3:], "permissions": self.permissions,
                "provides": self.provides, "source": self.source, "path": self.path, "description": self.description}


class _PluginCall:
    def __init__(self, plugin: PluginInfo):
        self.p = plugin

    def __enter__(self):
        if not hasattr(_plugin_ctx, "stack"):
            _plugin_ctx.stack = []
        _plugin_ctx.stack.append(self.p)

    def __exit__(self, *a):
        _plugin_ctx.stack.pop()


_MISSING = object()


class PluginAPI:
    """Object passed to a plugin's register(api). Everything a plugin adds goes
    through here, so it can be removed again and errors are isolated."""

    version = API_VERSION

    def __init__(self, plugin: PluginInfo):
        self._p = plugin
        self.name = plugin.name
        self.core = sys.modules[__name__]
        self.Instrument, self.Note, self.Pattern, self.Track, self.Song, self.Clip = Instrument, Note, Pattern, Track, Song, Clip

    @property
    def data_dir(self) -> Path:
        d = home_dir() / "plugin-data" / self._p.name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def log(self, msg: str):
        print(f"[{self._p.name}] {msg}", file=sys.stderr)

    # -- internals -----------------------------------------------------------
    def _put(self, reg: dict, key: str, value: Any, what: str):
        self._p._undo.append((reg, key, reg.get(key, _MISSING)))
        reg[key] = value
        self._p.provides.append(f"{what}:{key}")

    def guard(self, fn: Callable, fallback: Optional[Callable] = None) -> Callable:
        p = self._p

        def wrapped(*a, **kw):
            try:
                with _PluginCall(p):
                    return fn(*a, **kw)
            except Exception as e:  # isolation: report, never crash the host
                msg = f"{type(e).__name__}: {e}"
                p.errors.append(msg)
                print(f"[plugin {p.name}] error: {msg}", file=sys.stderr)
                if fallback is not None:
                    return fallback(*a, **kw)
                raise PluginError(f"plugin '{p.name}' failed: {msg}") from None
        wrapped.__name__ = getattr(fn, "__name__", "plugin_fn")
        wrapped.__doc__ = getattr(fn, "__doc__", None)
        return wrapped

    # -- extension points ------------------------------------------------------
    def add_instrument(self, inst):
        inst = inst if isinstance(inst, Instrument) else Instrument.from_dict(inst)
        self._put(PRESETS, inst.name, inst, "instrument")

    def add_wave(self, name: str, fn: Callable):
        """fn(phase: ndarray cycles, t: ndarray seconds, inst: dict) -> ndarray in -1..1"""
        self._put(EXTRA_WAVES, name, self.guard(fn, lambda ph, t, inst: np.where((ph % 1) < 0.5, 1.0, -1.0)), "wave")

    def add_effect(self, name: str, fn: Callable, params: Optional[Dict[str, Tuple[float, float, float]]] = None):
        """fn(x: ndarray (n,2), sr: int, **params) -> ndarray (n,2)"""
        self._put(EXTRA_FX, name, self.guard(fn, lambda x, sr, **kw: x), "effect")
        self._put(FX_PARAMS, name, params or {}, "effect-params")

    def add_style(self, name: str, fn_or_spec):
        """A function fn(rng, bars, key) -> Song, or a style spec dict like STYLES entries."""
        if callable(fn_or_spec):
            self._put(STYLE_FUNCS, name, self.guard(fn_or_spec), "style")
        else:
            self._put(STYLES, name, dict(fn_or_spec), "style")

    def add_groove(self, name: str, rows: Dict[str, str]):
        self._put(GROOVES, name, dict(rows), "groove")

    def add_op(self, name: str, fn: Callable, help: str = "", **params):
        """params: name=dict(type=..., default=..., help=..., required=...) or the
        shorthand name=int / name="float" (default is then taken from fn's signature)."""
        import inspect
        try:
            sig = inspect.signature(fn).parameters
        except (TypeError, ValueError):
            sig = {}
        norm = {}
        for k, v in params.items():
            if isinstance(v, dict):
                spec = dict(v)
            else:
                spec = {"type": v.__name__ if isinstance(v, type) else str(v)}
            if "default" not in spec and k in sig and sig[k].default is not inspect.Parameter.empty:
                spec["default"] = sig[k].default
            norm[k] = spec
        self._put(OPS, name, Op(name, self.guard(fn), help or (fn.__doc__ or "").strip(), norm, self._p.name), "op")

    def add_exporter(self, name: str, ext: str, fn: Callable[[Song], Any]):
        self._put(EXPORTERS, name, (ext, self.guard(fn)), "exporter")

    def add_importer(self, ext: str, fn: Callable[[str], Song]):
        self._put(IMPORTERS, ext.lower(), self.guard(fn), "importer")

    def add_gui_panel(self, title: str, factory: Callable):
        GUI_PANELS.append((title, self.guard(factory), self._p.name))
        self._p._undo.append(({"__list__": GUI_PANELS}, title, _MISSING))
        self._p.provides.append(f"gui:{title}")

    def add_command(self, name: str, fn: Callable, help: str = ""):
        self._put(SLASH_COMMANDS, name, (self.guard(fn), help), "command")

    def add_visualizer(self, name: str, fn: Callable[[Song], str]):
        self._put(VISUALIZERS, name, self.guard(fn), "visualizer")

    def add_midi_mapping(self, name: str, mapping: dict):
        self._put(MIDI_MAPPINGS, name, dict(mapping), "midi")

    def add_ml_backend(self, name: str, backend: Any):
        """backend.generate(prompt: str, song: Song, **kw) -> Song | .8bt text"""
        class _Guarded:
            def __init__(s, b):
                s.b, s.generate = b, self.guard(b.generate)
        self._put(ML_BACKENDS, name, _Guarded(backend), "ml")


def manifest_from_file(path: Path) -> dict:
    return _load_toml(Path(path))


def validate_manifest(m: dict) -> List[str]:
    errs = validate_schema(m, MANIFEST_SCHEMA)
    if not errs:
        try:
            if not version_satisfies(m["api_version"]):
                errs.append(f"api_version {m['api_version']!r} is not compatible with host API {API_VERSION}")
        except ValueError as e:
            errs.append(str(e))
    return errs


def _find_manifests(root: Path, depth: int = 2) -> List[Path]:
    out: List[Path] = []
    if not root.is_dir():
        return out
    if (root / "plugin.toml").exists():
        return [root / "plugin.toml"]
    if depth <= 0:
        return out
    for d in sorted(root.iterdir()):
        if d.is_dir() and not d.name.startswith((".", "_")) and d.name not in ("dist", "build", "tests", "node_modules"):
            out += _find_manifests(d, depth - 1)
    return out


class PluginManager:
    def __init__(self, search_paths: Optional[List[Path]] = None, use_entry_points: bool = True, include_defaults: bool = True):
        self.paths: List[Path] = [Path(p) for p in (search_paths or [])]
        if include_defaults:
            self.paths += [home_dir() / "plugins", Path.cwd() / "plugins"]
            self.paths += [Path(p) for p in os.environ.get("EIGHTBMS_PLUGIN_PATH", "").split(os.pathsep) if p]
        self.use_entry_points = use_entry_points
        self.plugins: Dict[str, PluginInfo] = {}
        self.problems: List[str] = []

    # state -------------------------------------------------------------------
    @staticmethod
    def state_file() -> Path:
        return home_dir() / "plugins.json"

    def disabled(self) -> List[str]:
        try:
            return json.loads(self.state_file().read_text()).get("disabled", [])
        except Exception:
            return []

    def set_enabled(self, name: str, on: bool):
        d = set(self.disabled())
        (d.discard if on else d.add)(name)
        self.state_file().write_text(json.dumps({"disabled": sorted(d)}, indent=1))
        if name in self.plugins:
            self.plugins[name].enabled = on
            if not on:
                self.unload(name)

    # discovery ---------------------------------------------------------------
    def discover(self) -> List[PluginInfo]:
        disabled = set(self.disabled())
        seen: Dict[str, PluginInfo] = {}
        for root in self.paths:
            for mf in _find_manifests(root):
                try:
                    m = manifest_from_file(mf)
                except Exception as e:
                    self.problems.append(f"{mf}: bad TOML: {e}")
                    continue
                errs = validate_manifest(m)
                name = m.get("name") or mf.parent.name
                info = PluginInfo(name=name, **{k: m[k] for k in ("version", "api_version", "types", "entry", "description") if k in m},
                                  permissions=list(m.get("permissions", [])), path=str(mf.parent), source="folder")
                if errs:
                    info.error = "; ".join(errs)
                if name in seen:
                    self.problems.append(f"{mf}: plugin '{name}' shadowed by {seen[name].path}")
                    continue
                info.enabled = name not in disabled
                seen[name] = info
        if self.use_entry_points:
            try:
                from importlib.metadata import entry_points
                eps = entry_points(group=EP_GROUP)
            except Exception:
                eps = []
            for ep in eps:
                if ep.name in seen:
                    continue
                info = PluginInfo(name=ep.name, entry=ep.value, source="entrypoint", description=f"entry point {ep.value}")
                info.enabled = ep.name not in disabled
                info._obj = ep
                seen[ep.name] = info
        self.plugins = seen
        return list(seen.values())

    # loading -----------------------------------------------------------------
    def _import_entry(self, info: PluginInfo) -> Callable:
        if info.source == "entrypoint":
            obj = info._obj.load()
            mod = sys.modules.get(getattr(obj, "__module__", "") or "", None) if callable(obj) else obj
            mpath = Path(getattr(mod, "__file__", "") or "").parent / "plugin.toml" if mod else None
            if mpath and mpath.exists():
                m = manifest_from_file(mpath)
                errs = validate_manifest(m)
                if errs:
                    raise PluginError("; ".join(errs))
                for k in ("version", "api_version", "types", "description"):
                    if k in m:
                        setattr(info, k, m[k])
                info.permissions = list(m.get("permissions", []))
            elif mod is not None and hasattr(mod, "MANIFEST"):
                for k, v in getattr(mod, "MANIFEST").items():
                    if hasattr(info, k):
                        setattr(info, k, v)
            if not version_satisfies(info.api_version):
                raise PluginError(f"api_version {info.api_version} incompatible with {API_VERSION}")
            return obj if callable(obj) else getattr(obj, "register")
        root = Path(info.path or ".")
        modname, _, fn = info.entry.partition(":")
        fn = fn or "register"
        first = modname.split(".")[0]
        uniq = f"_8bms_plugin_{re.sub(r'[^A-Za-z0-9_]', '_', info.name)}_{hashlib.md5(str(root).encode()).hexdigest()[:8]}"
        pkg_dir, file_ = root / first, root / f"{first}.py"
        if (pkg_dir / "__init__.py").exists():
            spec = importlib.util.spec_from_file_location(uniq, pkg_dir / "__init__.py", submodule_search_locations=[str(pkg_dir)])
        elif file_.exists():
            spec = importlib.util.spec_from_file_location(uniq, file_)
        else:
            raise PluginError(f"entry module '{first}' not found in {root}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[uniq] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        for part in modname.split(".")[1:]:
            mod = importlib.import_module(f"{uniq}.{part}")
        if not hasattr(mod, fn):
            raise PluginError(f"entry function '{fn}' missing in {modname}")
        return getattr(mod, fn)

    def load(self, info: PluginInfo) -> PluginInfo:
        if info.loaded or not info.enabled or info.error:
            return info
        try:
            with _PluginCall(info):
                reg = self._import_entry(info)
                reg(PluginAPI(info))
            info.loaded = True
        except Exception as e:
            info.error = f"{type(e).__name__}: {e}"
            self.unload(info.name)
        return info

    def load_all(self) -> List[PluginInfo]:
        if not self.plugins:
            self.discover()
        return [self.load(p) for p in self.plugins.values()]

    def unload(self, name: str):
        info = self.plugins.get(name)
        if not info:
            return
        for reg, key, prev in reversed(info._undo):
            if "__list__" in reg:
                lst = reg["__list__"]
                lst[:] = [x for x in lst if not (x[0] == key and x[2] == info.name)]
            elif prev is _MISSING:
                reg.pop(key, None)
            else:
                reg[key] = prev
        info._undo.clear()
        info.provides.clear()
        info.loaded = False


PLUGINS: Optional[PluginManager] = None


def load_plugins(force: bool = False) -> PluginManager:
    """Discover + load plugins once per process (EIGHTBMS_NO_PLUGINS=1 disables)."""
    global PLUGINS
    if PLUGINS is not None and not force:
        return PLUGINS
    PLUGINS = PluginManager()
    if os.environ.get("EIGHTBMS_NO_PLUGINS") != "1":
        PLUGINS.load_all()
    return PLUGINS


def load_plugin_dir(path, enable: bool = True) -> PluginInfo:
    """Load a single plugin folder (handy in plugin tests)."""
    pm = PluginManager(search_paths=[Path(path)], use_entry_points=False, include_defaults=False)
    infos = pm.discover()
    if not infos:
        raise PluginError(f"no plugin.toml under {path}")
    info = infos[0]
    info.enabled = enable
    pm.load(info)
    info._manager = pm  # type: ignore[attr-defined]
    return info


# ---------------------------------------------------------------------------
# Plugin developer tools: scaffold, validate, test (sandboxed), build, package,
# install / uninstall
# ---------------------------------------------------------------------------
from string import Template as _T

_TPL_CODE = {
    "instrument": '''
def register(api):
    """Adds a custom oscillator wave and an instrument preset that uses it."""
    def ${module}_wave(phase, t, inst):
        frac = phase % 1.0
        # two stacked pulses = a "fat" 8-bit tone, quantized to 4 bits
        v = np.where(frac < 0.5, 1.0, -1.0) * 0.6 + np.where((frac * 2) % 1.0 < 0.25, 1.0, -1.0) * 0.4
        return np.round(v * 7.5) / 7.5

    api.add_wave("$name", ${module}_wave)
    api.add_instrument({"name": "${name}_lead", "wave": "$name", "attack": 0.005, "decay": 0.1,
                        "sustain": 0.6, "release": 0.1, "volume": 0.5})
''',
    "effect": '''
def register(api):
    """Adds a stereo 'widen' effect: x -> mid/side with adjustable width."""
    def widen(x, sr, width=1.5):
        mid = (x[:, 0] + x[:, 1]) / 2
        side = (x[:, 0] - x[:, 1]) / 2 * width
        return np.stack([mid + side, mid - side], axis=1)

    api.add_effect("$name", widen, {"width": (0.0, 3.0, 1.5)})
''',
    "style": '''
def register(api):
    """Adds a generator style. Either a spec dict (like core STYLES) or fn(rng, bars, key) -> Song."""
    api.add_groove("${name}_beat", {"kick": "x..x..x...x..x..", "snare": "....x.......x...", "hat": "x.x.x.x.x.x.x.x."})
    api.add_style("$name", {
        "bpm": (110, 124), "scale": "minor", "keys": ["A", "D", "E"], "prog": [[0, 5, 2, 6], [0, 3, 4, 4]],
        "lead": "lead", "harm": "arpminor", "bass": "bass", "bass_style": "octave", "groove": "${name}_beat",
        "density": 0.6, "swing": 0.0, "fx": {"echo": {"time": 0.3, "feedback": 0.3, "mix": 0.2}},
    })
''',
    "op": '''
def register(api):
    """Adds an op. Ops show up in the CLI (8bms op $name), HTTP, MCP and ACP (/$name)."""
    def count_notes(src):
        song = api.core.load_any(src) if isinstance(src, str) else src
        per = {t.name: sum(len(p.notes) for p in t.patterns.values()) for t in song.tracks}
        return {"total": sum(per.values()), "per_track": per}

    api.add_op("$name", count_notes, "Count notes per track.",
               src={"type": "str", "required": True, "help": "song source"})
''',
    "exporter": '''
def register(api):
    """Adds an exporter: fn(song) -> str | bytes."""
    def to_csv(song):
        rows = ["track,bar,start_tick,length_ticks,pitch,velocity"]
        for ev_track, t in enumerate(song.tracks):
            for c in song.arrangement:
                if c.track != ev_track or c.pattern not in t.patterns:
                    continue
                for n in t.patterns[c.pattern].notes:
                    rows.append(f"{t.name},{c.bar + 1},{n.start},{n.length},{n.pitch},{n.velocity:.2f}")
        return "\\n".join(rows) + "\\n"

    api.add_exporter("$name", ".csv", to_csv)
''',
    "importer": '''
def register(api):
    """Adds an importer for '.${name}' files: one line per note 'pitch start_16th len_16th'."""
    def load(text):
        song = api.core.new_song()
        notes = []
        for line in text.splitlines():
            if line.strip() and not line.startswith("#"):
                p, s, l = line.split()[:3]
                notes.append(api.Note(int(s) * 24, int(l) * 24, api.core.parse_note_name(p)))
        song.tracks[0].patterns["A"].notes = notes
        return song

    api.add_importer(".$name", load)
''',
    "gui": '''
def register(api):
    """Adds a tab to the GUI notebook. factory(parent, app) -> tkinter widget."""
    def factory(parent, app):
        import tkinter as tk
        f = tk.Frame(parent, bg="#14141f")
        tk.Label(f, text="Hello from $name", fg="#7cf", bg="#14141f").pack(pady=10)
        tk.Button(f, text="Double tempo", command=lambda: app.set_bpm(app.song.bpm * 2)).pack()
        return f

    api.add_gui_panel("$Title", factory)
''',
    "command": '''
def register(api):
    """Adds a slash command for the terminal studio / ACP: /$name"""
    def cmd(interp, args):
        n = int(args[0]) if args else 1
        interp.snapshot()
        interp.song.bpm = round(interp.song.bpm * (1 + 0.05 * n), 1)
        return f"tempo nudged to {interp.song.bpm} bpm"

    api.add_command("$name", cmd, "/$name [n] - nudge tempo up 5% per step")
''',
    "visualizer": '''
def register(api):
    """Adds a text visualizer (/viz $name): fn(song) -> str"""
    def bars(song):
        out = []
        for t in song.tracks:
            n = sum(len(p.notes) for p in t.patterns.values())
            out.append(f"{t.name:>10} " + "#" * min(60, n // 2) + f" {n}")
        return "\\n".join(out)

    api.add_visualizer("$name", bars)
''',
    "midi": '''
def register(api):
    """Adds a MIDI controller mapping (see docs/plugins/types.md#midi)."""
    api.add_midi_mapping("$name", {
        "match": ["$name"],              # substrings of the MIDI port name
        "grid": {"notes": list(range(0, 64)), "rows": 8, "cols": 8},   # 8x8 pads -> drum steps
        "faders": {str(48 + i): i for i in range(8)},                  # CC -> track volume
        "master_cc": 56,
        "transport": {"play": 91, "stop": 92},
    })
''',
    "ml": '''
def register(api):
    """Adds an ML/composer backend: generate(prompt, song) -> Song or .8bt text.
    This stub is rule-based; swap in a real model (keep network off unless declared)."""
    class Backend:
        def generate(self, prompt, song, **kw):
            style = "boss" if "boss" in prompt else "mellow-space"
            return api.core.generate_song(style, 8, seed=len(prompt))

    api.add_ml_backend("$name", Backend())
''',
}

_TPL_TEST = {
    "instrument": 'y = bms.render_note_preview(bms.PRESETS["${name}_lead"], 60, 0.1)\n    assert np.isfinite(y).all() and np.abs(y).max() > 0.05',
    "effect": 'x = np.random.default_rng(0).uniform(-0.5, 0.5, (4410, 2))\n    y = bms.EXTRA_FX["$name"](x, 44100)\n    assert y.shape == x.shape and np.isfinite(y).all()',
    "style": 's = bms.generate_song("$name", 8, seed=1)\n    assert s.note_count() > 0 and s.length_bars() == 8',
    "op": 'res = bms.run_op("$name", src="demo")\n    assert res["total"] > 0',
    "exporter": 'text = bms.EXPORTERS["$name"][1](bms.demo_song())\n    assert text.startswith("track,")',
    "importer": 's = bms.IMPORTERS[".$name"]("C4 0 4\\nE4 4 4\\n")\n    assert len(s.tracks[0].patterns["A"].notes) == 2',
    "gui": 'assert any(t == "$Title" for t, _, _ in bms.GUI_PANELS)',
    "command": 'it = bms.Interpreter(bms.demo_song())\n    assert "bpm" in it.execute("/$name 2")',
    "visualizer": 'assert "Lead" in bms.VISUALIZERS["$name"](bms.demo_song())',
    "midi": 'assert "$name" in bms.MIDI_MAPPINGS and bms.MIDI_MAPPINGS["$name"]["grid"]["rows"] == 8',
    "ml": 'it = bms.Interpreter(bms.new_song())\n    out = it.execute("/ml $name a boss theme")\n    assert out.startswith("ok") and it.song.note_count() > 0',
}

_TPL_FILES = {
    "plugin.toml": '''name = "$name"
version = "0.1.0"
api_version = "^1.0"
types = ["$type"]
entry = "$module:register"
permissions = []
description = "$Title - an 8bms $type plugin for 8Bit Music Code Studio"
''',
    "$module/__init__.py": '''"""$Title: an 8bms $type plugin for 8Bit Music Code Studio (public plugin API v1)."""
import numpy as np  # noqa: F401  (most plugins work on numpy arrays)
$code''',
    "tests/test_plugin.py": '''from pathlib import Path

import numpy as np  # noqa: F401

import eightbit_studio as bms

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_is_valid():
    assert bms.validate_manifest(bms.manifest_from_file(ROOT / "plugin.toml")) == []


def test_plugin_loads_and_works():
    info = bms.load_plugin_dir(ROOT)
    assert info.loaded, info.error
    assert info.provides
    $test
    info._manager.unload(info.name)
''',
    "README.md": '''# $Title ($type plugin)

An 8bms `$type` plugin for [8Bit Music Code Studio](https://github.com/RechargedIdeas/8bit-music-code-studio).

```bash
8bms plugin validate .     # manifest + API compatibility + dry load
8bms plugin test .         # sandboxed pytest
8bms plugin install .      # copy into ~/.8bms/plugins
8bms plugin build .        # dist/*.whl  (pip-installable, entry point group eightbit_studio.plugins)
8bms plugin package .      # dist/*.zip  (8bms plugin install dist/x.zip)
```

See `example/example.8bt` for a song that uses it.
''',
    "example/example.8bt": '''# example song for the $name plugin
title $Title demo
bpm 120; key C major
track lead inst=lead
pat lead.A: o5 l8 c e g e d f a f | e g b g c/2
$example''',
    "pyproject.toml": '''[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "eightbit-studio-plugin-$name"
version = "0.1.0"
description = "$Title - an 8bms $type plugin for 8Bit Music Code Studio"
requires-python = ">=3.10"
dependencies = ["numpy"]

[project.entry-points."eightbit_studio.plugins"]
$name = "$module:register"

[tool.setuptools]
packages = ["$module"]
# NOTE: '8bms plugin build' also copies plugin.toml into the package.
''',
    ".github/workflows/ci.yml": '''name: plugin-ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install 8Bit Music Code Studio
        env:
          EIGHTBMS_SOURCE: $${{ vars.EIGHTBMS_SOURCE || 'git+https://github.com/RechargedIdeas/8bit-music-code-studio' }}
        run: pip install numpy pytest "$$EIGHTBMS_SOURCE"
      - run: 8bms plugin validate .
      - run: 8bms plugin test .
      - run: 8bms plugin build . && 8bms plugin package .
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
''',
}

_TPL_EXAMPLE = {
    "instrument": "inst lead ${name}_lead\n", "effect": "fx $name width=2\n", "style": "# try: 8bms gen --style $name --bars 8\n",
    "exporter": "# try: 8bms export example/example.8bt --to $name\n", "op": "# try: 8bms op $name src=example/example.8bt\n",
}


def scaffold_plugin(ptype: str, name: str, dest: Optional[Path] = None) -> Path:
    if ptype not in PLUGIN_TYPES:
        raise ValueError(f"type must be one of {', '.join(PLUGIN_TYPES)}")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{1,40}", name):
        raise ValueError("name: lowercase letters, digits, - or _, 2-41 chars, starting with a letter")
    root = Path(dest or Path.cwd()) / name
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"{root} exists and is not empty")
    module = "bms_" + name.replace("-", "_")
    subs = {"name": name, "module": module, "type": ptype, "Title": name.replace("-", " ").replace("_", " ").title()}
    subs["code"] = _T(_TPL_CODE[ptype]).safe_substitute(subs)
    subs["test"] = _T(_TPL_TEST[ptype]).safe_substitute(subs)
    subs["example"] = _T(_TPL_EXAMPLE.get(ptype, "")).safe_substitute(subs)
    for rel, body in _TPL_FILES.items():
        p = root / _T(rel).safe_substitute(subs)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_T(body).substitute(subs))
    return root


def _plugin_root(path) -> Tuple[Path, dict]:
    root = Path(path).resolve()
    if root.is_file() and root.name == "plugin.toml":
        root = root.parent
    mf = root / "plugin.toml"
    if not mf.exists():
        raise PluginError(f"no plugin.toml in {root}")
    return root, manifest_from_file(mf)


def validate_plugin(path) -> dict:
    """Manifest schema + API compat + entry import + dry-run register()."""
    root, m = _plugin_root(path)
    errs = validate_manifest(m)
    provides: List[str] = []
    if not errs:
        info = load_plugin_dir(root)
        if info.error:
            errs.append(info.error)
        provides = list(info.provides)
        declared = set(m["types"])
        kinds = {p.split(":")[0] for p in provides}
        type_kinds = {"instrument": {"instrument", "wave"}, "effect": {"effect"}, "style": {"style", "groove"}, "op": {"op"},
                      "exporter": {"exporter"}, "importer": {"importer"}, "gui": {"gui"}, "command": {"command"},
                      "visualizer": {"visualizer"}, "midi": {"midi"}, "ml": {"ml"}}
        for t in declared:
            if not (type_kinds[t] & kinds) and not info.error:
                errs.append(f"declares type '{t}' but registered nothing for it")
        info._manager.unload(info.name)  # type: ignore[attr-defined]
    return {"ok": not errs, "name": m.get("name"), "version": m.get("version"), "errors": errs, "provides": provides}


_SANDBOX_SITE = '''import os, socket
if os.environ.get("EIGHTBMS_SANDBOX_NET") != "1":
    def _blocked(*a, **k):
        raise PermissionError("network is disabled in the 8bms plugin test sandbox")
    socket.socket.connect = _blocked
    socket.create_connection = _blocked
'''


def test_plugin(path, timeout: int = 600, extra: Optional[List[str]] = None) -> dict:
    """Run the plugin's tests in a subprocess with a throwaway home, no network
    (unless the manifest grants it) and a timeout."""
    root, m = _plugin_root(path)
    with tempfile.TemporaryDirectory(prefix="8bms-sandbox-") as td:
        (Path(td) / "sitecustomize.py").write_text(_SANDBOX_SITE)
        env = dict(os.environ)
        repo = str(Path(__file__).resolve().parent)
        env["PYTHONPATH"] = os.pathsep.join([td, repo, env.get("PYTHONPATH", "")])
        env["EIGHTBMS_HOME"] = str(Path(td) / "home")
        env["EIGHTBMS_NO_PLUGINS"] = "1"
        env["EIGHTBMS_SANDBOX_NET"] = "1" if "network" in m.get("permissions", []) else "0"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests", *(extra or [])]
        try:
            r = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"ok": False, "name": m.get("name"), "summary": f"timeout after {timeout}s"}
    lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
    return {"ok": r.returncode == 0, "name": m.get("name"), "summary": lines[-1] if lines else r.stderr.strip()[-300:],
            "output": r.stdout[-4000:] + r.stderr[-2000:] if r.returncode else ""}


def _wheel_record_line(arc: str, data: bytes) -> str:
    dig = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{arc},sha256={dig},{len(data)}"


def build_plugin_wheel(path, out_dir: Optional[Path] = None) -> Path:
    """Build a pure-python wheel (no setuptools needed) with an entry point in
    group eightbit_studio.plugins and plugin.toml inside the package."""
    root, m = _plugin_root(path)
    errs = validate_manifest(m)
    if errs:
        raise PluginError("; ".join(errs))
    mod = m["entry"].split(":")[0].split(".")[0]
    pkg = root / mod
    if not (pkg / "__init__.py").exists():
        raise PluginError(f"wheel needs a package folder '{mod}/' (use 'plugin package' for single-file plugins)")
    dist = "eightbit_studio_plugin_" + m["name"].replace("-", "_")
    ver = m["version"]
    out_dir = Path(out_dir or root / "dist")
    out_dir.mkdir(parents=True, exist_ok=True)
    whl = out_dir / f"{dist}-{ver}-py3-none-any.whl"
    di = f"{dist}-{ver}.dist-info"
    files: List[Tuple[str, bytes]] = []
    for f in sorted(pkg.rglob("*")):
        if f.is_file() and "__pycache__" not in f.parts and f.suffix not in (".pyc",):
            files.append((f"{mod}/{f.relative_to(pkg).as_posix()}", f.read_bytes()))
    files.append((f"{mod}/plugin.toml", (root / "plugin.toml").read_bytes()))
    files.append((f"{di}/METADATA", (f"Metadata-Version: 2.1\nName: {dist.replace('_', '-')}\nVersion: {ver}\n"
                                     f"Summary: {m['description']}\nRequires-Python: >=3.10\nRequires-Dist: numpy\n").encode()))
    files.append((f"{di}/WHEEL", b"Wheel-Version: 1.0\nGenerator: 8bms\nRoot-Is-Purelib: true\nTag: py3-none-any\n"))
    files.append((f"{di}/entry_points.txt", f"[{EP_GROUP}]\n{m['name']} = {m['entry'] if ':' in m['entry'] else m['entry'] + ':register'}\n".encode()))
    record = [_wheel_record_line(a, d) for a, d in files] + [f"{di}/RECORD,,"]
    files.append((f"{di}/RECORD", ("\n".join(record) + "\n").encode()))
    with zipfile.ZipFile(whl, "w", zipfile.ZIP_DEFLATED) as z:
        for a, d in files:
            z.writestr(a, d)
    return whl


def package_plugin_zip(path, out_dir: Optional[Path] = None) -> Path:
    root, m = _plugin_root(path)
    errs = validate_manifest(m)
    if errs:
        raise PluginError("; ".join(errs))
    out_dir = Path(out_dir or root / "dist")
    out_dir.mkdir(parents=True, exist_ok=True)
    z = out_dir / f"{m['name']}-{m['version']}.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(root.rglob("*")):
            rel = f.relative_to(root)
            if f.is_file() and not any(p in ("dist", "__pycache__", ".pytest_cache", ".git") for p in rel.parts):
                zf.write(f, f"{m['name']}/{rel.as_posix()}")
    return z


def _pip_cmd() -> List[str]:
    try:
        import pip  # noqa: F401
        return [sys.executable, "-m", "pip"]
    except ImportError:
        if shutil.which("uv"):
            return ["uv", "pip"]
        raise PluginError("pip is not available in this environment")


def install_plugin(spec: str) -> dict:
    """Install from a folder, .zip, git URL, wheel or pip requirement."""
    dest_root = home_dir() / "plugins"
    dest_root.mkdir(parents=True, exist_ok=True)
    p = Path(os.path.expanduser(spec))

    def from_dir(d: Path) -> dict:
        root, m = _plugin_root(d)
        errs = validate_manifest(m)
        if errs:
            raise PluginError("; ".join(errs))
        target = dest_root / m["name"]
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(root, target, ignore=shutil.ignore_patterns("dist", "__pycache__", ".pytest_cache", ".git"))
        return {"installed": m["name"], "version": m["version"], "path": str(target), "via": "folder"}

    if p.is_dir():
        return from_dir(p)
    if p.suffix == ".zip" and p.exists():
        with tempfile.TemporaryDirectory() as td:
            with zipfile.ZipFile(p) as z:
                for n in z.namelist():
                    if n.startswith("/") or ".." in Path(n).parts:
                        raise PluginError(f"unsafe path in zip: {n}")
                z.extractall(td)
            mfs = list(Path(td).rglob("plugin.toml"))
            if not mfs:
                raise PluginError("zip has no plugin.toml")
            res = from_dir(min(mfs, key=lambda x: len(x.parts)).parent)
            res["via"] = "zip"
            return res
    if spec.startswith(("git+", "https://", "git@")) and (spec.endswith(".git") or "github.com" in spec or spec.startswith("git+")):
        url = spec[4:] if spec.startswith("git+") else spec
        with tempfile.TemporaryDirectory() as td:
            r = subprocess.run(["git", "clone", "--depth", "1", url, td + "/src"], capture_output=True, text=True)
            if r.returncode:
                raise PluginError(f"git clone failed: {r.stderr.strip()[:300]}")
            res = from_dir(Path(td) / "src")
            res["via"] = "git"
            return res
    cmd = _pip_cmd()
    if cmd[0] == "uv":
        cmd = ["uv", "pip", "install", "--python", sys.executable, spec]
    else:
        cmd = cmd + ["install", spec]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise PluginError(f"pip install failed: {r.stderr.strip()[-400:]}")
    return {"installed": spec, "via": "pip"}


def uninstall_plugin(name: str) -> dict:
    target = home_dir() / "plugins" / name
    if target.exists():
        shutil.rmtree(target)
        return {"uninstalled": name, "via": "folder"}
    dist = "eightbit-studio-plugin-" + name
    cmd = _pip_cmd()
    cmd = ["uv", "pip", "uninstall", "--python", sys.executable, dist] if cmd[0] == "uv" else cmd + ["uninstall", "-y", dist]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise PluginError(f"not installed: {name}")
    return {"uninstalled": name, "via": "pip"}


# ---------------------------------------------------------------------------
# Audio playback: sounddevice -> simpleaudio -> OS player -> silent
# ---------------------------------------------------------------------------
class AudioOut:
    """Plays a (possibly looping) song buffer plus one-shot preview sounds."""

    def __init__(self):
        self.backend = "none"
        self._sd = self._sa = None
        self._stream = None
        self._buf: Optional[np.ndarray] = None
        self._pos = 0
        self._loop = False
        self._oneshots: List[List[Any]] = []
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._sa_play = None
        self.volume = 1.0
        self.playing = False
        self._t_start = 0.0
        self._start_offset = 0
        try:
            import sounddevice as sd  # type: ignore
            sd.query_devices(kind="output")
            self._sd, self.backend = sd, "sounddevice"
        except Exception:
            try:
                import simpleaudio as sa  # type: ignore
                self._sa, self.backend = sa, "simpleaudio"
            except Exception:
                for player in (["paplay"], ["aplay", "-q"], ["afplay"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]):
                    if shutil.which(player[0]):
                        self._player, self.backend = player, f"os:{player[0]}"
                        break

    # -- sounddevice path ---------------------------------------------------
    def _ensure_stream(self):
        if self._stream is None and self._sd is not None:
            def cb(outdata, frames, t, status):
                out = np.zeros((frames, 2), dtype=np.float32)
                with self._lock:
                    if self.playing and self._buf is not None:
                        got = 0
                        while got < frames:
                            chunk = self._buf[self._pos:self._pos + frames - got]
                            out[got:got + len(chunk)] += chunk
                            got += len(chunk)
                            self._pos += len(chunk)
                            if self._pos >= len(self._buf):
                                if self._loop:
                                    self._pos = 0
                                else:
                                    self.playing = False
                                    break
                            if len(chunk) == 0:
                                break
                    keep = []
                    for s in self._oneshots:
                        c = s[0][s[1]:s[1] + frames]
                        out[: len(c)] += c
                        s[1] += frames
                        if s[1] < len(s[0]):
                            keep.append(s)
                    self._oneshots = keep
                outdata[:] = np.clip(out * self.volume, -1, 1)
            self._stream = self._sd.OutputStream(samplerate=SR, channels=2, dtype="float32", callback=cb, blocksize=512)
            self._stream.start()

    def position_samples(self) -> int:
        if self._sd is not None:
            return self._pos
        if not self.playing:
            return self._start_offset
        p = self._start_offset + int((time.monotonic() - self._t_start) * SR)
        if self._buf is not None and len(self._buf):
            if self._loop:
                p %= len(self._buf)
            elif p >= len(self._buf):
                self.playing = False
        return p

    def play(self, buf: np.ndarray, loop: bool = False, offset: int = 0):
        self.stop()
        buf = buf.astype(np.float32)
        with self._lock:
            self._buf, self._pos, self._loop = buf, offset, loop
            self.playing = True
        self._t_start, self._start_offset = time.monotonic(), offset
        if self._sd is not None:
            self._ensure_stream()
        elif self._sa is not None:
            self._sa_play = self._sa.play_buffer(to_int16(buf[offset:] * self.volume).tobytes(), 2, 2, SR)
        elif self.backend.startswith("os:"):
            fd, tmp = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            write_wav(tmp, buf[offset:] * self.volume)
            self._proc = subprocess.Popen(self._player + [tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop(self):
        with self._lock:
            self.playing = False
        if self._sa_play is not None:
            try:
                self._sa_play.stop()
            except Exception:
                pass
            self._sa_play = None
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None

    def needs_restart(self) -> bool:
        """For non-streaming backends: True when a loop iteration ended."""
        if self._sd is not None or not self.playing or not self._loop or self._buf is None:
            return False
        return (time.monotonic() - self._t_start) * SR + self._start_offset >= len(self._buf)

    def preview(self, buf: np.ndarray):
        if self._sd is not None:
            self._ensure_stream()
            with self._lock:
                self._oneshots.append([buf.astype(np.float32), 0])
        elif self._sa is not None:
            try:
                self._sa.play_buffer(to_int16(buf * self.volume).tobytes(), 2, 2, SR)
            except Exception:
                pass
        elif self.backend.startswith("os:"):
            fd, tmp = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            write_wav(tmp, buf * self.volume)
            subprocess.Popen(self._player + [tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def close(self):
        self.stop()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# MIDI input + Akai APC controller support (optional: pip install mido python-rtmidi)
# ---------------------------------------------------------------------------
MIDI_MAPPINGS.update({
    # APC mini / APC mini mk2: 8x8 pads notes 0-63 (bottom-left = 0), faders CC 48-56
    "apc-mini": {"match": ["APC MINI", "APC mini"], "grid": {"notes": list(range(64)), "rows": 8, "cols": 8, "origin": "bottom"},
                 "faders": {str(48 + i): i for i in range(8)}, "master_cc": 56,
                 "scene": list(range(82, 90)), "track_buttons": list(range(64, 72)), "shift": 98,
                 "led": {"off": 0, "on": 1, "accent": 5, "playhead": 3}},
    # APC Key 25: 5x8 pads notes 0-39 + 25-key keyboard on the same port/channel 1
    "apc-key25": {"match": ["APC Key 25", "APC KEY 25"], "grid": {"notes": list(range(40)), "rows": 5, "cols": 8, "origin": "bottom"},
                  "knobs": {str(48 + i): i for i in range(8)}, "keys_channel": 1, "transport": {"play": 91, "record": 93},
                  "led": {"off": 0, "on": 1, "accent": 5, "playhead": 3}},
    # APC40 mk2: clip grid 5x8 notes 32-39,24-31,...; track faders CC 7 on channels 0-7, master CC 14
    "apc40": {"match": ["APC40"], "grid": {"notes": [32 + c - 8 * r for r in range(5) for c in range(8)], "rows": 5, "cols": 8, "origin": "top"},
              "fader_cc": 7, "master_cc": 14, "transport": {"play": 91, "stop": 92, "record": 93},
              "led": {"off": 0, "on": 1, "accent": 5, "playhead": 3}},
    "generic": {"match": [""], "keys_channel": None},
})


def midi_available() -> bool:
    try:
        import mido  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False


def midi_ports() -> List[str]:
    try:
        import mido  # type: ignore
        return list(mido.get_input_names())
    except Exception:
        return []


def mapping_for_port(port: str) -> Tuple[str, dict]:
    for name, m in MIDI_MAPPINGS.items():
        if name != "generic" and any(s and s.lower() in port.lower() for s in m.get("match", [])):
            return name, m
    return "generic", MIDI_MAPPINGS["generic"]


class MidiController:
    """Translates MIDI messages into studio actions via a mapping. The handler
    gets ('note_on', pitch, vel) / ('note_off', pitch) / ('grid', row, col) /
    ('fader', track, value01) / ('master', value01) / ('transport', name) /
    ('scene', index)."""

    def __init__(self, handler: Callable[..., None], mapping: Optional[dict] = None):
        self.handler = handler
        self.mapping = mapping or MIDI_MAPPINGS["generic"]
        self.port = None
        self.out = None

    def handle(self, msg) -> None:
        m = self.mapping
        t = getattr(msg, "type", None)
        grid = m.get("grid", {})
        notes = grid.get("notes", [])
        if t in ("note_on", "note_off"):
            note, vel = msg.note, getattr(msg, "velocity", 0)
            ch = getattr(msg, "channel", 0)
            keys_ch = m.get("keys_channel")
            if notes and note in notes and (keys_ch is None or ch != keys_ch) and m is not MIDI_MAPPINGS["generic"]:
                if t == "note_on" and vel > 0:
                    i = notes.index(note)
                    r, c = divmod(i, grid["cols"])
                    row = (grid["rows"] - 1 - r) if grid.get("origin") == "bottom" else r
                    self.handler("grid", row, c)
                return
            for name, n in m.get("transport", {}).items():
                if note == n and t == "note_on" and vel > 0:
                    self.handler("transport", name)
                    return
            if note in m.get("scene", []) and t == "note_on" and vel > 0:
                self.handler("scene", m["scene"].index(note))
                return
            if t == "note_on" and vel > 0:
                self.handler("note_on", note, vel / 127)
            else:
                self.handler("note_off", note)
        elif t == "control_change":
            cc, val = msg.control, msg.value / 127
            if str(cc) in m.get("faders", {}):
                self.handler("fader", m["faders"][str(cc)], val)
            elif m.get("fader_cc") is not None and cc == m["fader_cc"]:
                self.handler("fader", getattr(msg, "channel", 0), val)
            elif cc == m.get("master_cc"):
                self.handler("master", val)
            elif str(cc) in m.get("knobs", {}):
                self.handler("knob", m["knobs"][str(cc)], val)

    def open(self, port_name: str) -> str:
        import mido  # type: ignore
        name, self.mapping = mapping_for_port(port_name)
        self.port = mido.open_input(port_name, callback=self.handle)
        try:
            if port_name in mido.get_output_names():
                self.out = mido.open_output(port_name)
        except Exception:
            self.out = None
        return name

    def set_led(self, row: int, col: int, state: str = "on"):
        """Light a grid pad (APC LED feedback)."""
        if self.out is None:
            return
        import mido  # type: ignore
        g = self.mapping.get("grid", {})
        if not g:
            return
        r = (g["rows"] - 1 - row) if g.get("origin") == "bottom" else row
        idx = r * g["cols"] + col
        if 0 <= idx < len(g["notes"]):
            self.out.send(mido.Message("note_on", note=g["notes"][idx], velocity=self.mapping.get("led", {}).get(state, 1)))

    def close(self):
        for p in (self.port, self.out):
            try:
                if p:
                    p.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Agent Client Protocol (ACP) server: `8bms acp`  (JSON-RPC 2.0, NDJSON on stdio)
# Spec: https://agentclientprotocol.com  - protocol version 1
# ---------------------------------------------------------------------------
ACP_PROTOCOL_VERSION = 1
ACP_COMMANDS = [
    ("help", "Show what you can type", None), ("new", "Start an empty song", "title"), ("demo", "Load the demo song", None),
    ("gen", "Generate a song: /gen <style> [bars] [seed]", "style bars seed"), ("load", "Load .8bms/.8bt", "path"),
    ("save", "Save project (.8bms or .8bt)", "path"), ("show", "Print the song as .8bt score", None),
    ("info", "Song summary", None), ("bpm", "Set tempo", "bpm"), ("key", "Set key, e.g. /key A minor", "key scale"),
    ("track", "Select or create a track", "name [inst=..]"), ("pat", "Select pattern", "name"),
    ("transpose", "Transpose melodic tracks", "semitones"), ("undo", "Undo last change", None),
    ("render", "Render WAV (--loop, --seamless)", "path"), ("stems", "Render per-track stems", "dir"),
    ("export", "Export js|py|json|score|project", "kind path"), ("presets", "List instruments", None),
    ("styles", "List generator styles", None), ("roll", "ASCII piano roll of current pattern", None),
    ("viz", "Run a visualizer", "name"),
]


def _jdump(o) -> str:
    return json.dumps(o, separators=(",", ":"), default=lambda x: f"<{type(x).__name__}>")


class ACPServer:
    def __init__(self, inp=None, out=None):
        self.inp = inp or sys.stdin
        self.out = out or sys.stdout
        self.lock = threading.Lock()
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.client_caps: dict = {}
        self.threads: List[threading.Thread] = []

    # transport ---------------------------------------------------------------
    def send(self, msg: dict):
        with self.lock:
            self.out.write(_jdump(msg) + "\n")
            self.out.flush()

    def notify(self, sid: str, update: dict):
        self.send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": sid, "update": update}})

    def reply(self, mid, result=None, error=None):
        msg: Dict[str, Any] = {"jsonrpc": "2.0", "id": mid}
        if error:
            msg["error"] = error
        else:
            msg["result"] = result
        self.send(msg)

    def serve(self):
        for line in self.inp:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as e:
                self.reply(None, error={"code": -32700, "message": f"parse error: {e}"})
                continue
            self.dispatch(msg)
        for t in self.threads:
            t.join(timeout=30)

    # dispatch ----------------------------------------------------------------
    def dispatch(self, msg: dict):
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            self.reply(msg.get("id") if isinstance(msg, dict) else None, error={"code": -32600, "message": "invalid request"})
            return
        method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
        if method is None:
            return  # a response to something we sent; we send no requests
        try:
            if method == "initialize":
                self.client_caps = params.get("clientCapabilities", {})
                self.reply(mid, {
                    "protocolVersion": ACP_PROTOCOL_VERSION,
                    "agentCapabilities": {"loadSession": True,
                                          "promptCapabilities": {"image": False, "audio": False, "embeddedContext": True},
                                          "mcpCapabilities": {"http": False, "sse": False}},
                    "agentInfo": {"name": "8bms", "title": APP_NAME, "version": APP_VERSION},
                    "authMethods": []})
            elif method == "authenticate":
                self.reply(mid, {})
            elif method == "session/new":
                self.reply(mid, {"sessionId": self.new_session(params)})
                self.advertise(self._last_sid)
            elif method == "session/load":
                sid = params.get("sessionId")
                self.load_session(sid, params)
                self.reply(mid, {})
                self.advertise(sid)
            elif method == "session/prompt":
                sid = params.get("sessionId")
                if sid not in self.sessions:
                    raise _RPCError(-32602, f"unknown session {sid!r}")
                if self.sessions[sid].get("busy"):
                    raise _RPCError(-32602, "a prompt is already running in this session")
                self.sessions[sid]["busy"] = True
                th = threading.Thread(target=self.prompt, args=(mid, sid, params.get("prompt") or []), daemon=True)
                self.threads.append(th)
                th.start()
            elif method == "session/cancel":
                s = self.sessions.get(params.get("sessionId"))
                if s:
                    s["interp"].cancelled = True
            elif method == "session/set_mode":
                self.reply(mid, {})
            elif mid is not None:
                raise _RPCError(-32601, f"method not found: {method}")
        except _RPCError as e:
            if mid is not None:
                self.reply(mid, error={"code": e.code, "message": str(e)})
        except Exception as e:  # never die on a bad request
            if mid is not None:
                self.reply(mid, error={"code": -32603, "message": f"{type(e).__name__}: {e}"})

    # sessions ----------------------------------------------------------------
    @staticmethod
    def session_file(sid: str) -> Path:
        d = home_dir() / "acp-sessions"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{re.sub(r'[^A-Za-z0-9_-]', '', sid)}.json"

    def _make(self, sid: str, cwd: str, song: Optional[Song] = None, history=None):
        if not cwd or not os.path.isabs(cwd):
            raise _RPCError(-32602, "cwd must be an absolute path")
        interp = Interpreter(song or new_song(), cwd)
        interp.emit = lambda _ev, **d: self._on_emit(sid, _ev, d)
        self.sessions[sid] = {"interp": interp, "history": history or [], "cwd": cwd, "busy": False}
        self._last_sid = sid

    def new_session(self, params: dict) -> str:
        sid = "sess_" + uuid.uuid4().hex[:16]
        self._make(sid, params.get("cwd") or os.getcwd())
        return sid

    def load_session(self, sid: str, params: dict):
        f = self.session_file(sid or "")
        if not sid or not f.exists():
            raise _RPCError(-32602, f"unknown session {sid!r}")
        d = json.loads(f.read_text())
        self._make(sid, params.get("cwd") or d.get("cwd"), Song.from_dict(d["song"]), d.get("history", []))
        for h in d.get("history", []):
            kind = "user_message_chunk" if h["role"] == "user" else "agent_message_chunk"
            self.notify(sid, {"sessionUpdate": kind, "content": {"type": "text", "text": h["text"]}})

    def save_session(self, sid: str):
        s = self.sessions[sid]
        self.session_file(sid).write_text(json.dumps({"song": s["interp"].song.to_dict(), "history": s["history"][-200:], "cwd": s["cwd"]}))

    def advertise(self, sid: str):
        cmds = [{"name": n, "description": d, **({"input": {"hint": h}} if h else {})} for n, d, h in ACP_COMMANDS]
        cmds += [{"name": n, "description": h or f"plugin command {n}", "input": {"hint": "args"}} for n, (_, h) in SLASH_COMMANDS.items()]
        cmds += [{"name": n, "description": op.help or n, "input": {"hint": " ".join(f"{k}=" for k in op.params)}}
                 for n, op in OPS.items() if n not in {c[0] for c in ACP_COMMANDS}]
        self.notify(sid, {"sessionUpdate": "available_commands_update", "availableCommands": cmds})

    def _on_emit(self, sid: str, kind: str, d: dict):
        if kind == "tool_start":
            self.notify(sid, {"sessionUpdate": "tool_call", "toolCallId": d["id"], "title": d["title"], "kind": d["kind"],
                              "status": "in_progress", "rawInput": d.get("input")})
        elif kind == "tool_end":
            content = [{"type": "content", "content": {"type": "text", "text": d.get("text", "")}}]
            paths = d.get("paths") or []
            for p in paths:
                content.append({"type": "content", "content": {"type": "resource_link", "uri": Path(p).resolve().as_uri(), "name": Path(p).name}})
            upd = {"sessionUpdate": "tool_call_update", "toolCallId": d["id"], "status": d["status"], "content": content}
            if paths:
                upd["locations"] = [{"path": str(Path(p).resolve())} for p in paths]
            if d.get("output") is not None:
                upd["rawOutput"] = json.loads(_jdump({k: v for k, v in d["output"].items() if k != "song"}))
            self.notify(sid, upd)

    def prompt(self, mid, sid: str, blocks: List[dict]):
        s = self.sessions[sid]
        interp: Interpreter = s["interp"]
        interp.cancelled = False
        texts: List[str] = []
        try:
            for b in blocks:
                t = b.get("type")
                if t == "text":
                    texts.append(b.get("text", ""))
                elif t == "resource":
                    r = b.get("resource", {})
                    if r.get("text") is not None and str(r.get("uri", "")).endswith(SCORE_EXT):
                        interp.snapshot()
                        interp.song = parse_score(r["text"])
                        texts.append("/info")
                    elif r.get("text"):
                        texts.append(r["text"])
                elif t == "resource_link":
                    uri = b.get("uri", "")
                    if uri.startswith("file://") and uri.endswith((SCORE_EXT, FILE_EXT)):
                        from urllib.parse import unquote, urlparse
                        texts.append(f"/load {unquote(urlparse(uri).path)}")
            text = "\n".join(texts).strip()
            s["history"].append({"role": "user", "text": text})
            lines = [l for l in text.splitlines() if l.strip()]
            if len(lines) > 1:
                self.notify(sid, {"sessionUpdate": "plan", "entries": [{"content": l[:80], "priority": "medium", "status": "pending"} for l in lines]})
            replies = []
            for i, line in enumerate(lines or [""]):
                if interp.cancelled:
                    raise Cancelled()
                try:
                    r = interp.execute_line(line.strip())
                except (ScoreError, NoteSyntaxError, ValueError, KeyError, PluginError, FileNotFoundError) as e:
                    r = f"error: {e}"
                replies.append(r)
                self.notify(sid, {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": r + "\n"}})
                if len(lines) > 1:
                    self.notify(sid, {"sessionUpdate": "plan", "entries": [
                        {"content": l[:80], "priority": "medium", "status": "completed" if j <= i else "pending"} for j, l in enumerate(lines)]})
            s["history"].append({"role": "agent", "text": "\n".join(replies)})
            self.save_session(sid)
            stop = "end_turn"
        except Cancelled:
            stop = "cancelled"
        except Exception as e:
            self.notify(sid, {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": f"error: {type(e).__name__}: {e}\n"}})
            stop = "end_turn"
        finally:
            s["busy"] = False
        self.reply(mid, {"stopReason": stop})


class _RPCError(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code


def run_acp():
    """Stdout carries only protocol messages; everything else goes to stderr."""
    real_out = sys.stdout
    sys.stdout = sys.stderr
    load_plugins()
    ACPServer(sys.stdin, real_out).serve()


# ---------------------------------------------------------------------------
# MCP server (`8bms mcp`) - exposes every op + a stateful 'studio' tool
# ---------------------------------------------------------------------------
def run_mcp(inp=None, out=None):
    inp, real_out = inp or sys.stdin, out or sys.stdout
    if out is None:
        sys.stdout = sys.stderr
    load_plugins()
    interp = Interpreter(new_song(), os.getcwd())

    def send(m):
        real_out.write(_jdump(m) + "\n")
        real_out.flush()
    for line in inp:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if mid is None:
            continue
        try:
            if method == "initialize":
                res = {"protocolVersion": params.get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}},
                       "serverInfo": {"name": "8bms", "version": APP_VERSION}}
            elif method == "ping":
                res = {}
            elif method == "tools/list":
                tools = [{"name": "studio", "description": "Stateful chiptune studio: send note language, .8bt statements, slash commands or simple English. Returns a terse reply.",
                          "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}]
                tools += [{"name": n, "description": op.help, "inputSchema": op.json_schema()} for n, op in OPS.items()]
                res = {"tools": tools}
            elif method == "tools/call":
                name, args = params.get("name"), params.get("arguments") or {}
                try:
                    txt = interp.execute(args.get("text", "")) if name == "studio" else _jdump(run_op(name, **args))
                    res = {"content": [{"type": "text", "text": txt}], "isError": False}
                except Exception as e:
                    res = {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}
            else:
                send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}})
                continue
            send({"jsonrpc": "2.0", "id": mid, "result": res})
        except Exception as e:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}})


# ---------------------------------------------------------------------------
# Local HTTP API (`8bms serve`): GET /ops  POST /ops/<name>  POST /prompt
# ---------------------------------------------------------------------------
def make_http_server(host: str = "127.0.0.1", port: int = 8765):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    interp = Interpreter(new_song(), os.getcwd())
    lock = threading.Lock()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code: int, obj: Any):
            body = _jdump(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"ok": True, "version": APP_VERSION})
            if self.path == "/ops":
                return self._send(200, {n: {"help": o.help, "params": o.json_schema(), "owner": o.owner} for n, o in OPS.items()})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                if self.path.startswith("/ops/"):
                    return self._send(200, run_op(self.path[5:], **body))
                if self.path == "/prompt":
                    with lock:
                        return self._send(200, {"reply": interp.execute(body.get("text", ""))})
                self._send(404, {"error": "not found"})
            except Exception as e:
                self._send(400, {"error": f"{type(e).__name__}: {e}"})
    return ThreadingHTTPServer((host, port), H)


# ---------------------------------------------------------------------------
# Terminal studio (`8bms repl`)
# ---------------------------------------------------------------------------
def run_repl(src: Optional[str] = None):
    load_plugins()
    interp = Interpreter(load_any(src) if src else new_song())
    audio = None
    print(f"{APP_NAME} terminal studio - /help for commands, /play to listen, /quit to exit")
    while True:
        try:
            line = input("8bms> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line.strip() in ("/quit", "/exit", "quit", "exit"):
            break
        if line.strip() in ("/play", "/stop"):
            audio = audio or AudioOut()
            if line.strip() == "/stop":
                audio.stop()
            else:
                audio.play(render_song(interp.song))
                print(f"playing via {audio.backend}")
            continue
        try:
            print(interp.execute(line))
        except Exception as e:
            print(f"error: {e}")
    if audio:
        audio.close()


# ---------------------------------------------------------------------------
# GUI (tkinter). Imported lazily so the engine/CLI work without a display.
# ---------------------------------------------------------------------------
THEME = {"bg": "#11111b", "panel": "#1a1a2a", "panel2": "#222236", "grid": "#2b2b44", "grid2": "#3a3a5c", "text": "#dcdcf5",
         "dim": "#8a8ab0", "accent": "#ff4f9a", "cyan": "#3ce0ff", "green": "#7dff8a", "yellow": "#ffd84f", "row_in": "#1d1d30",
         "row_out": "#151522", "black_key": "#22223a", "white_key": "#d8d8e8", "playhead": "#ffd84f", "loop": "#3ce0ff"}
KIND_COLORS = {"pulse1": "#ff4f9a", "pulse2": "#ff9f43", "triangle": "#3ce0ff", "noise": "#7dff8a", "extra": "#c084fc"}
SNAPS = {"1/4": PPQ, "1/8": PPQ // 2, "1/16": PPQ // 4, "1/32": PPQ // 8, "1/8T": PPQ // 3, "1/16T": PPQ // 6, "1/32T": PPQ // 12}
KEYS_LOWER = "zsxdcvgbhnjm,l.;/"
KEYS_UPPER = "q2w3er5t6y7ui9o0p[=]"
SHORTCUTS = """\
TRANSPORT        Space play/pause - Home stop & rewind - L loop on/off - F follow playhead
                 R record - M metronome - T tap tempo
EDIT             Ctrl+Z undo - Ctrl+Y / Ctrl+Shift+Z redo - Ctrl+C/X/V copy/cut/paste
                 Ctrl+D duplicate - Ctrl+A select all - Delete remove - Q quantize
                 Up/Down transpose +-1 - Shift+Up/Down +-12 - Left/Right nudge by snap
TOOLS            D draw - S select - E erase - C chord stamp
PIANO ROLL       Click empty = add note (drag to set length) - drag note = move
                 drag right edge = resize - right-click / double-click = delete
                 Shift+click = add to selection - Select tool or Ctrl+drag = box select
                 Mouse wheel = scroll, Shift+wheel = horizontal, Ctrl+wheel = zoom
                 Bottom strip = velocity (drag bars up/down)
COMPUTER KEYS    Ctrl+K (or K) toggles keyboard playing. Lower row Z S X D C V... = C, C#, D...
                 Upper row Q 2 W 3 E R... = one octave up. Minus / Equals = octave down / up.
                 Esc leaves keyboard mode. With Record on, played notes are written in.
ARRANGEMENT      Drag a pattern from the list onto a track row - drag clips to move
                 right-click clip = delete - double-click clip = edit it
                 Ctrl+click empty cell = place current pattern
                 Drag on the bar ruler = set loop region - click ruler = move playhead
                 right-click ruler = clear loop
FILES            Ctrl+N new - Ctrl+O open - Ctrl+S save - Ctrl+Shift+S save as - Ctrl+E export WAV
HELP             F1 this window
"""


def _shade(hex_color: str, f: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (min(255, int(r * f)), min(255, int(g * f)), min(255, int(b * f)))


def launch_gui(path: Optional[str] = None, screenshot: Optional[str] = None, selftest: bool = False) -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    class ToolTip:
        def __init__(self, w, text):
            self.w, self.text, self.tip = w, text, None
            w.bind("<Enter>", self.show, add="+")
            w.bind("<Leave>", self.hide, add="+")

        def show(self, _e=None):
            if self.tip:
                return
            x, y = self.w.winfo_rootx() + 10, self.w.winfo_rooty() + self.w.winfo_height() + 4
            self.tip = tk.Toplevel(self.w)
            self.tip.wm_overrideredirect(True)
            self.tip.geometry(f"+{x}+{y}")
            tk.Label(self.tip, text=self.text, bg="#2b2b44", fg=THEME["text"], relief="solid", bd=1, padx=6, pady=2).pack()

        def hide(self, _e=None):
            if self.tip:
                self.tip.destroy()
                self.tip = None

    class App:
        def __init__(self, root: "tk.Tk"):
            self.root = root
            self.song = new_song()
            self.path: Optional[Path] = None
            self.dirty = False
            self.cur_track = 0
            self.cur_pattern = "A"
            self.sel: List[Note] = []
            self.clipboard: List[dict] = []
            self.undo_stack: List[dict] = []
            self.redo_stack: List[dict] = []
            self.audio = AudioOut()
            self.playing = False
            self.play_tick = 0
            self.play_start_tick = 0
            self.play_buf_ticks = 0
            self.pos_tick = 0
            self.render_gen = 0
            self.taps: List[float] = []
            self.pressed: Dict[str, int] = {}
            self.rec_open: Dict[int, Note] = {}
            self.midi: Optional[MidiController] = None
            self.drum_page = 0
            self.v = {k: tk.BooleanVar(value=d) for k, d in (("loop", False), ("follow", True), ("record", False), ("metro", False),
                                                                  ("keys", False), ("snapscale", False), ("diatonic", True))}
            self.v["keys"].trace_add("write", lambda *a: (self.kb.redraw() if hasattr(self, "kb") else None,
                                                         self.status("Computer keyboard: " + ("ON (Esc to leave)" if self.v["keys"].get() else "off"))))
            self.snap_var = tk.StringVar(value="1/16")
            self.snap_var.trace_add("write", lambda *a: self.refresh_editors() if hasattr(self, "roll") else None)
            self.tool_var = tk.StringVar(value="draw")
            self.chord_var = tk.StringVar(value="maj")
            self.octave = tk.IntVar(value=4)
            self.bpm_var = tk.DoubleVar(value=120)
            self.swing_var = tk.DoubleVar(value=0)
            self.key_var = tk.StringVar(value="C")
            self.scale_var = tk.StringVar(value="major")
            self.ts_var = tk.StringVar(value="4/4")
            self.pat_var = tk.StringVar(value="A")
            self.bars_var = tk.IntVar(value=4)
            self.status_var = tk.StringVar(value="Welcome!")
            self.pos_var = tk.StringVar(value="bar 1.1")
            self.build_style()
            self.build_menu()
            self.build_toolbar()
            self.build_status()
            self.build_body()
            self.bind_keys()
            root.protocol("WM_DELETE_WINDOW", self.quit)
            root.after(40, self.tick)
            root.after(60000, self.autosave_tick)

        # ---------------------------------------------------------- styling
        def build_style(self):
            st = ttk.Style(self.root)
            try:
                st.theme_use("clam")
            except Exception:
                pass
            T = THEME
            self.root.configure(bg=T["bg"])
            st.configure(".", background=T["panel"], foreground=T["text"], fieldbackground=T["panel2"], bordercolor=T["grid"],
                         lightcolor=T["panel"], darkcolor=T["panel"], troughcolor=T["bg"], selectbackground=T["accent"], insertcolor=T["text"])
            st.configure("TButton", background=T["panel2"], padding=(6, 3))
            st.map("TButton", background=[("active", T["grid2"]), ("pressed", T["accent"])])
            st.configure("Accent.TButton", background=T["accent"], foreground="#000")
            st.map("Accent.TButton", background=[("active", "#ff7ab5")])
            st.configure("TCheckbutton", background=T["panel"])
            st.map("TCheckbutton", background=[("active", T["panel"])], indicatorcolor=[("selected", T["cyan"])])
            st.configure("Toolbutton", background=T["panel2"], padding=(6, 3))
            st.map("Toolbutton", background=[("selected", T["accent"]), ("active", T["grid2"])], foreground=[("selected", "#000")])
            st.configure("TNotebook", background=T["bg"], tabmargins=0)
            st.configure("TNotebook.Tab", background=T["panel2"], padding=(12, 4))
            st.map("TNotebook.Tab", background=[("selected", T["accent"])], foreground=[("selected", "#000")])
            st.configure("TLabel", background=T["panel"])
            st.configure("Status.TLabel", background=T["bg"], foreground=T["dim"])
            st.configure("Head.TLabel", foreground=T["cyan"], font=("TkDefaultFont", 10, "bold"))
            st.configure("TCombobox", fieldbackground=T["panel2"], background=T["panel2"], arrowcolor=T["text"])
            st.map("TCombobox", fieldbackground=[("readonly", T["panel2"])], foreground=[("readonly", T["text"])])
            st.configure("TSpinbox", fieldbackground=T["panel2"], arrowcolor=T["text"])
            self.root.option_add("*TCombobox*Listbox.background", T["panel2"])
            self.root.option_add("*TCombobox*Listbox.foreground", T["text"])
            self.root.option_add("*Menu.background", T["panel2"])
            self.root.option_add("*Menu.foreground", T["text"])
            self.root.option_add("*Menu.activeBackground", T["accent"])

        # ---------------------------------------------------------- menus
        def build_menu(self):
            m = tk.Menu(self.root)
            fm = tk.Menu(m, tearoff=0)
            fm.add_command(label="New", accelerator="Ctrl+N", command=self.cmd_new)
            fm.add_command(label="Open...", accelerator="Ctrl+O", command=self.cmd_open)
            self.recent_menu = tk.Menu(fm, tearoff=0, postcommand=self.fill_recent)
            fm.add_cascade(label="Open Recent", menu=self.recent_menu)
            fm.add_command(label="Load Demo Song", command=lambda: self.confirm_discard() and self.set_song(demo_song(), None))
            fm.add_command(label="Save", accelerator="Ctrl+S", command=self.cmd_save)
            fm.add_command(label="Save As...", accelerator="Ctrl+Shift+S", command=self.cmd_save_as)
            fm.add_separator()
            fm.add_command(label="Export WAV - whole song...", accelerator="Ctrl+E", command=lambda: self.cmd_export_audio("song"))
            fm.add_command(label="Export WAV - loop region...", command=lambda: self.cmd_export_audio("loop"))
            fm.add_command(label="Export WAV - seamless loop...", command=lambda: self.cmd_export_audio("seamless"))
            fm.add_command(label="Export stems (one WAV per track)...", command=self.cmd_export_stems)
            fm.add_command(label="Export OGG / MP3 / FLAC (ffmpeg)...", command=lambda: self.cmd_export_audio("other"))
            fm.add_separator()
            self.code_menu = tk.Menu(fm, tearoff=0, postcommand=self.fill_code_menu)
            fm.add_cascade(label="Save as Code", menu=self.code_menu)
            fm.add_separator()
            fm.add_command(label="Quit", command=self.quit)
            m.add_cascade(label="File", menu=fm)
            em = tk.Menu(m, tearoff=0)
            for lbl, acc, cmd in (("Undo", "Ctrl+Z", self.undo), ("Redo", "Ctrl+Y", self.redo), (None, None, None),
                                  ("Cut", "Ctrl+X", self.cut), ("Copy", "Ctrl+C", self.copy), ("Paste", "Ctrl+V", self.paste),
                                  ("Duplicate", "Ctrl+D", self.duplicate), ("Select All", "Ctrl+A", self.select_all),
                                  ("Delete", "Del", self.delete_sel), (None, None, None), ("Quantize", "Q", self.quantize_sel),
                                  ("Transpose +1", "Up", lambda: self.transpose_sel(1)), ("Transpose -1", "Down", lambda: self.transpose_sel(-1)),
                                  ("Octave Up", "Shift+Up", lambda: self.transpose_sel(12)), ("Octave Down", "Shift+Down", lambda: self.transpose_sel(-12))):
                if lbl is None:
                    em.add_separator()
                else:
                    em.add_command(label=lbl, accelerator=acc, command=cmd)
            m.add_cascade(label="Edit", menu=em)
            tm = tk.Menu(m, tearoff=0)
            tm.add_command(label="Generate Song...", command=self.cmd_generate)
            tm.add_command(label="Random Melody (in key)", command=self.random_melody)
            tm.add_command(label="Random Drums", command=self.random_drums)
            tm.add_command(label="Arpeggiate Selection", command=self.arp_sel)
            tm.add_command(label="Add Chords (I-vi-IV-V) to Pattern", command=self.fill_chords)
            tm.add_separator()
            tm.add_checkbutton(label="Metronome", variable=self.v["metro"])
            tm.add_command(label="Tap Tempo", accelerator="T", command=self.tap)
            tm.add_checkbutton(label="Snap to Scale", variable=self.v["snapscale"])
            tm.add_command(label="Score Console (type music)...", command=self.open_console)
            m.add_cascade(label="Tools", menu=tm)
            self.plugin_menu = tk.Menu(m, tearoff=0, postcommand=self.fill_plugin_menu)
            m.add_cascade(label="Plugins", menu=self.plugin_menu)
            self.midi_menu = tk.Menu(m, tearoff=0, postcommand=self.fill_midi_menu)
            m.add_cascade(label="MIDI", menu=self.midi_menu)
            hm = tk.Menu(m, tearoff=0)
            hm.add_command(label="Keyboard Shortcuts", accelerator="F1", command=self.show_help)
            hm.add_command(label="Score / Note Language", command=lambda: self.text_window("Score format", SCORE_HELP + "\n" + HELP_TEXT))
            hm.add_command(label="About", command=lambda: messagebox.showinfo("About", f"{APP_NAME} {APP_VERSION}\nAudio: {self.audio.backend}\nEverything is synthesized - no samples.", parent=self.root))
            m.add_cascade(label="Help", menu=hm)
            self.root.config(menu=m)

        def fill_recent(self):
            self.recent_menu.delete(0, "end")
            rec = recent_files()
            for p in rec:
                self.recent_menu.add_command(label=p, command=lambda p=p: self.confirm_discard() and self.open_path(p))
            if not rec:
                self.recent_menu.add_command(label="(none)", state="disabled")

        def fill_code_menu(self):
            self.code_menu.delete(0, "end")
            names = {"py": "Python script (regenerates WAV)", "js": "JavaScript Web Audio module", "json": "JSON data", "score": ".8bt text score", "project": ".8bms project"}
            for k, (ext, _) in EXPORTERS.items():
                self.code_menu.add_command(label=f"{names.get(k, k)}  ({ext})", command=lambda k=k: self.cmd_export_code(k))

        def fill_plugin_menu(self):
            pm = load_plugins()
            self.plugin_menu.delete(0, "end")
            for p in pm.plugins.values():
                state = "error" if p.error else ("on" if p.loaded else "off")
                var = tk.BooleanVar(value=p.enabled)

                def toggle(p=p, var=var):
                    pm.set_enabled(p.name, var.get())
                    if var.get():
                        pm.load(p)
                    else:
                        pm.unload(p.name)
                    self.status(f"plugin {p.name}: {'enabled' if var.get() else 'disabled'}" + (f" ({p.error})" if p.error else ""))
                self.plugin_menu.add_checkbutton(label=f"{p.name} {p.version} [{state}]", variable=var, command=toggle)
            if not pm.plugins:
                self.plugin_menu.add_command(label="(no plugins found)", state="disabled")
            self.plugin_menu.add_separator()
            self.plugin_menu.add_command(label="Plugin folder: " + str(home_dir() / "plugins"), state="disabled")

        def fill_midi_menu(self):
            self.midi_menu.delete(0, "end")
            if not midi_available():
                self.midi_menu.add_command(label="Install 'mido python-rtmidi' for MIDI / Akai APC", state="disabled")
                return
            ports = midi_ports()
            for p in ports:
                self.midi_menu.add_command(label=f"Connect {p}  [{mapping_for_port(p)[0]}]", command=lambda p=p: self.connect_midi(p))
            if not ports:
                self.midi_menu.add_command(label="(no MIDI inputs found)", state="disabled")

        # ---------------------------------------------------------- toolbar
        def build_toolbar(self):
            T = THEME
            bar = tk.Frame(self.root, bg=T["panel"])
            bar.pack(side="top", fill="x")
            row1 = tk.Frame(bar, bg=T["panel"])
            row1.pack(fill="x", padx=4, pady=(4, 1))

            def btn(parent, text, cmd, tip, style="TButton", width=None):
                b = ttk.Button(parent, text=text, command=cmd, style=style, width=width or -(len(text) + 1))
                b.pack(side="left", padx=1)
                ToolTip(b, tip)
                return b

            def chk(parent, text, var, tip):
                c = ttk.Checkbutton(parent, text=text, variable=var, style="Toolbutton")
                c.pack(side="left", padx=1)
                ToolTip(c, tip)
                return c
            btn(row1, "New", self.cmd_new, "New song (Ctrl+N)")
            btn(row1, "Open", self.cmd_open, "Open .8bms / .8bt (Ctrl+O)")
            btn(row1, "Save", self.cmd_save, "Save project (Ctrl+S)")
            btn(row1, "WAV", lambda: self.cmd_export_audio("song"), "Export the song as WAV (Ctrl+E)")
            btn(row1, "Code", lambda: self.cmd_export_code("py"), "Save as a Python script that rebuilds the WAV (more in File > Save as Code)")
            tk.Frame(row1, width=12, bg=T["panel"]).pack(side="left")
            self.play_btn = btn(row1, "\u25b6 Play", self.toggle_play, "Play / pause (Space)", "Accent.TButton", 8)
            btn(row1, "\u25a0 Stop", self.stop, "Stop and rewind (Home)")
            chk(row1, "Loop", self.v["loop"], "Loop the loop region (L). Drag on the arrangement ruler to set it.")
            chk(row1, "Follow", self.v["follow"], "Scroll with the playhead (F)")
            chk(row1, "\u25cf Rec", self.v["record"], "Record played notes into the pattern (R)")
            chk(row1, "Metro", self.v["metro"], "Metronome click (M)")
            chk(row1, "Keys", self.v["keys"], "Play notes with the computer keyboard (Ctrl+K)")
            tk.Frame(row1, width=12, bg=T["panel"]).pack(side="left")
            ttk.Label(row1, text="BPM").pack(side="left")
            sp = ttk.Spinbox(row1, from_=30, to=300, increment=1, width=5, textvariable=self.bpm_var, command=self.on_song_settings)
            sp.pack(side="left", padx=2)
            sp.bind("<Return>", lambda e: self.on_song_settings())
            sp.bind("<FocusOut>", lambda e: self.on_song_settings())
            ToolTip(sp, "Tempo in beats per minute")
            btn(row1, "Tap", self.tap, "Tap repeatedly to set the tempo (T)")
            ttk.Label(row1, text="Time").pack(side="left", padx=(6, 0))
            cb = ttk.Combobox(row1, textvariable=self.ts_var, values=["4/4", "3/4", "2/4", "6/8", "5/4", "7/8"], width=4, state="readonly")
            cb.pack(side="left", padx=2)
            cb.bind("<<ComboboxSelected>>", lambda e: self.on_song_settings())
            ttk.Label(row1, text="Swing").pack(side="left", padx=(6, 0))
            sw = ttk.Scale(row1, from_=0, to=0.5, variable=self.swing_var, length=70)
            sw.bind("<ButtonRelease-1>", lambda e: self.on_song_settings())
            sw.pack(side="left", padx=2)
            ToolTip(sw, "Swing: delays every second 16th note")
            ttk.Label(row1, text="Key").pack(side="left", padx=(6, 0))
            kc = ttk.Combobox(row1, textvariable=self.key_var, values=NOTE_NAMES, width=3, state="readonly")
            kc.pack(side="left", padx=2)
            kc.bind("<<ComboboxSelected>>", lambda e: self.on_song_settings())
            sc = ttk.Combobox(row1, textvariable=self.scale_var, values=list(SCALES), width=13, state="readonly")
            sc.pack(side="left", padx=2)
            sc.bind("<<ComboboxSelected>>", lambda e: self.on_song_settings())
            ToolTip(sc, "Scale: highlighted rows in the piano roll; used by generators and snap-to-scale")
            btn(row1, "?", self.show_help, "Keyboard shortcuts & help (F1)", width=2)

            row2 = tk.Frame(bar, bg=T["panel"])
            row2.pack(fill="x", padx=4, pady=(1, 4))
            ttk.Label(row2, text="Tool").pack(side="left")
            for val, lbl, tip in (("draw", "\u270e Draw", "Draw/move/resize notes (D)"), ("select", "\u25a2 Select", "Box-select notes (S)"),
                                  ("erase", "\u2716 Erase", "Click notes to delete (E)"), ("chord", "\u266b Chord", "Click to stamp a chord (C)")):
                r = ttk.Radiobutton(row2, text=lbl, value=val, variable=self.tool_var, style="Toolbutton")
                r.pack(side="left", padx=1)
                ToolTip(r, tip)
            ch = ttk.Combobox(row2, textvariable=self.chord_var, values=list(CHORDS), width=5, state="readonly")
            ch.pack(side="left", padx=2)
            ToolTip(ch, "Chord type for the chord tool (ignored when Diatonic is on)")
            chk(row2, "Diatonic", self.v["diatonic"], "Chord tool builds chords from the song's scale")
            ttk.Label(row2, text="Snap").pack(side="left", padx=(8, 0))
            sn = ttk.Combobox(row2, textvariable=self.snap_var, values=list(SNAPS), width=6, state="readonly")
            sn.pack(side="left", padx=2)
            ToolTip(sn, "Grid snap (T = triplets)")
            chk(row2, "Scale snap", self.v["snapscale"], "Force new notes into the scale")
            tk.Frame(row2, width=12, bg=T["panel"]).pack(side="left")
            self.track_lbl = ttk.Label(row2, text="Track: -", style="Head.TLabel")
            self.track_lbl.pack(side="left", padx=4)
            ttk.Label(row2, text="Pattern").pack(side="left")
            self.pat_cb = ttk.Combobox(row2, textvariable=self.pat_var, width=6, state="readonly")
            self.pat_cb.pack(side="left", padx=2)
            self.pat_cb.bind("<<ComboboxSelected>>", lambda e: self.select_pattern(self.pat_var.get()))
            btn(row2, "+", self.new_pattern, "New empty pattern on this track", width=2)
            btn(row2, "Dup", self.dup_pattern, "Duplicate pattern")
            btn(row2, "Del", self.del_pattern, "Delete pattern")
            ttk.Label(row2, text="Bars").pack(side="left", padx=(6, 0))
            bs = ttk.Spinbox(row2, from_=1, to=64, width=3, textvariable=self.bars_var, command=self.set_pattern_bars)
            bs.pack(side="left", padx=2)
            bs.bind("<Return>", lambda e: self.set_pattern_bars())
            ToolTip(bs, "Pattern length in bars")
            btn(row2, "\u2684 Melody", self.random_melody, "Random melody in the key/scale for this pattern")
            btn(row2, "\u2684 Drums", self.random_drums, "Random drum groove")
            btn(row2, "Generate...", self.cmd_generate, "Generate a whole song in a style")

        # ---------------------------------------------------------- body
        def build_body(self):
            T = THEME
            outer = tk.PanedWindow(self.root, orient="horizontal", bg=T["bg"], sashwidth=5, sashrelief="flat", bd=0)
            outer.pack(fill="both", expand=True)
            self.mixer_frame = tk.Frame(outer, bg=T["panel"], width=250)
            outer.add(self.mixer_frame, minsize=210, width=250)
            right = tk.PanedWindow(outer, orient="vertical", bg=T["bg"], sashwidth=5, bd=0)
            outer.add(right, minsize=500)
            self.nb = ttk.Notebook(right)
            right.add(self.nb, minsize=220, height=420)
            self.roll = PianoRoll(self, self.nb)
            self.nb.add(self.roll.frame, text="Piano Roll")
            self.drums = DrumGrid(self, self.nb)
            self.nb.add(self.drums.frame, text="Drum Sequencer")
            self.inst_ed = InstrumentEditor(self, self.nb)
            self.nb.add(self.inst_ed.frame, text="Instruments")
            for title, factory, owner in list(GUI_PANELS):
                try:
                    w = factory(self.nb, self)
                    self.nb.add(w, text=title)
                except Exception as e:
                    self.status(f"plugin panel '{title}' ({owner}) failed: {e}")
            self.arr = Arranger(self, right)
            right.add(self.arr.frame, minsize=120, height=200)
            self.kb = KeyboardWidget(self, right)
            right.add(self.kb.frame, minsize=70, height=86)
            self.nb.bind("<<NotebookTabChanged>>", lambda e: self.refresh_editors())

        def build_status(self):
            f = tk.Frame(self.root, bg=THEME["bg"])
            f.pack(side="bottom", fill="x")
            ttk.Label(f, textvariable=self.status_var, style="Status.TLabel").pack(side="left", padx=6)
            ttk.Label(f, text=f"audio: {self.audio.backend}", style="Status.TLabel").pack(side="right", padx=6)
            ttk.Label(f, textvariable=self.pos_var, style="Status.TLabel").pack(side="right", padx=6)

        # ---------------------------------------------------------- mixer
        def build_mixer(self):
            T = THEME
            for w in self.mixer_frame.winfo_children():
                w.destroy()
            ttk.Label(self.mixer_frame, text="MIXER", style="Head.TLabel").pack(anchor="w", padx=6, pady=(6, 2))
            canvas = tk.Canvas(self.mixer_frame, bg=T["panel"], highlightthickness=0, width=240)
            sb = ttk.Scrollbar(self.mixer_frame, orient="vertical", command=canvas.yview)
            inner = tk.Frame(canvas, bg=T["panel"])
            inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            win = canvas.create_window((0, 0), window=inner, anchor="nw")
            canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
            canvas.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            canvas.pack(fill="both", expand=True)
            inst_names = sorted(set(PRESETS) | set(self.song.instruments))
            for i, t in enumerate(self.song.tracks):
                sel = i == self.cur_track
                bg = T["panel2"] if sel else T["panel"]
                f = tk.Frame(inner, bg=bg, highlightthickness=2 if sel else 0, highlightbackground=T["accent"])
                f.pack(fill="x", padx=4, pady=3)
                top = tk.Frame(f, bg=bg)
                top.pack(fill="x")
                tk.Label(top, bg=KIND_COLORS.get(t.kind, "#888"), width=1).pack(side="left", fill="y", padx=(0, 4))
                nm = tk.Label(top, text=t.name, fg=T["text"], bg=bg, font=("TkDefaultFont", 10, "bold"), cursor="hand2")
                nm.pack(side="left")
                nm.bind("<Button-1>", lambda e, i=i: self.select_track(i))
                nm.bind("<Double-Button-1>", lambda e, i=i: self.rename_track(i))
                ToolTip(nm, f"{t.kind} channel - click to edit, double-click to rename")
                for txt, attr, col in (("S", "solo", T["yellow"]), ("M", "mute", T["accent"])):
                    on = getattr(t, attr)
                    b = tk.Label(top, text=txt, width=2, bg=col if on else T["grid"], fg="#000" if on else T["text"], cursor="hand2")
                    b.pack(side="right", padx=1)
                    b.bind("<Button-1>", lambda e, t=t, a=attr: (self.push_undo(), setattr(t, a, not getattr(t, a)), self.after_mix_change()))
                    ToolTip(b, "Solo" if txt == "S" else "Mute")
                mid = tk.Frame(f, bg=bg)
                mid.pack(fill="x")
                iv = tk.StringVar(value=t.instrument)
                cb = ttk.Combobox(mid, textvariable=iv, values=inst_names, width=11, state="readonly")
                cb.pack(side="left", padx=2, pady=1)
                cb.bind("<<ComboboxSelected>>", lambda e, t=t, iv=iv: (self.push_undo(), setattr(t, "instrument", iv.get()), self.after_mix_change()))
                ToolTip(cb, "Instrument for this track")
                dv = tk.BooleanVar(value=t.drum)
                ttk.Checkbutton(mid, text="drum", variable=dv, command=lambda t=t, dv=dv: (self.push_undo(), setattr(t, "drum", dv.get()), self.refresh_all())).pack(side="left")
                for lbl, attr, lo, hi in (("vol", "volume", 0.0, 1.0), ("pan", "pan", -1.0, 1.0)):
                    r = tk.Frame(f, bg=bg)
                    r.pack(fill="x")
                    tk.Label(r, text=lbl, fg=T["dim"], bg=bg, width=3).pack(side="left")
                    var = tk.DoubleVar(value=getattr(t, attr))
                    ttk.Scale(r, from_=lo, to=hi, variable=var, command=lambda v, t=t, a=attr, var=var: (setattr(t, a, round(var.get(), 3)), self.mark_dirty(), self.schedule_rerender())).pack(side="left", fill="x", expand=True, padx=2)
            ctl = tk.Frame(inner, bg=T["panel"])
            ctl.pack(fill="x", padx=4, pady=4)
            ttk.Button(ctl, text="+ Track", command=self.add_track).pack(side="left", padx=1)
            ttk.Button(ctl, text="- Track", command=self.remove_track).pack(side="left", padx=1)
            ttk.Label(inner, text="MASTER", style="Head.TLabel").pack(anchor="w", padx=6, pady=(8, 0))
            mv = tk.DoubleVar(value=self.song.master)
            ttk.Scale(inner, from_=0, to=1, variable=mv, command=lambda v: (setattr(self.song, "master", round(mv.get(), 3)), self.mark_dirty(), self.schedule_rerender())).pack(fill="x", padx=8)
            ttk.Label(inner, text="EFFECTS (master)", style="Head.TLabel").pack(anchor="w", padx=6, pady=(8, 0))
            existing = {f["type"] for f in self.song.effects}
            for name in list(EXTRA_FX):
                if name not in existing:
                    self.song.effects.append({"type": name, "enabled": False, "params": {k: v[2] for k, v in FX_PARAMS.get(name, {}).items()}})
            for fx in self.song.effects:
                fr = tk.Frame(inner, bg=T["panel"])
                fr.pack(fill="x", padx=6, pady=2)
                ev = tk.BooleanVar(value=fx.get("enabled", False))
                ttk.Checkbutton(fr, text=fx["type"], variable=ev, command=lambda fx=fx, ev=ev: (self.push_undo(), fx.__setitem__("enabled", ev.get()), self.after_mix_change())).pack(anchor="w")
                for pname, (lo, hi, dflt) in FX_PARAMS.get(fx["type"], {}).items():
                    r = tk.Frame(fr, bg=T["panel"])
                    r.pack(fill="x")
                    tk.Label(r, text=pname, fg=T["dim"], bg=T["panel"], width=9, anchor="w").pack(side="left")
                    pv = tk.DoubleVar(value=fx.setdefault("params", {}).get(pname, dflt))
                    ttk.Scale(r, from_=lo, to=hi, variable=pv, command=lambda v, fx=fx, p=pname, pv=pv: (fx["params"].__setitem__(p, round(pv.get(), 3)), self.mark_dirty(), self.schedule_rerender())).pack(side="left", fill="x", expand=True)

        # ---------------------------------------------------------- state helpers
        @property
        def track(self) -> Optional[Track]:
            return self.song.tracks[self.cur_track] if 0 <= self.cur_track < len(self.song.tracks) else None

        @property
        def pattern(self) -> Optional[Pattern]:
            t = self.track
            if t is None:
                return None
            if self.cur_pattern not in t.patterns:
                if not t.patterns:
                    t.patterns["A"] = Pattern("A", 4)
                self.cur_pattern = next(iter(t.patterns))
            return t.patterns[self.cur_pattern]

        def snap(self) -> int:
            return SNAPS.get(self.snap_var.get(), PPQ // 4)

        def status(self, msg: str):
            self.status_var.set(msg)

        def mark_dirty(self):
            self.dirty = True
            self.root.title(f"{APP_NAME} - {self.song.title} *")

        def push_undo(self):
            self.undo_stack.append(self.song.to_dict())
            self.undo_stack = self.undo_stack[-200:]
            self.redo_stack.clear()
            self.mark_dirty()

        def _restore(self, d: dict):
            self.song = Song.from_dict(d)
            self.sel = []
            self.refresh_all()

        def undo(self):
            if not self.undo_stack:
                return self.status("Nothing to undo")
            self.redo_stack.append(self.song.to_dict())
            self._restore(self.undo_stack.pop())
            self.status("Undo")

        def redo(self):
            if not self.redo_stack:
                return self.status("Nothing to redo")
            self.undo_stack.append(self.song.to_dict())
            self._restore(self.redo_stack.pop())
            self.status("Redo")

        def set_song(self, song: Song, path: Optional[Path]):
            self.stop()
            self.song, self.path = song, path
            self.cur_track, self.cur_pattern, self.sel = 0, "A", []
            self.pos_tick = 0
            self.dirty = False
            self.refresh_all()
            self.root.title(f"{APP_NAME} - {song.title}")
            self.status(f"Loaded '{song.title}': {len(song.tracks)} tracks, {song.length_bars()} bars - press Space to play")
            return True

        def refresh_all(self):
            s = self.song
            self.bpm_var.set(s.bpm)
            self.swing_var.set(s.swing)
            self.key_var.set(NOTE_NAMES[key_root(s.key)])
            self.scale_var.set(s.scale)
            self.ts_var.set(f"{s.time_sig[0]}/{s.time_sig[1]}")
            self.cur_track = min(self.cur_track, max(len(s.tracks) - 1, 0))
            self.build_mixer()
            self.refresh_pattern_bar()
            self.refresh_editors()
            self.arr.redraw()
            self.inst_ed.refresh_list()
            self.kb.redraw()
            self.schedule_rerender()

        def refresh_pattern_bar(self):
            t = self.track
            self.track_lbl.configure(text=f"Track: {t.name}" if t else "Track: -")
            self.pat_cb.configure(values=list(t.patterns) if t else [])
            p = self.pattern
            self.pat_var.set(p.name if p else "")
            self.bars_var.set(p.bars if p else 1)

        def refresh_editors(self):
            try:
                tab = self.nb.index(self.nb.select())
            except Exception:
                tab = 0
            if tab == 0:
                self.roll.redraw()
            elif tab == 1:
                self.drums.redraw()

        def after_mix_change(self):
            self.build_mixer()
            self.arr.redraw()
            self.schedule_rerender()

        def on_song_settings(self):
            try:
                bpm = float(self.bpm_var.get())
                n, d = (int(x) for x in self.ts_var.get().split("/"))
            except (tk.TclError, ValueError):
                return
            s = self.song
            new = (round(max(20.0, min(400.0, bpm)), 2), (n, d), round(float(self.swing_var.get()), 3), self.key_var.get(), self.scale_var.get())
            cur = (round(s.bpm, 2), tuple(s.time_sig), round(s.swing, 3), NOTE_NAMES[key_root(s.key)], s.scale)
            if new == cur:
                return
            self.push_undo()
            s.bpm, s.time_sig, s.swing, s.key, s.scale = new
            self.refresh_editors()
            self.arr.redraw()
            self.schedule_rerender()

        def set_bpm(self, bpm: float):
            self.push_undo()
            self.song.bpm = float(bpm)
            self.refresh_all()

        # ---------------------------------------------------------- tracks & patterns
        def select_track(self, i: int):
            if not (0 <= i < len(self.song.tracks)):
                return
            self.cur_track = i
            t = self.track
            self.cur_pattern = next((c.pattern for c in self.song.arrangement if c.track == i), next(iter(t.patterns), "A"))
            self.sel = []
            self.build_mixer()
            self.refresh_pattern_bar()
            tab = self.nb.index(self.nb.select())
            if t.drum and tab == 0:
                self.nb.select(1)
            elif not t.drum and tab == 1:
                self.nb.select(0)
            self.refresh_editors()
            self.arr.redraw()
            self.inst_ed.select(t.instrument)

        def select_pattern(self, name: str):
            if self.track and name in self.track.patterns:
                self.cur_pattern = name
            self.sel = []
            self.refresh_pattern_bar()
            self.refresh_editors()
            self.arr.redraw()
            self.sync_leds()

        def rename_track(self, i: int):
            n = simpledialog.askstring("Rename track", "Track name:", initialvalue=self.song.tracks[i].name, parent=self.root)
            if n and n.strip():
                self.push_undo()
                self.song.tracks[i].name = n.strip()
                self.refresh_all()

        def add_track(self):
            kinds = [t.kind for t in self.song.tracks]
            kind = next((k for k in CHANNEL_KINDS if k not in kinds), "extra")
            inst = {"pulse1": "lead", "pulse2": "arp", "triangle": "bass", "noise": "snare", "extra": "saw"}[kind]
            self.push_undo()
            self.song.tracks.append(Track(f"Track {len(self.song.tracks) + 1}", kind, inst, 0.7, 0.0, drum=kind == "noise", patterns={"A": Pattern("A", 4)}))
            self.cur_track = len(self.song.tracks) - 1
            self.cur_pattern = "A"
            self.refresh_all()

        def remove_track(self):
            if not self.song.tracks or not messagebox.askyesno("Remove track", f"Remove track '{self.track.name}'?", parent=self.root):
                return
            self.push_undo()
            i = self.cur_track
            del self.song.tracks[i]
            self.song.arrangement = [Clip(c.track - (1 if c.track > i else 0), c.pattern, c.bar) for c in self.song.arrangement if c.track != i]
            self.cur_track = max(0, i - 1)
            self.refresh_all()

        def _next_pattern_name(self) -> str:
            t = self.track
            for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                if ch not in t.patterns:
                    return ch
            return f"P{len(t.patterns)}"

        def new_pattern(self):
            if not self.track:
                return
            self.push_undo()
            n = self._next_pattern_name()
            self.track.patterns[n] = Pattern(n, self.pattern.bars if self.pattern else 4)
            self.select_pattern(n)
            self.status(f"New pattern {n} - drag it from the pattern list onto the timeline")

        def dup_pattern(self):
            p = self.pattern
            if not p:
                return
            self.push_undo()
            n = self._next_pattern_name()
            self.track.patterns[n] = Pattern(n, p.bars, [Note.from_dict(x.to_dict()) for x in p.notes])
            self.select_pattern(n)
            self.status(f"Duplicated pattern {p.name} -> {n}")

        def del_pattern(self):
            t, p = self.track, self.pattern
            if not p or len(t.patterns) <= 1:
                return self.status("A track needs at least one pattern")
            self.push_undo()
            del t.patterns[p.name]
            self.song.arrangement = [c for c in self.song.arrangement if not (c.track == self.cur_track and c.pattern == p.name)]
            self.cur_pattern = next(iter(t.patterns))
            self.refresh_all()

        def set_pattern_bars(self):
            p = self.pattern
            try:
                b = max(1, min(64, int(self.bars_var.get())))
            except (tk.TclError, ValueError):
                return
            if p and b != p.bars:
                self.push_undo()
                p.bars = b
                self.refresh_editors()
                self.arr.redraw()
                self.schedule_rerender()

        # ---------------------------------------------------------- note editing
        def add_notes(self, notes: List[Note]):
            self.pattern.notes.extend(notes)
            self.ensure_arranged()
            self.schedule_rerender()

        def ensure_arranged(self):
            ti = self.cur_track
            if not any(c.track == ti for c in self.song.arrangement):
                self.song.arrangement.append(Clip(ti, self.cur_pattern, 0))
                self.arr.redraw()

        def delete_sel(self):
            if not self.sel:
                return
            self.push_undo()
            ids = {id(n) for n in self.sel}
            self.pattern.notes = [n for n in self.pattern.notes if id(n) not in ids]
            self.sel = []
            self.refresh_editors()
            self.schedule_rerender()

        def select_all(self):
            self.sel = list(self.pattern.notes) if self.pattern else []
            self.refresh_editors()
            self.status(f"{len(self.sel)} notes selected")

        def copy(self):
            if self.sel:
                base = min(n.start for n in self.sel)
                self.clipboard = [dict(n.to_dict(), start=n.start - base) for n in self.sel]
                self.status(f"Copied {len(self.sel)} notes")

        def cut(self):
            self.copy()
            self.delete_sel()

        def paste(self):
            if not self.clipboard or not self.pattern:
                return
            self.push_undo()
            at = max(n.end for n in self.sel) if self.sel else self.pos_tick % max(1, self.pattern.bars * self.song.ticks_per_bar)
            at = (at // self.snap()) * self.snap()
            new = [Note.from_dict(dict(d, start=d["start"] + at)) for d in self.clipboard]
            self.add_notes(new)
            self.sel = new
            self.refresh_editors()
            self.status(f"Pasted {len(new)} notes")

        def duplicate(self):
            if not self.sel:
                return
            self.push_undo()
            span = max(n.end for n in self.sel) - min(n.start for n in self.sel)
            new = [Note(n.start + span, n.length, n.pitch, n.velocity, n.inst) for n in self.sel]
            self.add_notes(new)
            self.sel = new
            self.refresh_editors()

        def quantize_sel(self):
            notes = self.sel or (self.pattern.notes if self.pattern else [])
            if not notes:
                return
            self.push_undo()
            quantize(notes, self.snap())
            self.refresh_editors()
            self.schedule_rerender()
            self.status(f"Quantized {len(notes)} notes to {self.snap_var.get()}")

        def transpose_sel(self, n: int):
            if not self.sel:
                return
            self.push_undo()
            for x in self.sel:
                x.pitch = max(0, min(127, x.pitch + n))
            self.refresh_editors()
            self.schedule_rerender()

        def nudge_sel(self, d: int):
            if not self.sel:
                return
            self.push_undo()
            for x in self.sel:
                x.start = max(0, x.start + d * self.snap())
            self.refresh_editors()
            self.schedule_rerender()

        def arp_sel(self):
            p = self.pattern
            notes = self.sel or list(p.notes)
            if not notes:
                return
            self.push_undo()
            ids = {id(n) for n in notes}
            p.notes = [n for n in p.notes if id(n) not in ids] + arpeggiate(notes, self.snap(), "updown")
            self.sel = []
            self.refresh_editors()
            self.schedule_rerender()
            self.status("Arpeggiated")

        def fill_chords(self):
            p, s = self.pattern, self.song
            self.push_undo()
            p.notes.extend(gen_pad(48 + key_root(s.key), s.scale, [0, 5, 3, 4], p.bars, s.ticks_per_bar))
            self.ensure_arranged()
            self.refresh_editors()
            self.schedule_rerender()
            self.status("Added I-vi-IV-V chords")

        def random_melody(self):
            if self.track and self.track.drum:
                return self.random_drums()
            s, p = self.song, self.pattern
            self.push_undo()
            rng = random.Random()
            p.notes = gen_melody(rng, 60 + key_root(s.key), s.scale, rng.choice([[0, 5, 3, 4], [0, 3, 4, 0], [5, 3, 0, 4]]), p.bars, s.ticks_per_bar, 0.6)
            self.ensure_arranged()
            self.sel = []
            self.refresh_editors()
            self.schedule_rerender()
            self.status(f"Random melody in {s.key} {s.scale}")

        def random_drums(self):
            s = self.song
            if not self.track or not self.track.drum:
                di = next((i for i, t in enumerate(s.tracks) if t.drum), None)
                if di is None:
                    return self.status("No drum track - tick 'drum' on a track in the mixer")
                self.select_track(di)
            p = self.pattern
            self.push_undo()
            groove = random.choice([g for g in GROOVES if g != "none"])
            p.notes = gen_drums(groove, p.bars, s.ticks_per_bar, fill_last=True, rng=random.Random())
            self.ensure_arranged()
            self.refresh_editors()
            self.schedule_rerender()
            self.status(f"Random drums: '{groove}' groove")

        def preview(self, pitch: int, inst: Optional[str] = None, vel: float = 0.8):
            t = self.track
            name = inst or (t.instrument if t else "lead")
            try:
                self.audio.preview(render_note_preview(self.song.get_instrument(name), pitch, 0.25, vel))
            except Exception:
                pass

        # ---------------------------------------------------------- transport
        def toggle_play(self):
            self.pause() if self.playing else self.play()

        def play(self, from_tick: Optional[int] = None):
            s = self.song
            tpb = s.ticks_per_bar
            loop = self.v["loop"].get()
            if loop:
                a, b = s.loop_range()
            else:
                a, b = 0, max(1, s.length_bars())
            start = self.pos_tick if from_tick is None else from_tick
            if not (a * tpb <= start < b * tpb):
                start = a * tpb
            seg_a = a if loop else start // tpb
            buf = render_song(s, seg_a, b, seamless=loop, tail=0 if loop else 1.5)
            if self.v["metro"].get():
                c = click_track(s, b - seg_a)[: len(buf)]
                buf[: len(c)] += c
            offset = int((start - seg_a * tpb) * s.tick_seconds() * SR)
            self.play_start_tick = seg_a * tpb
            self.play_buf_ticks = (b - seg_a) * tpb
            self.play_tick = start
            self.audio.play(buf, loop=loop, offset=max(0, offset))
            self.playing = True
            self.play_btn.configure(text="\u275a\u275a Pause")
            self.status(f"Playing via {self.audio.backend}" + (f" - looping bars {a + 1}-{b}" if loop else ""))

        def pause(self):
            self.audio.stop()
            self.playing = False
            self.pos_tick = self.play_tick
            self.play_btn.configure(text="\u25b6 Play")
            self.close_recorded()

        def stop(self):
            self.audio.stop()
            self.playing = False
            if hasattr(self, "play_btn"):
                self.play_btn.configure(text="\u25b6 Play")
            self.pos_tick = self.song.loop_range()[0] * self.song.ticks_per_bar if self.v["loop"].get() else 0
            self.play_tick = self.pos_tick
            self.close_recorded()
            if hasattr(self, "arr"):
                self.refresh_playheads()

        def schedule_rerender(self):
            if not self.playing:
                return
            self.render_gen += 1
            g = self.render_gen
            self.root.after(350, lambda: self._rerender(g))

        def _rerender(self, g):
            if g == self.render_gen and self.playing:
                self.audio.stop()
                self.play(self.play_tick)

        def tick(self):
            try:
                if self.playing:
                    if self.audio.needs_restart():
                        self.play(self.play_start_tick)
                    pos = self.audio.position_samples()
                    t = self.play_start_tick + int(pos / SR / self.song.tick_seconds())
                    if self.play_buf_ticks and self.v["loop"].get():
                        t = self.play_start_tick + (t - self.play_start_tick) % self.play_buf_ticks
                    self.play_tick = t
                    end = self.play_start_tick + self.play_buf_ticks
                    if not self.v["loop"].get() and (t >= end or (self.audio.backend == "sounddevice" and not self.audio.playing)):
                        self.stop()
                    elif self.audio.backend == "none" and self.v["loop"].get() and pos >= self.play_buf_ticks * self.song.tick_seconds() * SR:
                        self.play(self.play_start_tick)
                    self.refresh_playheads()
                    self.update_recorded()
            except Exception:
                traceback.print_exc()
            finally:
                self.root.after(40, self.tick)

        def refresh_playheads(self):
            t = self.play_tick if self.playing else self.pos_tick
            tpb = self.song.ticks_per_bar
            beat = PPQ * 4 // self.song.time_sig[1]
            self.pos_var.set(f"bar {t // tpb + 1}.{(t % tpb) // beat + 1}   {t * self.song.tick_seconds():6.2f}s")
            self.roll.draw_playhead(t)
            self.drums.draw_playhead(t)
            self.arr.draw_playhead(t)

        def tap(self):
            now = time.monotonic()
            self.taps = [x for x in self.taps if now - x < 3] + [now]
            if len(self.taps) >= 2:
                iv = float(np.diff(self.taps[-5:]).mean())
                self.bpm_var.set(round(60 / iv, 1))
                self.on_song_settings()
                self.status(f"Tap tempo: {self.bpm_var.get()} BPM")
            else:
                self.status("Tap again...")

        # ---------------------------------------------------------- recording / keyboard
        def pattern_tick_now(self) -> Optional[int]:
            """Playhead position inside the edited pattern, if that pattern is sounding."""
            t, tpb, p = self.play_tick, self.song.ticks_per_bar, self.pattern
            if not p:
                return None
            for c in self.song.arrangement:
                if c.track == self.cur_track and c.pattern == self.cur_pattern and c.bar * tpb <= t < (c.bar + p.bars) * tpb:
                    return t - c.bar * tpb
            return None

        def note_on(self, pitch: int, vel: float = 0.8):
            drum = bool(self.track and self.track.drum)
            if drum:
                self.preview(60, DRUM_ROWS[pitch % len(DRUM_ROWS)], vel)
            else:
                self.preview(pitch, None, vel)
            self.kb.highlight(pitch, True)
            p = self.pattern
            if not self.v["record"].get() or not p:
                return
            snap = self.snap()
            plen = p.bars * self.song.ticks_per_bar
            if self.playing:
                pt = self.pattern_tick_now()
                if pt is None:
                    return self.status("Recording: the selected pattern isn't playing right now")
                st = int(round(pt / snap) * snap) % plen
            else:
                st = (self.pos_tick % plen // snap) * snap
                self.pos_tick = (st + snap) % plen
            if not self.rec_open:
                self.push_undo()
            n = Note(st, snap, 60 if drum else pitch, vel, DRUM_ROWS[pitch % len(DRUM_ROWS)] if drum else None)
            p.notes.append(n)
            self.ensure_arranged()
            if self.playing:
                self.rec_open[pitch] = n
            self.refresh_editors()

        def note_off(self, pitch: int):
            self.kb.highlight(pitch, False)
            n = self.rec_open.pop(pitch, None)
            if n is not None:
                self.update_recorded(final=n)
                self.refresh_editors()
                self.schedule_rerender()

        def update_recorded(self, final: Optional[Note] = None):
            if not self.rec_open and final is None:
                return
            pt = self.pattern_tick_now()
            if pt is None:
                return
            snap = self.snap()
            for n in list(self.rec_open.values()) + ([final] if final else []):
                ln = pt - n.start
                if ln > 0:
                    n.length = max(snap, int(round(ln / snap) * snap))

        def close_recorded(self):
            self.rec_open.clear()

        def key_to_pitch(self, ch: str) -> Optional[int]:
            base = (self.octave.get() + 1) * 12
            if ch in KEYS_LOWER:
                return base + KEYS_LOWER.index(ch)
            if ch in KEYS_UPPER:
                return base + 12 + KEYS_UPPER.index(ch)
            return None

        def bind_keys(self):
            r = self.root
            self._repeat: Dict[str, bool] = {}
            keysym_char = {"comma": ",", "period": ".", "semicolon": ";", "slash": "/", "bracketleft": "[", "bracketright": "]", "equal": "=", "minus": "-"}

            def focus_is_entry():
                try:
                    w = r.focus_get()
                except Exception:
                    return False
                return isinstance(w, (tk.Entry, ttk.Entry, ttk.Spinbox, ttk.Combobox, tk.Text))

            def on_press(e):
                if focus_is_entry() or (e.state & 0x4):
                    return
                ch = (e.char or keysym_char.get(e.keysym, "")).lower()
                if self.v["keys"].get():
                    if e.keysym == "Escape":
                        self.v["keys"].set(False)
                        return "break"
                    if ch in self.pressed:
                        self._repeat[ch] = True
                        return "break"
                    if ch == "-":
                        self.kb.shift(-1)
                        return "break"
                    if ch == "=" and ch not in KEYS_UPPER:
                        self.kb.shift(1)
                        return "break"
                    p = self.key_to_pitch(ch) if ch else None
                    if p is not None:
                        self.pressed[ch] = p
                        self.note_on(p)
                        return "break"
                if e.keysym == "space":
                    self.toggle_play()
                    return "break"
                if self.v["keys"].get():
                    return
                k = e.keysym.lower()
                shift = bool(e.state & 0x1)
                acts = {"home": self.stop, "delete": self.delete_sel, "backspace": self.delete_sel, "q": self.quantize_sel,
                        "l": lambda: self.v["loop"].set(not self.v["loop"].get()), "f": lambda: self.v["follow"].set(not self.v["follow"].get()),
                        "r": lambda: self.v["record"].set(not self.v["record"].get()), "m": lambda: self.v["metro"].set(not self.v["metro"].get()),
                        "k": lambda: self.v["keys"].set(True), "t": self.tap, "f1": self.show_help,
                        "d": lambda: self.tool_var.set("draw"), "s": lambda: self.tool_var.set("select"),
                        "e": lambda: self.tool_var.set("erase"), "c": lambda: self.tool_var.set("chord"),
                        "up": lambda: self.transpose_sel(12 if shift else 1), "down": lambda: self.transpose_sel(-12 if shift else -1),
                        "left": lambda: self.nudge_sel(-1), "right": lambda: self.nudge_sel(1)}
                if k in acts:
                    acts[k]()
                    return "break"

            def on_release(e):
                ch = (e.char or keysym_char.get(e.keysym, e.keysym)).lower()
                if ch in self.pressed:
                    def check(ch=ch):
                        if self._repeat.get(ch):
                            self._repeat[ch] = False
                        elif ch in self.pressed:
                            self.note_off(self.pressed.pop(ch))
                    r.after(30, check)

            def ctl(e, fn):
                if focus_is_entry() and e.keysym.lower() in ("c", "x", "v", "a", "z", "y"):
                    return None
                fn()
                return "break"

            r.bind_all("<KeyPress>", on_press)
            r.bind_all("<KeyRelease>", on_release)
            for seq, fn in (("<Control-n>", self.cmd_new), ("<Control-o>", self.cmd_open), ("<Control-s>", self.cmd_save),
                            ("<Control-S>", self.cmd_save_as), ("<Control-z>", self.undo), ("<Control-y>", self.redo), ("<Control-Z>", self.redo),
                            ("<Control-c>", self.copy), ("<Control-x>", self.cut), ("<Control-v>", self.paste), ("<Control-d>", self.duplicate),
                            ("<Control-a>", self.select_all), ("<Control-e>", lambda: self.cmd_export_audio("song")),
                            ("<Control-k>", lambda: self.v["keys"].set(not self.v["keys"].get())), ("<F1>", self.show_help)):
                r.bind_all(seq, lambda e, fn=fn: ctl(e, fn))

        # ---------------------------------------------------------- MIDI / Akai APC
        def connect_midi(self, port: str):
            if self.midi:
                self.midi.close()
            self.midi = MidiController(lambda kind, *a: self.root.after(0, lambda: self.on_midi(kind, *a)))
            try:
                name = self.midi.open(port)
                self.status(f"MIDI connected: {port} (mapping: {name})")
                self.sync_leds()
            except Exception as e:
                self.midi = None
                self.status(f"MIDI error: {e}")

        def on_midi(self, kind, *a):
            if kind == "note_on":
                self.note_on(a[0], a[1])
            elif kind == "note_off":
                self.note_off(a[0])
            elif kind == "grid":
                row, col = a
                di = next((i for i, t in enumerate(self.song.tracks) if t.drum), None)
                if di is None or row >= len(DRUM_ROWS):
                    return
                if self.cur_track != di:
                    self.select_track(di)
                self.push_undo()
                cols = self.midi.mapping.get("grid", {}).get("cols", 8) if self.midi else 8
                self.drums.toggle(DRUM_ROWS[row], col + self.drum_page * cols)
                self.sync_leds()
            elif kind in ("fader", "knob") and a[0] < len(self.song.tracks):
                self.song.tracks[a[0]].volume = round(a[1], 3)
                self.mark_dirty()
                self.schedule_rerender()
                self.root.after(150, self.build_mixer)
            elif kind == "master":
                self.song.master = round(a[0], 3)
                self.mark_dirty()
                self.schedule_rerender()
            elif kind == "transport":
                {"play": self.toggle_play, "stop": self.stop, "record": lambda: self.v["record"].set(not self.v["record"].get())}.get(a[0], lambda: None)()
            elif kind == "scene":
                pats = list(self.track.patterns) if self.track else []
                if self.track and self.track.drum:
                    self.drum_page = a[0]
                    self.status(f"APC drum page {a[0] + 1}")
                    self.sync_leds()
                elif a[0] < len(pats):
                    self.select_pattern(pats[a[0]])

        def sync_leds(self):
            if not self.midi or not getattr(self.midi, "out", None):
                return
            g, p = self.midi.mapping.get("grid", {}), self.pattern
            if not g or not p:
                return
            on = {(n.inst, n.start // (PPQ // 4)) for n in p.notes}
            for r in range(min(g["rows"], len(DRUM_ROWS))):
                for c in range(g["cols"]):
                    self.midi.set_led(r, c, "on" if (DRUM_ROWS[r], c + self.drum_page * g["cols"]) in on else "off")

        # ---------------------------------------------------------- files
        def confirm_discard(self) -> bool:
            if not self.dirty:
                return True
            r = messagebox.askyesnocancel("Unsaved changes", "Save changes first?", parent=self.root)
            if r is None:
                return False
            return self.cmd_save() if r else True

        def cmd_new(self):
            if self.confirm_discard():
                self.set_song(new_song(), None)
                self.undo_stack.clear()

        def cmd_open(self):
            if not self.confirm_discard():
                return
            p = filedialog.askopenfilename(parent=self.root, filetypes=[("8Bit projects & scores", "*.8bms *.8bt *.json"), ("All files", "*.*")])
            if p:
                self.open_path(p)

        def open_path(self, p):
            try:
                self.set_song(load_project(p), Path(p) if Path(p).suffix == FILE_EXT else None)
                self.undo_stack.clear()
                add_recent(p)
            except Exception as e:
                messagebox.showerror("Open failed", str(e), parent=self.root)

        def cmd_save(self) -> bool:
            if not self.path:
                return self.cmd_save_as()
            try:
                save_project(self.song, self.path)
                add_recent(self.path)
                self.dirty = False
                self.root.title(f"{APP_NAME} - {self.song.title}")
                self.status(f"Saved {self.path}")
                autosave_path().unlink(missing_ok=True)
                return True
            except Exception as e:
                messagebox.showerror("Save failed", str(e), parent=self.root)
                return False

        def cmd_save_as(self) -> bool:
            p = filedialog.asksaveasfilename(parent=self.root, defaultextension=FILE_EXT, initialfile=_slug(self.song.title) + FILE_EXT,
                                             filetypes=[("8Bit project", "*.8bms"), ("8Bit text score", "*.8bt")])
            if not p:
                return False
            if self.song.title in ("Untitled", ""):
                self.song.title = Path(p).stem
            if Path(p).suffix == SCORE_EXT:
                save_project(self.song, p)
                add_recent(p)
                self.status(f"Saved score {p}")
                return True
            self.path = Path(p)
            return self.cmd_save()

        def cmd_export_audio(self, mode: str):
            s = self.song
            ext, types = ".wav", [("WAV audio", "*.wav")]
            if mode == "other":
                if not ffmpeg_available():
                    messagebox.showinfo("ffmpeg needed", "Install ffmpeg (on PATH) to export OGG/MP3/FLAC. WAV export always works.", parent=self.root)
                    return
                ext, types = ".ogg", [("OGG", "*.ogg"), ("MP3", "*.mp3"), ("FLAC", "*.flac")]
            p = filedialog.asksaveasfilename(parent=self.root, defaultextension=ext, filetypes=types,
                                             initialfile=_slug(s.title) + ("-loop" if mode in ("loop", "seamless") else "") + ext)
            if not p:
                return
            self.status("Rendering...")
            self.root.update_idletasks()
            try:
                a, b = s.loop_range() if mode in ("loop", "seamless") else (0, s.length_bars())
                data = render_song(s, a, b, seamless=mode == "seamless", tail=0 if mode == "seamless" else 2.0)
                export_audio(p, data)
                self.status(f"Exported {p} ({len(data) / SR:.1f}s)")
            except Exception as e:
                messagebox.showerror("Export failed", str(e), parent=self.root)

        def cmd_export_stems(self):
            d = filedialog.askdirectory(parent=self.root, title="Folder for stems")
            if not d:
                return
            try:
                res = op_render(self.song, str(Path(d) / (_slug(self.song.title) + "-mix.wav")), stems=d)
                self.status(f"Wrote {len(res['stems'])} stems + mix to {d}")
            except Exception as e:
                messagebox.showerror("Export failed", str(e), parent=self.root)

        def cmd_export_code(self, kind: str):
            ext = EXPORTERS[kind][0]
            p = filedialog.asksaveasfilename(parent=self.root, defaultextension=ext, initialfile=_slug(self.song.title) + ext)
            if not p:
                return
            try:
                export_code(self.song, kind, p)
                self.status(f"Saved {kind} code: {p}")
            except Exception as e:
                messagebox.showerror("Export failed", str(e), parent=self.root)

        def cmd_generate(self):
            w = tk.Toplevel(self.root, bg=THEME["panel"])
            w.title("Generate song")
            w.transient(self.root)
            sv, bv, seedv = tk.StringVar(value="mellow-space"), tk.IntVar(value=16), tk.StringVar(value="")
            for i, (lbl, wid) in enumerate((("Style", ttk.Combobox(w, textvariable=sv, values=style_names(), state="readonly")),
                                            ("Bars", ttk.Spinbox(w, from_=4, to=128, increment=4, textvariable=bv, width=6)),
                                            ("Seed (blank = random)", ttk.Entry(w, textvariable=seedv, width=10)))):
                ttk.Label(w, text=lbl).grid(row=i, column=0, sticky="w", padx=8, pady=4)
                wid.grid(row=i, column=1, sticky="w", padx=8, pady=4)

            def go():
                seed = int(seedv.get()) if seedv.get().strip().isdigit() else None
                old = self.song.to_dict()
                self.set_song(generate_song(sv.get(), int(bv.get()), seed), None)
                self.undo_stack.append(old)
                self.mark_dirty()
                w.destroy()
            ttk.Button(w, text="Generate", style="Accent.TButton", command=go).grid(row=3, column=0, columnspan=2, pady=8)

        def open_console(self):
            w = tk.Toplevel(self.root, bg=THEME["panel"])
            w.title("Score console - type notes, .8bt lines, /commands or plain English")
            out = tk.Text(w, height=16, width=96, bg=THEME["bg"], fg=THEME["text"], insertbackground=THEME["text"], font=("TkFixedFont", 10))
            out.pack(fill="both", expand=True, padx=4, pady=4)
            out.insert("end", HELP_TEXT + "\nExamples:  c4 e4 g4 c5/2   |   /gen boss 8   |   faster   |   [c4 e4 g4]/1\n")
            e = ttk.Entry(w)
            e.pack(fill="x", padx=4, pady=4)
            e.focus_set()

            def run(_ev=None):
                txt = e.get()
                e.delete(0, "end")
                it = Interpreter(self.song)
                it.track, it.pattern = self.cur_track, self.cur_pattern
                self.push_undo()
                try:
                    r = it.execute(txt)
                except Exception as ex:
                    r = f"error: {ex}"
                out.insert("end", f"> {txt}\n{r}\n")
                out.see("end")
                self.song = it.song
                self.cur_track = min(it.track, max(0, len(self.song.tracks) - 1))
                self.cur_pattern = it.pattern
                self.refresh_all()
            e.bind("<Return>", run)

        def text_window(self, title: str, text: str):
            w = tk.Toplevel(self.root, bg=THEME["panel"])
            w.title(title)
            t = tk.Text(w, width=104, height=34, bg=THEME["bg"], fg=THEME["text"], font=("TkFixedFont", 10), wrap="none")
            t.insert("1.0", text)
            t.configure(state="disabled")
            t.pack(fill="both", expand=True, padx=6, pady=6)
            ttk.Button(w, text="Close", command=w.destroy).pack(pady=4)

        def show_help(self):
            self.text_window("Keyboard shortcuts & help", SHORTCUTS + "\n" + HELP_TEXT)

        def autosave_tick(self):
            try:
                if self.dirty:
                    autosave_path().write_text(json.dumps({"path": str(self.path or ""), "song": self.song.to_dict()}))
            except Exception:
                pass
            finally:
                self.root.after(60000, self.autosave_tick)

        def quit(self):
            if not self.confirm_discard():
                return
            autosave_path().unlink(missing_ok=True)
            self.audio.close()
            if self.midi:
                self.midi.close()
            self.root.destroy()

    # ================================================================ piano roll
    class PianoRoll:
        LO, HI = 24, 108
        ROW = 12
        KEYW = 46

        def __init__(self, app: App, parent):
            T = THEME
            self.app = app
            self.zoom = 0.667
            self.last_len = PPQ // 4
            self.frame = tk.Frame(parent, bg=T["bg"])
            self.frame.grid_rowconfigure(1, weight=1)
            self.frame.grid_columnconfigure(1, weight=1)
            self.ruler = tk.Canvas(self.frame, height=18, bg=T["panel"], highlightthickness=0)
            self.keys = tk.Canvas(self.frame, width=self.KEYW, bg=T["panel"], highlightthickness=0)
            self.c = tk.Canvas(self.frame, bg=T["row_out"], highlightthickness=0, cursor="crosshair")
            self.vel = tk.Canvas(self.frame, height=50, bg=T["panel"], highlightthickness=0)
            self.hs = ttk.Scrollbar(self.frame, orient="horizontal", command=self.xview)
            self.vs = ttk.Scrollbar(self.frame, orient="vertical", command=self.yview)
            tk.Label(self.frame, text="vel", fg=T["dim"], bg=T["panel"]).grid(row=2, column=0, sticky="nsew")
            self.ruler.grid(row=0, column=1, sticky="ew")
            self.keys.grid(row=1, column=0, sticky="ns")
            self.c.grid(row=1, column=1, sticky="nsew")
            self.vs.grid(row=1, column=2, sticky="ns")
            self.vel.grid(row=2, column=1, sticky="ew")
            self.hs.grid(row=3, column=1, sticky="ew")
            self.c.configure(xscrollcommand=self.hs.set, yscrollcommand=self.vs.set)
            self.drag = None
            c = self.c
            c.bind("<ButtonPress-1>", self.press)
            c.bind("<B1-Motion>", self.motion)
            c.bind("<ButtonRelease-1>", self.release)
            c.bind("<ButtonPress-3>", self.right)
            c.bind("<Double-Button-1>", self.right)
            c.bind("<Motion>", self.hover)
            for w in (c, self.keys):
                w.bind("<MouseWheel>", self.wheel)
                w.bind("<Button-4>", lambda e: self.wheel(e, 120))
                w.bind("<Button-5>", lambda e: self.wheel(e, -120))
            self.keys.bind("<ButtonPress-1>", self.key_click)
            self.vel.bind("<ButtonPress-1>", lambda e: self.vel_set(e, True))
            self.vel.bind("<B1-Motion>", self.vel_set)
            self.ruler.bind("<ButtonPress-1>", self.ruler_click)
            self.frame.after(80, self.scroll_to_notes)

        def scroll_to_notes(self):
            p = self.app.pattern
            pitches = [n.pitch for n in p.notes if not n.inst] if p else []
            mid = (max(pitches) + min(pitches)) // 2 if pitches else 66
            self.yview("moveto", max(0.0, (self.HI - mid - 12) / (self.HI - self.LO + 1)))

        def xview(self, *a):
            self.c.xview(*a)
            self.ruler.xview(*a)
            self.vel.xview(*a)

        def yview(self, *a):
            self.c.yview(*a)
            self.keys.yview(*a)

        def wheel(self, e, delta=None):
            d = delta if delta is not None else e.delta
            if e.state & 0x4:
                self.zoom = max(0.15, min(3.0, self.zoom * (1.15 if d > 0 else 1 / 1.15)))
                self.redraw()
            elif e.state & 0x1:
                self.xview("scroll", -1 if d > 0 else 1, "units")
            else:
                self.yview("scroll", -2 if d > 0 else 2, "units")
            return "break"

        def y_of(self, pitch):
            return (self.HI - pitch) * self.ROW

        def pitch_at(self, y):
            return max(self.LO, min(self.HI, self.HI - int(self.c.canvasy(y) // self.ROW)))

        def tick_at(self, x):
            return max(0, int(self.c.canvasx(x) / self.zoom))

        @staticmethod
        def shown_pitch(n: Note) -> int:
            return n.pitch if not n.inst else 60

        def redraw(self):
            app, T, c = self.app, THEME, self.c
            p = app.pattern
            c.delete("all")
            self.keys.delete("all")
            self.ruler.delete("all")
            if p is None:
                return
            s = app.song
            tpb = s.ticks_per_bar
            total = p.bars * tpb
            W = max(int(total * self.zoom) + 1, 200)
            H = (self.HI - self.LO + 1) * self.ROW
            c.configure(scrollregion=(0, 0, W, H))
            self.keys.configure(scrollregion=(0, 0, self.KEYW, H))
            self.ruler.configure(scrollregion=(0, 0, W, 18))
            self.vel.configure(scrollregion=(0, 0, W, 50))
            root = key_root(s.key)
            for pitch in range(self.LO, self.HI + 1):
                y = self.y_of(pitch)
                c.create_rectangle(0, y, W, y + self.ROW, fill=T["row_in"] if in_scale(pitch, root, s.scale) else T["row_out"], width=0)
                black = (pitch % 12) in (1, 3, 6, 8, 10)
                self.keys.create_rectangle(0, y, self.KEYW, y + self.ROW, fill=T["black_key"] if black else T["white_key"], outline="#666")
                if pitch % 12 == 0:
                    self.keys.create_text(self.KEYW - 3, y + self.ROW / 2, text=note_name(pitch), anchor="e", font=("TkDefaultFont", 7), fill="#000")
                    c.create_line(0, y + self.ROW, W, y + self.ROW, fill=T["grid2"])
                if (pitch - root) % 12 == 0:
                    self.keys.create_rectangle(0, y, 4, y + self.ROW, fill=T["cyan"], width=0)
            snap = app.snap()
            beat = PPQ * 4 // s.time_sig[1]
            t = 0
            while t <= total:
                x = t * self.zoom
                col = "#55557a" if t % tpb == 0 else (T["grid2"] if t % beat == 0 else T["grid"])
                if t % tpb == 0:
                    self.ruler.create_text(x + 3, 9, text=str(t // tpb + 1), anchor="w", fill=T["text"], font=("TkDefaultFont", 8))
                c.create_line(x, 0, x, H, fill=col)
                t += snap
            selected = {id(n) for n in app.sel}
            color = KIND_COLORS.get(app.track.kind, T["accent"])
            for n in p.notes:
                y = self.y_of(self.shown_pitch(n))
                x0, x1 = n.start * self.zoom, n.end * self.zoom
                sel = id(n) in selected
                c.create_rectangle(x0 + 1, y + 1, max(x1 - 1, x0 + 3), y + self.ROW - 1, fill=_shade(color, 0.45 + 0.55 * n.velocity),
                                   outline="#ffffff" if sel else "#000", width=2 if sel else 1)
                if (x1 - x0) > 28:
                    c.create_text(x0 + 3, y + self.ROW / 2, text=n.inst or note_name(n.pitch), anchor="w", font=("TkDefaultFont", 7), fill="#000")
            c.create_rectangle(total * self.zoom, 0, W + 2000, H, fill="#0b0b12", width=0)
            self.draw_vel()
            self.draw_playhead(app.play_tick if app.playing else app.pos_tick)

        def draw_vel(self):
            v, app = self.vel, self.app
            v.delete("all")
            p = app.pattern
            if not p:
                return
            selected = {id(n) for n in app.sel}
            for n in p.notes:
                x = n.start * self.zoom
                h = 46 * n.velocity
                v.create_rectangle(x, 48 - h, x + 4, 48, fill=THEME["yellow"] if id(n) in selected else THEME["cyan"], width=0)

        def draw_playhead(self, tick):
            self.c.delete("ph")
            self.ruler.delete("ph")
            app = self.app
            p = app.pattern
            if not p:
                return
            if app.playing:
                t = app.pattern_tick_now()
                if t is None:
                    return
            else:
                t = tick % max(1, p.bars * app.song.ticks_per_bar)
            x = t * self.zoom
            self.c.create_line(x, 0, x, 99999, fill=THEME["playhead"], width=2, tags="ph")
            self.ruler.create_polygon(x - 5, 0, x + 5, 0, x, 8, fill=THEME["playhead"], tags="ph")
            if app.playing and app.v["follow"].get():
                x0, x1 = self.c.canvasx(0), self.c.canvasx(self.c.winfo_width())
                if x > x1 - 20 or x < x0:
                    W = float(str(self.c.cget("scrollregion")).split()[2] or 1)
                    self.xview("moveto", max(0.0, (x - 30) / max(W, 1.0)))

        def note_at(self, e) -> Tuple[Optional[Note], bool]:
            p = self.app.pattern
            if not p:
                return None, False
            t, pitch = self.tick_at(e.x), self.pitch_at(e.y)
            for n in reversed(p.notes):
                if self.shown_pitch(n) == pitch and n.start <= t < n.end:
                    return n, (n.end * self.zoom - self.c.canvasx(e.x)) < 6
            return None, False

        def hover(self, e):
            n, edge = self.note_at(e)
            self.c.configure(cursor="sb_h_double_arrow" if edge else ("fleur" if n else "crosshair"))
            self.app.pos_var.set(f"{note_name(self.pitch_at(e.y))}   tick {self.tick_at(e.x)}")

        def press(self, e):
            app = self.app
            p = app.pattern
            if not p:
                return
            self.c.focus_set()
            n, edge = self.note_at(e)
            tool = app.tool_var.get()
            snap = app.snap()
            t = (self.tick_at(e.x) // snap) * snap
            pitch = self.pitch_at(e.y)
            if tool == "erase":
                app.push_undo()
                if n:
                    p.notes.remove(n)
                    app.sel = [x for x in app.sel if x is not n]
                    self.redraw()
                    app.schedule_rerender()
                self.drag = ("erase",)
                return
            if n:
                app.push_undo()
                if e.state & 0x1:
                    app.sel = [x for x in app.sel if x is not n] if n in app.sel else app.sel + [n]
                elif n not in app.sel:
                    app.sel = [n]
                app.preview(n.pitch, n.inst, n.velocity)
                orig = [(x, x.start, x.pitch, x.length) for x in app.sel]
                self.drag = ("resize" if edge else "move", self.tick_at(e.x), pitch, orig)
                self.redraw()
                return
            if tool == "select" or (e.state & 0x4):
                self.drag = ("box", self.c.canvasx(e.x), self.c.canvasy(e.y))
                if not e.state & 0x1:
                    app.sel = []
                self.redraw()
                return
            if app.track.drum:
                app.status("Drum tracks are easiest in the Drum Sequencer tab (notes here use the 'kick' row)")
            if app.v["snapscale"].get():
                pitch = snap_to_scale(pitch, key_root(app.song.key), app.song.scale)
            app.push_undo()
            if tool == "chord":
                new = chord_stamp(pitch, app.chord_var.get(), t, max(snap, PPQ), app.song, app.v["diatonic"].get())
                for x in new:
                    app.preview(x.pitch)
            else:
                new = [Note(t, self.last_len, pitch, 0.8, "kick" if app.track.drum else None)]
                app.preview(pitch)
            app.add_notes(new)
            app.sel = new
            self.drag = ("resize", self.tick_at(e.x), pitch, [(x, x.start, x.pitch, x.length) for x in new])
            self.redraw()

        def motion(self, e):
            if not self.drag:
                return
            app = self.app
            snap = app.snap()
            kind = self.drag[0]
            if kind == "erase":
                n, _ = self.note_at(e)
                if n:
                    app.pattern.notes.remove(n)
                    self.redraw()
                return
            if kind == "box":
                self.c.delete("box")
                self.c.create_rectangle(self.drag[1], self.drag[2], self.c.canvasx(e.x), self.c.canvasy(e.y), outline=THEME["cyan"], dash=(3, 2), tags="box")
                return
            _, t0, p0, orig = self.drag
            dt = int(round((self.tick_at(e.x) - t0) / snap)) * snap
            if kind == "move":
                dp = self.pitch_at(e.y) - p0
                for n, st, pi, ln in orig:
                    n.start = max(0, st + dt)
                    if not n.inst:
                        newp = max(0, min(127, pi + dp))
                        if n.pitch != newp and len(orig) == 1:
                            app.preview(newp)
                        n.pitch = newp
            else:
                for n, st, pi, ln in orig:
                    n.length = max(snap, ln + dt)
                if orig:
                    self.last_len = orig[0][0].length
            self.redraw()

        def release(self, e):
            app = self.app
            if self.drag and self.drag[0] == "box":
                x0, y0 = self.drag[1], self.drag[2]
                x1, y1 = self.c.canvasx(e.x), self.c.canvasy(e.y)
                t0, t1 = sorted((x0 / self.zoom, x1 / self.zoom))
                pa, pb = sorted((self.HI - int(y0 // self.ROW), self.HI - int(y1 // self.ROW)))
                ids = {id(n) for n in app.sel}
                app.sel += [n for n in app.pattern.notes if n.end > t0 and n.start < t1 and pa <= self.shown_pitch(n) <= pb and id(n) not in ids]
                self.c.delete("box")
                app.status(f"{len(app.sel)} notes selected")
                self.redraw()
            elif self.drag:
                app.schedule_rerender()
            self.drag = None

        def right(self, e):
            n, _ = self.note_at(e)
            if n:
                self.app.push_undo()
                self.app.pattern.notes.remove(n)
                self.app.sel = [x for x in self.app.sel if x is not n]
                self.redraw()
                self.app.schedule_rerender()
            return "break"

        def key_click(self, e):
            self.app.preview(self.HI - int(self.keys.canvasy(e.y) // self.ROW))

        def vel_set(self, e, first=False):
            app = self.app
            p = app.pattern
            if not p or not p.notes:
                return
            x = self.vel.canvasx(e.x)
            t = x / self.zoom
            v = max(0.05, min(1.0, (48 - e.y) / 46))
            cands = app.sel if app.sel else p.notes
            near = min(cands, key=lambda n: abs(n.start - t))
            if abs(near.start * self.zoom - x) > 12:
                return
            if first:
                app.push_undo()
            for n in cands:
                if n.start == near.start:
                    n.velocity = round(v, 3)
            self.redraw()
            app.schedule_rerender()

        def ruler_click(self, e):
            app = self.app
            t = int(self.ruler.canvasx(e.x) / self.zoom)
            base = next((c.bar * app.song.ticks_per_bar for c in app.song.arrangement if c.track == app.cur_track and c.pattern == app.cur_pattern), 0)
            app.pos_tick = base + t
            if app.playing:
                app.audio.stop()
                app.play(app.pos_tick)
            app.refresh_playheads()

    # ================================================================ drum step sequencer
    class DrumGrid:
        CW, CH, LW = 22, 26, 70

        def __init__(self, app: App, parent):
            T = THEME
            self.app = app
            self.frame = tk.Frame(parent, bg=T["bg"])
            top = tk.Frame(self.frame, bg=T["panel"])
            top.pack(fill="x")
            self.info = ttk.Label(top, text="", style="Head.TLabel")
            self.info.pack(side="left", padx=6, pady=3)
            ttk.Label(top, text="Click = hit, right-click = accent / ghost / off, drag = paint, click a row name = listen").pack(side="left", padx=6)
            self.c = tk.Canvas(self.frame, bg=T["bg"], highlightthickness=0)
            hs = ttk.Scrollbar(self.frame, orient="horizontal", command=self.c.xview)
            self.c.configure(xscrollcommand=hs.set)
            hs.pack(side="bottom", fill="x")
            self.c.pack(fill="both", expand=True)
            self.c.bind("<ButtonPress-1>", self.press)
            self.c.bind("<B1-Motion>", self.paint)
            self.c.bind("<ButtonRelease-1>", lambda e: setattr(self, "paint_val", None))
            self.c.bind("<ButtonPress-3>", self.cycle)
            self.paint_val: Optional[bool] = None

        def rows(self) -> List[str]:
            p = self.app.pattern
            extra = sorted({n.inst for n in (p.notes if p else []) if n.inst and n.inst not in DRUM_ROWS})
            return DRUM_ROWS + extra

        def cell(self, e) -> Tuple[Optional[str], Optional[int]]:
            x, y = self.c.canvasx(e.x), self.c.canvasy(e.y)
            r = int((y - 20) // self.CH)
            rows = self.rows()
            if not (0 <= r < len(rows)) or y < 20:
                return None, None
            if x < self.LW:
                return rows[r], None
            return rows[r], int((x - self.LW) // self.CW)

        def redraw(self):
            app, T, c = self.app, THEME, self.c
            c.delete("all")
            t, p = app.track, app.pattern
            if not t or not p:
                return
            if not t.drum:
                self.info.configure(text=f"'{t.name}' is not a drum track")
                c.create_text(20, 30, anchor="w", text="Select a drum track in the mixer (or tick 'drum' on this track) to use the step sequencer.", fill=T["dim"])
                return
            self.info.configure(text=f"{t.name} . pattern {p.name}")
            step = PPQ // 4
            steps = p.bars * app.song.ticks_per_bar // step
            per_bar = app.song.ticks_per_bar // step
            hits = {(n.inst, n.start // step): n for n in p.notes if n.start % step == 0}
            beat_steps = max(1, (PPQ * 4 // app.song.time_sig[1]) // step)
            for ci in range(0, steps, per_bar):
                c.create_text(self.LW + ci * self.CW + 4, 10, text=f"bar {ci // per_bar + 1}", anchor="w", fill=T["dim"], font=("TkDefaultFont", 8))
            for ri, row in enumerate(self.rows()):
                y = 20 + ri * self.CH
                c.create_rectangle(0, y, self.LW - 4, y + self.CH - 3, fill=T["panel2"], width=0)
                c.create_text(6, y + self.CH / 2 - 1, text=row, anchor="w", fill=T["text"])
                for ci in range(steps):
                    x = self.LW + ci * self.CW
                    n = hits.get((row, ci))
                    base = T["panel2"] if (ci // beat_steps) % 2 == 0 else T["panel"]
                    fill = base if not n else (T["accent"] if n.velocity >= 0.95 else (T["green"] if n.velocity >= 0.6 else "#3f7f45"))
                    c.create_rectangle(x + 1, y, x + self.CW - 2, y + self.CH - 3, fill=fill, outline=T["grid2"])
            c.configure(scrollregion=(0, 0, self.LW + steps * self.CW + 10, 20 + len(self.rows()) * self.CH))
            self.draw_playhead(app.play_tick if app.playing else app.pos_tick)

        def draw_playhead(self, tick):
            self.c.delete("ph")
            app = self.app
            if not app.playing or not app.track or not app.track.drum or not app.pattern:
                return
            pt = app.pattern_tick_now()
            if pt is None:
                return
            x = self.LW + pt / (PPQ // 4) * self.CW
            self.c.create_line(x, 14, x, 20 + len(self.rows()) * self.CH, fill=THEME["playhead"], width=2, tags="ph")

        def toggle(self, row: str, col: int, on: Optional[bool] = None, vel: float = 0.8) -> bool:
            app = self.app
            p = app.pattern
            step = PPQ // 4
            if col * step >= p.bars * app.song.ticks_per_bar:
                return False
            ex = [n for n in p.notes if n.inst == row and n.start == col * step]
            want = (not ex) if on is None else on
            if ex and not want:
                p.notes = [n for n in p.notes if not (n.inst == row and n.start == col * step)]
            elif want and not ex:
                p.notes.append(Note(col * step, step, 60, vel, row))
                app.preview(60, row, vel)
            app.ensure_arranged()
            self.redraw()
            app.schedule_rerender()
            return want

        def press(self, e):
            row, col = self.cell(e)
            if row is None:
                return
            if col is None:
                self.app.preview(60, row)
                return
            if not self.app.track.drum:
                return
            self.app.push_undo()
            self.paint_val = self.toggle(row, col)

        def paint(self, e):
            row, col = self.cell(e)
            if row is None or col is None or self.paint_val is None:
                return
            has = any(n.inst == row and n.start == col * (PPQ // 4) for n in self.app.pattern.notes)
            if has != self.paint_val:
                self.toggle(row, col, self.paint_val)

        def cycle(self, e):
            row, col = self.cell(e)
            if row is None or col is None or not self.app.track.drum:
                return
            p = self.app.pattern
            step = PPQ // 4
            ex = [n for n in p.notes if n.inst == row and n.start == col * step]
            self.app.push_undo()
            if not ex:
                self.toggle(row, col, True, 1.0)
                return
            n = ex[0]
            if n.velocity >= 0.95:
                n.velocity = 0.45
            elif n.velocity < 0.6:
                self.toggle(row, col, False)
                return
            else:
                n.velocity = 1.0
            self.redraw()
            self.app.schedule_rerender()

    # ================================================================ arrangement
    class Arranger:
        HW, RH, BW, RUL = 110, 30, 44, 22

        def __init__(self, app: App, parent):
            T = THEME
            self.app = app
            self.frame = tk.Frame(parent, bg=T["bg"])
            left = tk.Frame(self.frame, bg=T["panel"])
            left.pack(side="left", fill="y")
            ttk.Label(left, text="PATTERNS", style="Head.TLabel").pack(anchor="w", padx=4, pady=(4, 0))
            ttk.Label(left, text="drag onto timeline", style="Status.TLabel").pack(anchor="w", padx=4)
            self.lb = tk.Listbox(left, width=14, bg=T["panel2"], fg=T["text"], selectbackground=T["accent"], highlightthickness=0, bd=0, exportselection=False)
            self.lb.pack(fill="y", expand=True, padx=4, pady=4)
            self.lb.bind("<ButtonPress-1>", self.lb_press)
            self.lb.bind("<B1-Motion>", self.lb_drag)
            self.lb.bind("<ButtonRelease-1>", self.lb_drop)
            ToolTip(self.lb, "Patterns of the selected track. Drag one onto any track row in the timeline.")
            self.c = tk.Canvas(self.frame, bg=T["bg"], highlightthickness=0)
            hs = ttk.Scrollbar(self.frame, orient="horizontal", command=self.c.xview)
            vs = ttk.Scrollbar(self.frame, orient="vertical", command=self.c.yview)
            self.c.configure(xscrollcommand=hs.set, yscrollcommand=vs.set)
            hs.pack(side="bottom", fill="x")
            vs.pack(side="right", fill="y")
            self.c.pack(fill="both", expand=True)
            self.c.bind("<ButtonPress-1>", self.press)
            self.c.bind("<B1-Motion>", self.motion)
            self.c.bind("<ButtonRelease-1>", self.release)
            self.c.bind("<ButtonPress-3>", self.right)
            self.c.bind("<Double-Button-1>", self.double)
            self.drag = None
            self.lb_item: Optional[Tuple[int, str]] = None

        def bars_shown(self) -> int:
            return max(self.app.song.length_bars() + 8, 32)

        def redraw(self):
            app, T, c = self.app, THEME, self.c
            s = app.song
            c.delete("all")
            nb = self.bars_shown()
            W = self.HW + nb * self.BW
            H = self.RUL + len(s.tracks) * self.RH + 4
            c.configure(scrollregion=(0, 0, W, H))
            c.create_rectangle(0, 0, W, self.RUL, fill=T["panel"], width=0)
            if s.loop_end > s.loop_start:
                a, b = s.loop_start, s.loop_end
                c.create_rectangle(self.HW + a * self.BW, 2, self.HW + b * self.BW, self.RUL - 2, fill="#1d4a55", outline=T["loop"])
                c.create_text(self.HW + a * self.BW + 4, self.RUL / 2, text="LOOP", anchor="w", fill=T["loop"], font=("TkDefaultFont", 7, "bold"))
            for bar in range(nb):
                x = self.HW + bar * self.BW
                c.create_line(x, self.RUL - 6, x, H, fill=T["grid"])
                c.create_text(x + self.BW - 4, self.RUL / 2, text=str(bar + 1), anchor="e", fill=T["dim"], font=("TkDefaultFont", 8))
            for ti, t in enumerate(s.tracks):
                y = self.RUL + ti * self.RH
                c.create_rectangle(0, y, self.HW - 2, y + self.RH - 2, fill=T["panel2"] if ti == app.cur_track else T["panel"], width=0)
                c.create_rectangle(0, y, 4, y + self.RH - 2, fill=KIND_COLORS.get(t.kind, "#888"), width=0)
                c.create_text(10, y + self.RH / 2, text=t.name + (" (M)" if t.mute else "") + (" (S)" if t.solo else ""), anchor="w", fill=T["text"])
                c.create_line(self.HW, y + self.RH - 1, W, y + self.RH - 1, fill=T["grid"])
            for cl in s.arrangement:
                p = s.pattern_of(cl)
                if not p or cl.track >= len(s.tracks):
                    continue
                y = self.RUL + cl.track * self.RH
                x0 = self.HW + cl.bar * self.BW
                x1 = x0 + p.bars * self.BW
                col = KIND_COLORS.get(s.tracks[cl.track].kind, T["accent"])
                cur = cl.track == app.cur_track and cl.pattern == app.cur_pattern
                c.create_rectangle(x0 + 1, y + 2, x1 - 1, y + self.RH - 4, fill=_shade(col, 0.55), outline="#ffffff" if cur else col, width=2 if cur else 1)
                c.create_text(x0 + 5, y + self.RH / 2 - 1, text=cl.pattern, anchor="w", fill="#000", font=("TkDefaultFont", 9, "bold"))
                tone = [n for n in p.notes if not n.inst] or p.notes
                if tone:
                    lo, hi = min(n.pitch for n in tone), max(n.pitch for n in tone)
                    span, plen = max(hi - lo, 1), p.bars * s.ticks_per_bar
                    for n in tone[:300]:
                        nx = x0 + 16 + n.start / plen * (x1 - x0 - 18)
                        ny = y + self.RH - 7 - (n.pitch - lo) / span * (self.RH - 12)
                        c.create_line(nx, ny, nx + max(1.0, n.length / plen * (x1 - x0 - 18)), ny, fill="#111")
            self.lb.delete(0, "end")
            if app.track:
                for name, p in app.track.patterns.items():
                    self.lb.insert("end", f"{name}  ({p.bars} bar{'s' if p.bars > 1 else ''})")
            self.draw_playhead(app.play_tick if app.playing else app.pos_tick)

        def draw_playhead(self, tick):
            c = self.c
            c.delete("ph")
            x = self.HW + tick / self.app.song.ticks_per_bar * self.BW
            c.create_line(x, 0, x, 4000, fill=THEME["playhead"], width=2, tags="ph")
            if self.app.playing and self.app.v["follow"].get():
                x0, x1 = c.canvasx(0), c.canvasx(c.winfo_width())
                if x > x1 - 10 or x < x0 + self.HW:
                    c.xview("moveto", max(0.0, (x - self.HW - 20) / (self.HW + self.bars_shown() * self.BW)))

        def hit(self, e):
            x, y = self.c.canvasx(e.x), self.c.canvasy(e.y)
            s = self.app.song
            if y < self.RUL:
                return ("ruler", max(0, int((x - self.HW) // self.BW)))
            ti = int((y - self.RUL) // self.RH)
            bar = int((x - self.HW) // self.BW)
            if not (0 <= ti < len(s.tracks)):
                return None
            if x < self.HW:
                return ("head", ti)
            for cl in reversed(s.arrangement):
                p = s.pattern_of(cl)
                if cl.track == ti and p and cl.bar <= bar < cl.bar + p.bars:
                    return ("clip", cl, bar)
            return ("empty", ti, max(0, bar))

        def press(self, e):
            h = self.hit(e)
            app = self.app
            self.drag = None
            if not h:
                return
            if h[0] == "ruler":
                self.drag = ("ruler", h[1], h[1])
            elif h[0] == "head":
                app.select_track(h[1])
            elif h[0] == "clip":
                cl = h[1]
                if cl.track != app.cur_track:
                    app.select_track(cl.track)
                app.select_pattern(cl.pattern)
                app.push_undo()
                self.drag = ("clip", cl, h[2], cl.bar)
            elif h[0] == "empty":
                if h[1] != app.cur_track:
                    app.select_track(h[1])
                elif e.state & 0x4 and app.pattern:
                    app.push_undo()
                    app.song.arrangement.append(Clip(h[1], app.cur_pattern, h[2]))
                    self.redraw()
                    app.schedule_rerender()

        def motion(self, e):
            if not self.drag:
                return
            app = self.app
            bar = max(0, int((self.c.canvasx(e.x) - self.HW) // self.BW))
            if self.drag[0] == "ruler":
                self.drag = ("ruler", self.drag[1], bar)
                a, b = sorted((self.drag[1], bar))
                if b > a:
                    app.song.loop_start, app.song.loop_end = a, b + 1
                    self.redraw()
            elif self.drag[0] == "clip":
                _, cl, grab, bar0 = self.drag
                cl.bar = max(0, bar0 + bar - grab)
                ti = int((self.c.canvasy(e.y) - self.RUL) // self.RH)
                if 0 <= ti < len(app.song.tracks) and cl.pattern in app.song.tracks[ti].patterns:
                    cl.track = ti
                self.redraw()

        def release(self, e):
            app = self.app
            if self.drag and self.drag[0] == "ruler":
                if self.drag[1] == self.drag[2]:
                    app.pos_tick = self.drag[1] * app.song.ticks_per_bar
                    if app.playing:
                        app.audio.stop()
                        app.play(app.pos_tick)
                    app.refresh_playheads()
                else:
                    app.v["loop"].set(True)
                    app.mark_dirty()
                    a, b = app.song.loop_range()
                    app.status(f"Loop set to bars {a + 1}-{b} (loop playback on)")
                    if app.playing:
                        app.schedule_rerender()
            elif self.drag and self.drag[0] == "clip":
                app.cur_track = self.drag[1].track
                app.build_mixer()
                app.schedule_rerender()
            self.drag = None

        def right(self, e):
            h = self.hit(e)
            app = self.app
            if not h:
                return
            if h[0] == "clip":
                app.push_undo()
                app.song.arrangement.remove(h[1])
                self.redraw()
                app.schedule_rerender()
            elif h[0] == "ruler":
                app.push_undo()
                app.song.loop_start = app.song.loop_end = 0
                self.redraw()
                app.status("Loop region cleared (loops whole song)")

        def double(self, e):
            h = self.hit(e)
            if h and h[0] == "clip":
                app = self.app
                app.select_track(h[1].track)
                app.select_pattern(h[1].pattern)
                app.nb.select(1 if app.track.drum else 0)

        def lb_press(self, e):
            i = self.lb.nearest(e.y)
            t = self.app.track
            if t and 0 <= i < len(t.patterns):
                name = list(t.patterns)[i]
                self.lb_item = (self.app.cur_track, name)
                self.app.select_pattern(name)
                self.lb.selection_clear(0, "end")
                self.lb.selection_set(i)

        def lb_drag(self, e):
            if self.lb_item:
                self.lb.configure(cursor="hand2")

        def lb_drop(self, e):
            self.lb.configure(cursor="")
            item, self.lb_item = self.lb_item, None
            if not item:
                return
            x, y = e.x_root - self.c.winfo_rootx(), e.y_root - self.c.winfo_rooty()
            if not (0 <= x <= self.c.winfo_width() and 0 <= y <= self.c.winfo_height()):
                return
            self.drop_pattern(item[0], item[1], self.c.canvasx(x), self.c.canvasy(y))

        def drop_pattern(self, src_track: int, pname: str, cx: float, cy: float) -> bool:
            app, s = self.app, self.app.song
            ti = int((cy - self.RUL) // self.RH)
            bar = max(0, int((cx - self.HW) // self.BW))
            if not (0 <= ti < len(s.tracks)):
                return False
            app.push_undo()
            if pname not in s.tracks[ti].patterns:
                src = s.tracks[src_track].patterns[pname]
                s.tracks[ti].patterns[pname] = Pattern(pname, src.bars, [Note.from_dict(n.to_dict()) for n in src.notes])
            s.arrangement.append(Clip(ti, pname, bar))
            self.redraw()
            app.status(f"Placed pattern {pname} on {s.tracks[ti].name} at bar {bar + 1}")
            app.schedule_rerender()
            return True

    # ================================================================ on-screen piano
    class KeyboardWidget:
        def __init__(self, app: App, parent):
            self.app = app
            self.frame = tk.Frame(parent, bg=THEME["bg"])
            side = tk.Frame(self.frame, bg=THEME["bg"])
            side.pack(side="left", fill="y")
            ttk.Button(side, text="Oct +", width=5, command=lambda: self.shift(1)).pack(padx=2, pady=2)
            self.olbl = ttk.Label(side, text="", style="Status.TLabel")
            self.olbl.pack()
            ttk.Button(side, text="Oct -", width=5, command=lambda: self.shift(-1)).pack(padx=2, pady=2)
            self.c = tk.Canvas(self.frame, height=80, bg=THEME["bg"], highlightthickness=0)
            self.c.pack(side="left", fill="both", expand=True)
            self.c.bind("<Configure>", lambda e: self.redraw())
            self.c.bind("<ButtonPress-1>", self.press)
            self.c.bind("<B1-Motion>", self.glide)
            self.c.bind("<ButtonRelease-1>", self.release)
            self.down: Optional[int] = None
            self.lit: set = set()

        def shift(self, d):
            self.app.octave.set(max(0, min(8, self.app.octave.get() + d)))
            self.redraw()
            self.app.status(f"Keyboard octave: C{self.app.octave.get()}")

        def layout(self):
            w = max(self.c.winfo_width(), 300)
            h = max(self.c.winfo_height(), 60) - 2
            base = self.app.octave.get() * 12  # one octave below the computer-key base
            whites = [p for p in range(base, base + 36) if (p % 12) not in (1, 3, 6, 8, 10)]
            ww = w / len(whites)
            keys = [(p, i * ww, 0, (i + 1) * ww, h, False) for i, p in enumerate(whites)]
            for i, p in enumerate(whites):
                if (p + 1) % 12 in (1, 3, 6, 8, 10) and p + 1 < base + 36:
                    keys.append((p + 1, (i + 1) * ww - ww * 0.3, 0, (i + 1) * ww + ww * 0.3, h * 0.6, True))
            return keys

        def redraw(self):
            c = self.c
            c.delete("all")
            self.olbl.configure(text=f"C{self.app.octave.get()}")
            kb_base = (self.app.octave.get() + 1) * 12
            show = self.app.v["keys"].get()
            for p, x0, y0, x1, y1, black in self.layout():
                lit = p in self.lit
                c.create_rectangle(x0, y0, x1, y1, fill=(THEME["accent"] if lit else ("#22223a" if black else "#e4e4f0")), outline="#555")
                if not black and p % 12 == 0:
                    c.create_text((x0 + x1) / 2, y1 - 8, text=note_name(p), font=("TkDefaultFont", 7), fill="#333")
                hint = None
                if 0 <= p - kb_base < len(KEYS_LOWER):
                    hint = KEYS_LOWER[p - kb_base]
                elif 0 <= p - kb_base - 12 < len(KEYS_UPPER):
                    hint = KEYS_UPPER[p - kb_base - 12]
                if hint and show:
                    c.create_text((x0 + x1) / 2, (y1 - 22) if not black else (y1 - 8), text=hint.upper(), font=("TkDefaultFont", 7, "bold"),
                                  fill="#c0306e" if not black else THEME["yellow"])

        def key_at(self, x, y):
            whites = None
            for p, x0, y0, x1, y1, black in self.layout():
                if x0 <= x <= x1 and y0 <= y <= y1:
                    if black:
                        return p
                    whites = p
            return whites

        def press(self, e):
            p = self.key_at(e.x, e.y)
            if p is not None:
                self.down = p
                self.app.note_on(p)

        def glide(self, e):
            p = self.key_at(e.x, e.y)
            if p is not None and p != self.down:
                if self.down is not None:
                    self.app.note_off(self.down)
                self.down = p
                self.app.note_on(p)

        def release(self, e):
            if self.down is not None:
                self.app.note_off(self.down)
                self.down = None

        def highlight(self, p, on):
            (self.lit.add if on else self.lit.discard)(p)
            self.redraw()

    # ================================================================ instrument editor
    class InstrumentEditor:
        FIELDS = [("wave", "choice", WAVE_TYPES), ("duty", "choice", ["0.125", "0.25", "0.5", "0.75"]), ("noise_mode", "choice", ["long", "short"]),
                  ("volume", 0.0, 1.0), ("attack", 0.0, 1.0), ("decay", 0.0, 1.5), ("sustain", 0.0, 1.0), ("release", 0.0, 2.0),
                  ("vib_depth", 0.0, 2.0), ("vib_rate", 0.0, 15.0), ("vib_delay", 0.0, 1.0), ("arp", "text", None), ("arp_speed", 1.0, 60.0),
                  ("slide", -48.0, 48.0), ("slide_time", 0.01, 1.0), ("duty_sweep", -2.0, 2.0), ("noise_rate", 0.25, 4.0),
                  ("fixed_note", "text", None), ("transpose", -24.0, 24.0)]
        TIPS = {"wave": "Waveform: pulse (NES square), triangle, saw, sine, noise (LFSR) or a plugin wave",
                "duty": "Pulse width: 12.5% thin, 25% classic, 50% square, 75% = 25% inverted",
                "noise_mode": "long = hiss, short = metallic buzz (NES 93-step mode)",
                "vib_depth": "Vibrato depth in semitones", "vib_rate": "Vibrato speed in Hz", "vib_delay": "Seconds before vibrato starts",
                "arp": "Arpeggio: semitone offsets cycled fast, e.g. 0,4,7", "arp_speed": "Arpeggio steps per second",
                "slide": "Pitch slide in semitones (+ up, - down) during slide time", "duty_sweep": "Pulse width change per second",
                "noise_rate": "Noise clock multiplier", "fixed_note": "Always play this note (drums), e.g. 60 or C4; blank = played pitch",
                "transpose": "Shift by semitones"}

        def __init__(self, app: App, parent):
            T = THEME
            self.app = app
            self.frame = tk.Frame(parent, bg=T["panel"])
            left = tk.Frame(self.frame, bg=T["panel"])
            left.pack(side="left", fill="y", padx=4, pady=4)
            ttk.Label(left, text="INSTRUMENTS  (* = in song)", style="Head.TLabel").pack(anchor="w")
            row = tk.Frame(left, bg=T["panel"])
            row.pack(fill="both", expand=True)
            self.lb = tk.Listbox(row, width=20, bg=T["panel2"], fg=T["text"], selectbackground=T["accent"], highlightthickness=0, bd=0, exportselection=False)
            self.lb.pack(side="left", fill="y", expand=True)
            self.lb.bind("<<ListboxSelect>>", lambda e: self.on_pick())
            bf = tk.Frame(row, bg=T["panel"])
            bf.pack(side="left", fill="y", padx=4)
            for txt, cmd, tip in (("Preview", self.preview, "Play C4 with this instrument"), ("New", self.new, "New instrument copied from the selected one"),
                                  ("Use", self.assign, "Use on the current track"), ("Save", self.save_lib, "Save to your instrument library (~/.8bms/instruments)"),
                                  ("Load", self.load_file, "Load an instrument .json"), ("Export", self.export_file, "Export as .json")):
                b = ttk.Button(bf, text=txt, command=cmd, width=8)
                b.pack(side="top", fill="x", pady=1)
                ToolTip(b, tip)
            form = tk.Frame(self.frame, bg=T["panel"])
            form.pack(side="left", fill="both", expand=True, padx=8, pady=4)
            self.title = ttk.Label(form, text="", style="Head.TLabel")
            self.title.grid(row=0, column=0, columnspan=6, sticky="w")
            self.vars: Dict[str, tk.Variable] = {}
            self.cur: Optional[str] = None
            self.loading = False
            for i, f in enumerate(self.FIELDS):
                name = f[0]
                r, col = 1 + i % 10, (i // 10) * 3
                lbl = ttk.Label(form, text=name.replace("_", " "))
                lbl.grid(row=r, column=col, sticky="w", padx=(8, 4), pady=2)
                if name in self.TIPS:
                    ToolTip(lbl, self.TIPS[name])
                if f[1] == "choice":
                    v = tk.StringVar()
                    w = ttk.Combobox(form, textvariable=v, values=f[2], width=9, state="readonly")
                    w.bind("<<ComboboxSelected>>", lambda e, n=name: self.on_change(n))
                elif f[1] == "text":
                    v = tk.StringVar()
                    w = ttk.Entry(form, textvariable=v, width=12)
                    w.bind("<Return>", lambda e, n=name: self.on_change(n))
                    w.bind("<FocusOut>", lambda e, n=name: self.on_change(n))
                else:
                    v = tk.DoubleVar()
                    w = ttk.Scale(form, from_=f[1], to=f[2], variable=v, length=150, command=lambda e, n=name: self.on_change(n))
                    w.bind("<ButtonRelease-1>", lambda e: self.preview())
                    vl = ttk.Label(form, text="", width=6)
                    vl.grid(row=r, column=col + 2, sticky="w")
                    v.trace_add("write", lambda *a, v=v, vl=vl: vl.configure(text=f"{v.get():.3g}"))
                w.grid(row=r, column=col + 1, sticky="w", pady=2)
                self.vars[name] = v

        def names(self) -> List[str]:
            return list(self.app.song.instruments) + [n for n in PRESETS if n not in self.app.song.instruments]

        def refresh_list(self):
            self.lb.delete(0, "end")
            for n in self.names():
                self.lb.insert("end", ("* " if n in self.app.song.instruments else "  ") + n)
            if self.app.track:
                self.select(self.app.track.instrument)

        def select(self, name: str):
            ns = self.names()
            if name in ns:
                i = ns.index(name)
                self.lb.selection_clear(0, "end")
                self.lb.selection_set(i)
                self.lb.see(i)
                self.load(name)

        def on_pick(self):
            sel = self.lb.curselection()
            if sel:
                self.load(self.names()[sel[0]])

        def load(self, name: str):
            self.cur = name
            inst = self.app.song.get_instrument(name)
            self.title.configure(text=f"{name}   " + ("(song instrument)" if name in self.app.song.instruments else "(preset - editing makes a song copy)"))
            self.loading = True
            for f in self.FIELDS:
                v = getattr(inst, f[0])
                if f[0] == "arp":
                    self.vars["arp"].set(",".join(map(str, v)))
                elif f[0] == "fixed_note":
                    self.vars["fixed_note"].set("" if v is None else str(v))
                elif f[1] == "choice":
                    self.vars[f[0]].set(str(v))
                else:
                    self.vars[f[0]].set(float(v))
            self.loading = False

        def on_change(self, name: str):
            if self.loading or not self.cur:
                return
            app, s = self.app, self.app.song
            if self.cur not in s.instruments:
                app.push_undo()
                s.instruments[self.cur] = copy.deepcopy(s.get_instrument(self.cur))
                cur = self.cur
                self.refresh_list()
                self.select(cur)
            inst = s.instruments[self.cur]
            v = self.vars[name].get()
            try:
                if name == "arp":
                    inst.arp = [int(x) for x in re.split(r"[,\s]+", str(v)) if x.strip()]
                elif name == "fixed_note":
                    sv = str(v).strip()
                    inst.fixed_note = None if not sv else (int(sv) if sv.lstrip("-").isdigit() else parse_note_name(sv))
                elif name in ("wave", "noise_mode"):
                    setattr(inst, name, str(v))
                elif name == "duty":
                    inst.duty = float(v)
                elif name == "transpose":
                    inst.transpose = int(round(float(v)))
                else:
                    setattr(inst, name, round(float(v), 4))
            except ValueError as e:
                app.status(f"Bad value: {e}")
                return
            app.mark_dirty()
            app.schedule_rerender()

        def preview(self):
            if self.cur:
                self.app.audio.preview(render_note_preview(self.app.song.get_instrument(self.cur), 60, 0.4))

        def new(self):
            base = self.cur or "lead"
            name = simpledialog.askstring("New instrument", "Name:", initialvalue=f"{base}2", parent=self.app.root)
            if not name:
                return
            self.app.push_undo()
            inst = copy.deepcopy(self.app.song.get_instrument(base))
            inst.name = name
            self.app.song.instruments[name] = inst
            self.refresh_list()
            self.select(name)

        def assign(self):
            if self.cur and self.app.track:
                self.app.push_undo()
                self.app.track.instrument = self.cur
                self.app.build_mixer()
                self.app.schedule_rerender()
                self.app.status(f"{self.app.track.name} now uses '{self.cur}'")

        def save_lib(self):
            if self.cur:
                self.app.status(f"Saved instrument to {save_instrument(self.app.song.get_instrument(self.cur))}")

        def load_file(self):
            p = filedialog.askopenfilename(parent=self.app.root, filetypes=[("Instrument", "*.json")], initialdir=str(user_instrument_dir()))
            if p:
                try:
                    inst = load_instrument(Path(p))
                    self.app.push_undo()
                    self.app.song.instruments[inst.name] = inst
                    self.refresh_list()
                    self.select(inst.name)
                except Exception as e:
                    messagebox.showerror("Load failed", str(e), parent=self.app.root)

        def export_file(self):
            if self.cur:
                p = filedialog.asksaveasfilename(parent=self.app.root, defaultextension=".json", initialfile=f"{self.cur}.json")
                if p:
                    save_instrument(self.app.song.get_instrument(self.cur), Path(p))
                    self.app.status(f"Exported {p}")

    # ================================================================ start-up
    class _Ev:
        def __init__(self, x, y, state=0):
            self.x, self.y, self.state, self.delta = x, y, state, 0
            self.x_root = self.y_root = 0
            self.char, self.keysym = "", ""

    load_plugins()
    for name, inst in user_instruments().items():
        PRESETS.setdefault(name, inst)
    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry("1400x880")
    root.minsize(900, 600)
    app = App(root)
    first = not (home_dir() / "launched").exists()
    song, spath = None, None
    if path:
        try:
            song = load_project(path)
            spath = Path(path) if Path(path).suffix == FILE_EXT else None
            add_recent(path)
        except Exception as e:
            print(f"could not open {path}: {e}", file=sys.stderr)
    elif autosave_path().exists() and not (selftest or screenshot):
        try:
            d = json.loads(autosave_path().read_text())
            if messagebox.askyesno("Recover", "Unsaved work from your last session was found. Recover it?"):
                song = Song.from_dict(d["song"])
                spath = Path(d["path"]) if d.get("path") else None
        except Exception:
            pass
    if song is None:
        song = demo_song() if (first or selftest or screenshot) else new_song()
    (home_dir() / "launched").write_text(APP_VERSION)
    app.set_song(song, spath)
    app.roll.scroll_to_notes()
    if first:
        app.status("Welcome! A demo song is loaded - press Space to play. Drag notes in the piano roll; F1 lists every shortcut.")
    rc = {"code": 0}

    def run_checks():
        """Exercise the real GUI handlers (used by --selftest / --screenshot)."""
        try:
            app.select_track(0)
            app.nb.select(0)
            root.update()
            roll = app.roll
            p = app.pattern
            n0 = len(p.notes)
            # draw a note by clicking an empty cell, drag to lengthen
            y = roll.y_of(100) + 3 - roll.c.canvasy(0)
            roll.press(_Ev(5, y))
            roll.motion(_Ev(5 + int(PPQ * roll.zoom), y))
            roll.release(_Ev(5 + int(PPQ * roll.zoom), y))
            assert len(p.notes) == n0 + 1, "draw note"
            new = p.notes[-1]
            assert new.pitch == 100 and new.length >= PPQ // 4, (new.pitch, new.length)
            # move it up two semitones
            x = int(new.start * roll.zoom) + 2 - roll.c.canvasx(0)
            roll.press(_Ev(x, y))
            roll.motion(_Ev(x, y - 2 * roll.ROW))
            roll.release(_Ev(x, y - 2 * roll.ROW))
            assert new.pitch == 102, new.pitch
            app.copy(); app.paste()
            assert len(p.notes) == n0 + 2
            app.undo(); app.undo(); app.undo(); app.undo()
            assert len(app.pattern.notes) == n0, "undo"
            app.redo(); app.undo()
            app.select_all(); app.transpose_sel(1); app.transpose_sel(-1); app.quantize_sel()
            app.sel = []
            di = next(i for i, t in enumerate(app.song.tracks) if t.drum)
            app.select_track(di)
            root.update()
            app.push_undo()
            assert app.drums.toggle("clap", 3) is True
            assert app.drums.toggle("clap", 3) is False
            # arrangement: drop pattern A of the drum track at bar 30
            before = len(app.song.arrangement)
            assert app.arr.drop_pattern(di, app.cur_pattern, app.arr.HW + 30 * app.arr.BW + 2, app.arr.RUL + di * app.arr.RH + 3)
            assert len(app.song.arrangement) == before + 1
            app.undo()
            app.nb.select(2)
            root.update()
            app.inst_ed.select("lead")
            app.nb.select(0)
            app.select_track(0)
            app.v["loop"].set(True)
            app.play()
            for _ in range(8):
                root.update()
                time.sleep(0.03)
            app.stop()
            app.v["loop"].set(False)
            app.kb.highlight(64, True)
            app.refresh_all()
            root.update()
            print("selftest ok")
        except Exception:
            traceback.print_exc()
            rc["code"] = 1

    if selftest or screenshot:
        def shoot():
            run_checks()
            app.kb.lit.clear()
            app.roll.scroll_to_notes()
            app.status("Demo song loaded - Space plays, F1 shows shortcuts")
            app.kb.redraw()
            root.update()
            time.sleep(0.3)
            root.update()
            if screenshot:
                try:
                    y0 = max(0, root.winfo_y())          # include the menu bar
                    x, y = root.winfo_rootx(), y0
                    w, h = root.winfo_width(), root.winfo_rooty() - y0 + root.winfo_height()
                    if shutil.which("import"):
                        subprocess.run(["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}", screenshot], check=True)
                    else:
                        from PIL import ImageGrab  # type: ignore
                        ImageGrab.grab(bbox=(x, y, x + w, y + h), xdisplay=os.environ.get("DISPLAY")).save(screenshot)
                    print(f"screenshot {screenshot}")
                except Exception as e:
                    print(f"screenshot failed: {e}", file=sys.stderr)
                    rc["code"] = 1
            app.dirty = False
            app.audio.close()
            root.destroy()
        root.after(1200, shoot)
    root.mainloop()
    return rc["code"]


# ---------------------------------------------------------------------------
# Command line: `8bms ...` (no arguments = GUI). Terse output by default,
# --json for machine-readable output, --quiet for exit-code-only.
# ---------------------------------------------------------------------------
CLI_EPILOG = """\
examples:
  8bms                                   open the GUI (demo song on first launch)
  8bms gen --style boss --bars 16 --seed 3 -o boss.8bt
  8bms render boss.8bt -o boss.wav [--loop|--seamless] [--stems stems/]
  8bms export boss.8bt --js boss.js      (also --py --json --score --project --to <plugin>)
  8bms do "gen town 8; bpm 100; /render town.wav"
  8bms acp | mcp | serve | repl          agent / tool / HTTP / terminal front-ends
  8bms plugin new effect my-fx && 8bms plugin test my-fx
"""


class _Out:
    def __init__(self, json_mode: bool = False, quiet: bool = False):
        self.json, self.quiet = json_mode, quiet

    def __call__(self, res: Any, text: Optional[str] = None):
        if self.quiet:
            return
        if self.json:
            print(_jdump(res))
        else:
            print(text if text is not None else (_terse(res) if isinstance(res, dict) else str(res)))


def _kv_args(items: List[str]) -> Dict[str, str]:
    out = {}
    for it in items:
        if "=" not in it:
            raise SystemExit(f"expected key=value, got {it!r}")
        k, v = it.split("=", 1)
        out[k.strip().replace("-", "_")] = v
    return out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="8bms", description=f"{APP_NAME} {APP_VERSION} - chiptune studio (GUI + CLI + agents)",
                                 epilog=CLI_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    sub = ap.add_subparsers(dest="cmd")

    g = sub.add_parser("gui", help="open the GUI")
    g.add_argument("file", nargs="?")
    g.add_argument("--screenshot", help="(testing) save a screenshot and exit")
    g.add_argument("--selftest", action="store_true", help="(testing) exercise the GUI and exit")

    r = sub.add_parser("render", help="render WAV/OGG/MP3/FLAC")
    r.add_argument("src", help="file.8bt|.8bms, 'demo', 'gen:style:bars:seed' or '-' (stdin)")
    r.add_argument("-o", "--out", default=None)
    r.add_argument("--loop", action="store_true", help="only the loop region")
    r.add_argument("--seamless", action="store_true", help="loop region with the tail wrapped (perfect loop)")
    r.add_argument("--bars", help="range like 5-12")
    r.add_argument("--stems", help="folder for per-track stems")

    e = sub.add_parser("export", help="save as code/data")
    e.add_argument("src")
    for k in ("js", "py", "json", "score", "project"):
        e.add_argument(f"--{k}", metavar="PATH")
    e.add_argument("--to", metavar="KIND", help="any exporter (incl. plugins)")
    e.add_argument("-o", "--out")

    gn = sub.add_parser("gen", help="generate a song")
    gn.add_argument("--style", default="mellow-space")
    gn.add_argument("--bars", type=int, default=16)
    gn.add_argument("--seed", type=int)
    gn.add_argument("--key")
    gn.add_argument("--bpm", type=float)
    gn.add_argument("-o", "--out", help="write .8bt/.8bms (default: print score)")
    gn.add_argument("--wav", help="also render WAV")

    for name, h in (("info", "summarize a song"), ("check", "validate a score/project"), ("show", "print a song as .8bt score")):
        p = sub.add_parser(name, help=h)
        p.add_argument("src")
    pl = sub.add_parser("play", help="play a song through the speakers")
    pl.add_argument("src")
    pl.add_argument("--loop", action="store_true")
    sub.add_parser("presets", help="list instruments")
    sub.add_parser("styles", help="list generator styles")
    sub.add_parser("score-help", help=".8bt syntax cheat-sheet")
    d = sub.add_parser("do", help="run studio commands/notes/English (';' or newlines separate)")
    d.add_argument("text", nargs="+")
    d.add_argument("--song", default=None, help="start from this song")
    d.add_argument("--save", default=None, help="save the result (.8bt/.8bms)")
    sub.add_parser("acp", help="run as an Agent Client Protocol agent on stdio")
    sub.add_parser("mcp", help="run as an MCP tool server on stdio")
    sv = sub.add_parser("serve", help="local HTTP API")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8765)
    rp = sub.add_parser("repl", help="terminal studio")
    rp.add_argument("src", nargs="?")
    md = sub.add_parser("midi", help="list MIDI inputs / monitor a controller (Akai APC etc.)")
    md.add_argument("--port")
    md.add_argument("--seconds", type=float, default=0)
    o = sub.add_parser("op", help="run any registered op: 8bms op <name> k=v ...")
    o.add_argument("name", nargs="?")
    o.add_argument("kv", nargs="*")

    pg = sub.add_parser("plugin", help="manage / develop plugins")
    ps = pg.add_subparsers(dest="pcmd")
    ps.add_parser("list")
    for n in ("info", "enable", "disable", "uninstall"):
        ps.add_parser(n).add_argument("name")
    ps.add_parser("install").add_argument("spec", help="folder, .zip, git URL, wheel or pip name")
    for n in ("validate", "test", "build", "package"):
        x = ps.add_parser(n)
        x.add_argument("path", nargs="?", default=".")
        if n in ("build", "package"):
            x.add_argument("-o", "--out")
    nw = ps.add_parser("new")
    nw.add_argument("type", choices=PLUGIN_TYPES)
    nw.add_argument("name")
    nw.add_argument("--dir", default=".")

    reserved = set(sub.choices)
    for name, op in OPS.items():
        if name in reserved or name.replace("_", "-") in reserved:
            continue
        p = sub.add_parser(name, help=f"[op:{op.owner}] {op.help[:60]}")
        for k, spec in op.params.items():
            p.add_argument(f"--{k.replace('_', '-')}", dest=k, required=bool(spec.get("required")), default=spec.get("default"), help=spec.get("help"))
        p.set_defaults(_op=name)
    return ap


def _resolve_plugin(name_or_path: str) -> str:
    """Plugin name -> folder path (for validate/test/build on installed plugins)."""
    if Path(name_or_path).exists():
        return name_or_path
    pm = load_plugins()
    info = pm.plugins.get(name_or_path)
    if info and info.path:
        return info.path
    raise SystemExit(f"no plugin folder or installed plugin named {name_or_path!r}")


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    flags = {f: False for f in ("--json", "--quiet", "-q", "--no-plugins")}
    keep: List[str] = []
    for i, a in enumerate(argv):
        # `export --json out.json` is the JSON exporter, not the global output flag
        if a == "--json" and keep[:1] == ["export"] and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            keep.append(a)
        elif a in flags:
            flags[a] = True
        else:
            keep.append(a)
    argv = keep
    if flags["--no-plugins"]:
        os.environ["EIGHTBMS_NO_PLUGINS"] = "1"
    out = _Out(flags["--json"], flags["--quiet"] or flags["-q"])
    if not argv:
        return launch_gui()
    if argv[0] not in ("acp", "mcp", "gui") and not (argv[0] == "plugin" and len(argv) > 1 and argv[1] in ("validate", "test", "new", "build", "package")):
        load_plugins()
    a = build_parser().parse_args(argv)
    try:
        return _dispatch(a, out) or 0
    except (ScoreError, NoteSyntaxError, PluginError, FileNotFoundError, ValueError, KeyError) as e:
        msg = str(e).strip("'\"")
        if out.json:
            print(_jdump({"ok": False, "error": msg}))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return 1


def _dispatch(a, out: _Out) -> Optional[int]:
    c = a.cmd
    if getattr(a, "_op", None):
        out(run_op(a._op, **{k: v for k, v in vars(a).items() if k not in ("cmd", "_op") and v is not None}))
    elif c == "gui":
        return launch_gui(a.file, a.screenshot, a.selftest)
    elif c == "render":
        src = a.src
        default = (Path(src).stem if Path(src).suffix in (SCORE_EXT, FILE_EXT) else _slug(src.split(":")[0] or "song")) + ".wav"
        out(op_render(src, a.out or default, loop=a.loop, seamless=a.seamless, bars=a.bars, stems=a.stems))
    elif c == "export":
        kinds = [(k, getattr(a, k)) for k in ("js", "py", "json", "score", "project") if getattr(a, k)]
        if a.to:
            kinds.append((a.to, a.out))
        if not kinds:
            raise ValueError("pick a format: --js/--py/--json/--score/--project PATH or --to KIND")
        song = load_any(a.src)
        res = [op_export(song, k, p) for k, p in kinds]
        out(res[0] if len(res) == 1 else {"paths": [r["path"] for r in res]})
    elif c == "gen":
        res = op_gen(a.style, a.bars, a.seed, a.key, a.bpm, a.out, a.wav)
        if "score" in res and not out.json:
            out(res, res["score"].rstrip())
        else:
            out(res)
    elif c == "info":
        out(op_info(a.src))
    elif c == "check":
        out(op_check(a.src))
    elif c == "show":
        txt = song_to_score(load_any(a.src))
        out({"score": txt}, txt.rstrip())
    elif c == "play":
        song = load_any(a.src)
        audio = AudioOut()
        if audio.backend == "none":
            raise ValueError("no audio output available (install sounddevice or simpleaudio, or use `8bms render`)")
        buf = render_song(song, *(song.loop_range() if a.loop else (0, song.length_bars())), seamless=a.loop)
        out({"playing": song.title, "backend": audio.backend, "seconds": round(len(buf) / SR, 2)})
        audio.play(buf, loop=a.loop)
        try:
            while audio.playing and (a.loop or audio.position_samples() < len(buf)):
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        audio.close()
    elif c == "presets":
        res = op_presets()
        out(res, " ".join(res["presets"]) + (("\nuser: " + " ".join(res["user"])) if res["user"] else ""))
    elif c == "styles":
        res = op_styles()
        out(res, " ".join(res["styles"]))
    elif c == "score-help":
        out({"text": SCORE_HELP}, SCORE_HELP.rstrip())
    elif c == "do":
        it = Interpreter(load_any(a.song) if a.song else new_song())
        text = " ".join(a.text).replace(";", "\n") if not any("\n" in t for t in a.text) else "\n".join(a.text)
        reply = it.execute(text)
        res: Dict[str, Any] = {"reply": reply}
        if a.save:
            res["path"] = str(save_project(it.song, a.save).resolve())
        out(res, reply + (f"\nsaved {res['path']}" if a.save else ""))
    elif c == "acp":
        run_acp()
    elif c == "mcp":
        run_mcp()
    elif c == "serve":
        srv = make_http_server(a.host, a.port)
        out({"url": f"http://{a.host}:{a.port}"}, f"serving http://{a.host}:{a.port}  (GET /ops, POST /ops/<name>, POST /prompt)")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
    elif c == "repl":
        run_repl(a.src)
    elif c == "midi":
        if not midi_available():
            raise ValueError("MIDI needs: pip install mido python-rtmidi")
        if not a.port:
            ports = midi_ports()
            out({"ports": ports, "mappings": {p: mapping_for_port(p)[0] for p in ports}},
                "\n".join(f"{p}  [{mapping_for_port(p)[0]}]" for p in ports) or "no MIDI inputs")
            return 0
        mc = MidiController(lambda kind, *x: print(kind, *x, flush=True))
        print(f"listening on {a.port} (mapping {mc.open(a.port)}) - Ctrl+C to stop")
        try:
            t0 = time.time()
            while not a.seconds or time.time() - t0 < a.seconds:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        mc.close()
    elif c == "op":
        if not a.name:
            out({n: o.help for n, o in OPS.items()}, "\n".join(f"{n:12} {o.help}" for n, o in OPS.items()))
        else:
            out(run_op(a.name, **_kv_args(a.kv)))
    elif c == "plugin":
        return _plugin_cmd(a, out)
    else:
        build_parser().print_help()
    return 0


def _plugin_cmd(a, out: _Out) -> int:
    p = a.pcmd
    if p in (None, "list"):
        pm = load_plugins()
        rows = [i.summary() for i in pm.plugins.values()]
        lines = [f"{r['name']:18} {r['version']:8} {','.join(r['types']):18} {'ERR ' + r['error'] if r['error'] else ('on' if r['loaded'] else 'off')}" for r in rows]
        out({"plugins": rows, "problems": pm.problems}, "\n".join(lines + pm.problems) or "no plugins (try: 8bms plugin new effect my-fx)")
    elif p == "info":
        pm = load_plugins()
        if a.name not in pm.plugins:
            raise KeyError(f"no plugin {a.name}")
        out(pm.plugins[a.name].summary())
    elif p in ("enable", "disable"):
        pm = load_plugins()
        pm.set_enabled(a.name, p == "enable")
        out({"plugin": a.name, "enabled": p == "enable"}, f"{a.name}: {p}d")
    elif p == "install":
        out(install_plugin(a.spec))
    elif p == "uninstall":
        out(uninstall_plugin(a.name))
    elif p == "validate":
        res = validate_plugin(_resolve_plugin(a.path))
        out(res, ("ok " if res["ok"] else "INVALID ") + f"{res.get('name')}: " + ("; ".join(res["errors"]) or ", ".join(res.get("provides", []))))
        return 0 if res["ok"] else 1
    elif p == "test":
        res = test_plugin(_resolve_plugin(a.path))
        out(res, ("ok " if res["ok"] else "FAIL ") + f"{res['name']}: {res['summary']}" + (("\n" + res["output"]) if not res["ok"] else ""))
        return 0 if res["ok"] else 1
    elif p == "new":
        root = scaffold_plugin(a.type, a.name, Path(a.dir))
        out({"path": str(root)}, f"created {root}\nnext: 8bms plugin validate {root} && 8bms plugin test {root}")
    elif p == "build":
        w = build_plugin_wheel(_resolve_plugin(a.path), Path(a.out) if a.out else None)
        out({"path": str(w)}, str(w))
    elif p == "package":
        z = package_plugin_zip(_resolve_plugin(a.path), Path(a.out) if a.out else None)
        out({"path": str(z)}, str(z))
    return 0


if __name__ == "__main__":
    sys.exit(main())

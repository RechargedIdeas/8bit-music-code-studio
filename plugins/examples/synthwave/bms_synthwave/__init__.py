"""Synthwave: a generator style for 8Bit Music Code Studio.

    8bms gen --style synthwave --bars 16 --seed 7 -o night.8bt
"""

STYLE = {
    "bpm": (96, 112), "scale": "minor", "keys": ["A", "F#", "D", "E"],
    "prog": [[0, 5, 2, 6], [0, 5, 3, 4], [5, 3, 0, 4]],
    "lead": "saw", "harm": "pad", "bass": "pulsebass", "bass_style": "octave", "groove": "synthwave",
    "density": 0.5, "swing": 0.0,
    "fx": {"echo": {"time": 0.42, "feedback": 0.45, "mix": 0.3}, "lowpass": {"cutoff": 7000}},
}

GROOVE = {"kick": "x...x...x...x...", "snare": "....X.......X...", "hat": "x.x.x.x.x.x.x.xx", "ohat": "..............x."}


def register(api):
    api.add_groove("synthwave", GROOVE)
    api.add_style("synthwave", STYLE)

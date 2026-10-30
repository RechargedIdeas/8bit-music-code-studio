"""MML exporter for 8Bit Music Code Studio.

    8bms export song.8bt --to mml -o song.mml

Writes classic MML: one line per track (A, B, C, ...), ``t`` tempo, ``o`` octave,
``l`` default length, ``v`` volume (0-15), ``r`` rests, ``&`` ties and ``>``/``<``.
Chords are reduced to their top note (MML channels are monophonic); drum tracks are
written as noise notes (kick=c, snare=e, hat=g ...).
"""
PPQ = 96
_NAMES = ["c", "c+", "d", "d+", "e", "f", "f+", "g", "g+", "a", "a+", "b"]
_DRUM_PITCH = {"kick": 36, "snare": 40, "clap": 39, "hat": 43, "ohat": 46, "tom": 45, "crash": 49}
_LENS = [(1, PPQ * 4), (2, PPQ * 2), (4, PPQ), (8, PPQ // 2), (16, PPQ // 4), (32, PPQ // 8), (64, PPQ // 16)]


def _len_parts(ticks):
    """Split a tick length into MML length tokens (with dots), e.g. 144 -> ['4.']."""
    parts = []
    while ticks >= PPQ // 16:
        for den, t in _LENS:
            if ticks >= t * 3 // 2 and t % 2 == 0:
                parts.append(f"{den}.")
                ticks -= t * 3 // 2
                break
            if ticks >= t:
                parts.append(str(den))
                ticks -= t
                break
    return parts or ["64"]


def _track_notes(song, ti):
    tpb = song.ticks_per_bar
    out = []
    for c in song.arrangement:
        if c.track != ti:
            continue
        p = song.pattern_of(c)
        if not p:
            continue
        for n in p.notes:
            if n.start < p.bars * tpb:
                pitch = _DRUM_PITCH.get(n.inst, 42) if n.inst else n.pitch
                out.append((c.bar * tpb + n.start, min(n.length, p.bars * tpb - n.start), pitch, n.velocity))
    # monophonic: at equal starts keep the highest pitch; cut overlaps
    out.sort(key=lambda e: (e[0], -e[2]))
    mono = []
    for e in out:
        if mono and mono[-1][0] == e[0]:
            continue
        if mono and mono[-1][0] + mono[-1][1] > e[0]:
            s, ln, p, v = mono[-1]
            mono[-1] = (s, e[0] - s, p, v)
        mono.append(e)
    return [e for e in mono if e[1] > 0]


def song_to_mml(song):
    lines = [f"; {song.title} - exported by 8Bit Music Code Studio (MML)", f"#TITLE {song.title}"]
    letters = "ABCDEFGHIJ"
    for ti, track in enumerate(song.tracks[:len(letters)]):
        notes = _track_notes(song, ti)
        toks = [f"t{int(round(song.bpm))}", "l8"]
        octave, vol, cur = None, None, 0
        for start, ln, pitch, vel in notes:
            if start > cur:
                toks.append("&".join("r" + ("" if x == "8" else x) for x in _len_parts(start - cur)))
            o, name = pitch // 12 - 1, _NAMES[pitch % 12]
            if octave is None:
                toks.append(f"o{o}")
            elif o != octave:
                toks.append((">" if o > octave else "<") * abs(o - octave))
            octave = o
            v = max(1, min(15, int(round(vel * 15))))
            if v != vol:
                toks.append(f"v{v}")
                vol = v
            parts = _len_parts(ln)
            toks.append("&".join(name + ("" if p == "8" else p) for p in parts))
            cur = start + ln
        lines.append(f"{letters[ti]} " + " ".join(toks) + f"   ; {track.name} ({track.instrument})")
    return "\n".join(lines) + "\n"


def register(api):
    api.add_exporter("mml", ".mml", song_to_mml)

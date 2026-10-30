"""Python API tour: compose -> vary -> critique -> loop -> export. Run: python examples/python_api.py [outdir]"""
import sys
from pathlib import Path

import eightbit_studio as bms   # pip install eightbit-music-code-studio (or run from the repo root)

out = Path(sys.argv[1] if len(sys.argv) > 1 else "out")
out.mkdir(parents=True, exist_ok=True)

theme = bms.run_op("compose", prompt="calm town at dusk", bars=8, seed=4)          # -> {"handle": "@…", "score": …}
print("theme", theme["handle"], "score", theme["score"])
var = bms.run_op("variation", src=theme["handle"], amount=0.25, seed=1)
print("critique:", bms.run_op("critique", src=var["handle"])["tips"][:1])
loop = bms.run_op("loopify", src=var["handle"], wav=str(out / "town-loop.wav"), out=str(out / "town-loop.8bt"))
print("loop", loop["loop_seconds"], "s ->", loop["wav"])

song = bms.load_any(var["handle"])                    # a Song object: edit it directly
song.bpm = 96
bms.op_export(song, "js", str(out / "town.js"))      # Web Audio ES module
print(bms.song_to_score(song).splitlines()[1])        # .8bt text is the cheapest format to read

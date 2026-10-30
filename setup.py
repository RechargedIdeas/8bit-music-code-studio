"""Build hook: the app is one file (8BitMusicCodeStudio.py, not an importable
name). Wheels get a copy as eightbit_studio/_core.py plus the tiny ML model, so
installs work on Windows/macOS/Linux without symlinks."""
import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent


class BuildPy(build_py):
    def run(self):
        super().run()
        pkg = Path(self.build_lib) / "eightbit_studio"
        pkg.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "8BitMusicCodeStudio.py", pkg / "_core.py")
        model = ROOT / "models" / "tiny-v1.json"
        if model.exists():
            (pkg / "models").mkdir(exist_ok=True)
            shutil.copyfile(model, pkg / "models" / model.name)


setup(cmdclass={"build_py": BuildPy})

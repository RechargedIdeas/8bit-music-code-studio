import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# isolate user state (autosave, recent files, plugins.json) from the real ~/.8bms
os.environ.setdefault("EIGHTBMS_HOME", tempfile.mkdtemp(prefix="8bms-test-home-"))
os.environ["EIGHTBMS_NO_PLUGINS"] = "1"
os.environ.setdefault("PYTHONIOENCODING", "utf-8")   # child processes print UTF-8 on Windows too

import pytest  # noqa: E402

import eightbit_studio as bms  # noqa: E402

APP = ROOT / "8BitMusicCodeStudio.py"


@pytest.fixture
def song():
    return bms.demo_song()


@pytest.fixture
def app_path():
    return APP

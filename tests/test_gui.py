"""Run the real Tk GUI headless (xvfb) and drive its handlers via --selftest."""
import os
import shutil
import subprocess
import sys

import pytest

from conftest import APP

needs_display = pytest.mark.skipif(not (os.environ.get("DISPLAY") or shutil.which("xvfb-run")), reason="no X display / xvfb-run")


@needs_display
def test_gui_selftest_and_screenshot(tmp_path):
    pytest.importorskip("tkinter")
    shot = tmp_path / "shot.png"
    cmd = [sys.executable, str(APP), "gui", "--selftest", "--screenshot", str(shot)]
    if not os.environ.get("DISPLAY"):
        cmd = ["xvfb-run", "-a", "-s", "-screen 0 1440x960x24"] + cmd
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "selftest ok" in (r.stdout + r.stderr).lower()
    assert shot.exists() and shot.stat().st_size > 20000

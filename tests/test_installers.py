"""Installer scripts: version stamp, syntax, and the stale-copy handover."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version():
    return re.search(r'(?m)^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text()).group(1)


def test_installer_versions_match_package():
    v = _pyproject_version()
    assert f'INSTALLER_VERSION="{v}"' in (ROOT / "install.sh").read_text()
    assert f'$InstallerVersion = "{v}"' in (ROOT / "install.ps1").read_text(encoding="utf-8")


@pytest.mark.skipif(not shutil.which("sh"), reason="no sh")
def test_install_sh_syntax_and_help():
    subprocess.run(["sh", "-n", str(ROOT / "install.sh")], check=True)
    out = subprocess.run(["sh", str(ROOT / "install.sh"), "--help"], capture_output=True, text=True, check=True).stdout
    assert "--method" in out and "--verbose" in out


@pytest.mark.skipif(not shutil.which("pwsh"), reason="no pwsh")
def test_install_ps1_parses():
    cmd = ("$e=$null; $null=[System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$null,[ref]$e); "
           "if ($e) { $e | %% { $_.ToString() }; exit 1 }" % (ROOT / "install.ps1"))
    r = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_installers_never_call_bare_shims_for_install():
    """pipx/uv shims can be stale (that broke a Windows user); installs go through `python -m pipx`."""
    ps = (ROOT / "install.ps1").read_text(encoding="utf-8")
    assert '"-m", "pipx", "install"' in ps
    assert not re.search(r'(?m)^\s*(pipx|uv) (install|tool install)', ps)
    assert "8bms.cmd\"\n" not in ps and 'Set-Content -Path $shim' not in ps   # no cmd.exe shim for the venv method

"""Import shim: exposes 8BitMusicCodeStudio.py (which is not a valid module
name) as the package ``eightbit_studio``. Everything lives in that one file."""
import importlib.util as _ilu
import sys as _sys
from pathlib import Path as _Path

_core = _sys.modules.get("eightbit_studio_core")
if _core is None:
    _here = _Path(__file__).resolve().parent
    _file = _here.parent / "8BitMusicCodeStudio.py"      # source checkout / editable install
    if not _file.exists():
        _file = _here / "_core.py"                       # wheel: symlink copied as a real file
    _spec = _ilu.spec_from_file_location("eightbit_studio_core", _file)
    _core = _ilu.module_from_spec(_spec)
    _sys.modules["eightbit_studio_core"] = _core
    _spec.loader.exec_module(_core)

globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
__all__ = [k for k in vars(_core) if not k.startswith("_")]
__version__ = _core.APP_VERSION

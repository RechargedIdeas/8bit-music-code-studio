# 8Bit Music Code Studio - common tasks (uses .venv if present)
PY ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
APP = 8BitMusicCodeStudio.py

.PHONY: help venv install test gui demo screenshot plugins plugin-new clean

help:
	@echo "make venv | install | test | gui | demo | screenshot | plugins | plugin-new TYPE=effect NAME=my-fx | clean"

venv:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pillow

install:            ## put `8bms` on PATH (uv tool, falls back to pip --user)
	uv tool install --force --editable . || $(PY) -m pip install --user -e .

test:
	$(PY) -m pytest -q

gui:
	$(PY) $(APP)

demo:
	$(PY) $(APP) render demo -o demo.wav

screenshot:
	xvfb-run -a -s "-screen 0 1440x960x24" $(PY) $(APP) gui --screenshot screenshot.png --selftest

plugins:            ## validate + test + build + package every plugin
	$(PY) scripts/build_all_plugins.py plugins

plugin-new:
	$(PY) scripts/new_plugin.py $(TYPE) $(NAME) --dir plugins

clean:
	rm -rf dist build *.egg-info .pytest_cache plugins/examples/*/dist
	find . -name __pycache__ -prune -exec rm -rf {} +

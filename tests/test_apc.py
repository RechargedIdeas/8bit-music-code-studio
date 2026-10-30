"""Akai APC support without hardware: VirtualApc (in-memory device + MIDI backend)
drives the real MidiController, LED feedback and the `8bms apc test` diagnostic.
An optional loopback test uses python-rtmidi virtual ports when the OS allows it."""
import json
import subprocess
import sys
import time

import pytest

import eightbit_studio as bms
from conftest import APP

CORE = sys.modules["eightbit_studio_core"]


@pytest.mark.parametrize("port,want", [
    ("APC MINI", "apc-mini"), ("APC MINI 0", "apc-mini"), ("APC MINI:APC MINI MIDI 1 20:0", "apc-mini"),
    ("APC mini mk2 Control", "apc-mini-mk2"), ("APC mini mk2:APC mini mk2 APC mini mk2 Contr 20:0", "apc-mini-mk2"),
    ("MIDIIN2 (APC mini mk2)", "apc-mini-mk2"), ("APC Key 25", "apc-key25"), ("APC Key 25 mk2 Control", "apc-key25-mk2"),
    ("APC Key 25 mk2 Keys", "apc-key25-mk2"), ("APC40 mkII", "apc40"), ("Akai APC40", "apc40"), ("USB Keystation 61", "generic"),
])
def test_port_name_detection(port, want):
    assert bms.mapping_for_port(port)[0] == want


@pytest.mark.parametrize("inp,outs,want", [
    ("APC MINI", ["APC MINI"], "APC MINI"),
    ("APC MINI 0", ["Microsoft GS Wavetable Synth 0", "APC MINI 1"], "APC MINI 1"),
    ("APC mini mk2:APC mini mk2 APC mini mk2 Contr 20:0", ["Midi Through:Midi Through Port-0 14:0", "APC mini mk2:APC mini mk2 APC mini mk2 Contr 20:0"],
     "APC mini mk2:APC mini mk2 APC mini mk2 Contr 20:0"),
    ("APC Key 25", ["Midi Through Port-0"], None),
])
def test_output_port_pairing(inp, outs, want):
    assert bms.match_output_port(inp, outs) == want


def _open(model):
    dev = bms.VirtualApc(model)
    events = []
    mc = bms.MidiController(lambda *e: events.append(e), backend=dev)
    assert mc.open(dev.port_name) == model
    assert mc.out is dev
    return dev, mc, events


@pytest.mark.parametrize("model", bms.APC_MODELS)
def test_every_pad_and_led_round_trip(model):
    """Each pad press arrives as (grid, row, col); set_led(row, col) lights exactly that pad on the device."""
    dev, mc, events = _open(model)
    g = dev.mapping["grid"]
    for r in range(g["rows"]):
        for c in range(g["cols"]):
            events.clear()
            dev.press(r, c)
            assert events == [("grid", r, c)], (model, r, c, events)
            mc.clear_leds()
            mc.set_led(r, c, "accent")
            assert dev.lit() == [(r, c)] and dev.led_state(r, c) == "accent"
    mc.set_led(0, 0, "playhead")
    assert dev.led_state(0, 0) == "playhead"
    mc.clear_leds()
    assert dev.lit() == []


@pytest.mark.parametrize("model", bms.APC_MODELS)
def test_faders_knobs_master_transport_scenes(model):
    dev, mc, events = _open(model)
    m = dev.mapping
    kind = "knob" if m.get("knobs") else "fader"
    for i in range(8):
        events.clear()
        dev.fader(i, 1.0)
        assert events == [(kind, i, 1.0)]
    if m.get("master_cc") is not None:
        events.clear()
        dev.master(0.5)
        assert events[0][0] == "master" and abs(events[0][1] - 64 / 127) < 1e-9
    for name in m.get("transport", {}):
        events.clear()
        dev.button(name)
        assert events == [("transport", name)]
    for i in range(len(m.get("scene", []))):
        events.clear()
        dev.scene(i)
        assert events == [("scene", i)]


def test_led_wire_format():
    """Exact bytes the hardware sees: mk1 uses velocity colours on ch 0, mk2 RGB palette on ch 6, APC40 grid starts at note 32 top-left."""
    M = bms.MIDI_MAPPINGS
    assert bms.led_message(M["apc-mini"], 7, 0, "on") == {"type": "note_on", "channel": 0, "note": 0, "velocity": 1}
    assert bms.led_message(M["apc-mini"], 0, 7, "off")["note"] == 63
    assert bms.led_message(M["apc-mini-mk2"], 7, 0, "on") == {"type": "note_on", "channel": 6, "note": 0, "velocity": 21}
    assert bms.led_message(M["apc-key25"], 0, 0, "accent") == {"type": "note_on", "channel": 0, "note": 32, "velocity": 5}
    assert bms.led_message(M["apc40"], 0, 0, "on")["note"] == 32 and bms.led_message(M["apc40"], 4, 0, "on")["note"] == 0
    assert bms.led_message(M["apc-mini"], 8, 0) is None


def test_key25_keyboard_channel_never_hits_pads_or_transport():
    dev, mc, events = _open("apc-key25")
    for note in (0, 39, 82, 91, 93):          # same numbers as pads / scene / play / record, but on the keys channel
        events.clear()
        dev.key(note)
        assert events == [("note_on", note, 100 / 127), ("note_off", note)]


def test_unmapped_messages_are_reported():
    dev, mc, events = _open("apc-mini")
    seen = []
    mc.on_raw = lambda msg, handled: seen.append(handled)
    dev.raw("control_change", control=7, value=10, channel=3)
    dev.press(0, 0)
    assert seen == [False, True, True] and events == [("grid", 0, 0)]


@pytest.mark.parametrize("model", bms.APC_MODELS)
def test_apc_test_virtual_passes(model):
    rep = bms.apc_test(virtual=model, timeout=2, led_delay=0)
    assert rep["status"] == "pass", rep
    assert rep["mapping"] == model and rep["output"]
    assert all(s.get("led_ok", True) for s in rep["steps"])
    md = bms.apc_report_md(rep)
    assert "PASS" in md and "| pad_bottom_left | pass" in md


def test_apc_test_flags_wrong_controls(monkeypatch):
    def clumsy(dev, step):
        if step["id"] == "pad_top_right":
            dev.press(1, 1)                       # not the lit pad
        elif step["id"] != "master":              # master: does nothing -> timeout
            orig(dev, step)
    orig = CORE._virtual_actor
    monkeypatch.setattr(CORE, "_virtual_actor", clumsy)
    rep = bms.apc_test(virtual="apc-mini", timeout=0.3, led_delay=0)
    st = {s["id"]: s["status"] for s in rep["steps"]}
    assert st["pad_top_right"] == "wrong" and st["master"] == "timeout" and st["pad_bottom_left"] == "pass"
    assert rep["status"] == "partial" and any("Hardware report" in h or "hardware" in h.lower() for h in rep["hints"])


def test_apc_cli_virtual_report(tmp_path):
    rpt = tmp_path / "apc.md"
    r = subprocess.run([sys.executable, str(APP), "apc", "test", "--virtual", "apc-mini-mk2", "--report", str(rpt), "--json"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(r.stdout.strip().splitlines()[-1])["status"] == "pass"
    assert "apc-mini-mk2" in rpt.read_text(encoding="utf-8")
    r = subprocess.run([sys.executable, str(APP), "apc", "models"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0 and all(m in r.stdout for m in bms.APC_MODELS)


def test_real_midi_loopback_with_virtual_ports():
    """python-rtmidi virtual ports (macOS CoreMIDI, Linux with snd-seq). Skips where the OS can't create them."""
    mido = pytest.importorskip("mido")
    pytest.importorskip("rtmidi")
    name = "8bms Loop APC MINI"
    try:
        dev_out = mido.open_output(name, virtual=True)      # the "controller" side: sends pad presses
        dev_in = mido.open_input(name, virtual=True)        # receives LED messages
    except Exception as e:
        pytest.skip(f"virtual MIDI ports unavailable here: {e}")
    try:
        time.sleep(0.3)
        backend = bms.MidoBackend()
        port = next((p for p in backend.input_names() if name in p), None)
        if port is None:
            pytest.skip("virtual port not visible to this process")
        events = []
        mc = bms.MidiController(lambda *e: events.append(e), backend=backend)
        assert mc.open(port) == "apc-mini"
        dev_out.send(mido.Message("note_on", note=0, velocity=127))
        dev_out.send(mido.Message("control_change", control=48, value=127))
        t = time.time()
        while len(events) < 2 and time.time() - t < 3:
            time.sleep(0.05)
        assert ("grid", 7, 0) in events and ("fader", 0, 1.0) in events
        if mc.out is not None:
            mc.set_led(7, 0, "on")
            msg = dev_in.receive(block=False)
            t = time.time()
            while msg is None and time.time() - t < 3:
                time.sleep(0.05)
                msg = dev_in.receive(block=False)
            assert msg is not None and msg.type == "note_on" and msg.note == 0 and msg.velocity == 1
        mc.close()
    finally:
        dev_out.close()
        dev_in.close()

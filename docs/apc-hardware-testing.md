# Testing with real APC hardware

> **TL;DR** Plug the APC in, run `8bms apc test --report apc-report.md`, follow the prompts (press the lit pad, move a fader, press Play), then attach `apc-report.md` to a [hardware report issue](https://github.com/RechargedIdeas/8bit-music-code-studio/issues/new?template=apc-hardware-report.yml). Exit code 0 means every check passed.

The APC mappings are tested in CI against a simulated controller (`VirtualApc`), which checks every pad, LED message, fader, knob, scene and transport button for each model. Only real hardware can confirm that Akai's devices actually send and light what their protocol documents say, so reports from owners are what turns "should work" into "works".

## 1. Set up
```sh
sh install.sh --midi                       # or: pip install "eightbit-music-code-studio[midi]"  (mido + python-rtmidi)
8bms midi                                  # lists MIDI inputs and the mapping picked for each
```
- **Linux:** the ALSA sequencer must be loaded (`sudo modprobe snd-seq`), and your user usually needs to be in the `audio` group.
- **Windows:** close every other app that might hold the port (Ableton Live, a DAW, browser tabs using Web MIDI). Windows lets only one app open a MIDI port.
- **macOS:** nothing extra; if the APC does not show up, open *Audio MIDI Setup* once.
- **APC40 mkII:** needs its power supply; USB power alone does not light the pads.

## 2. Run the check
```sh
8bms apc test                              # auto-detects the first port that looks like an APC
8bms apc test --port "APC mini mk2"        # pick a port (part of the name is enough for detection; use the full name from `8bms midi`)
8bms apc test --model apc-mini-mk2         # force a mapping if detection guessed wrong
8bms apc test --timeout 30 --seconds 20    # more time per prompt, then 20 s of free play that is logged too
8bms apc test --report apc-report.md       # save the Markdown report
```

What happens:
1. **LED sweep.** Every pad lights up row by row, once in each of three colours, then turns off. Watch for dead pads or wrong colours.
2. **Press the lit pad** (bottom-left, then top-right). This checks pad input *and* that LED rows and columns are not flipped: if you press the pad that is lit and the test says PASS, both directions agree.
3. **Fader 1 / knob 1**, **master fader**, **Play**, **first scene button**, and on an APC Key 25 **any key**, depending on the model.
4. Optional **free play** (`--seconds N`): everything you press is logged, and anything the mapping does not understand is listed as *unmapped*.

## 3. Read the results
| Result | Meaning |
|---|---|
| `pass` | the control sent exactly what the mapping expects |
| `wrong` | a message arrived, but not the expected one; the report shows what arrived |
| `timeout` | nothing arrived in time (not pressed, wrong port, or the control sends nothing in this mode) |
| status `NO-MIDI` / `NO-DEVICE` | MIDI libraries or the MIDI system are missing, or no APC port was found; the hints say what to try |

Exit codes: `0` all passed, `1` some failed, `2` no MIDI system or no device.

## 4. Send a report
Open a [hardware report issue](https://github.com/RechargedIdeas/8bit-music-code-studio/issues/new?template=apc-hardware-report.yml), paste `apc-report.md`, and say whether the LED sweep looked right. Reports that pass are just as useful as failures: they let the docs say a model is confirmed.

## Without hardware
`8bms apc test --virtual [apc-mini|apc-mini-mk2|apc-key25|apc-key25-mk2|apc40]` runs the same check against an in-memory APC that "presses" whichever pad is lit. Developers can use the same simulator in Python:

```python
import eightbit_studio as bms
dev = bms.VirtualApc("apc-mini-mk2")
mc = bms.MidiController(print, backend=dev)   # prints ('grid', row, col), ('fader', i, v), ...
mc.open(dev.port_name)
dev.press(7, 0)                               # bottom-left pad -> grid 7 0
mc.set_led(7, 0, "on"); print(dev.led_state(7, 0))   # 'on'
```

The test suite also has a loopback test that uses real python-rtmidi virtual ports where the OS allows it (macOS, and Linux with `snd-seq`).

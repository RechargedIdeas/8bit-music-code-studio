# ML: the tiny offline model

> **TL;DR** The ML is **small, CPU-only, offline, deterministic and optional**: one 43 KB JSON model (`models/tiny-v1.json`) trained in about 30 ms from the app's own generator output, with no network, no GPU and no third-party data. It powers `compose --model tiny` (the default), `8bms suggest`, `intent`, chord estimation, grooves and humanize. Run `8bms ml info` for provenance and `8bms ml bench` for latency.

```sh
8bms compose "sneaky stealth level" --model tiny --seed 2 --fields handle,score
8bms suggest @last --kind next --k 3         # next-note ideas for the lead pattern
8bms suggest @last --kind chords             # chord per bar (Viterbi)
8bms suggest @last --kind groove             # a sampled drum groove
8bms intent "make it loop and a bit faster"  # English -> op call
8bms ml info | train -o models/tiny-v1.json | bench
```
The same functions are available in the GUI **AI** menu (Ctrl+Space suggests the next note), as studio `/suggest` (with Tab completion), as MCP tools and as HTTP routes.

## Principles
| Principle | How |
|---|---|
| Small | one JSON file, 43,453 bytes; pure NumPy/stdlib inference |
| CPU-only, offline | no network access, no GPU, no downloads; works on a plane |
| Deterministic | same args + seed → identical notes; training is deterministic (fixed corpus hash) |
| Optional | `--model rules` skips it; if the file is missing it is retrained in memory (about 30 ms) |
| Provenance | `8bms ml info` shows the corpus recipe, `corpus_sha256` and license (MIT, self-generated: no third-party music or samples) |

## Implemented
| Piece | What it is | Used by |
|---|---|---|
| Melody model | 3-gram Markov over scale-degree/duration tokens (614 contexts, vocab 61) with backoff. Constrained decoding: in scale and range, fits the bar, chord tones on strong beats, no long repeats, phrases end on the tonic | `compose`, `extend`, `variation`, GUI Compose |
| Next-note suggester | top-k from the same model at the cursor | `suggest --kind next`, GUI Ctrl+Space, studio Tab |
| Chord estimator | Viterbi over diatonic degrees with learned transitions (33 progressions) | `suggest --kind chords`, `arrange`, `describe` |
| Groove sampler | per-step drum probabilities learned from the style grooves | `suggest --kind groove`, `compose`, `arrange` |
| Intent parser | naive Bayes over 404 synthetic phrases + regex slot filling (context, style, bars, bpm, key, seed) | `intent`, studio/ACP English, MCP `studio` |
| Critic | rule-based 0–100 score (range, leaps, repetition, rhythm, harmony fit, mix) with tips | `critique`, reranking `compose --candidates N` |
| Humanizer | seeded micro-timing and velocity (hats push, snares lay back) | `humanize`, GUI |
| Plugin hook | `ml` plugin type registers a backend for `compose --model <name>` and `/ml <backend> <prompt>` | plugins |

## Sizes and latency
These are the results of `8bms ml bench` on an 8-vCPU x86-64 Linux box with Python 3.12 (medians, in ms).

| Task | ms |
|---|---|
| train the whole model | 30 |
| tiny-model 16-bar composition (model only) | 13.8 |
| `compose` op, 16 bars, 1 candidate / 4 candidates reranked | 3.9 / 13.7 |
| 8-bar melody | 2.1 |
| next-note suggestion | 0.17 |
| chords for a song | 0.42 |
| critique | 0.48 |
| intent parse | 0.09–0.16 |
| humanize | 0.57 |
| groove | 0.04 |
| render 16 bars: cold / voice cache / song cache | 265 / 106 / 2.6 |

`tests/test_ml.py` enforces budgets: compose under 400 ms, suggest under 50 ms. `EIGHTBMS_BUDGET_SCALE` relaxes them on slow CI runners.

## Design-only (not implemented)
These are written down so the interfaces stay stable. None of them ship today.
- **A small neural melody model** (≤ 5 MB, GRU or tiny transformer, ONNX on CPU) as an `ml` plugin behind `compose --model`. It would keep the same constrained decoder and determinism, and train on the self-generated corpus plus user-owned songs only.
- **A learned critic** trained on the user's own keep/discard choices (local only), blended with the rule-based score.
- **Hum or whistle to melody** (pitch tracking → note language).
- **Timbre matching:** pick the instrument preset closest to a reference WAV.
- **Similarity search** over the user's library (`describe` features → nearest songs).

Each would arrive as an optional plugin with its own size and latency budget and its own provenance in `8bms ml info`.

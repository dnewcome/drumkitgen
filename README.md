<h1 align="center">drumkitgen</h1>

<p align="center">
  <em>Generate and analyze drum kits for electronic music — from heuristic prompts.</em>
</p>

<p align="center">
  <img alt="status: alpha" src="https://img.shields.io/badge/status-alpha-orange">
  <img alt="python" src="https://img.shields.io/badge/python-3.10%2B-blue">
  <img alt="license: MIT" src="https://img.shields.io/badge/license-MIT-green">
</p>

---

**drumkitgen** builds drum kits the way a producer thinks about them: as a set of
one-shots with roles (kick, snare, closed hat, …), described by a prompt, and
backed by real measurements of each sound. It's **multi-modal** by design — a kit
can be assembled from analyzed samples, generative models, DSP synthesis, and
corpus recombination — but it's held together by one idea:

> **A kit is a folder of one-shots plus a canonical `kit.yaml`.**
> Everything a sampler can load (`.sfz` today) is *generated from* that file.
> Every way of producing sound is just a *producer* that drops pieces into it.

That inversion is the whole architecture. `kit.yaml` is the source of truth and
holds everything the sampler formats can't — the prompt that made the kit, where
each sound came from, and a full analysis of every one-shot. The `.sfz` is
disposable; the metadata is not.

```
                              ┌───────────────────────────┐
   producers  ─────────────►  │        kit.yaml           │  ─────────►  render targets
                              │   (canonical, source of   │
   • analyze existing WAVs    │    truth: prompt,         │              • .sfz            ✅
   • generative models (api)  │    provenance, per-piece  │              • Decent Sampler  ⬜
   • generative models (local)│    analysis, slot→key)    │              • Ableton Rack    ⬜
   • DSP synthesis "beef-up"  │                           │              • …
   • corpus recombination     └───────────────────────────┘
   • kit morphing
        ▲ ✅ = shipping today,  ⬜ = on the roadmap
```

## Status

**Shipping: the spine.** Point it at a folder of one-shots and it analyzes each
sound, classifies it into a slot, lays the kit out across MIDI keys, and writes a
packaged, playable kit (`samples/` + `kit.yaml` + `.sfz`) you can drag into any
DAW. The generative / synthesis / corpus producers are next — see the
[roadmap](#roadmap). This spine exists first on purpose: it forces the metadata
schema to be designed properly before anything depends on it.

## Install

```bash
git clone https://github.com/dnewcome/drumkitgen
cd drumkitgen
python -m venv .venv && source .venv/bin/activate
pip install -e ".[loudness]"                # loudness extra adds LUFS metering
# optional: low-latency engine for the interactive `audition` pad
pip install -e ".[loudness,audition]"       # adds sounddevice
```

## Quickstart

No samples on hand? Synthesize a starter kit and pack it in one command:

```bash
drumkitgen demo --out out/demo-kit
```

Have a folder of one-shots? Pack it into a kit:

```bash
drumkitgen pack ./my_samples --out out/my-kit \
    --name "detroit-01" \
    --prompt "gritty 90s Detroit techno, analog, overdriven, short decays" \
    --tags techno,analog,gritty
```

Inspect an existing kit, or list the slot taxonomy:

```bash
drumkitgen inspect out/my-kit/kit.yaml
drumkitgen slots
```

**Remix** an existing kit into a re-voiced variant — the first *transform
producer*. It reads each pristine one-shot, applies slot-aware DSP (sub-weight
under kicks, saturation grit, optional tuning), and records every step in the new
kit's provenance:

```bash
drumkitgen remix out/my-kit --out out/my-kit-remix \
    --drive 0.6 --sub 0.75 --tune -2
```

```
                     metalhead  →  metalhead-remix
┏━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ id            ┃ slot  ┃ sub% → ┃  cen Hz → ┃ chain                      ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ dark_kick11   │ kick  │  47→71 │ 3571→3256 │ tune(-2st)·sub_layer·satur │
│ liquid_snare33│ snare │   8→19 │ 5160→4785 │ tune(-2st)·saturate(0.60)  │
│ future_hat03  │ hat   │    0→0 │ 10540→94… │ tune(-2st)·saturate(0.24)  │
└───────────────┴───────┴────────┴───────────┴────────────────────────────┘
```

The source kit is never touched; the remix is a derivative whose `source.chain`
says exactly how to reproduce it.

**Audition** a kit (or any folder of one-shots) as an interactive terminal drum
pad — it auto-maps keyboard keys to samples and plays them on keypress:

```bash
drumkitgen audition out/my-kit-remix
```

```
             audition · metalhead-remix  (9 pads)
┏━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ key ┃ sample              ┃ info                           ┃
┡━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│  a  │ dark_kick11         │ kick · 131ms · 3.3k · sub 71%  │
│  s  │ temple_kick14       │ kick · 172ms · 2.2k · sub 88%  │
│  d  │ liquid_snare33      │ snare · 497ms · 4.8k · sub 19% │
│  h  │ future_hat03        │ hat_closed · 182ms · 9.4k      │
│ ... │                     │                                │
└─────┴─────────────────────┴────────────────────────────────┘
```

A kit is laid out by MIDI key (kick under the resting `a`); a raw folder is laid
out by filename. Playback uses `sounddevice` for low-latency polyphony if the
`[audition]` extra is installed, otherwise it shells out to an installed CLI
player (`pw-play` / `ffplay` / `paplay` / `aplay`). Press `?` for the legend,
`Ctrl-C`/`ESC` to quit.

**Report** — render a self-contained HTML page that characterizes a kit's samples
and, with `--compare`, exactly how a remix changed them:

```bash
drumkitgen report out/my-kit --compare out/my-kit-remix --open
```

It's pure inline SVG (no plotting library, no external assets, works headless)
and includes:
- a **feature map** (spectral centroid × sub-energy, colored by slot family) with
  **before→after arrows** showing how each sound moved,
- a **spectral heatmap** (energy per frequency band) characterizing the input,
- a **change heatmap** (diverging: energy gained/lost per band),
- **waveform envelopes** overlaying source vs remix, and
- a **table view** of every measurement.

Colors come from a colorblind-validated palette; light and dark themes are both
first-class.

The demo analyzes and classifies eight synthesized drums, lays them out across
the General MIDI keys, and writes the packaged kit:

```
$ drumkitgen demo --out out/demo-kit

                           demo-kit  (8 pieces)
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━┳━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━┓
┃ id            ┃ slot       ┃ key ┃ conf ┃   dur ┃ cen Hz ┃ f0 Hz ┃ sub% ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━╇━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━┩
│ kick_01       │ kick       │  36 │ 0.94 │ 0.50s │    565 │    46 │   96 │
│ snare_01      │ snare      │  38 │ 0.64 │ 0.30s │   8048 │     - │    0 │
│ clap_01       │ clap       │  39 │ 0.60 │ 0.40s │  11337 │     - │    0 │
│ tom_low_01    │ tom_low    │  41 │ 0.68 │ 0.35s │    254 │    91 │   91 │
│ hat_closed_01 │ hat_closed │  42 │ 0.94 │ 0.09s │  12690 │     - │    0 │
│ hat_open_01   │ hat_open   │  46 │ 0.96 │ 0.60s │  12528 │     - │    0 │
│ crash_01      │ crash      │  49 │ 0.90 │ 1.60s │  12143 │     - │    0 │
│ tom_high_01   │ tom_high   │  50 │ 0.60 │ 0.25s │    324 │   201 │    0 │
└───────────────┴────────────┴─────┴──────┴───────┴────────┴───────┴──────┘

✓ demo kit written to out/demo-kit
```

Note how the measurements tell the story: the kick owns the sub band (96%) and is
the only low-pitched hit (46 Hz); the hats and crash are bright (>12 kHz) with no
sub; the toms are tonal (clean f0). That's exactly what the classifier reasons
over.

## How it works

The `pack` pipeline, end to end:

```
find audio ─► load (mono) ─► analyze ─► classify ─► assign keys ─► Kit
                                                                    │
                        copy samples  +  write kit.yaml  +  render .sfz  ◄┘
```

1. **Analyze** (`analysis.py`) — for each one-shot, extract level (peak/RMS/LUFS),
   spectral shape (centroid, bandwidth, rolloff, flatness, ZCR), envelope
   (attack/decay), a pitched fundamental (pYIN), and a normalized **band-energy
   profile**. Built to stay robust on very short, transient hits.
2. **Classify** (`classify.py`) — fuse two independent signals into a
   `(slot, confidence)`: a **filename prior** (`kick_01.wav` is a strong hint) and
   **audio-feature heuristics** (kicks own the sub band; hats are short, bright,
   noisy; toms are tonal with a decaying body; …). The feature scorer lives behind
   one function so a trained model can replace it later without touching callers.
3. **Lay out** (`layout.py`) — map each slot to its General MIDI note; stack
   same-slot pieces as round-robins; hand overflow/unmapped slots ascending keys.
4. **Render** (`render/sfz.py`) — emit one `<region>` per piece. Pure function of
   the kit; carries nothing `kit.yaml` doesn't.

## The kit format

`kit.yaml` is the canonical artifact. An analyzed kick looks like this:

```yaml
schema_version: 1
name: detroit-01
prompt: gritty 90s Detroit techno, analog, overdriven, short decays
tags: [techno, analog, gritty]
provenance:
  tool: drumkitgen
  version: 0.1.0
  created: '2026-07-06T18:20:00Z'
  source: analyze          # analyze | generate | morph | corpus | mixed
pieces:
  - id: kick_01
    slot: kick
    file: samples/kick_01.wav
    classify_confidence: 0.87
    source:
      kind: analyzed        # analyzed | generated | synthesized | morphed | recombined
      origin: /path/to/original/kick_01.wav
    analysis:
      duration_s: 0.5
      peak_dbfs: -1.0
      rms_dbfs: -14.2
      spectral_centroid_hz: 430.0
      spectral_flatness: 0.001
      fundamental_hz: 58.0
      attack_time_s: 0.002
      decay_time_s: 0.19
      sub_energy_ratio: 0.61
      band_energy: {sub: 0.61, low: 0.22, lowmid: 0.11, highmid: 0.05, high: 0.01}
    playback:
      root_key: 36          # General MIDI kick
```

The `.sfz` is generated from it — one region per piece, mapped to `root_key`,
same-key pieces cycled as round-robins:

```sfz
<region> // kick_01 [kick]
sample=kick_01.wav
key=36
pitch_keycenter=36
```

### Why `kit.yaml` is the source of truth

SFZ (and Drum Rack, and Decent Sampler) can't hold a prompt, a provenance chain,
or a feature vector — but morphing, selection, and regeneration all need exactly
those. So they live in `kit.yaml`, and the sampler formats stay disposable render
targets. A generated piece fills the *same* `Piece` as an analyzed one, differing
only in `source.kind` and the transform `chain` — which is what lets future
producers plug into the spine without reshaping it.

## Slot taxonomy

Slots are anchored to the **General MIDI** percussion map, so a rendered kit lands
on the keys any DAW drum instrument expects:

| slot | GM note | | slot | GM note |
|---|---|---|---|---|
| `kick` | 36 | | `hat_open` | 46 |
| `rimshot` | 37 | | `tom_low` / `tom_mid` / `tom_high` | 41 / 45 / 50 |
| `snare` | 38 | | `crash` | 49 |
| `clap` | 39 | | `ride` | 51 |
| `hat_closed` / `hat_pedal` | 42 / 44 | | `perc` / `fx` | overflow (60+) |

## Roadmap

Detailed, fleshed-out plans live in **[ROADMAP.md](ROADMAP.md)** — the next focus
is a **variation & randomization** loop (seeded, reproducible rolls; per-slot
locks + mutation; an interactive terminal explorer built on the audition pad).

The spine is built so each of these is an additive *producer* or *render target*,
not a rewrite:

- [x] **Analysis + kit spine** — analyze existing WAVs → `kit.yaml` + `.sfz`
- [x] **Remix / synthesis "beef-up" (first cut)** — `drumkitgen remix` re-voices a
      kit with slot-aware DSP (sub-layer, saturation, tune) and records the
      transform chain in provenance
- [ ] **Variation & randomization** *(next — see [ROADMAP.md](ROADMAP.md))* —
      seeded/reproducible rolls, per-slot locks + mutation, and an interactive
      terminal explorer (`explore`) + batch generator (`vary`)
- [ ] **API generation** — prompt → hosted text-to-audio → classified one-shots
- [ ] **Local generation** — self-hosted models (e.g. Stable Audio Open) for
      overnight bulk generation of one-shots
- [ ] **More synthesis** — noise-transient layering, transient shaping,
      multiband processing, stereo-preserving chains
- [ ] **Corpus recombination** — index a tagged sample library; filter and layer
      by analysis features to build kits from source material
- [ ] **Kit morphing** — interpolate between two analyzed kits in feature space
- [ ] **More render targets** — Decent Sampler, Ableton Drum Rack, plain mapped folder
- [ ] **Trained slot classifier** — replace the feature heuristics behind the
      existing `classify()` interface

## Design principles

1. **The kit spine is the product.** Every sound source is a producer that drops
   pieces into one shared kit definition.
2. **`kit.yaml` is canonical; render targets are generated.** Never let a sampler
   format become the source of truth.
3. **Analysis is foundational.** It's load-bearing for classification, corpus
   organization, and morphing — built from v1, not bolted on.
4. **Synthesis is a post-processor.** A "beef-up" stage that runs *after* a sample
   exists, never the primary source.
5. **Non-destructive.** One-shots are copied verbatim; gain/tune/pan live in
   metadata, so the audio stays pristine and re-renderable.

## Project layout

```
src/drumkitgen/
├── model.py         # pydantic schema — the canonical Kit / Piece / Analysis
├── slots.py         # slot taxonomy + General MIDI mapping
├── audio.py         # soundfile/numpy I/O helpers
├── analysis.py      # feature extraction (librosa)
├── classify.py      # slot classifier: filename prior + feature heuristics
├── layout.py        # assign MIDI keys to pieces
├── ingest.py        # folder -> Kit -> disk (the pack pipeline)
├── remix.py         # transform producer: re-voice a kit with slot-aware DSP
├── audition.py      # interactive terminal drum pad (keys -> samples)
├── report.py        # self-contained SVG HTML report (stats + before/after)
├── render/sfz.py    # Kit -> .sfz
├── io_yaml.py       # Kit <-> kit.yaml
├── synth_probe.py   # DSP one-shot synths (demo kit, test fixtures)
└── cli.py           # `drumkitgen` command
```

## Development

```bash
pip install -e ".[loudness,dev]"
pytest
```

The test suite synthesizes known drums (`synth_probe.py`) and asserts the analyzer
measures them correctly and the classifier recovers their slots — so classifier
tuning has a regression net.

## License

MIT — see [LICENSE](LICENSE).

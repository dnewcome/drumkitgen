# drumkitgen roadmap — planned features

This is the detailed backlog. The README has the one-line checklist; this file is
where features are fleshed out before they're built. Everything below the
"Shipped" line is **planned, not implemented** — proposed CLI signatures, key
bindings, and schema notes are design intent, not current behavior.

Legend: `[x]` shipped · `[ ]` planned · `[~]` partial

---

## Shipped

- [x] **Kit spine** — analyze a folder of one-shots → classify into GM slots →
  canonical `kit.yaml` + rendered `.sfz`. `kit.yaml` is the source of truth.
- [x] **`remix` producer** — re-voice a kit with slot-aware DSP (sub-layer,
  saturation, tune); every step logged in `source.chain`.
- [x] **`audition` pad** — interactive terminal drum pad, keys → samples.
- [x] **`report`** — self-contained SVG stats dashboard (feature map, spectral
  heatmaps, before/after change, waveforms, table).

---

## Focus: variation & randomization

The next chunk of work. Goal: **explore the space of kits fast** — roll variations
of a kit, lock what you like, mutate the rest, keep favorites, write out the
winners. Built on the `remix` producer and the `audition` engine we already have.

Deliberately in scope (chosen 2026-07-06): randomized DSP re-voicing, per-slot
locks + mutation, and a terminal-TUI explorer. Deliberately **deferred** (see
bottom): cross-kit recombination and evolutionary breeding.

### 1. Randomization engine (the primitive everything sits on)

A small, seeded, reproducible core — new module `variation.py`.

- [ ] **Seeded & reproducible.** One integer `seed` derives every random choice
  (numpy `default_rng(seed)`). A variation is fully defined by
  `(source kit, seed, amount, locks)` → regenerates byte-for-identical. This
  extends the existing "provenance chain is a reproducible recipe" principle.
- [ ] **`amount` knob (0..1, subtle → wild).** Scales the *width* of every sampled
  parameter range around its center. `0` = source untouched, `1` = full range.
- [ ] **Per-slot & per-parameter locks.** A locked slot keeps its source values
  (no randomization) — groovebox-style "hold the kick, roll the rest." Locks are
  a `set[Slot]` (v1) with room to grow to per-parameter locks.
- [ ] **Per-slot parameter ranges.** A tunable table of musical bounds so random
  stays *usable*, e.g.

  | slot | drive | sub | tune (st) |
  |------|-------|-----|-----------|
  | kick | 0.2–0.7 | 0.4–0.9 | −3 … +1 |
  | snare / clap | 0.3–0.8 | — | −2 … +2 |
  | hats / cymbals | 0.0–0.3 | — | −1 … +1 |
  | perc | 0.2–0.6 | 0.0–0.3 | −2 … +2 |

  These are first-guess ranges to be tuned against real kits (open question below).
- [ ] **Mutation.** `mutate(recipe, seed, sigma)` — Gaussian perturbation of the
  *unlocked* params around a starting point, clamped to the ranges. This is how
  "nudge a favorite" works without a full re-roll.

Proposed surface:

```python
spec = RandomSpec(amount=0.5, locks={Slot.KICK}, seed=4471)
recipe = sample_recipe(source_kit, spec)          # -> a concrete RemixRecipe
varied = remix_kit(source_kit, out, recipe)       # reuse the existing producer
child  = mutate(recipe, seed=4472, sigma=0.15)    # perturb around it
```

### 2. Randomized DSP re-voicing

Extend the `remix` producer so its recipe can be *sampled* rather than only
hand-set.

- [ ] **Per-slot recipe overrides.** `RemixRecipe` grows an explicit
  `per_slot: dict[Slot, SlotParams]` so a roll can drive the kick hard while
  leaving hats crisp — today the slot policy is baked into `process_piece`.
- [ ] **`sample_recipe(kit, spec)`** — draws a concrete `RemixRecipe` from the
  ranges, seed, amount, and locks. Pure; no audio touched.
- [ ] **Musical guards.** Keep rolls from going degenerate (e.g. never tune a hat
  ±12 st, cap total gain, avoid sub-layer on non-kicks unless asked).

### 3. Interactive variation explorer — `drumkitgen explore` (TUI)

Built on the `audition` pad: same key→sample map and playback engine, plus a
generation loop. Proposed command and bindings:

```
drumkitgen explore <kit-or-folder> [--seed S] [--amount A] [--lock kick,snare]
```

```
 kit: metalhead      gen 3      seed 4471      amount 0.5      locks: kick
 ─────────────────────────────────────────────────────────────────────────
 a kick    s snare   d clap    f snare   g hat …          (play a pad)
 ─────────────────────────────────────────────────────────────────────────
 [space] re-roll all      [1-9] re-roll one pad     [L]+key lock/unlock a pad
 [k] keep favorite (★2)   [m] mutate a favorite     [+/-] amount
 [w] write current kit    [r] report vs source      [?] help   [Ctrl-C] quit
```

- [ ] **Re-roll** all (new seed) or a single pad/slot; hear it instantly.
- [ ] **Locks** toggled live; locked pads show a marker and never change on roll.
- [ ] **Keep** snapshots the current `(seed, recipe)` as a favorite; **mutate**
  perturbs a favorite into the new current.
- [ ] **Write** the current variation as a real kit (samples + `kit.yaml` +
  `.sfz`), provenance recording the seed/amount/locks.
- [ ] **Report** shells to the `report` builder for a source-vs-current diff.
- [ ] **Playback of in-memory rolls.** The `rt` (sounddevice) engine can play
  freshly-processed buffers directly; the subprocess fallback writes temp WAVs
  per roll. (Open question: require `[audition]` for `explore`, or always temp-file?)

### 4. Batch sibling — `drumkitgen vary` (non-interactive)

Same engine, headless — for generating many at once (the "GBs overnight" case).

```
drumkitgen vary <kit> --count 16 --seed 100 --amount 0.6 --lock kick --out out/vars
```

- [ ] Writes `out/vars/01..16/` (seeds `100..115`) + one comparison `report.html`
  to browse, then audition the keepers.

---

## Schema / architecture notes

- **Provenance of a variation.** Each varied piece's `source.chain` already logs
  its concrete transforms. Add the kit-level knobs so a whole variation is
  reproducible. *Open:* extend `Provenance` with optional `seed` / `amount` /
  `locks`, vs. stash them in `notes`. Leaning toward first-class fields.
- **`source.kind` / `provenance.source`.** A rolled kit is still `kind="remixed"`
  per piece; kit-level `provenance.source` gains `"varied"`.
- **Reuse, don't fork.** `sample_recipe` → `remix_kit` (existing) → `write_kit`
  (existing). The explorer reuses `audition`'s engine and keymap. Net new code is
  the randomization core + the TUI loop.
- **Non-destructive, as always.** Sources are read pristine; rolls write new files.

## Open questions

1. **Range tuning.** The per-slot ranges above are guesses — they need a pass
   against real kits so "amount 0.5" reliably sounds good, not broken.
2. **Re-roll granularity.** A slot can hold several pads (2 kicks). Does `[1-9]`
   re-roll one *pad* or one *slot*? (Proposing: one pad; the slot's other pads
   are independent rolls.)
3. **`explore` audio path.** Require the `[audition]` extra (sounddevice) for
   gapless in-memory rolls, or always fall back to per-roll temp WAVs?
4. **Favorites persistence.** Keep favorites in-session only, or write a
   `favorites.yaml` (seeds + recipes) you can reload later?

---

## Deferred (captured, consciously out of scope for now)

- **Cross-kit recombination** — assemble a kit by pulling each slot from different
  source kits / a tagged corpus. Powerful, but needs the corpus-indexing layer
  first; revisit after the single-kit variation loop feels good.
- **Evolutionary breeding** — rate variations, then *crossover* favorites (not
  just mutate) with a fitness signal, breeding toward a target. `explore`'s
  keep + mutate is the seed of this; full crossover/fitness is a later layer.

## Longer horizon (from the README roadmap)

- [ ] **API generation** — prompt → hosted text-to-audio → classify → into the spine.
- [ ] **Local generation** — self-hosted models for overnight bulk one-shots.
- [ ] **More synthesis** — noise-transient layering, transient shaping, multiband,
  stereo-preserving chains (drops the current mono fold-down in `remix`).
- [ ] **Corpus recombination** — index a tagged library; filter/layer by features.
- [ ] **Kit morphing** — interpolate between two analyzed kits in feature space.
- [ ] **More render targets** — Decent Sampler, Ableton Drum Rack, mapped folder.
- [ ] **Trained slot classifier** — replace the heuristics behind `classify()`.

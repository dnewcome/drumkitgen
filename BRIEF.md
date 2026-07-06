# drumkitgen — kickoff brief

- **Problem:** Assembling drum kits for my tracks is manual and ad hoc. I want prompt-driven, multi-source kit creation with metadata rich enough to key into larger production setups.
- **Done looks like:** Point it at a folder of WAVs → get back a packaged, playable kit (one-shots + `.sfz` + a metadata sidecar) I can drag into a DAW.
- **Not now:** Local gen models, API gen, corpus recombination, kit morphing, and synthesis beef-up — all real, all deferred until the spine exists and the schema is proven.
- **First slice:** Ingest a folder of WAVs → analyze + classify each into a slot (kick/snare/hat/…) → emit `.sfz` + a canonical metadata file (`kit.yaml`).
- **Open question:** Will the metadata schema survive later sources (gen/morph/corpus) plugging in? And how reliable is auto slot-classification from audio features alone — do heuristics (spectral centroid, ZCR, duration, sub energy) suffice, or is a small trained classifier needed?

## Architectural commitments

1. **The kit spine is the product.** A kit = folder of one-shots + `.sfz` + a metadata sidecar. Every sound source (local gen, API gen, corpus recombination, morphing, synthesis) is just a *producer* that drops pieces into this spine.
2. **`kit.yaml` is the source of truth; `.sfz` is a render target.** SFZ can't hold prompts, morph params, provenance, or feature vectors. The canonical metadata lives in `kit.yaml`; `.sfz` (and later Decent Sampler, Ableton Drum Rack, …) are generated *from* it. This keeps us format-agnostic for bigger setups.
3. **Analysis is foundational.** Load-bearing for slot classification, corpus organization, and morphing — built from v1, not bolted on.
4. **Synthesis is a post-processor.** A "beef-up" stage (sub sine under a kick, noise transient on a hat) that runs *after* a sample exists — never the primary source.

## Build order

Spine first (analyze → classify → SFZ + metadata on existing WAVs), then plug in sources: API gen → local gen → corpus recombination → morph → synthesis beef-up.

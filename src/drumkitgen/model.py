"""The canonical kit schema — the source of truth for everything downstream.

``kit.yaml`` is this model serialized. Render targets (``.sfz`` and friends) are
*generated from* it and never hold anything this model can't. That inversion is
deliberate: SFZ can't carry a prompt, a provenance chain, or a feature vector,
so those live here and the sampler formats stay disposable.

Designed to survive future producers plugging in: a generated piece fills the
same ``Piece`` as an analyzed one, differing only in ``source`` and (optionally)
the transforms recorded in ``source.chain``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .slots import Slot

#: Bump when a change to these models is not backward-compatible. Readers should
#: check this before trusting a ``kit.yaml`` written by another version.
SCHEMA_VERSION = 1


class Analysis(BaseModel):
    """Objective, measured descriptors of a single one-shot.

    Everything here is derived from the audio itself (see :mod:`.analysis`); it
    is what the classifier reasons over and what later morph/selection logic
    will query. Kept flat and numeric so it is trivial to diff, sort, and embed.
    """

    duration_s: float
    sample_rate: int
    channels: int

    # Levels
    peak_dbfs: float
    rms_dbfs: float
    crest_factor_db: float
    loudness_lufs: Optional[float] = None  # best-effort; None for very short hits

    # Spectral shape
    spectral_centroid_hz: float
    spectral_bandwidth_hz: float
    spectral_rolloff_hz: float
    spectral_flatness: float  # 0 = tonal, 1 = noise-like
    zero_crossing_rate: float

    # Pitch (meaningful mostly for tonal hits: kick, toms)
    fundamental_hz: Optional[float] = None

    # Envelope
    attack_time_s: float
    decay_time_s: float  # peak -> -20 dB

    # Energy distribution: normalized fraction of spectral energy per band.
    band_energy: dict[str, float] = Field(default_factory=dict)
    sub_energy_ratio: float = 0.0  # fraction of energy below 120 Hz


class SourceInfo(BaseModel):
    """Where a piece came from and what was done to it — its provenance.

    ``kind`` is the producer type; this is the field that distinguishes an
    analyzed sample from a generated / synthesized / morphed / recombined one.
    ``chain`` records ordered transforms (e.g. later synthesis beef-up steps)
    so a piece can, in principle, be regenerated from its recipe.
    """

    kind: str = "analyzed"  # analyzed | generated | synthesized | remixed | morphed | recombined
    origin: Optional[str] = None  # source path, model id, or parent-kit reference
    prompt: Optional[str] = None  # per-piece prompt, if a generator made it
    chain: list[str] = Field(default_factory=list)


class Playback(BaseModel):
    """How a piece should be played back — non-destructive render hints.

    Gain/tune/pan live here rather than being baked into the audio so the
    one-shots stay pristine and re-renderable. The renderer maps these onto
    the target format's opcodes.
    """

    root_key: int  # MIDI note this piece is mapped to
    tune_cents: int = 0
    gain_db: float = 0.0
    pan: float = 0.0


class Piece(BaseModel):
    """One one-shot in a kit: a file, its slot, its measurements, its playback."""

    id: str
    slot: Slot
    file: str  # path relative to the kit directory, e.g. "samples/kick_01.wav"
    classify_confidence: float = 0.0
    source: SourceInfo = Field(default_factory=SourceInfo)
    analysis: Optional[Analysis] = None
    playback: Playback


class Provenance(BaseModel):
    """Kit-level record of what produced this kit and when."""

    tool: str = "drumkitgen"
    version: str
    created: datetime
    source: str = "analyze"  # analyze | generate | morph | corpus | mixed


class Kit(BaseModel):
    """A complete kit: metadata + the pieces. This is what ``kit.yaml`` holds."""

    schema_version: int = SCHEMA_VERSION
    name: str
    prompt: Optional[str] = None  # the heuristic prompt that defines/created the kit
    tags: list[str] = Field(default_factory=list)
    bpm_hint: Optional[float] = None
    key_hint: Optional[str] = None
    provenance: Provenance
    notes: str = ""
    pieces: list[Piece] = Field(default_factory=list)

    def by_slot(self, slot: Slot) -> list[Piece]:
        """All pieces assigned to ``slot``."""
        return [p for p in self.pieces if p.slot == slot]

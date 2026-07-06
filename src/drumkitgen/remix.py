"""Remix: the first *transform producer* — take an existing kit and re-voice it.

This is the roadmap's "synthesis beef-up" stage in its first form: it reads each
piece's *pristine* original, applies slot-aware DSP (sub-weight under kicks,
saturation grit, optional tuning), writes a new one-shot, and records every step
in ``source.chain``. The source kit is never touched — a remix is a derivative,
and its provenance says exactly how to reproduce it.

The processed audio is then *re-analyzed*, so the new ``kit.yaml`` reflects what
the sound actually became (e.g. a beefed kick's sub-energy ratio visibly rises).
Everything here is pure numpy/scipy/librosa — no new dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from . import __version__
from .analysis import analyze
from .audio import load_mono
from .ingest import _slug, _unique, _unique_filename
from .layout import assign_keys
from .model import Kit, Piece, Playback, Provenance, SourceInfo
from .render import render_sfz
from .slots import HAT_SLOTS, Slot

# Slots that should stay crisp/airy — they get only a light touch of the drive.
_GENTLE_SLOTS = frozenset({*HAT_SLOTS, Slot.RIDE, Slot.CRASH})


@dataclass
class RemixRecipe:
    """Global character knobs for a remix. Slot-aware policy is applied on top."""

    drive: float = 0.5   # 0..1 saturation amount (grit / warmth)
    sub: float = 0.6     # 0..1 sub-sine weight added under kicks
    tune: float = 0.0    # semitones to pitch-shift the whole kit
    name: str = "remix"


# --- DSP primitives ----------------------------------------------------------


def _peak(y: np.ndarray) -> float:
    return float(np.max(np.abs(y))) or 1.0


def saturate(y: np.ndarray, drive: float) -> np.ndarray:
    """Soft-clip via tanh, preserving the input's peak level.

    ``drive`` maps to pre-gain, so louder input drives harder into the curve —
    which is what gives saturation its program-dependent, musical character.
    """
    if drive <= 0:
        return y
    pre = 1.0 + drive * 9.0
    out = np.tanh(y * pre)
    return (out / _peak(out) * _peak(y)).astype(np.float32)


def sub_layer(y: np.ndarray, sr: int, freq: float, amount: float, decay: float = 0.18) -> np.ndarray:
    """Add a decaying sine under a hit — synthetic sub weight for a kick.

    The sine is aligned to the start of the sample (where a kick's transient
    lives) and scaled relative to the hit's own peak, so it beefs without
    swamping.
    """
    if amount <= 0:
        return y
    n = y.size
    t = np.arange(n) / sr
    sine = np.sin(2 * np.pi * freq * t) * np.exp(-t / decay)
    sine = sine.astype(np.float32) * amount * _peak(y)
    return y + sine


def tune(y: np.ndarray, sr: int, semitones: float) -> np.ndarray:
    """Pitch-shift while preserving length (phase vocoder, via librosa)."""
    if abs(semitones) < 1e-3:
        return y
    return librosa.effects.pitch_shift(y, sr=sr, n_steps=semitones).astype(np.float32)


def _safe_norm(y: np.ndarray, ceiling: float = 0.95) -> np.ndarray:
    """Scale down only if the signal would clip; never boost quiet hits."""
    p = _peak(y)
    return (y * (ceiling / p)).astype(np.float32) if p > ceiling else y.astype(np.float32)


# --- Per-piece processing ----------------------------------------------------


def process_piece(y: np.ndarray, sr: int, slot: Slot, f0: float | None, recipe: RemixRecipe):
    """Apply the slot-aware transform chain. Returns ``(audio, chain)``."""
    chain: list[str] = []

    y = tune(y, sr, recipe.tune)
    if recipe.tune:
        chain.append(f"tune({recipe.tune:+g}st)")

    if slot is Slot.KICK and recipe.sub > 0:
        f = float(np.clip(f0 or 50.0, 30.0, 80.0))
        y = sub_layer(y, sr, f, recipe.sub)
        chain.append(f"sub_layer({f:.0f}Hz,{recipe.sub:g})")

    drive = recipe.drive * (0.4 if slot in _GENTLE_SLOTS else 1.0)
    if drive > 0:
        y = saturate(y, drive)
        chain.append(f"saturate({drive:.2f})")

    return _safe_norm(y), chain


# --- Kit-level remix ---------------------------------------------------------


def remix_kit(src: Kit, out_dir: str | Path, recipe: RemixRecipe, prompt: str | None = None) -> Kit:
    """Produce a re-voiced derivative of ``src`` and write it to ``out_dir``.

    Reads each piece's pristine ``source.origin``, processes it, writes a new
    24-bit one-shot, re-analyzes it, and stamps provenance. Slots are inherited
    from the source (we already know what each sound is), not re-classified.
    """
    out = Path(out_dir)
    (out / "samples").mkdir(parents=True, exist_ok=True)

    pieces: list[Piece] = []
    used_ids: set[str] = set()
    used_names: set[str] = set()

    for piece in src.pieces:
        if not piece.source.origin:
            continue
        y, sr, channels = load_mono(piece.source.origin)
        f0 = piece.analysis.fundamental_hz if piece.analysis else None
        y2, chain = process_piece(y, sr, piece.slot, f0, recipe)

        dest_name = _unique_filename(f"{piece.id}.wav", used_names)
        sf.write(out / "samples" / dest_name, y2, sr, subtype="PCM_24")

        pieces.append(
            Piece(
                id=_unique(piece.id, used_ids),
                slot=piece.slot,
                file=f"samples/{dest_name}",
                classify_confidence=piece.classify_confidence,
                source=SourceInfo(
                    kind="remixed",
                    origin=piece.source.origin,
                    chain=chain,
                ),
                analysis=analyze(y2, sr, channels),
                playback=Playback(root_key=piece.playback.root_key),
            )
        )

    assign_keys(pieces)

    kit = Kit(
        name=recipe.name,
        prompt=prompt or (f"remix of {src.name}: {_recipe_desc(recipe)}"),
        tags=sorted({*src.tags, "remix"}),
        provenance=Provenance(
            version=__version__,
            created=datetime.now(timezone.utc),
            source="mixed",
        ),
        notes=f"remixed from '{src.name}' — {_recipe_desc(recipe)}",
        pieces=pieces,
    )
    from .io_yaml import write as write_yaml

    write_yaml(kit, out / "kit.yaml")
    (out / f"{_slug(kit.name)}.sfz").write_text(render_sfz(kit), encoding="utf-8")
    return kit


def _recipe_desc(r: RemixRecipe) -> str:
    parts = [f"drive={r.drive:g}", f"sub={r.sub:g}"]
    if r.tune:
        parts.append(f"tune={r.tune:+g}st")
    return ", ".join(parts)

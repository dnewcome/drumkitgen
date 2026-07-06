"""Low-level audio I/O helpers. Thin wrapper over soundfile + numpy."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import soundfile as sf

#: Extensions we treat as importable one-shots.
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac", ".ogg"}


def to_db(x: float, floor_db: float = -120.0) -> float:
    """Amplitude ratio -> dBFS, clamped so silence maps to ``floor_db``."""
    if x <= 0.0:
        return floor_db
    return max(floor_db, 20.0 * math.log10(x))


def load_mono(path: str | Path) -> tuple[np.ndarray, int, int]:
    """Load an audio file as float32 mono.

    Returns ``(mono_signal, sample_rate, original_channel_count)``. Downmix is a
    plain channel mean — fine for analysis; the original file is what actually
    ships in the kit, so no fidelity is lost by analyzing a mono fold-down.
    """
    data, sr = sf.read(str(path), always_2d=True, dtype="float32")
    channels = int(data.shape[1])
    mono = data.mean(axis=1).astype(np.float32)
    return mono, int(sr), channels


def find_audio(directory: str | Path) -> list[Path]:
    """Return sorted audio files directly under ``directory`` (non-recursive)."""
    d = Path(directory)
    return sorted(
        p for p in d.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    )

"""Feature extraction: a mono signal in, an :class:`Analysis` out.

These descriptors are the substrate the classifier reasons over and the
handles future selection/morphing will grab. The goal is robustness on *short,
transient* one-shots (a 40 ms hat, a 4 s crash) — which is where naive spectral
code tends to break — so FFT sizes adapt to length and every fragile estimate
(f0, LUFS) degrades to ``None`` instead of throwing.
"""

from __future__ import annotations

import warnings

import librosa
import numpy as np

from .audio import to_db
from .model import Analysis

#: Spectral bands (Hz) used for the normalized energy profile. The ``sub`` band
#: is what most cleanly separates kicks/toms from everything else.
BANDS: dict[str, tuple[float, float]] = {
    "sub": (20.0, 120.0),
    "low": (120.0, 500.0),
    "lowmid": (500.0, 2000.0),
    "highmid": (2000.0, 6000.0),
    "high": (6000.0, 20000.0),
}

SUB_HZ = 120.0


def _fft_size(n: int) -> int:
    """Largest power-of-two FFT <= min(n, 2048), floored at 256."""
    if n <= 256:
        return 256
    size = 256
    while size * 2 <= min(n, 2048):
        size *= 2
    return size


def _envelope_times(y: np.ndarray, sr: int) -> tuple[float, float]:
    """Attack (start->peak) and decay (peak->-20 dB) of the amplitude envelope."""
    if y.size == 0:
        return 0.0, 0.0
    env = np.abs(y)
    # Smooth over ~3 ms so a single noisy sample doesn't define the peak.
    win = max(1, int(sr * 0.003))
    if win > 1:
        env = np.convolve(env, np.ones(win, dtype=np.float32) / win, mode="same")
    peak_idx = int(np.argmax(env))
    peak = float(env[peak_idx])
    attack = peak_idx / sr
    if peak <= 0.0:
        return attack, 0.0
    thresh = peak * 0.1  # -20 dB
    tail = env[peak_idx:]
    below = np.flatnonzero(tail < thresh)
    decay = (below[0] / sr) if below.size else (tail.size / sr)
    return attack, decay


def _estimate_f0(y: np.ndarray, sr: int) -> float | None:
    """Median voiced f0 via pYIN, or ``None`` when nothing tonal is found."""
    if y.size < 512:
        return None
    frame = 2048
    padded = y if y.size >= frame else np.pad(y, (0, frame - y.size))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            f0, voiced, _ = librosa.pyin(
                padded, fmin=30.0, fmax=1000.0, sr=sr, frame_length=frame
            )
    except Exception:
        return None
    vals = f0[np.isfinite(f0) & (voiced > 0.5)]
    if vals.size < 3:
        return None
    return float(np.median(vals))


def _loudness_lufs(y: np.ndarray, sr: int) -> float | None:
    """Integrated LUFS via pyloudnorm, if installed and the hit is long enough."""
    try:
        import pyloudnorm as pyln
    except Exception:
        return None
    # pyloudnorm's gating block is 400 ms; shorter signals can't be measured.
    if y.size < int(sr * 0.4):
        return None
    try:
        meter = pyln.Meter(sr)
        value = float(meter.integrated_loudness(y.astype(np.float64)))
    except Exception:
        return None
    return value if np.isfinite(value) else None


def analyze(y: np.ndarray, sr: int, channels: int = 1) -> Analysis:
    """Extract an :class:`Analysis` from a mono float32 signal."""
    y = np.ascontiguousarray(y, dtype=np.float32)
    n = y.size
    duration = n / sr if sr else 0.0

    peak = float(np.max(np.abs(y))) if n else 0.0
    rms = float(np.sqrt(np.mean(np.square(y)))) if n else 0.0
    peak_db = to_db(peak)
    rms_db = to_db(rms)

    n_fft = _fft_size(n)
    y_spec = y if n >= n_fft else np.pad(y, (0, n_fft - n))
    hop = max(64, n_fft // 4)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        centroid = float(
            np.mean(librosa.feature.spectral_centroid(y=y_spec, sr=sr, n_fft=n_fft, hop_length=hop))
        )
        bandwidth = float(
            np.mean(librosa.feature.spectral_bandwidth(y=y_spec, sr=sr, n_fft=n_fft, hop_length=hop))
        )
        rolloff = float(
            np.mean(librosa.feature.spectral_rolloff(y=y_spec, sr=sr, n_fft=n_fft, hop_length=hop, roll_percent=0.85))
        )
        flatness = float(
            np.mean(librosa.feature.spectral_flatness(y=y_spec, n_fft=n_fft, hop_length=hop))
        )
        zcr = float(np.mean(librosa.feature.zero_crossing_rate(y_spec, frame_length=n_fft, hop_length=hop)))

        stft = np.abs(librosa.stft(y_spec, n_fft=n_fft, hop_length=hop)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    total = float(stft.sum()) + 1e-12
    band_energy: dict[str, float] = {}
    for name, (lo, hi) in BANDS.items():
        mask = (freqs >= lo) & (freqs < hi)
        band_energy[name] = float(stft[mask].sum() / total)
    sub_ratio = band_energy.get("sub", 0.0)

    attack, decay = _envelope_times(y, sr)

    return Analysis(
        duration_s=round(duration, 5),
        sample_rate=sr,
        channels=channels,
        peak_dbfs=round(peak_db, 2),
        rms_dbfs=round(rms_db, 2),
        crest_factor_db=round(peak_db - rms_db, 2),
        loudness_lufs=_round_opt(_loudness_lufs(y, sr), 2),
        spectral_centroid_hz=round(centroid, 1),
        spectral_bandwidth_hz=round(bandwidth, 1),
        spectral_rolloff_hz=round(rolloff, 1),
        spectral_flatness=round(flatness, 5),
        zero_crossing_rate=round(zcr, 5),
        fundamental_hz=_round_opt(_estimate_f0(y, sr), 2),
        attack_time_s=round(attack, 5),
        decay_time_s=round(decay, 5),
        band_energy={k: round(v, 5) for k, v in band_energy.items()},
        sub_energy_ratio=round(sub_ratio, 5),
    )


def _round_opt(x: float | None, ndigits: int) -> float | None:
    return round(x, ndigits) if x is not None else None

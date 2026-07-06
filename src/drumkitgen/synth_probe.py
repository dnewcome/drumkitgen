"""Tiny DSP synthesizers for one-shot drums.

Two jobs today, one tomorrow:

* **Demo** — ``drumkitgen demo`` needs no samples on disk; it synthesizes a
  starter kit so a new user (or a test) can exercise the whole pipeline in one
  command.
* **Fixtures** — the test suite generates known drums and asserts the classifier
  recovers them.
* **Foreshadow** — these are the seed of the eventual synthesis "beef-up" stage
  (sub sine under a kick, noise transient on a hat). They are intentionally
  simple, not production drum design.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100


def _env(n: int, attack: float, decay: float, sr: int = SR) -> np.ndarray:
    """Percussive AD envelope, linear attack then exponential decay."""
    t = np.arange(n) / sr
    a = max(attack, 1e-4)
    env = np.where(t < a, t / a, np.exp(-(t - a) / max(decay, 1e-4)))
    return env.astype(np.float32)


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def kick(dur: float = 0.5, sr: int = SR) -> np.ndarray:
    n = int(dur * sr)
    t = np.arange(n) / sr
    # Pitch sweep 120 -> 45 Hz gives the classic "thump + body".
    f = 45 + (120 - 45) * np.exp(-t / 0.03)
    phase = 2 * np.pi * np.cumsum(f) / sr
    body = np.sin(phase) * _env(n, 0.001, 0.16, sr)
    click = _rng(1).standard_normal(n).astype(np.float32) * _env(n, 0.0, 0.004, sr) * 0.4
    return _norm(body + click)


def snare(dur: float = 0.3, sr: int = SR) -> np.ndarray:
    n = int(dur * sr)
    t = np.arange(n) / sr
    tone = (np.sin(2 * np.pi * 180 * t) + np.sin(2 * np.pi * 330 * t)) * _env(n, 0.001, 0.09, sr)
    # Band-limit the snare "buzz" (~250 Hz–5 kHz) so its centroid sits where a
    # real snare's does, rather than reading as bright white noise.
    buzz = _highpass(_lowpass(_rng(2).standard_normal(n).astype(np.float32), 5000, sr), 250, sr)
    noise = buzz * _env(n, 0.001, 0.12, sr)
    return _norm(0.5 * tone + 1.2 * noise)


def clap(dur: float = 0.4, sr: int = SR) -> np.ndarray:
    n = int(dur * sr)
    out = np.zeros(n, dtype=np.float32)
    noise = _rng(3).standard_normal(n).astype(np.float32)
    # Three fast bursts + a diffuse tail: the hallmark clap "smear".
    for offset in (0.0, 0.010, 0.021):
        start = int(offset * sr)
        seg = np.zeros(n, dtype=np.float32)
        seg[start:] = noise[: n - start] * _env(n - start, 0.0005, 0.012, sr)
        out += seg
    out += noise * _env(n, 0.031, 0.05, sr) * 0.5
    return _norm(_highpass(out, 800, sr))


def hat(dur: float | None = None, open_: bool = False, sr: int = SR) -> np.ndarray:
    decay = 0.4 if open_ else 0.03
    # Give the signal enough length for its decay tail to actually breathe:
    # a closed hat is a tick, an open hat rings.
    if dur is None:
        dur = 0.6 if open_ else 0.09
    n = int(dur * sr)
    noise = _rng(4 if not open_ else 5).standard_normal(n).astype(np.float32)
    return _norm(_highpass(noise, 7000, sr) * _env(n, 0.0002, decay, sr))


def tom(dur: float = 0.35, freq: float = 110.0, sr: int = SR) -> np.ndarray:
    n = int(dur * sr)
    t = np.arange(n) / sr
    f = freq * (1 + 0.4 * np.exp(-t / 0.02))  # slight pitch drop
    phase = 2 * np.pi * np.cumsum(f) / sr
    return _norm(np.sin(phase) * _env(n, 0.001, 0.13, sr))


def crash(dur: float = 1.6, sr: int = SR) -> np.ndarray:
    n = int(dur * sr)
    noise = _rng(6).standard_normal(n).astype(np.float32)
    return _norm(_highpass(noise, 4000, sr) * _env(n, 0.002, 0.7, sr))


def _highpass(x: np.ndarray, cutoff: float, sr: int) -> np.ndarray:
    """One-pole high-pass — cheap, dependency-free brightening."""
    rc = 1.0 / (2 * np.pi * cutoff)
    alpha = rc / (rc + 1.0 / sr)
    y = np.zeros_like(x)
    prev_x = 0.0
    prev_y = 0.0
    for i, xi in enumerate(x):
        prev_y = alpha * (prev_y + xi - prev_x)
        y[i] = prev_y
        prev_x = xi
    return y


def _lowpass(x: np.ndarray, cutoff: float, sr: int) -> np.ndarray:
    """One-pole low-pass — the mirror of ``_highpass``, for band-limiting."""
    dt = 1.0 / sr
    rc = 1.0 / (2 * np.pi * cutoff)
    alpha = dt / (rc + dt)
    y = np.zeros_like(x)
    prev = 0.0
    for i, xi in enumerate(x):
        prev = prev + alpha * (xi - prev)
        y[i] = prev
    return y


def _norm(x: np.ndarray, peak: float = 0.89) -> np.ndarray:
    m = float(np.max(np.abs(x))) or 1.0
    return (x / m * peak).astype(np.float32)


#: The demo/test kit: (filename, signal factory). Names carry no slot hints on
#: purpose for a couple of them, so the feature classifier gets a real workout.
DEMO_KIT: dict[str, callable] = {
    "kick_01.wav": kick,
    "snare_01.wav": snare,
    "clap_01.wav": clap,
    "hat_closed_01.wav": lambda: hat(open_=False),
    "hat_open_01.wav": lambda: hat(open_=True),
    "tom_low_01.wav": lambda: tom(freq=90),
    "tom_high_01.wav": lambda: tom(freq=200, dur=0.25),
    "crash_01.wav": crash,
}


def write_demo_samples(out_dir: str | Path, sr: int = SR) -> Path:
    """Synthesize the demo kit's raw one-shots into ``out_dir``. Returns it."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for filename, make in DEMO_KIT.items():
        sf.write(out / filename, make(), sr, subtype="PCM_16")
    return out

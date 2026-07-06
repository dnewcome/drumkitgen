"""Slot classification: given an :class:`Analysis` (and optionally a filename),
decide which drum slot a one-shot belongs to.

Two independent signals, deliberately kept separate so either can be swapped:

1. **Filename prior** — a folder named ``kick_01.wav`` is telling you something
   loud and clear. Cheap, high-precision when present, absent otherwise.
2. **Audio features** — hand-tuned heuristics over the spectral/envelope
   descriptors. This is the part the project's open question is about; it lives
   behind :func:`score_by_features` so a trained model can replace it wholesale
   without touching callers.

They are fused in :func:`classify`, which returns ``(slot, confidence)``.
Confidence reflects how strongly the winning slot beat the field *and* whether
the two signals agreed.
"""

from __future__ import annotations

import re

from .model import Analysis
from .slots import Slot

# --- 1. Filename prior -------------------------------------------------------

# Ordered most-specific first: "openhat" must win before the bare "hat" rule.
_NAME_PATTERNS: list[tuple[Slot, tuple[str, ...]]] = [
    (Slot.HAT_OPEN, ("openhat", "open_hat", "hihatopen", "hatopen", "ohh", "ohat", "hho")),
    (Slot.HAT_PEDAL, ("pedalhat", "pedal_hat", "hatpedal", "phh")),
    (Slot.HAT_CLOSED, ("closedhat", "closed_hat", "hihatclosed", "hatclosed", "chh", "chat", "hhc")),
    (Slot.RIMSHOT, ("rimshot", "rim", "sidestick", "side_stick", "xstick", "stick")),
    (Slot.CLAP, ("clap", "clp", "handclap")),
    (Slot.SNARE, ("snare", "snr", "sd", "rullet")),
    (Slot.KICK, ("kick", "kik", "bassdrum", "bass_drum", "bd", "bdrum")),
    (Slot.TOM_LOW, ("lowtom", "tomlow", "floortom", "tom_lo", "lotom")),
    (Slot.TOM_HIGH, ("hightom", "tomhigh", "hitom", "tom_hi")),
    (Slot.TOM_MID, ("midtom", "tommid", "tom_mid", "tom")),
    (Slot.CRASH, ("crash", "cymbal", "cym")),
    (Slot.RIDE, ("ride",)),
    (Slot.HAT_CLOSED, ("hihat", "hat", "hh")),  # bare hat -> assume closed
    (Slot.PERC, ("perc", "conga", "bongo", "shaker", "tamb", "cowbell", "clave", "block", "cabasa")),
    (Slot.FX, ("fx", "riser", "sweep", "impact", "uplifter", "downlifter", "noise", "drone")),
]


def slot_from_name(filename: str | None) -> Slot | None:
    """Best slot guess from a filename, or ``None`` if nothing matches."""
    if not filename:
        return None
    key = re.sub(r"[^a-z0-9]", "", filename.lower())
    for slot, needles in _NAME_PATTERNS:
        if any(n in key for n in needles):
            return slot
    return None


# --- 2. Feature heuristics ---------------------------------------------------


def score_by_features(a: Analysis) -> dict[Slot, float]:
    """Score each slot from measured features. Higher = more likely.

    Scores are non-negative and unnormalized; :func:`classify` normalizes them.
    The rules encode ordinary drum acoustics: kicks own the sub band, hats are
    short and bright and noisy, snares are mid and noisy, toms are tonal with a
    decaying body, cymbals are long and bright.
    """
    dur = a.duration_s
    cen = a.spectral_centroid_hz
    flat = a.spectral_flatness
    zcr = a.zero_crossing_rate
    sub = a.sub_energy_ratio
    decay = a.decay_time_s
    f0 = a.fundamental_hz
    be = a.band_energy
    high = be.get("high", 0.0) + be.get("highmid", 0.0)

    s: dict[Slot, float] = {slot: 0.0 for slot in Slot if slot != Slot.UNKNOWN}

    # KICK: dominant sub energy, low centroid, low pitched fundamental.
    s[Slot.KICK] += 3.0 * sub
    if cen < 800:
        s[Slot.KICK] += 1.2
    if f0 is not None and 30 <= f0 <= 130:
        s[Slot.KICK] += 1.0
    if decay < 0.6:
        s[Slot.KICK] += 0.3

    # HATS: short, very bright, noisy, little sub.
    bright_noise = min(cen / 6000.0, 2.0) + zcr * 4.0 + flat * 2.0
    if sub < 0.1:
        if decay < 0.13:
            s[Slot.HAT_CLOSED] += 1.5 + bright_noise
        elif decay < 0.6:
            s[Slot.HAT_OPEN] += 1.2 + bright_noise
    # Pedal hat is a quiet, very short, dark-ish closed hat — leave to name prior.

    # SNARE: mid centroid, noisy body, moderate decay, energy in low/high-mid.
    if 700 <= cen <= 4500 and flat > 0.02:
        s[Slot.SNARE] += 1.5 + 2.0 * (be.get("lowmid", 0.0) + be.get("highmid", 0.0))
    if 0.05 <= decay <= 0.5:
        s[Slot.SNARE] += 0.5

    # CLAP: like a snare but brighter/noisier and typically longer smear.
    if 1200 <= cen <= 5000 and flat > 0.03 and 0.08 <= decay <= 0.6:
        s[Slot.CLAP] += 1.3 + 1.5 * flat

    # TOMS: tonal (low flatness), pitched body, medium decay, modest sub.
    if f0 is not None and 60 <= f0 <= 500 and flat < 0.2 and decay > 0.08:
        base = 1.6
        if f0 < 130:
            s[Slot.TOM_LOW] += base
        elif f0 < 250:
            s[Slot.TOM_MID] += base
        else:
            s[Slot.TOM_HIGH] += base

    # CYMBALS: long, bright, sustained high-frequency energy.
    if decay > 0.6 and cen > 4000:
        s[Slot.CRASH] += 1.2 + 2.0 * high
        if f0 is not None and flat < 0.15:  # a tonal "ping" -> ride
            s[Slot.RIDE] += 1.6

    # PERC / FX: weak catch-alls so nothing scores exactly zero everywhere.
    s[Slot.PERC] += 0.4
    if dur > 1.2 and sub < 0.2:
        s[Slot.FX] += 0.6

    return s


# --- 3. Fusion ---------------------------------------------------------------


def classify(
    analysis: Analysis,
    filename: str | None = None,
    name_weight: float = 0.6,
) -> tuple[Slot, float]:
    """Fuse the filename prior and feature scores into ``(slot, confidence)``.

    When a filename hint exists it is trusted heavily (``name_weight``) but the
    features still get a vote, so an obviously-mislabeled file can be overridden
    and, more usefully, the confidence drops when the two disagree.
    """
    feat = score_by_features(analysis)
    total = sum(feat.values()) or 1.0
    feat_norm = {k: v / total for k, v in feat.items()}

    name_slot = slot_from_name(filename)
    combined = dict(feat_norm)
    if name_slot is not None:
        for slot in combined:
            combined[slot] *= (1.0 - name_weight)
        combined[name_slot] = combined.get(name_slot, 0.0) + name_weight

    best = max(combined, key=combined.get)
    confidence = combined[best]
    if confidence < 0.15 and name_slot is None:
        return Slot.UNKNOWN, round(confidence, 3)
    return best, round(confidence, 3)

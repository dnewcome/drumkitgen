"""Canonical drum-slot taxonomy, mapped to the General MIDI percussion map.

Slots are the vocabulary the whole system speaks: the classifier assigns one to
each sound, the renderer maps each slot to a MIDI key, and future producers
(generation, morphing) target slots by name. Keeping the taxonomy anchored to
General MIDI means a rendered kit lands on the notes a producer expects when
they drop it into any DAW drum instrument.
"""

from __future__ import annotations

from enum import Enum


class Slot(str, Enum):
    """A canonical role a one-shot can play in a kit."""

    KICK = "kick"
    SNARE = "snare"
    RIMSHOT = "rimshot"
    CLAP = "clap"
    HAT_CLOSED = "hat_closed"
    HAT_PEDAL = "hat_pedal"
    HAT_OPEN = "hat_open"
    TOM_LOW = "tom_low"
    TOM_MID = "tom_mid"
    TOM_HIGH = "tom_high"
    CRASH = "crash"
    RIDE = "ride"
    PERC = "perc"
    FX = "fx"
    UNKNOWN = "unknown"


# General MIDI percussion note numbers. Slots without a natural GM home
# (perc, fx, unknown, or overflow when a slot has many samples) are laid out
# on ascending keys starting at ``OVERFLOW_START`` — see ``render.layout``.
GM_NOTE: dict[Slot, int] = {
    Slot.KICK: 36,        # Bass Drum 1
    Slot.RIMSHOT: 37,     # Side Stick
    Slot.SNARE: 38,       # Acoustic Snare
    Slot.CLAP: 39,        # Hand Clap
    Slot.TOM_LOW: 41,     # Low Floor Tom
    Slot.HAT_CLOSED: 42,  # Closed Hi-Hat
    Slot.HAT_PEDAL: 44,   # Pedal Hi-Hat
    Slot.TOM_MID: 45,     # Low Tom
    Slot.HAT_OPEN: 46,    # Open Hi-Hat
    Slot.CRASH: 49,       # Crash Cymbal 1
    Slot.TOM_HIGH: 50,    # High Tom
    Slot.RIDE: 51,        # Ride Cymbal 1
}

# Keys at/above here are handed out to slots with no GM note and to overflow.
OVERFLOW_START = 60  # C3 / "Middle C" region, above the standard GM kit


#: Slots that are members of the hi-hat family (mutually choking in real kits).
HAT_SLOTS = (Slot.HAT_CLOSED, Slot.HAT_PEDAL, Slot.HAT_OPEN)

#: Slots that are pitched/tonal enough for an f0 estimate to be meaningful.
TONAL_SLOTS = (Slot.KICK, Slot.TOM_LOW, Slot.TOM_MID, Slot.TOM_HIGH, Slot.RIDE)


def gm_note(slot: Slot) -> int | None:
    """Return the General MIDI note for ``slot``, or ``None`` if it has no home."""
    return GM_NOTE.get(slot)

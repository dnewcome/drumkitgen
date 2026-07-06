"""Assign MIDI keys to pieces — a canonical operation, not a render detail.

The key each piece lands on is part of the kit's identity (it's what a producer
plays), so it's stored in ``Piece.playback.root_key`` rather than being invented
per render target. Slots with a General MIDI home get their GM note; multiple
pieces sharing a slot stack on the same key as round-robins; slots with no GM
home (perc/fx/unknown) are handed ascending keys above the standard kit.
"""

from __future__ import annotations

from .model import Piece
from .slots import GM_NOTE, OVERFLOW_START, Slot


def assign_keys(pieces: list[Piece]) -> None:
    """Set ``piece.playback.root_key`` for every piece, in place.

    Pieces sharing a GM-mapped slot share that slot's key (they become
    round-robins at render time). Unmapped slots get consecutive keys starting
    at :data:`~drumkitgen.slots.OVERFLOW_START`, so nothing collides silently.
    """
    next_free = OVERFLOW_START
    overflow_key: dict[str, int] = {}  # id() bucket -> key, so unmapped slots stay grouped

    # Group unmapped pieces by slot so all "perc" hits share one key, etc.
    for piece in pieces:
        gm = GM_NOTE.get(piece.slot)
        if gm is not None:
            piece.playback.root_key = gm
            continue
        bucket = piece.slot.value
        if bucket not in overflow_key:
            overflow_key[bucket] = next_free
            next_free += 1
        piece.playback.root_key = overflow_key[bucket]

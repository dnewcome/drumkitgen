"""drumkitgen — generate and analyze drum kits for electronic music.

The kit *spine*: a kit is a folder of one-shots + a canonical ``kit.yaml``
metadata sidecar, from which render targets (``.sfz`` today; Decent Sampler,
Ableton Drum Rack, … later) are generated. Every sound source — analysis of
existing samples, generative models, DSP synthesis, corpus recombination,
morphing — is a *producer* that drops pieces into that spine.
"""

__version__ = "0.1.0"

from .model import Analysis, Kit, Piece, Playback, Provenance, SourceInfo
from .slots import GM_NOTE, Slot

__all__ = [
    "__version__",
    "Analysis",
    "Kit",
    "Piece",
    "Playback",
    "Provenance",
    "SourceInfo",
    "Slot",
    "GM_NOTE",
]

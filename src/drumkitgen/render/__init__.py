"""Render targets: turn a canonical :class:`~drumkitgen.model.Kit` into the
file formats a sampler can load. Every renderer is a pure function of the kit;
none of them is the source of truth.
"""

from .sfz import render_sfz

__all__ = ["render_sfz"]

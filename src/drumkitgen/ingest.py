"""Ingest: a folder of one-shots -> a canonical :class:`Kit`, then out to disk.

This is the first-slice pipeline end to end:

    find audio -> load -> analyze -> classify -> assign keys -> Kit
    Kit -> copy samples + write kit.yaml + render <name>.sfz

Producers added later (generation, morphing, recombination) build ``Piece``
objects a different way but hand them to the same :func:`write_kit`.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .analysis import analyze
from .audio import find_audio, load_mono
from .classify import classify
from .io_yaml import write as write_yaml
from .layout import assign_keys
from .model import Kit, Piece, Playback, Provenance, SourceInfo
from .render import render_sfz


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s or "piece"


def build_kit(
    input_dir: str | Path,
    name: str | None = None,
    prompt: str | None = None,
    tags: list[str] | None = None,
) -> Kit:
    """Analyze every one-shot in ``input_dir`` and return a populated :class:`Kit`.

    Nothing is written and no audio is modified — this is pure measurement.
    """
    input_dir = Path(input_dir)
    files = find_audio(input_dir)
    if not files:
        raise FileNotFoundError(f"no audio files found in {input_dir}")

    kit_name = name or input_dir.name
    pieces: list[Piece] = []
    used_ids: set[str] = set()
    used_names: set[str] = set()

    for path in files:
        mono, sr, channels = load_mono(path)
        analysis = analyze(mono, sr, channels)
        slot, confidence = classify(analysis, path.stem)

        piece_id = _unique(_slug(path.stem), used_ids)
        dest_name = _unique_filename(path.name, used_names)
        pieces.append(
            Piece(
                id=piece_id,
                slot=slot,
                file=f"samples/{dest_name}",
                classify_confidence=confidence,
                source=SourceInfo(kind="analyzed", origin=str(path.resolve())),
                analysis=analysis,
                playback=Playback(root_key=0),  # filled by assign_keys
            )
        )

    assign_keys(pieces)

    return Kit(
        name=kit_name,
        prompt=prompt,
        tags=tags or [],
        provenance=Provenance(
            version=__version__,
            created=datetime.now(timezone.utc),
            source="analyze",
        ),
        pieces=pieces,
    )


def write_kit(kit: Kit, out_dir: str | Path, copy_samples: bool = True) -> Path:
    """Write ``kit`` to ``out_dir``: samples/, kit.yaml, <name>.sfz.

    Sample files are copied verbatim (never re-encoded) from each piece's
    ``source.origin`` into ``samples/``. Returns the output directory.
    """
    out = Path(out_dir)
    (out / "samples").mkdir(parents=True, exist_ok=True)

    if copy_samples:
        for piece in kit.pieces:
            if not piece.source.origin:
                continue
            src = Path(piece.source.origin)
            dst = out / piece.file
            if src.resolve() != dst.resolve():
                shutil.copy2(src, dst)

    write_yaml(kit, out / "kit.yaml")
    (out / f"{_slug(kit.name)}.sfz").write_text(render_sfz(kit), encoding="utf-8")
    return out


def pack(
    input_dir: str | Path,
    out_dir: str | Path,
    name: str | None = None,
    prompt: str | None = None,
    tags: list[str] | None = None,
) -> Kit:
    """Convenience: :func:`build_kit` then :func:`write_kit`."""
    kit = build_kit(input_dir, name=name, prompt=prompt, tags=tags)
    write_kit(kit, out_dir)
    return kit


def _unique(base: str, seen: set[str]) -> str:
    if base not in seen:
        seen.add(base)
        return base
    i = 2
    while f"{base}_{i}" in seen:
        i += 1
    out = f"{base}_{i}"
    seen.add(out)
    return out


def _unique_filename(name: str, seen: set[str]) -> str:
    if name not in seen:
        seen.add(name)
        return name
    stem, dot, ext = name.partition(".")
    i = 2
    while f"{stem}_{i}{dot}{ext}" in seen:
        i += 1
    out = f"{stem}_{i}{dot}{ext}"
    seen.add(out)
    return out

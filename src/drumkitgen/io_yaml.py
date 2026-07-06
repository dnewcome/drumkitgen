"""Serialize the canonical kit to/from ``kit.yaml``.

YAML because it's the most human-legible of the options and the file is meant
to be read, hand-edited, and diffed. ``exclude_none`` keeps optional fields
from cluttering the file; ``sort_keys=False`` preserves the model's declared
field order so the important stuff (name, prompt, tags) stays on top.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .model import Kit

_HEADER = (
    "# drumkitgen kit — canonical metadata (source of truth).\n"
    "# Render targets like .sfz are generated FROM this file; edit here.\n"
)


def dumps(kit: Kit) -> str:
    """Serialize a kit to a YAML string."""
    data = kit.model_dump(mode="json", exclude_none=True)
    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return _HEADER + body


def loads(text: str) -> Kit:
    """Parse a kit from a YAML string, validating against the schema."""
    return Kit.model_validate(yaml.safe_load(text))


def write(kit: Kit, path: str | Path) -> None:
    Path(path).write_text(dumps(kit), encoding="utf-8")


def read(path: str | Path) -> Kit:
    return loads(Path(path).read_text(encoding="utf-8"))

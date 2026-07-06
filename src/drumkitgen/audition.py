"""Interactive terminal drum pad — press a key, hear the sample.

``drumkitgen audition <folder-or-kit>`` maps computer-keyboard keys to the
one-shots in a folder (or the pieces of a kit) and triggers them on keypress, so
you can jam a kit or A/B a remix without leaving the terminal.

Two playback engines, auto-selected:

* **rt** (preferred) — if ``sounddevice`` is installed, samples are preloaded
  into RAM and mixed in a real-time audio callback: low latency, true polyphony.
* **subprocess** (fallback) — spawns an installed CLI player (``pw-play`` /
  ``paplay`` / ``ffplay`` / ``aplay``) per hit. Zero extra dependencies; still
  polyphonic because each hit is its own process.

Nothing here mutates audio or kits — it's a read-only auditioner.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .audio import find_audio

# Pad order: home row first (so a kit's kick lands under the resting left hand),
# then the upper/lower rows, then digits. 36 pads — more than any real kit.
PAD_KEYS = "asdfghjkl" + "qwertyuiop" + "zxcvbnm" + "1234567890"

# CLI players tried in order; ffplay needs flags to run headless and quiet.
_PLAYERS: list[tuple[str, list[str]]] = [
    ("pw-play", []),
    ("paplay", []),
    ("ffplay", ["-autoexit", "-nodisp", "-loglevel", "quiet"]),
    ("aplay", ["-q"]),
]


@dataclass
class Pad:
    key: str
    path: Path
    label: str      # sample name shown to the user
    sublabel: str = ""  # slot / short analysis, when auditioning a kit


def collect_pads(input_path: str | Path) -> list[Pad]:
    """Build the key→sample map for a kit dir, a kit.yaml, or a folder of audio.

    A kit is ordered by MIDI key (kick first) and labeled with slot + a compact
    analysis readout; a raw folder is ordered by filename.
    """
    p = Path(input_path)
    items: list[tuple[Path, str, str]] = []  # (path, label, sublabel)

    kit_yaml = None
    if p.is_file() and p.suffix in (".yaml", ".yml"):
        kit_yaml = p
    elif p.is_dir() and (p / "kit.yaml").exists():
        kit_yaml = p / "kit.yaml"

    if kit_yaml is not None:
        from .io_yaml import read as read_kit

        kit = read_kit(kit_yaml)
        base = kit_yaml.parent
        pieces = sorted(kit.pieces, key=lambda pc: (pc.playback.root_key, pc.id))
        for pc in pieces:
            a = pc.analysis
            info = pc.slot.value
            sub = ""
            if a:
                sub = f"{pc.slot.value} · {a.duration_s * 1000:.0f}ms · {a.spectral_centroid_hz / 1000:.1f}k"
                if a.sub_energy_ratio > 0.15:
                    sub += f" · sub {a.sub_energy_ratio * 100:.0f}%"
            items.append((base / pc.file, pc.id, sub or info))
    else:
        if not p.is_dir():
            raise FileNotFoundError(f"{p} is not a kit or a folder of audio")
        for f in find_audio(p):
            items.append((f, f.stem, ""))

    if not items:
        raise FileNotFoundError(f"no audio to audition in {p}")

    pads = [Pad(key=k, path=path, label=label, sublabel=sub)
            for k, (path, label, sub) in zip(PAD_KEYS, items)]
    dropped = len(items) - len(pads)
    if dropped > 0:
        pads.append(Pad(key="", path=Path(), label=f"(+{dropped} more not mapped)", sublabel=""))
        pads = [pd for pd in pads if pd.key] + []  # keep only real pads for triggering
    return [pd for pd in pads if pd.key]


# --- playback engines --------------------------------------------------------


def find_player() -> list[str] | None:
    """Return the argv prefix for the best available CLI player, or None."""
    for name, flags in _PLAYERS:
        if shutil.which(name):
            return [name, *flags]
    return None


class SubprocessEngine:
    """Fire-and-forget: one player process per hit. No extra dependencies."""

    name = "subprocess"

    def __init__(self, pads: list[Pad]):
        self.cmd = find_player()
        if self.cmd is None:
            raise RuntimeError(
                "no CLI audio player found (looked for pw-play, paplay, ffplay, aplay)"
            )
        self._procs: list[subprocess.Popen] = []

    @property
    def detail(self) -> str:
        return f"subprocess ({self.cmd[0]})"

    def trigger(self, pad: Pad) -> None:
        self._procs = [pr for pr in self._procs if pr.poll() is None]  # reap finished
        self._procs.append(
            subprocess.Popen(
                [*self.cmd, str(pad.path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        )

    def close(self) -> None:
        for pr in self._procs:
            if pr.poll() is None:
                pr.terminate()


class RtEngine:
    """Real-time mixer via sounddevice: samples preloaded, voices summed live."""

    name = "rt"

    def __init__(self, pads: list[Pad]):
        import threading

        import numpy as np
        import sounddevice as sd
        import soundfile as sf

        self._np = np
        self._sr = 44100
        self._voices: list[list] = []  # [buffer(Nx2 float32), position]
        self._lock = threading.Lock()

        self._buffers: dict[str, "np.ndarray"] = {}
        for pad in pads:
            data, fsr = sf.read(str(pad.path), dtype="float32", always_2d=True)
            if fsr != self._sr:
                import librosa

                data = librosa.resample(data.T, orig_sr=fsr, target_sr=self._sr).T
            if data.shape[1] == 1:
                data = np.repeat(data, 2, axis=1)
            elif data.shape[1] > 2:
                data = data[:, :2]
            self._buffers[pad.key] = np.ascontiguousarray(data, dtype=np.float32)

        self._stream = sd.OutputStream(
            samplerate=self._sr, channels=2, blocksize=256, dtype="float32", callback=self._cb
        )
        self._stream.start()

    @property
    def detail(self) -> str:
        return "rt (sounddevice, 44.1k/256)"

    def _cb(self, outdata, frames, time_info, status):  # noqa: ARG002
        np = self._np
        outdata.fill(0)
        with self._lock:
            keep = []
            for voice in self._voices:
                buf, pos = voice
                chunk = buf[pos:pos + frames]
                outdata[:len(chunk)] += chunk
                voice[1] = pos + len(chunk)
                if voice[1] < len(buf):
                    keep.append(voice)
            self._voices = keep
        np.clip(outdata, -1.0, 1.0, out=outdata)

    def trigger(self, pad: Pad) -> None:
        buf = self._buffers.get(pad.key)
        if buf is not None:
            with self._lock:
                self._voices.append([buf, 0])

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


def make_engine(name: str, pads: list[Pad]):
    """Resolve an engine. ``auto`` prefers rt (sounddevice) then subprocess."""
    if name in ("auto", "rt"):
        try:
            import sounddevice  # noqa: F401

            return RtEngine(pads)
        except Exception:
            if name == "rt":
                raise
    return SubprocessEngine(pads)


# --- terminal key reading ----------------------------------------------------


@contextmanager
def _cbreak():
    """Put the terminal in cbreak mode (Ctrl-C still works), restore on exit."""
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_key() -> str:
    """Read one keypress. Returns the char, or 'ESC'/'ARROW' for escape codes."""
    import select

    ch = os.read(sys.stdin.fileno(), 1).decode(errors="ignore")
    if ch == "\x1b":  # escape: distinguish a lone ESC from an arrow-key sequence
        r, _, _ = select.select([sys.stdin], [], [], 0.02)
        if r:
            os.read(sys.stdin.fileno(), 4)  # drain the sequence
            return "ARROW"
        return "ESC"
    return ch

"""Command-line interface: ``drumkitgen <command>``.

Commands map onto the spine:

* ``pack``    folder of one-shots -> packaged kit (samples + kit.yaml + .sfz)
* ``inspect`` pretty-print an existing kit.yaml
* ``demo``    synthesize a starter kit and pack it — zero samples required
* ``slots``   show the canonical slot taxonomy and its General MIDI mapping
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .io_yaml import read as read_kit
from .slots import GM_NOTE, Slot

app = typer.Typer(
    add_completion=False,
    help="Generate and analyze drum kits for electronic music.",
    no_args_is_help=True,
)
console = Console()


def _summary_table(kit) -> Table:
    table = Table(title=f"{kit.name}  ({len(kit.pieces)} pieces)", title_style="bold")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("slot", style="green")
    table.add_column("key", justify="right")
    table.add_column("conf", justify="right")
    table.add_column("dur", justify="right")
    table.add_column("cen Hz", justify="right")
    table.add_column("f0 Hz", justify="right")
    table.add_column("sub%", justify="right")
    for p in kit.pieces:
        a = p.analysis
        table.add_row(
            p.id,
            p.slot.value,
            str(p.playback.root_key),
            f"{p.classify_confidence:.2f}",
            f"{a.duration_s:.2f}s" if a else "-",
            f"{a.spectral_centroid_hz:.0f}" if a else "-",
            f"{a.fundamental_hz:.0f}" if a and a.fundamental_hz else "-",
            f"{a.sub_energy_ratio * 100:.0f}" if a else "-",
        )
    return table


@app.command()
def pack(
    input_dir: Path = typer.Argument(..., help="Folder of one-shot audio files."),
    out: Path = typer.Option(..., "--out", "-o", help="Output kit directory."),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Kit name (default: input folder name)."),
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p", help="Heuristic prompt describing the kit."),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated tags."),
) -> None:
    """Analyze a folder of one-shots and write a packaged kit."""
    from .ingest import pack as do_pack  # deferred: pulls in librosa

    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    with console.status("[bold]analyzing…"):
        kit = do_pack(input_dir, out, name=name, prompt=prompt, tags=tag_list)
    console.print(_summary_table(kit))
    console.print(f"\n[green]✓[/green] wrote kit to [bold]{out}[/bold]")
    console.print(f"  • {out}/kit.yaml   [dim](canonical)[/dim]")
    console.print(f"  • {out}/{_slugged(kit.name)}.sfz   [dim](render target)[/dim]")
    console.print(f"  • {out}/samples/   [dim]({len(kit.pieces)} files)[/dim]")


@app.command()
def inspect(kit_yaml: Path = typer.Argument(..., help="Path to a kit.yaml file.")) -> None:
    """Pretty-print an existing kit's metadata."""
    kit = read_kit(kit_yaml)
    if kit.prompt:
        console.print(f"[dim]prompt:[/dim] {kit.prompt}")
    if kit.tags:
        console.print(f"[dim]tags:[/dim] {', '.join(kit.tags)}")
    console.print(_summary_table(kit))


@app.command()
def demo(
    out: Path = typer.Option(Path("out/demo-kit"), "--out", "-o", help="Output kit directory."),
) -> None:
    """Synthesize a starter kit and pack it — no input samples needed."""
    from .ingest import pack as do_pack
    from .synth_probe import write_demo_samples

    with tempfile.TemporaryDirectory() as tmp:
        write_demo_samples(tmp)
        with console.status("[bold]synthesizing + analyzing…"):
            kit = do_pack(
                tmp,
                out,
                name="demo-kit",
                prompt="synthesized demo kit (drumkitgen synth_probe)",
                tags=["demo", "synth"],
            )
    console.print(_summary_table(kit))
    console.print(f"\n[green]✓[/green] demo kit written to [bold]{out}[/bold]")


@app.command()
def remix(
    input_path: Path = typer.Argument(..., help="A kit folder, a kit dir with kit.yaml, or a kit.yaml file."),
    out: Path = typer.Option(..., "--out", "-o", help="Output kit directory."),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Remix name (default: <source>-remix)."),
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p", help="Override the remix prompt."),
    drive: float = typer.Option(0.5, "--drive", help="Saturation amount 0..1 (grit/warmth)."),
    sub: float = typer.Option(0.6, "--sub", help="Sub-sine weight added under kicks 0..1."),
    tune: float = typer.Option(0.0, "--tune", help="Semitones to pitch-shift the whole kit."),
) -> None:
    """Re-voice an existing kit with slot-aware DSP (sub-weight + saturation + tune)."""
    from .ingest import build_kit
    from .io_yaml import read as read_kit
    from .remix import RemixRecipe, remix_kit

    # Resolve input: an explicit kit.yaml, a dir containing one, or raw samples.
    if input_path.is_file() and input_path.suffix in (".yaml", ".yml"):
        src = read_kit(input_path)
    elif (input_path / "kit.yaml").exists():
        src = read_kit(input_path / "kit.yaml")
    else:
        with console.status("[bold]analyzing source…"):
            src = build_kit(input_path)

    recipe = RemixRecipe(drive=drive, sub=sub, tune=tune, name=name or f"{src.name}-remix")
    with console.status("[bold]remixing…"):
        remixed = remix_kit(src, out, recipe, prompt=prompt)

    console.print(_compare_table(src, remixed))
    console.print(f"\n[green]✓[/green] remix written to [bold]{out}[/bold]  [dim]({_recipe_line(recipe)})[/dim]")


def _recipe_line(r) -> str:
    bits = [f"drive={r.drive:g}", f"sub={r.sub:g}"]
    if r.tune:
        bits.append(f"tune={r.tune:+g}st")
    return ", ".join(bits)


def _compare_table(src, dst) -> Table:
    """Before/after: what the transform chain actually did to each hit."""
    table = Table(title=f"{src.name}  →  {dst.name}", title_style="bold")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("slot", style="green")
    table.add_column("sub% →", justify="right")
    table.add_column("cen Hz →", justify="right")
    table.add_column("peak dB →", justify="right")
    table.add_column("chain", style="dim")
    before = {p.id: p for p in src.pieces}
    for p in dst.pieces:
        b = before.get(p.id)
        ba, da = (b.analysis if b else None), p.analysis
        table.add_row(
            p.id,
            p.slot.value,
            f"{ba.sub_energy_ratio * 100:.0f}→{da.sub_energy_ratio * 100:.0f}" if ba and da else "-",
            f"{ba.spectral_centroid_hz:.0f}→{da.spectral_centroid_hz:.0f}" if ba and da else "-",
            f"{ba.peak_dbfs:.1f}→{da.peak_dbfs:.1f}" if ba and da else "-",
            " · ".join(p.source.chain) or "—",
        )
    return table


@app.command()
def audition(
    input_path: Path = typer.Argument(..., help="A kit folder, a kit dir with kit.yaml, a kit.yaml, or a folder of audio."),
    engine: str = typer.Option("auto", "--engine", "-e", help="Playback engine: auto | rt | subprocess."),
    list_only: bool = typer.Option(False, "--list", "-l", help="Print the key map and exit (no interaction)."),
) -> None:
    """Interactive terminal drum pad: map keys to samples and play on keypress."""
    from . import audition as au

    pads = au.collect_pads(input_path)
    keymap = {pad.key: pad for pad in pads}

    def show_legend() -> None:
        table = Table(title=f"audition · {Path(input_path).name}  ({len(pads)} pads)", title_style="bold")
        table.add_column("key", style="bold cyan", justify="center")
        table.add_column("sample", style="green")
        table.add_column("info", style="dim")
        for pad in pads:
            table.add_row(pad.key, pad.label, pad.sublabel)
        console.print(table)

    show_legend()

    if list_only or not sys.stdin.isatty():
        if not list_only:
            console.print("[yellow]stdin is not a TTY[/yellow] — run in a real terminal to trigger pads.")
        return

    try:
        eng = au.make_engine(engine, pads)
    except Exception as exc:  # no player / no device
        console.print(f"[red]could not start audio:[/red] {exc}")
        raise typer.Exit(1)

    console.print(f"[dim]engine:[/dim] {eng.detail}    [dim]keys:[/dim] play · [bold]?[/bold] legend · [bold]Ctrl-C/ESC[/bold] quit\n")
    try:
        with au._cbreak():
            while True:
                k = au._read_key()
                if k in ("ESC", "\x03"):
                    break
                if k == "?":
                    show_legend()
                    continue
                pad = keymap.get(k)
                if pad is not None:
                    eng.trigger(pad)
                    console.print(f"[cyan]▶ {pad.key}[/cyan]  [green]{pad.label}[/green]  [dim]{pad.sublabel}[/dim]")
    except KeyboardInterrupt:
        pass
    finally:
        eng.close()
    console.print("\n[dim]bye.[/dim]")


@app.command()
def slots() -> None:
    """Show the canonical slot taxonomy and its General MIDI mapping."""
    table = Table(title="drumkitgen slot taxonomy")
    table.add_column("slot", style="green")
    table.add_column("GM note", justify="right")
    for slot in Slot:
        if slot is Slot.UNKNOWN:
            continue
        note = GM_NOTE.get(slot)
        table.add_row(slot.value, str(note) if note is not None else "[dim]overflow[/dim]")
    console.print(table)


@app.command()
def version() -> None:
    """Print the drumkitgen version."""
    console.print(f"drumkitgen {__version__}")


def _slugged(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "kit"


if __name__ == "__main__":
    app()

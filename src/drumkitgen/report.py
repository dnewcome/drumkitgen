"""Visual report: characterize a kit's samples, and how a remix changed them.

Renders a self-contained HTML page (pure inline SVG — no plotting library, no
external assets, works headless) from a kit's analysis, optionally comparing a
"before" kit against an "after" kit (e.g. source vs remix). Every chart is
matched to its job per the data-viz method:

* feature map (scatter)  — identity + position; arrows show before→after motion
* spectral heatmap        — sequential magnitude (energy per frequency band)
* change heatmap          — diverging polarity (energy gained/lost per band)
* waveform envelopes      — shape/level change, source vs remix overlaid
* stat tiles + table view — the headline numbers and the accessible twin

Colors come from the validated reference palette; charts are colored by *slot
family* (≤ 8 categorical hues) and carry direct labels so identity never rests
on color alone.
"""

from __future__ import annotations

import html
import math
from pathlib import Path

import numpy as np
import soundfile as sf

from .model import Kit, Piece
from .slots import Slot

# --- slot families → the 8 validated categorical hues ------------------------

_FAMILY_OF: dict[Slot, str] = {
    Slot.KICK: "kick",
    Slot.SNARE: "snare",
    Slot.RIMSHOT: "snare",
    Slot.CLAP: "clap",
    Slot.HAT_CLOSED: "hat",
    Slot.HAT_OPEN: "hat",
    Slot.HAT_PEDAL: "hat",
    Slot.TOM_LOW: "tom",
    Slot.TOM_MID: "tom",
    Slot.TOM_HIGH: "tom",
    Slot.CRASH: "cymbal",
    Slot.RIDE: "cymbal",
    Slot.PERC: "perc",
    Slot.FX: "fx",
    Slot.UNKNOWN: "fx",
}
FAMILY_ORDER = ["kick", "snare", "clap", "hat", "tom", "cymbal", "perc", "fx"]
_CAT_LIGHT = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]
_CAT_DARK = ["#3987e5", "#199e70", "#c98500", "#008300", "#9085e9", "#e66767", "#d55181", "#d95926"]

BANDS = ["sub", "low", "lowmid", "highmid", "high"]
_BAND_LABEL = {"sub": "sub", "low": "low", "lowmid": "lo-mid", "highmid": "hi-mid", "high": "high"}


def _family(slot: Slot) -> str:
    return _FAMILY_OF.get(slot, "fx")


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


# --- small scale helpers -----------------------------------------------------


def _lin(v: float, d0: float, d1: float, r0: float, r1: float) -> float:
    if d1 == d0:
        return (r0 + r1) / 2
    return r0 + (v - d0) / (d1 - d0) * (r1 - r0)


def _log10(v: float, floor: float = 20.0) -> float:
    return math.log10(max(v, floor))


# --- audio envelope (for waveform small-multiples) ---------------------------


def _peak_envelope(path: Path, bins: int = 220) -> np.ndarray:
    """Absolute peak per bin, 0..1 — a cheap vector waveform, no matplotlib."""
    try:
        data, _ = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception:
        return np.zeros(bins, dtype=np.float32)
    mono = np.abs(data.mean(axis=1))
    if mono.size == 0:
        return np.zeros(bins, dtype=np.float32)
    idx = np.linspace(0, mono.size, bins + 1).astype(int)
    env = np.array([mono[idx[i]:idx[i + 1]].max() if idx[i + 1] > idx[i] else 0.0 for i in range(bins)])
    return env.astype(np.float32)


# =============================================================================
#  Chart builders — each returns an SVG string
# =============================================================================


def _feature_map(before: list[Piece], after_by_id: dict[str, Piece]) -> str:
    W, H = 720, 440
    ml, mr, mt, mb = 58, 20, 20, 46
    px0, px1, py0, py1 = ml, W - mr, mt, H - mb

    cents = [p.analysis.spectral_centroid_hz for p in before if p.analysis]
    cents += [a.analysis.spectral_centroid_hz for a in after_by_id.values() if a.analysis]
    if not cents:
        return ""
    x_d0, x_d1 = _log10(min(cents)) - 0.05, _log10(max(cents)) + 0.05
    y_d0, y_d1 = 0.0, max(5.0, max((p.analysis.sub_energy_ratio * 100 for p in before if p.analysis), default=5.0) * 1.1)

    def X(hz: float) -> float:
        return _lin(_log10(hz), x_d0, x_d1, px0, px1)

    def Y(pct: float) -> float:
        return _lin(pct, y_d0, y_d1, py1, py0)

    def R(dur: float) -> float:
        return _lin(min(dur, 2.0), 0.0, 2.0, 5.0, 15.0)

    parts: list[str] = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="feature map">']
    parts.append(
        '<defs><marker id="arw" markerWidth="7" markerHeight="7" refX="5.5" refY="3" orient="auto">'
        '<path d="M0,0 L6,3 L0,6 Z" fill="var(--muted)"/></marker></defs>'
    )
    # grid + x ticks (log)
    for hz in (50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000):
        if not (x_d0 <= _log10(hz) <= x_d1):
            continue
        x = X(hz)
        parts.append(f'<line x1="{x:.1f}" y1="{py0}" x2="{x:.1f}" y2="{py1}" class="grid"/>')
        lbl = f"{hz // 1000}k" if hz >= 1000 else str(hz)
        parts.append(f'<text x="{x:.1f}" y="{py1 + 16}" class="tick" text-anchor="middle">{lbl}</text>')
    for pct in range(0, int(y_d1) + 1, max(1, int(y_d1) // 4)):
        y = Y(pct)
        parts.append(f'<line x1="{px0}" y1="{y:.1f}" x2="{px1}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{px0 - 8}" y="{y + 4:.1f}" class="tick" text-anchor="end">{pct}</text>')
    parts.append(f'<text x="{(px0 + px1) / 2:.0f}" y="{H - 6}" class="axis-title" text-anchor="middle">spectral centroid (Hz, log)</text>')
    parts.append(f'<text transform="translate(14,{(py0 + py1) / 2:.0f}) rotate(-90)" class="axis-title" text-anchor="middle">sub energy (%)</text>')

    # before→after arrows
    for p in before:
        a = after_by_id.get(p.id)
        if not (a and p.analysis and a.analysis):
            continue
        x1, y1 = X(p.analysis.spectral_centroid_hz), Y(p.analysis.sub_energy_ratio * 100)
        x2, y2 = X(a.analysis.spectral_centroid_hz), Y(a.analysis.sub_energy_ratio * 100)
        if abs(x1 - x2) + abs(y1 - y2) > 6:
            parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="arrow" marker-end="url(#arw)"/>')

    # points: before hollow (if comparing), after/only filled
    comparing = bool(after_by_id)
    for p in before:
        if not p.analysis:
            continue
        fam = _family(p.slot)
        x, y, r = X(p.analysis.spectral_centroid_hz), Y(p.analysis.sub_energy_ratio * 100), R(p.analysis.duration_s)
        tip = f"{p.id} · {p.slot.value} · {p.analysis.spectral_centroid_hz:.0f} Hz · sub {p.analysis.sub_energy_ratio * 100:.0f}%"
        if comparing:
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="none" stroke="var(--c-{fam})" '
                f'stroke-width="1.5" opacity="0.55"><title>{_esc("before · " + tip)}</title></circle>'
            )
        else:
            parts.append(
                f'<g class="pt" data-tip="{_esc(tip)}"><circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" '
                f'fill="var(--c-{fam})" stroke="var(--surface)" stroke-width="2"/></g>'
            )
            parts.append(f'<text x="{x:.1f}" y="{y - r - 4:.1f}" class="pt-label" text-anchor="middle">{_esc(p.id)}</text>')
    for p in before:
        a = after_by_id.get(p.id)
        if not (a and a.analysis):
            continue
        fam = _family(a.slot)
        x, y, r = X(a.analysis.spectral_centroid_hz), Y(a.analysis.sub_energy_ratio * 100), R(a.analysis.duration_s)
        tip = f"{a.id} · {a.slot.value} · {a.analysis.spectral_centroid_hz:.0f} Hz · sub {a.analysis.sub_energy_ratio * 100:.0f}%"
        parts.append(
            f'<g class="pt" data-tip="{_esc("after · " + tip)}"><circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" '
            f'fill="var(--c-{fam})" stroke="var(--surface)" stroke-width="2"/></g>'
        )
        parts.append(f'<text x="{x:.1f}" y="{y - r - 4:.1f}" class="pt-label" text-anchor="middle">{_esc(a.id)}</text>')

    parts.append("</svg>")
    return "".join(parts)


def _heatmap(pieces: list[Piece], mode: str, other_by_id: dict[str, Piece] | None = None) -> str:
    """mode='seq' -> band energy (blue ramp); mode='div' -> Δ energy (blue↔red)."""
    rows = [p for p in pieces if p.analysis]
    if not rows:
        return ""
    cell_h, label_w, top = 22, 132, 22
    cols = len(BANDS)
    cell_w = 74
    W = label_w + cols * cell_w + 12
    H = top + len(rows) * cell_h + 8
    parts = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="{mode} heatmap">']
    for c, b in enumerate(BANDS):
        x = label_w + c * cell_w + cell_w / 2
        parts.append(f'<text x="{x:.0f}" y="14" class="tick" text-anchor="middle">{_BAND_LABEL[b]}</text>')
    for r, p in enumerate(rows):
        y = top + r * cell_h
        parts.append(f'<text x="{label_w - 8}" y="{y + cell_h / 2 + 4:.0f}" class="row-label" text-anchor="end">{_esc(p.id)}</text>')
        for c, b in enumerate(BANDS):
            x = label_w + c * cell_w
            v = p.analysis.band_energy.get(b, 0.0)
            if mode == "seq":
                bucket = min(5, int(v * 6 / 0.6)) if v > 0 else 0  # 0..0.6 -> 6 buckets
                cls = f"seq{bucket}"
                title = f"{p.id} · {_BAND_LABEL[b]} · {v * 100:.0f}%"
            else:
                ov = other_by_id.get(p.id) if other_by_id else None
                base = ov.analysis.band_energy.get(b, 0.0) if ov and ov.analysis else 0.0
                d = v - base
                cls = _div_bucket(d)
                title = f"{p.id} · {_BAND_LABEL[b]} · {d * 100:+.0f} pp"
            parts.append(
                f'<rect x="{x + 1:.0f}" y="{y + 1:.0f}" width="{cell_w - 2}" height="{cell_h - 2}" rx="2" '
                f'class="{cls}"><title>{_esc(title)}</title></rect>'
            )
    parts.append("</svg>")
    return "".join(parts)


def _div_bucket(d: float) -> str:
    steps = [(-0.12, "divn3"), (-0.05, "divn2"), (-0.015, "divn1"), (0.015, "div0"), (0.05, "divp1"), (0.12, "divp2")]
    for thr, cls in steps:
        if d < thr:
            return cls
    return "divp3"


def _waveforms(before: list[Piece], base_before: Path, after_by_id: dict[str, Piece], base_after: Path | None) -> str:
    cells = []
    for p in before:
        fam = _family(p.slot)
        env_b = _peak_envelope(base_before / p.file)
        env_a = None
        a = after_by_id.get(p.id)
        if a is not None and base_after is not None:
            env_a = _peak_envelope(base_after / a.file)
        cells.append((p.id, fam, env_b, env_a))

    cw, ch = 210, 84
    pad = 10
    inner = ch - 2 * pad
    out = ['<div class="wave-grid">']
    for pid, fam, env_b, env_a in cells:
        n = len(env_b)

        def path_for(env: np.ndarray) -> str:
            top = " ".join(f"{pad + i / (n - 1) * (cw - 2 * pad):.1f},{ch / 2 - e * inner / 2:.1f}" for i, e in enumerate(env))
            bot = " ".join(f"{pad + i / (n - 1) * (cw - 2 * pad):.1f},{ch / 2 + e * inner / 2:.1f}" for i, e in reversed(list(enumerate(env))))
            return f"M {top} L {bot} Z"

        svg = [f'<svg viewBox="0 0 {cw} {ch}" class="wave">']
        svg.append(f'<line x1="{pad}" y1="{ch / 2}" x2="{cw - pad}" y2="{ch / 2}" class="grid"/>')
        if env_a is not None:
            svg.append(f'<path d="{path_for(env_b)}" fill="var(--muted)" opacity="0.35"/>')
            svg.append(f'<path d="{path_for(env_a)}" fill="var(--c-{fam})" opacity="0.85"/>')
        else:
            svg.append(f'<path d="{path_for(env_b)}" fill="var(--c-{fam})" opacity="0.85"/>')
        svg.append("</svg>")
        legend = ' <span class="wv-b">■ source</span> <span class="wv-a">■ remix</span>' if env_a is not None else ""
        out.append(f'<figure class="wave-cell"><figcaption>{_esc(pid)}{legend}</figcaption>{"".join(svg)}</figure>')
    out.append("</div>")
    return "".join(out)


def _legend(families_present: list[str]) -> str:
    items = "".join(
        f'<span class="lg"><i class="sw" style="background:var(--c-{f})"></i>{f}</span>'
        for f in FAMILY_ORDER if f in families_present
    )
    return f'<div class="legend">{items}</div>'


def _stat_tiles(before: Kit, after: Kit | None, before_pieces, after_by_id) -> str:
    tiles = [("kit", _esc(before.name)), ("pieces", str(len(before_pieces))),
             ("slots", str(len({p.slot for p in before_pieces})))]
    if after is not None:
        d_sub, d_cen = [], []
        for p in before_pieces:
            a = after_by_id.get(p.id)
            if a and p.analysis and a.analysis:
                d_sub.append((a.analysis.sub_energy_ratio - p.analysis.sub_energy_ratio) * 100)
                if p.analysis.spectral_centroid_hz > 0:
                    d_cen.append((a.analysis.spectral_centroid_hz / p.analysis.spectral_centroid_hz - 1) * 100)
        if d_sub:
            tiles.append(("avg Δ sub", f"{np.mean(d_sub):+.1f} pp"))
        if d_cen:
            tiles.append(("avg centroid shift", f"{np.mean(d_cen):+.0f} %"))
    cells = "".join(f'<div class="tile"><div class="tval">{v}</div><div class="tlab">{k}</div></div>' for k, v in tiles)
    return f'<div class="tiles">{cells}</div>'


def _table(before_pieces, after_by_id) -> str:
    comparing = bool(after_by_id)
    head = ["id", "slot", "dur ms", "centroid Hz", "sub %", "peak dB"]
    if comparing:
        head += ["Δ sub pp", "Δ centroid %", "Δ peak dB"]
    rows = []
    for p in before_pieces:
        if not p.analysis:
            continue
        a = p.analysis
        cells = [p.id, p.slot.value, f"{a.duration_s * 1000:.0f}", f"{a.spectral_centroid_hz:.0f}",
                 f"{a.sub_energy_ratio * 100:.0f}", f"{a.peak_dbfs:.1f}"]
        if comparing:
            o = after_by_id.get(p.id)
            oa = o.analysis if o else None
            if oa:
                cells += [f"{(oa.sub_energy_ratio - a.sub_energy_ratio) * 100:+.0f}",
                          f"{(oa.spectral_centroid_hz / a.spectral_centroid_hz - 1) * 100:+.0f}" if a.spectral_centroid_hz else "–",
                          f"{oa.peak_dbfs - a.peak_dbfs:+.1f}"]
            else:
                cells += ["–", "–", "–"]
        rows.append("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in cells) + "</tr>")
    thead = "<tr>" + "".join(f"<th>{_esc(h)}</th>" for h in head) + "</tr>"
    return f'<table class="data"><thead>{thead}</thead><tbody>{"".join(rows)}</tbody></table>'


# --- CSS ---------------------------------------------------------------------


def _css() -> str:
    cat_light = "".join(f"  --c-{f}: {_CAT_LIGHT[i]};\n" for i, f in enumerate(FAMILY_ORDER))
    cat_dark = "".join(f"  --c-{f}: {_CAT_DARK[i]};\n" for i, f in enumerate(FAMILY_ORDER))
    # sequential blue ramp (light→dark) + dark-mode variant
    seq_light = ["#eef4fb", "#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#184f95"]
    seq_dark = ["#22303f", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4"]
    seq_l = "".join(f"  --seq{i}: {c};\n" for i, c in enumerate(seq_light))
    seq_d = "".join(f"  --seq{i}: {c};\n" for i, c in enumerate(seq_dark))
    return (
        """
*{box-sizing:border-box}
.viz{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--sec:#52514e;--muted:#898781;
--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.10);
--divn3:#d03b3b;--divn2:#e06a5a;--divn1:#e6a897;--div0:#f0efec;--divp1:#9ec5f4;--divp2:#4f95e0;--divp3:#184f95;
"""
        + cat_light
        + seq_l
        + """font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);background:var(--plane);
padding:24px;max-width:1180px;margin:0 auto;line-height:1.4}
@media (prefers-color-scheme:dark){.viz{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--sec:#c3c2b7;--muted:#898781;
--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);
--divn3:#e66767;--divn2:#d5715a;--divn1:#8f6a5c;--div0:#383835;--divp1:#2f5a86;--divp2:#3987e5;--divp3:#9ec5f4;
"""
        + cat_dark
        + seq_d
        + """}}
:root[data-theme=dark] .viz{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--sec:#c3c2b7;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);
--divn3:#e66767;--divn2:#d5715a;--divn1:#8f6a5c;--div0:#383835;--divp1:#2f5a86;--divp2:#3987e5;--divp3:#9ec5f4;
"""
        + cat_dark
        + seq_d
        + """}
:root[data-theme=light] .viz{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--grid:#e1e0d9;
"""
        + cat_light
        + seq_l
        + """}
h1{font-size:22px;margin:0 0 2px} h2{font-size:15px;margin:26px 0 8px;color:var(--sec);font-weight:600}
.sub{color:var(--sec);font-size:13px;margin:0 0 14px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:14px}
.chart{width:100%;height:auto;display:block;overflow:visible}
.grid{stroke:var(--grid);stroke-width:1}
.arrow{stroke:var(--muted);stroke-width:1.5;opacity:.7}
.tick{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.row-label{fill:var(--sec);font-size:11px;font-variant-numeric:tabular-nums}
.axis-title{fill:var(--sec);font-size:12px}
.pt-label{fill:var(--muted);font-size:10px}
.tiles{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0 4px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 16px;min-width:120px}
.tval{font-size:22px;font-weight:650} .tlab{font-size:12px;color:var(--sec);margin-top:2px}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin:2px 0 6px;font-size:12px;color:var(--sec)}
.lg{display:inline-flex;align-items:center;gap:5px} .sw{width:11px;height:11px;border-radius:3px;display:inline-block}
"""
        + "".join(f".seq{i}{{fill:var(--seq{i})}}\n" for i in range(6))
        + "".join(f".{c}{{fill:var(--{c})}}\n" for c in ["divn3", "divn2", "divn1", "div0", "divp1", "divp2", "divp3"])
        + """
.wave-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}
.wave-cell{margin:0;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:8px}
.wave-cell figcaption{font-size:11px;color:var(--sec);margin-bottom:2px}
.wave{width:100%;height:auto;display:block} .wv-b{color:var(--muted)} .wv-a{color:var(--sec)}
table.data{border-collapse:collapse;width:100%;font-size:12px;font-variant-numeric:tabular-nums}
table.data th,table.data td{text-align:right;padding:5px 9px;border-bottom:1px solid var(--border)}
table.data th{color:var(--sec);font-weight:600} table.data td:first-child,table.data th:first-child,
table.data td:nth-child(2),table.data th:nth-child(2){text-align:left}
details{margin-top:6px} summary{cursor:pointer;color:var(--sec);font-size:13px}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);padding:5px 8px;border-radius:6px;
font-size:12px;opacity:0;transition:opacity .08s;z-index:9;white-space:nowrap}
"""
    )


_JS = """
(function(){var t=document.getElementById('tip');if(!t)return;
document.querySelectorAll('.pt').forEach(function(g){
 g.addEventListener('mousemove',function(e){t.textContent=g.getAttribute('data-tip');
   t.style.left=(e.clientX+12)+'px';t.style.top=(e.clientY+12)+'px';t.style.opacity=1;});
 g.addEventListener('mouseleave',function(){t.style.opacity=0;});});})();
"""


# --- assembly ----------------------------------------------------------------


def build_report_html(before: Kit, base_before: Path, after: Kit | None = None,
                      base_after: Path | None = None, full_doc: bool = True) -> str:
    bp = before.pieces
    after_by_id = {p.id: p for p in after.pieces} if after else {}
    fams = [_family(p.slot) for p in bp] + [_family(p.slot) for p in after_by_id.values()]
    fams_present = [f for f in FAMILY_ORDER if f in fams]

    title = before.name if after is None else f"{before.name} → {after.name}"
    subtitle = (f"characterizing {len(bp)} one-shots"
                + (f" · and how the remix changed them" if after else ""))

    body = [f'<div class="viz">']
    body.append(f"<h1>drumkitgen report · {_esc(title)}</h1>")
    body.append(f'<p class="sub">{_esc(subtitle)}</p>')
    body.append(_stat_tiles(before, after, bp, after_by_id))

    body.append("<h2>Feature map — spectral centroid × sub energy</h2>")
    body.append(_legend(fams_present))
    body.append('<div class="card">' + _feature_map(bp, after_by_id) + "</div>")
    if after:
        body.append('<p class="sub">Hollow ring = source, filled = remix; the arrow is the shift. Marker size = duration.</p>')

    body.append("<h2>Spectral profile — energy per frequency band" + (" (source)" if after else "") + "</h2>")
    body.append('<div class="card">' + _heatmap(bp, "seq") + "</div>")

    if after:
        body.append("<h2>Spectral change — remix minus source (pp per band)</h2>")
        body.append('<p class="sub"><span style="color:var(--divp2)">■</span> gained energy &nbsp; <span style="color:var(--divn2)">■</span> lost energy</p>')
        body.append('<div class="card">' + _heatmap(list(after_by_id.values()), "div", {p.id: p for p in bp}) + "</div>")

    body.append("<h2>Waveform envelopes" + (" — source vs remix" if after else "") + "</h2>")
    body.append('<div class="card">' + _waveforms(bp, base_before, after_by_id, base_after) + "</div>")

    body.append("<h2>Table view</h2>")
    body.append("<details open><summary>all measurements</summary>" + _table(bp, after_by_id) + "</details>")

    body.append('<div id="tip"></div>')
    body.append("</div>")
    body.append(f"<script>{_JS}</script>")
    content = "\n".join(body)

    if not full_doc:
        return f"<style>{_css()}</style>\n{content}"
    return (
        f'<!doctype html><html><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>drumkitgen report · {_esc(title)}</title><style>{_css()}</style></head>"
        f"<body>{content}</body></html>"
    )


def write_report(before: Kit, base_before: Path, out_dir: str | Path,
                 after: Kit | None = None, base_after: Path | None = None) -> Path:
    """Write a standalone ``index.html`` report. Returns its path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "index.html"
    dest.write_text(build_report_html(before, base_before, after, base_after, full_doc=True), encoding="utf-8")
    return dest

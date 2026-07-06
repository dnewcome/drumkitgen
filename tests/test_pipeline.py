"""End-to-end + classifier sanity checks over synthesized fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from drumkitgen import io_yaml
from drumkitgen.analysis import analyze
from drumkitgen.classify import classify
from drumkitgen.ingest import build_kit, write_kit
from drumkitgen.slots import Slot
from drumkitgen import synth_probe as sp


def test_kick_reads_as_sub_heavy_and_low():
    a = analyze(sp.kick(), sp.SR)
    assert a.sub_energy_ratio > 0.3
    assert a.spectral_centroid_hz < 1500


def test_hat_reads_as_bright_and_short():
    a = analyze(sp.hat(open_=False), sp.SR)
    assert a.spectral_centroid_hz > 5000
    assert a.decay_time_s < 0.2
    assert a.sub_energy_ratio < 0.1


@pytest.mark.parametrize(
    "make, filename, expected",
    [
        (sp.kick, "kick_01.wav", Slot.KICK),
        (sp.snare, "snare_01.wav", Slot.SNARE),
        (lambda: sp.hat(open_=False), "hat_closed_01.wav", Slot.HAT_CLOSED),
        (lambda: sp.hat(open_=True), "hat_open_01.wav", Slot.HAT_OPEN),
        (sp.clap, "clap_01.wav", Slot.CLAP),
    ],
)
def test_classify_with_name_hint(make, filename, expected):
    a = analyze(make(), sp.SR)
    slot, conf = classify(a, filename)
    assert slot == expected
    assert conf > 0.3


def test_kick_classifies_from_features_alone():
    # No filename hint — features must carry it.
    a = analyze(sp.kick(), sp.SR)
    slot, _ = classify(a, filename=None)
    assert slot == Slot.KICK


def test_pack_roundtrip(tmp_path: Path):
    raw = sp.write_demo_samples(tmp_path / "raw")
    kit = build_kit(raw, name="testkit", prompt="a test")
    out = write_kit(kit, tmp_path / "kit")

    assert (out / "kit.yaml").exists()
    assert (out / "testkit.sfz").exists()
    assert len(list((out / "samples").glob("*.wav"))) == len(sp.DEMO_KIT)

    # Canonical round-trips losslessly.
    reloaded = io_yaml.read(out / "kit.yaml")
    assert reloaded.name == "testkit"
    assert reloaded.prompt == "a test"
    assert len(reloaded.pieces) == len(sp.DEMO_KIT)

    # Every piece got a MIDI key and the .sfz references it.
    sfz = (out / "testkit.sfz").read_text()
    for piece in reloaded.pieces:
        assert f"key={piece.playback.root_key}" in sfz


def test_sub_layer_adds_low_end():
    # The DSP claim, tested directly on a sound that starts with ~no sub.
    from drumkitgen.remix import sub_layer

    bright = sp.hat(open_=False)
    before = analyze(bright, sp.SR).sub_energy_ratio
    after = analyze(sub_layer(bright, sp.SR, freq=50.0, amount=0.8), sp.SR).sub_energy_ratio
    assert after > before + 0.1


def test_remix_records_chain_and_provenance(tmp_path: Path):
    from drumkitgen.remix import RemixRecipe, remix_kit

    raw = sp.write_demo_samples(tmp_path / "raw")
    src = build_kit(raw, name="src")
    out = remix_kit(src, tmp_path / "remix", RemixRecipe(drive=0.5, sub=0.8, tune=-1.0))

    assert (tmp_path / "remix" / "kit.yaml").exists()
    assert len(list((tmp_path / "remix" / "samples").glob("*.wav"))) == len(sp.DEMO_KIT)

    # Kicks get the sub-layer in their chain; everything is marked & traceable.
    assert any("sub_layer" in s for s in out.by_slot(Slot.KICK)[0].source.chain)
    for piece in out.pieces:
        assert piece.source.kind == "remixed"
        assert piece.source.chain  # non-empty transform history
        assert piece.source.origin  # points back at the pristine source

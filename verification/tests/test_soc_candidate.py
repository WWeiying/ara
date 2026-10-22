from pathlib import Path

import pytest

from fpga import prepare_soc_candidate as candidate
from fpga.prepare_linux_bundle import file_record


def fixture_tree(tmp_path):
    base = tmp_path / "export"
    (base / "rtl").mkdir(parents=True)
    (base / "rtl/a.sv").write_text("module a; endmodule\n")
    (base / "rtl/keep.sv").write_text("// preserved adapter\n")
    (base / "manifest.json").write_text("{}\n")
    incoming = tmp_path / "new.sv"
    incoming.write_text("module a; wire fixed_path; endmodule\n")
    replacements = {"rtl/a.sv": {"source": file_record(incoming), "reason": "test"}}
    return base, incoming, replacements


def test_stage_isolated_and_exact(tmp_path):
    base, incoming, replacements = fixture_tree(tmp_path)
    before = (base / "rtl/a.sv").read_bytes()
    destination = tmp_path / "candidate"
    records, changes = candidate.stage_tree(base, destination, replacements)
    assert (base / "rtl/a.sv").read_bytes() == before
    assert (destination / "rtl/a.sv").read_bytes() == incoming.read_bytes()
    assert (destination / "rtl/keep.sv").read_bytes() == (base / "rtl/keep.sv").read_bytes()
    assert (destination / "rtl/a.sv").stat().st_ino != incoming.stat().st_ino
    assert (destination / "rtl/keep.sv").stat().st_ino != (base / "rtl/keep.sv").stat().st_ino
    assert changes[0]["changed"] is True
    assert changes[0]["before"] == records["rtl/a.sv"]["sha256"]


def test_rejects_existing_output(tmp_path):
    base, _, replacements = fixture_tree(tmp_path)
    with pytest.raises(ValueError, match="unsafe destination"):
        candidate.stage_tree(base, base, replacements)


def test_rejects_nested_output(tmp_path):
    base, _, replacements = fixture_tree(tmp_path)
    with pytest.raises(ValueError, match="unsafe destination"):
        candidate.stage_tree(base, base / "new", replacements)


def test_rejects_source_drift(tmp_path):
    base, incoming, replacements = fixture_tree(tmp_path)
    incoming.write_text("unreviewed")
    with pytest.raises(ValueError, match="input changed"):
        candidate.stage_tree(base, tmp_path / "candidate", replacements)


def test_rejects_baseline_drift_after_validation(tmp_path):
    base, _, replacements = fixture_tree(tmp_path)
    records = candidate.tree_records(base, exclude_build=False)
    (base / "rtl/keep.sv").write_text("unreviewed adapter")
    destination = tmp_path / "candidate"
    with pytest.raises(ValueError, match="baseline drift since validation"):
        candidate.stage_tree(base, destination, replacements, records)
    assert not destination.exists()


def test_explicit_selection_omits_unsealed_artifacts(tmp_path):
    base, _, replacements = fixture_tree(tmp_path)
    (base / "old.bit").write_bytes(b"historical")
    destination = tmp_path / "candidate"
    candidate.stage_tree(base, destination, replacements,
                         include_paths={"rtl/a.sv", "rtl/keep.sv", "manifest.json"})
    assert not (destination / "old.bit").exists()
    assert (base / "old.bit").read_bytes() == b"historical"


def test_selection_cannot_exclude_replacement(tmp_path):
    base, _, replacements = fixture_tree(tmp_path)
    with pytest.raises(ValueError, match="replacement excluded"):
        candidate.stage_tree(base, tmp_path / "candidate", replacements,
                             include_paths={"rtl/keep.sv"})


def test_capture_rejects_rebased_evidence(tmp_path):
    source = tmp_path / "summary.json"
    source.write_text('{"status":"PASS"}')
    records = {}
    candidate.captured_json(records, source)
    source.write_text('{"status":"FAIL"}')
    with pytest.raises(ValueError, match="captured input drift"):
        candidate.capture(records, source)


def test_collect_rejects_core_drift_during_patch_validation(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    export = root / "export"
    export.mkdir(parents=True)
    meta = export / "manifest.json"
    meta.write_text("{}")
    patch_dir = root / "verification/patches"
    patch_dir.mkdir(parents=True)
    (patch_dir / "dependencies.json").write_text("{}")
    patch = patch_dir / "cva6-local-fixes.patch"
    patch.write_text("test approved patch")
    for name in candidate.CORE:
        path = root / "hardware/deps/cva6" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("reviewed input")
    patch_hash = file_record(patch)["sha256"]
    monkeypatch.setattr(candidate, "BASE_META", {"manifest.json": file_record(meta)["sha256"]})
    monkeypatch.setattr(candidate, "PATCH_HASHES", {"cva6": patch_hash})
    monkeypatch.setattr(candidate, "export_inventory", lambda _: ({"status": "valid"},))
    monkeypatch.setattr(candidate, "load_registry", lambda _: {
        "cva6": {"sha256": patch_hash, "revision": "fixture"}})
    monkeypatch.setattr(candidate, "validate_submodules", lambda *args: None)

    def changed_after_validation(*args):
        (root / "hardware/deps/cva6/core/decoder.sv").write_text("concurrent unreviewed edit")
        return "applied"

    monkeypatch.setattr(candidate, "patch_state", changed_after_validation)
    with pytest.raises(ValueError, match="input changed"):
        candidate.collect(root, export, root / "plic", root / "mmio", root / "linux")


@pytest.mark.parametrize("name", ("../outside.sv", "/outside.sv", "rtl/../outside.sv"))
def test_rejects_unsafe_target(tmp_path, name):
    base, _, replacements = fixture_tree(tmp_path)
    with pytest.raises(ValueError, match="unsafe"):
        candidate.stage_tree(base, tmp_path / "candidate", {name: replacements["rtl/a.sv"]})


def test_rejects_missing_target(tmp_path):
    base, _, replacements = fixture_tree(tmp_path)
    with pytest.raises(ValueError, match="target absent"):
        candidate.stage_tree(base, tmp_path / "candidate", {"rtl/missing.sv": replacements["rtl/a.sv"]})


def test_rejects_input_symlink(tmp_path):
    base, incoming, replacements = fixture_tree(tmp_path)
    (base / "rtl/alias.sv").symlink_to(incoming)
    with pytest.raises(ValueError, match="symlink"):
        candidate.stage_tree(base, tmp_path / "candidate", replacements)


def test_rejects_destination_symlink(tmp_path):
    base, _, replacements = fixture_tree(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(base, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        candidate.stage_tree(base, alias / "new", replacements)


def test_hash_gate(tmp_path):
    source = tmp_path / "input"
    source.write_text("old")
    expected = file_record(source)["sha256"]
    candidate.require_hash(source, expected)
    source.write_text("new")
    with pytest.raises(ValueError, match="unreviewed input"):
        candidate.require_hash(source, expected)


def test_seal_no_self_reference(tmp_path):
    source = tmp_path / "input"
    source.write_text("data")
    candidate.seal(tmp_path)
    first = (tmp_path / "SHA256SUMS").read_bytes()
    candidate.seal(tmp_path)
    assert first == (tmp_path / "SHA256SUMS").read_bytes()
    assert b"SHA256SUMS" not in first


def test_current_plic_and_mmio_evidence():
    out = candidate.ROOT / "verification/out"
    if not (out / "plic-contract-fixed-vcs-20260922/summary.json").is_file():
        pytest.skip("local VCS evidence not present")
    candidate.checked_run(out / "plic-contract-fixed-vcs-20260922", "plic")
    candidate.checked_run(out / "mmio-contract-fixed-vcs-20260922", "mmio")

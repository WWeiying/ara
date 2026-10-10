"""Preparation safety tests; these do not count as RTL coverage."""

import json
from pathlib import Path

import pytest

from fpga import prepare_mmio as prep
import run_plic_contract as contract


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(prep, "ROOT", tmp_path)
    return tmp_path / "verification/out"


def test_isolated_patch_and_pristine_sources(root):
    output = root / "new"
    report = prep.prepare(output)
    assert report["status"] == "PREPARED_NOT_VALIDATED"
    assert report["applied_to_export"] is False
    assert report["inputs_unchanged"] is True
    assert all(row["returncode"] == 0 for row in report["commands"])
    assert len(report["commands"]) == 2
    for name, expected in prep.INPUTS.items():
        assert prep.file_record(output / "inputs/export" / name)["sha256"] == expected
        assert prep.file_record(prep.EXPORT / name)["sha256"] == expected
        assert report["files"][name]["sha256"] != expected
    leaf = (output / "rtl/axi/src/axi_to_detailed_mem.sv").read_text()
    bridge = (output / "rtl/register_interface/src/axi_to_reg_v2.sv").read_text()
    assert "EnableReadByteMask = 1'b0" in leaf
    assert "read_byte_mask(meta.addr, meta.size)" in leaf
    assert "read_byte_mask(meta_buf.addr, meta_buf.size)" in leaf
    assert ".EnableReadByteMask ( 1'b1" in bridge
    assert "reg_req[i].write & (reg_req[i].wstrb" not in bridge


def test_stale_output_rejected(root):
    output = root / "old"
    output.mkdir(parents=True)
    (output / "keep").write_text("keep")
    with pytest.raises(ValueError, match="new directory"):
        prep.prepare(output)
    assert (output / "keep").read_text() == "keep"


def test_symlink_output_rejected(root):
    root.mkdir(parents=True)
    target = root / "target"
    link = root / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError):
        prep.prepare(link)
    assert not target.exists()


def test_changed_baseline_rejected(root):
    export = root / "fake_export"
    for name in prep.INPUTS:
        path = export / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((prep.EXPORT / name).read_bytes())
    path.write_text(path.read_text() + "// changed\n")
    with pytest.raises(ValueError, match="unreviewed MMIO baseline"):
        prep.prepare(root / "new", export)
    assert not (root / "new").exists()


@pytest.mark.parametrize("change", ["escape", "duplicate", "mode", "absolute"])
def test_unapproved_patch_rejected(change):
    text = prep.PATCH.read_text()
    if change == "escape":
        text = text.replace("axi/src/axi_to_detailed_mem.sv", "../outside.sv")
    elif change == "duplicate":
        text += text
    elif change == "mode":
        text += "new mode 100755\n"
    else:
        text += "--- /tmp/outside\n+++ /tmp/outside\n@@ -1 +1 @@\n-old\n+new\n"
    with pytest.raises(ValueError):
        prep.validate_patch(text)


def test_runner_uses_only_selected_overrides(root, monkeypatch):
    prepared = root / "sources"
    prep.prepare(prepared)
    plic = contract.ROOT / "verification/out/plic-candidate-20260922/rv_plic"
    if not plic.is_dir():
        pytest.skip("local candidate is unavailable")
    report = contract.run(plic, root / "test", prepare_only=True, mmio_dir=prepared / "rtl")
    assert report["status"] == "NOT_RUN", report["errors"]
    for name in contract.MMIO_OVERRIDES:
        record = report["sources"]["export/" + name]
        assert Path(record["path"]) == prepared / "rtl" / name
        assert prep.file_record(Path(record["frozen"]))["sha256"] == record["sha256"]
    assert Path(report["sources"]["export/axi/src/axi_pkg.sv"]["path"]) == contract.EXPORT / "axi/src/axi_pkg.sv"
    assert json.loads((root / "test/summary.json").read_text())["status"] == "NOT_RUN"


def test_missing_override_does_not_fallback(root):
    plic = contract.ROOT / "verification/out/plic-candidate-20260922/rv_plic"
    report = contract.run(plic, root / "missing", prepare_only=True, mmio_dir=root / "absent")
    assert report["status"] == "FAIL"
    assert not (root / "missing/build").exists()

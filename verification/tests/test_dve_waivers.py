import importlib.util
import hashlib
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "coverage/prepare_dve_waivers.py"
spec = importlib.util.spec_from_file_location("waivers", PATH)
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


def test_native_load_precedes_observer_exclusions():
    text = (PATH.parent / "dve_waivers.tcl").read_text()
    assert text.index("gui_exclusion_file -load") < text.index("foreach {path recursive reason}")
    assert text.index("eval $args") < text.index("gui_exclusion -id $id -recalculate")
    assert text.index("-recalculate") < text.index("gui_exclusion_file -save")


def test_scope_is_observer_only():
    data = b'''<design><srcdef name="ara_tb"><srcinst id="1" pid="0" name="ara_tb"/></srcdef>
    <srcdef name="ara_soc"><srcinst id="2" pid="1" name="dut"/></srcdef>
    <srcdef name="ara_commit_monitor"><srcinst id="3" pid="2" name="monitor"/></srcdef>
    <srcdef name="qbs_engine"><srcinst id="4" pid="2" name="qbs"/></srcdef></design>'''
    assert [r[0] for r in w.scopes(data)] == ["ara_tb.dut.monitor"]


def test_unknown_design_not_waived(tmp_path):
    d = tmp_path / "sim.vdb/snps/coverage/db/design"
    d.mkdir(parents=True)
    (d / "verilog.design.xml").write_text("<design/>")
    out = tmp_path / "report"
    out.mkdir()
    result = w.prepare(tmp_path / "sim.vdb", out, "auto")
    assert result["status"] == "NOT_APPLICABLE_UNREVIEWED_DESIGN"
    assert not (out / "waiver_plan.tcl").exists()
    assert not (out / "points.el").exists()


def test_disabled(tmp_path):
    d = tmp_path / "sim.vdb/snps/coverage/db/design"
    d.mkdir(parents=True)
    (d / "verilog.design.xml").write_text("<design/>")
    assert w.prepare(tmp_path / "sim.vdb", tmp_path, "off")["status"] == "DISABLED"
    assert json.loads((tmp_path / "waiver_status.json").read_text())["waived_report"] is None


def test_changed_design_rejected_at_finalization(tmp_path):
    import pytest
    d = tmp_path / "sim.vdb/snps/coverage/db/design"
    d.mkdir(parents=True)
    source = d / "verilog.design.xml"
    source.write_text("<design/>")
    w.prepare(tmp_path / "sim.vdb", tmp_path, "off")
    source.write_text("changed")
    with pytest.raises(ValueError, match="Compiled design changed"):
        w.finalize(tmp_path / "sim.vdb", tmp_path)


def native_points(points):
    """Include checksum/signature fields, as native DVE saved exclusions do."""
    lines = []
    for path, kind in sorted(points):
        lines += ['CHECKSUM: "1532764271 3998926456"', f"INSTANCE: {path}",
                  'ANNOTATION: "host fixture"']
        if kind.startswith("Branch "):
            branch, vector = kind.split()[1:]
            lines.append(f'Branch {branch} "949433246" "flush_i" {vector} "flush_i 1"')
        elif kind.startswith("Block "):
            lines.append(kind + ' "1270893570" "fixture assignment;"')
        elif kind == "Toggle flush_i":
            lines.append(kind + ' "net flush_i"')
        else:
            lines.append(kind)
    return "\n".join(lines) + "\n"


@pytest.fixture
def approved_design(tmp_path, monkeypatch):
    design = tmp_path / "sim.vdb"
    data_dir = design / "snps/coverage/db/design"
    data_dir.mkdir(parents=True)
    data = b'''<design><srcdef name="ara_tb"><srcinst id="1" pid="0" name="ara_tb"/></srcdef>
    <srcdef name="ara_commit_monitor"><srcinst id="2" pid="1" name="observer"/></srcdef>
    <srcdef name="ara"><srcinst id="3" pid="1" name="dut"/></srcdef></design>'''
    (data_dir / "verilog.design.xml").write_bytes(data)
    shape = design / "snps/coverage/db/shape"
    shape.mkdir()
    for metric in ("line", "branch", "tgl"):
        (shape / f"{metric}.xml").write_bytes(metric.encode())
    shape_files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in shape.iterdir()}
    shape_hash = hashlib.sha256(json.dumps(shape_files, sort_keys=True).encode()).hexdigest()
    monkeypatch.setattr(w, "APPROVED", {hashlib.sha256(data).hexdigest(): "host-fixture"})
    monkeypatch.setattr(w, "SHAPES", {"host-fixture": shape_hash})
    here = tmp_path / "tool"
    (here / "waivers").mkdir(parents=True)
    points = here / "waivers/operand_flush.el"
    points.write_text(native_points(w.approved_points()))
    monkeypatch.setattr(w, "HERE", here)
    output = tmp_path / "report"
    output.mkdir()
    return design, output, points


def saved_reports(design, output, points):
    w.prepare(design, output, "auto")
    raw = "Name,Depth,Line,Condition,Branch,FSM,Toggle\nara_tb,0,1%,2%,3%,NA,4%\n"
    waived = "Name,Depth,Line,Condition,Branch,FSM,Toggle\nara_tb,0,2%,3%,4%,NA,5%\n"
    (output / "summary.csv").write_text(raw)
    (output / "summary_waived.csv").write_text(waived)
    (output / "exclusions.el").write_text(points.read_text() + "INSTANCE: ara_tb.observer\n")
    return raw, waived


def test_approved_points_are_exact_and_not_whole_scope():
    points = w.approved_points()
    assert len(points) == 88
    assert len({path for path, _ in points}) == 24
    assert sum(kind.startswith("Branch ") for _, kind in points) == 16
    assert sum(kind.startswith("Block ") for _, kind in points) == 48
    assert sum(kind == "Toggle flush_i" for _, kind in points) == 24
    assert not any("lsu" in path or "fifo" in path or kind == "INSTANCE" for path, kind in points)


def test_native_checksum_signature_round_trip():
    assert w.exclusion_items(native_points(w.approved_points())) == w.approved_points()


def test_real_native_operand_file_matches_exact_allowlist():
    points = PATH.parent / "waivers/operand_flush.el"
    assert w.exclusion_items(points.read_text()) == w.approved_points()


def mutated_points(text, mutation):
    if mutation == "missing":
        return text.replace('Block 7 "1270893570" "fixture assignment;"\n', "", 1)
    if mutation == "extra":
        return text + "INSTANCE: ara_tb.dut\nBlock 999\n"
    if mutation == "whole_scope":
        return text + "INSTANCE: ara_tb.dut\n"
    if mutation == "operand_whole_scope":
        path = sorted(w.approved_points())[0][0]
        return text + f"INSTANCE: {path}\n"
    if mutation == "wrong_vector":
        return text.replace('(0) "flush_i 1"', '(1) "flush_i 0"', 1)
    if mutation == "dynamic_lsu":
        return text.replace("i_operand_queue_alu_a", "i_operand_queue_store", 1)
    if mutation == "descendant_fifo":
        return text + "INSTANCE: ara_tb.dut.i_operand_queue.i_operand_fifo\n"
    if mutation == "mfpu_branch":
        path = next(p for p, _ in sorted(w.approved_points()) if p.endswith("_mfpu_a"))
        return text + f"INSTANCE: {path}\nBranch 2 (0)\n"
    if mutation == "whole_branch":
        return text.replace(' (0) "flush_i 1"', "", 1)
    if mutation == "condition":
        return text + "INSTANCE: ara_tb.dut\nCondition 1\n"
    raise AssertionError(mutation)


MUTATIONS = ("missing", "extra", "whole_scope", "operand_whole_scope", "wrong_vector",
             "dynamic_lsu", "descendant_fifo", "mfpu_branch", "whole_branch", "condition")


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_prepare_rejects_missing_or_broader_native_input(approved_design, mutation):
    design, output, points = approved_design
    points.write_text(mutated_points(points.read_text(), mutation))
    with pytest.raises(ValueError):
        w.prepare(design, output, "auto")
    assert not (output / "points.el").exists()
    assert not (output / "waiver_status.json").exists()


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_finalize_rejects_missing_or_broader_native_output(approved_design, mutation):
    design, output, points = approved_design
    raw, waived = saved_reports(design, output, points)
    (output / "exclusions.el").write_text(mutated_points(points.read_text(), mutation) + "INSTANCE: ara_tb.observer\n")
    with pytest.raises(ValueError):
        w.finalize(design, output)
    assert json.loads((output / "waiver_status.json").read_text())["status"] == "PREPARED"
    assert (output / "summary.csv").read_text() == raw
    assert (output / "summary_waived.csv").read_text() == waived


def test_finalize_rejects_missing_observer_scope(approved_design):
    design, output, points = approved_design
    saved_reports(design, output, points)
    (output / "exclusions.el").write_text(points.read_text())
    with pytest.raises(ValueError, match="missing or additional"):
        w.finalize(design, output)


def test_finalize_rejects_observers_only_regression(approved_design):
    design, output, points = approved_design
    saved_reports(design, output, points)
    (output / "exclusions.el").write_text("INSTANCE: ara_tb.observer\n")
    with pytest.raises(ValueError, match="missing or additional"):
        w.finalize(design, output)


def test_finalize_exact_set_preserves_raw_and_native_file(approved_design):
    design, output, points = approved_design
    raw, waived = saved_reports(design, output, points)
    native = (output / "exclusions.el").read_bytes()
    w.finalize(design, output)
    record = json.loads((output / "waiver_status.json").read_text())
    assert record["status"] == "APPLIED"
    assert (output / "summary.csv").read_text() == raw
    assert (output / "summary_waived.csv").read_text() == waived
    assert (output / "exclusions.el").read_bytes() == native
    assert record["files"]["exclusions.el"] == hashlib.sha256(native).hexdigest()


@pytest.mark.parametrize("mutation", ("changed", "missing", "extra"))
def test_prepare_shape_inventory_is_bound(approved_design, mutation):
    design, output, _ = approved_design
    shape = design / "snps/coverage/db/shape"
    if mutation == "changed":
        (shape / "line.xml").write_text("changed point mapping")
    elif mutation == "missing":
        (shape / "line.xml").unlink()
    else:
        (shape / "unreviewed.xml").write_text("extra points")
    with pytest.raises(ValueError, match="Coverage point shapes"):
        w.prepare(design, output, "auto")


def test_finalize_rejects_shape_drift(approved_design):
    design, output, points = approved_design
    saved_reports(design, output, points)
    (design / "snps/coverage/db/shape/line.xml").write_text("drift")
    with pytest.raises(ValueError, match="shape changed"):
        w.finalize(design, output)


@pytest.mark.parametrize("mode", ("off", "unknown"))
def test_disabled_or_unknown_design_never_reads_bad_native_points(approved_design, mode):
    design, output, points = approved_design
    points.write_text("INSTANCE: ara_tb.dut\n")
    if mode == "unknown":
        (design / "snps/coverage/db/design/verilog.design.xml").write_text("<different_design/>")
    result = w.prepare(design, output, "off" if mode == "off" else "auto")
    assert result["status"] == ("DISABLED" if mode == "off" else "NOT_APPLICABLE_UNREVIEWED_DESIGN")
    assert not (output / "points.el").exists()
    assert not (output / "waiver_plan.tcl").exists()


@pytest.mark.parametrize("stage", ("input", "saved_output"))
def test_extra_branch_vector_on_same_native_line_is_rejected(approved_design, stage):
    design, output, points = approved_design
    original = points.read_text()
    expanded = original.replace('(0) "flush_i 1"', '(0) "flush_i 1" (1) "flush_i 0"', 1)
    assert expanded != original
    if stage == "input":
        points.write_text(expanded)
        with pytest.raises(ValueError):
            w.prepare(design, output, "auto")
    else:
        saved_reports(design, output, points)
        (output / "exclusions.el").write_text(expanded + "INSTANCE: ara_tb.observer\n")
        with pytest.raises(ValueError):
            w.finalize(design, output)

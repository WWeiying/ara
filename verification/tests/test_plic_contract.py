"""Host-only tests. Synthetic logs below do not establish any RTL coverage."""

import json
from pathlib import Path
import re
import sys
from unittest.mock import Mock

import pytest

import run_plic_contract as runner


def kv(values):
    return " ".join(f"{key}={value}" for key, value in values.items())


def evidence():
    console = ["PLIC_CONFIG " + kv({**runner.SHAPE, "axi_data": 64, "axi_addr": 48, "cut": 1})]
    rows = []
    for txn in range(300):
        console += [f"PLIC_TX_BEGIN txn={txn} write=1 addr=000004000004 size=2 data=0000000300000000 strb=f0 expected=00",
                    f"PLIC_TX_END txn={txn} resp=00 data=0000000000000000"]
        for phase in range(7):
            row = dict.fromkeys(sorted(runner.FIELDS), "0")
            row.update(cycle=str(len(rows)), time_ns=f"{5 + 10 * len(rows):.3f}", rst="1",
                       txn=str(txn), case="physical_decode", awaddr="000004000004",
                       awid=f"{txn % 16:x}", awsize="2", wd="0000000300000000", ws="f0",
                       wl="1", bid=f"{txn % 16:x}", bresp="00", rresp="00")
            if phase == 0:
                row.update(awv="1", awr="1", wv="1", wr="1")
            else:
                row.update(bv="1", br="1" if phase == 6 else "0")
            rows.append(kv(row))
    console += [f"PLIC_CASE name={name} status=PASS failures=0" for name in runner.CASES]
    console += [f"PLIC_SOURCE id={source} context={context} status=PASS"
                for context in range(2) for source in runner.SOURCE_IDS]
    values = (0xfffffffe, 0xfffffffe, 1, 0, 6)
    console += [f"PLIC_EXPECT code={code} case=synthetic txn=0 cycle=1 expected={value:x} actual={value:x} status=PASS"
                for code, value in zip(runner.EXPECTS, values)]
    console += [f"PLIC_RESET case={name} cycle=1" for name in
                ("reserved_holes", "competition_completion", "read_side_effect")]
    console += [f"PLIC_RESULT status=PASS cases=7 transactions=300 checks=2400 cycles={len(rows)} failures=0"]
    probe = [f"# PLIC_PROBE schema=1 sample=pre_edge max_cycles={runner.MAX_CYCLES}", *rows,
             f"# END rows={len(rows)} completed=1 transactions=300 checks=2400"]
    return "\n".join(console), "\n".join(probe)


def test_synthetic_complete_evidence():
    assert runner.analyze(*evidence(), runner.SHAPE)["errors"] == []


@pytest.mark.parametrize("suffix", ["Fatal: injected", "Error-[BAD] injected", "Assertion failed",
                                   "UVM_ERROR injected", "PLIC_FAIL code=x case=x txn=0 addr=0 cycle=1"])
def test_late_error_overrides_pass(suffix):
    console, probe = evidence()
    assert runner.analyze(console + "\n" + suffix, probe, runner.SHAPE)["errors"]


@pytest.mark.parametrize("marker", ["PLIC_CASE name=word_lanes", "PLIC_SOURCE id=57 context=1",
                                    "PLIC_EXPECT code=threshold_read_claimed", "PLIC_RESULT",
                                    "PLIC_TX_END txn=299 "])
@pytest.mark.parametrize("duplicate", [False, True])
def test_missing_duplicate_marker(marker, duplicate):
    console, probe = evidence()
    line = next(line for line in console.splitlines() if line.startswith(marker))
    console = console + "\n" + line if duplicate else console.replace(line, "")
    assert runner.analyze(console, probe, runner.SHAPE)["errors"]


def test_recoverable_failure_stays_failure_with_later_pass():
    console, probe = evidence()
    console = console.replace("actual=fffffffe status=PASS", "actual=ffffffff status=FAIL", 1)
    result = runner.analyze(console, probe, runner.SHAPE)
    assert any("ie_zero_context0" in error for error in result["errors"])
    assert result["first_failure"]["code"] == "ie_zero_context0"
    assert len(result["observations"]) == 5


@pytest.mark.parametrize("old,new", [("cycle=1 ", "cycle=0 "), ("br=1", "br=0"),
                                    ("bresp=00", "bresp=10"), ("irq=0", "irq=x"),
                                    ("ip=0", "ip=1"), ("completed=1", "completed=0"),
                                    ("max_cycles=8192", "max_cycles=9999"),
                                    ("awaddr=000004000004", "awaddr=000000000004"),
                                    ("time_ns=5.000", "time_ns=6.000")])
def test_corrupted_probe_rejected(old, new):
    console, probe = evidence()
    assert old in probe
    # Inactive B payload has no contract; corrupt every B to reach an accepted one.
    changed = probe.replace(old, new) if old == "bresp=00" else probe.replace(old, new, 1)
    assert runner.analyze(console, changed, runner.SHAPE)["errors"]


def test_missing_and_truncated_probe():
    console, probe = evidence()
    for value in ("", "\n".join(probe.splitlines()[:-1]), probe + "\ntruncated"):
        assert runner.analyze(console, value, runner.SHAPE)["errors"]


def test_stale_output(tmp_path):
    (tmp_path / "summary.json").write_text("old")
    with pytest.raises(ValueError):
        runner.prepare_output(tmp_path)
    assert (tmp_path / "summary.json").read_text() == "old"


def test_symlink_output(tmp_path):
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "absent", target_is_directory=True)
    with pytest.raises(ValueError):
        runner.prepare_output(link)


def test_missing_candidate_does_not_compile(tmp_path, monkeypatch):
    command = Mock(side_effect=AssertionError("must not compile"))
    monkeypatch.setattr(runner, "command_run", command)
    report = runner.run(tmp_path / "missing", tmp_path / "out", prepare_only=True)
    assert report["status"] == "FAIL"
    command.assert_not_called()


def candidate():
    path = runner.ROOT / "verification/out/plic-candidate-20260922/rv_plic"
    if not path.is_dir():
        pytest.skip("isolated generated candidate unavailable")
    return path


def test_real_snapshot_prepare_only(tmp_path, monkeypatch):
    command = Mock(side_effect=AssertionError("prepare-only must never execute VCS"))
    monkeypatch.setattr(runner, "command_run", command)
    report = runner.run(candidate(), tmp_path / "out", prepare_only=True)
    assert report["status"] == "NOT_RUN", report["errors"]
    assert report["shape"] == runner.SHAPE
    assert runner.changed_sources(report["sources"]) == []
    command.assert_not_called()
    for entry in report["sources"].values():
        assert runner.sha256(entry["frozen"]) == entry["sha256"]
    command = json.loads((tmp_path / "out/compile_command.json").read_text())
    for argument in command:
        if argument.endswith(".sv") or argument.startswith("+incdir+"):
            assert str(tmp_path / "out/inputs") in argument
            assert "hardware/deps" not in argument
    bridge = [s for s in command if s.endswith("/axi_to_reg_v2.sv")]
    assert len(bridge) == 1 and "/register_interface/src/" in bridge[0]
    frozen_tb = Path(report["sources"]["tb/plic_contract_tb.sv"]["frozen"])
    frozen_tb.write_text("changed")
    assert runner.sha256(frozen_tb) != report["sources"]["tb/plic_contract_tb.sv"]["sha256"]


def test_shape_gate_and_legacy_is_not_pass(tmp_path, monkeypatch):
    plic = candidate()
    command = Mock(side_effect=AssertionError("must not compile wrong shape"))
    monkeypatch.setattr(runner, "command_run", command)
    report = runner.run(plic, tmp_path / "wrong", prepare_only=True, expect_legacy_failure=True)
    assert report["status"] == "FAIL"
    assert "unexpected PLIC shape" in report["errors"][0]
    console, probe = evidence()
    report = runner.analyze(console.replace("src=58 targets=2", "src=32 targets=1")
                           .replace("block_aw=26", "block_aw=27"), probe, runner.LEGACY_SHAPE)
    # Shape alone never changes normative outcomes or the explicit run-level legacy FAIL.
    assert report["probe"]["legacy_first_address_miss"] is False


def test_source_and_include_closure():
    paths = [runner.EXPORT / p for p in runner.EXPORT_SOURCES + runner.HEADERS]
    paths += [candidate() / p for p in runner.PLIC_SOURCES] + [runner.TB]
    for path in paths:
        assert path.is_file(), path
        text = re.sub(r"//[^\n]*|/\*.*?\*/", "", path.read_text(), flags=re.S)
        for include in re.findall(r'`include\s+"([^"]+)"', text):
            if include == "uvm_macros.svh":
                # Conditional only under UVM, which this runner does not define.
                continue
            assert any((runner.EXPORT / d / include).is_file() and
                       str(Path(d) / include) in runner.HEADERS for d in runner.INCLUDES), include
    assert len(set(runner.EXPORT_SOURCES)) == len(runner.EXPORT_SOURCES)


def test_bounded_command_timeout_cleanup(tmp_path):
    result = runner.command_run([sys.executable, "-c", "import time; time.sleep(20)"],
                                tmp_path / "timeout", 0.1)
    assert result["status"] == "TIMEOUT"
    assert result["returncode"] is not None
    assert result["elapsed_s"] < 10

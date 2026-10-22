import sys
import json
import signal
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

import run_qbs_read_contract as runner


def completed_log(mode="delayed"):
    return "\n".join([
        "QBS_MMU_RESPONSE t=200 combinational=%d req=1 valid=1" % (mode == "combinational"),
        "QBS read legacy cases PASS t=12345",
        *[f"[QBS_READ_CASE] {case} PASS" for case in runner.CASES],
        *[f"QBS stalled-AR fault PASS mode={m} delay={d}" for m in range(3) for d in (0, 6)],
        "QBS read engine PASS", "",
    ])


@pytest.mark.parametrize("mode", ["delayed", "combinational"])
def test_complete(mode):
    assert runner.check_log(completed_log(mode), mode) == []


@pytest.mark.parametrize("case", runner.CASES)
def test_missing_case_rejected(case):
    text = completed_log().replace(f"[QBS_READ_CASE] {case} PASS\n", "")
    assert runner.check_log(text, "delayed")


@pytest.mark.parametrize("record", [
    "QBS read engine PASS", "[QBS_READ_CASE] second_page_fault PASS",
    "QBS stalled-AR fault PASS mode=0 delay=0",
])
def test_duplicate_rejected(record):
    assert runner.check_log(completed_log() + record + "\n", "delayed")


@pytest.mark.parametrize("record", ["Fatal: injected", "Error-[ASSERT] bad", "Assertion failed"])
def test_pass_does_not_override_error(record):
    assert runner.check_log(completed_log() + record, "delayed")


def test_wrong_latency_mode_rejected():
    assert runner.check_log(completed_log("combinational"), "delayed")


def test_missing_matrix_rejected():
    text = completed_log().replace("QBS stalled-AR fault PASS mode=2 delay=6\n", "")
    assert runner.check_log(text, "delayed")


def test_stale_output_rejected(tmp_path):
    (tmp_path / "run.log").write_text("old pass")
    with pytest.raises(ValueError):
        runner.prepare_output(tmp_path)
    assert (tmp_path / "run.log").read_text() == "old pass"


def test_symlink_output_rejected(tmp_path):
    output = tmp_path / "link"
    output.symlink_to(tmp_path / "missing", target_is_directory=True)
    with pytest.raises(ValueError):
        runner.prepare_output(output)


def test_owner_exclusive_even_when_precheck_observes_empty(tmp_path, monkeypatch):
    runner.prepare_output(tmp_path)
    owner = (tmp_path / ".run-owner").read_text()
    # Model the other process having checked before the first claimed ownership.
    monkeypatch.setattr(Path, "iterdir", lambda self: iter(()))
    with pytest.raises(ValueError, match="another run owns"):
        runner.prepare_output(tmp_path)
    assert (tmp_path / ".run-owner").read_text() == owner


def test_snapshot_and_drift(tmp_path, monkeypatch):
    root, output = tmp_path / "repo", tmp_path / "out"
    root.mkdir()
    (root / "dut.sv").write_text("old")
    monkeypatch.setattr(runner, "SOURCES", ("dut.sv",))
    monkeypatch.setattr(runner, "HEADERS", ())
    records = runner.snapshot_sources(root, output)
    assert runner.changed_sources(records) == []
    (root / "dut.sv").write_text("new")
    assert (output / "inputs/dut.sv").read_text() == "old"
    assert runner.changed_sources(records) == ["dut.sv"]


def test_process_exit_and_log(tmp_path):
    result = runner.command_run([sys.executable, "-c", "print('test'); exit(3)"], tmp_path, 5)
    assert result["status"] == "FAIL"
    assert result["returncode"] == 3
    assert Path(result["log"]).read_text().strip() == "test"


def test_process_timeout(tmp_path):
    result = runner.command_run([sys.executable, "-c", "import time; time.sleep(60)"], tmp_path, .1)
    assert result["status"] == "TIMEOUT"
    assert result["returncode"] is not None


def test_missing_executable(tmp_path):
    result = runner.command_run([str(tmp_path / "absent")], tmp_path, 5)
    assert result["status"] == "FAIL"
    assert result["errors"]


@pytest.mark.parametrize("slow_parent", [False, True])
def test_children_killed_even_when_parent_exits_on_term(monkeypatch, slow_parent):
    process = Mock(pid=123)
    process.wait.side_effect = [subprocess.TimeoutExpired("test", 5) if slow_parent else 0, 0]
    kill = Mock()
    monkeypatch.setattr(runner.os, "killpg", kill)
    runner.stop_process_group(process)
    assert [call.args for call in kill.call_args_list] == [
        (123, signal.SIGTERM), (123, signal.SIGKILL)]


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_interrupt_cleans_and_records_failure(tmp_path, monkeypatch, interruption):
    process = Mock(pid=123, returncode=-signal.SIGTERM)
    process.wait.side_effect = [interruption(), 0, 0]
    monkeypatch.setattr(runner.subprocess, "Popen", Mock(return_value=process))
    kill = Mock()
    monkeypatch.setattr(runner.os, "killpg", kill)
    with pytest.raises(interruption):
        runner.command_run(["simv"], tmp_path, 10)
    result = json.loads((tmp_path / "command_result.json").read_text())
    assert result["status"] == "INTERRUPTED"
    assert kill.call_count == 2

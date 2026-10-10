import json
import os
from pathlib import Path
import signal
import sys
from unittest.mock import patch

import pytest

from ara_verify.model import TestCase as Case
from ara_verify.runner import (
    RegressionRunner, RunOptions, _contract_evidence, _run_monitored,
)
from verify import _parser
from ara_verify.plan import audit_run


SUCCESS = "Core Test *** SUCCESS ***\n"
SUMMARY = ("[ARA_CONTRACT] requests=2 responses=2 exceptions=0 mmu_request_cycles=0 "
           "protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0\n")


def options(root, **kwargs):
    values = dict(repo_root=root, output_root=root / "out", config="default", jobs=1,
                  seed=1, dry_run=False, build_only=False, skip_build=True,
                  simv=root / "simv", commit_trace=False, timeout_s=2,
                  contract_monitor=True)
    values.update(kwargs)
    return RunOptions(**values)


def logs(root, console, vcs=None):
    console_path, vcs_path = root / "console.log", root / "run.vcs.log"
    console_path.write_text(console)
    vcs_path.write_text(console if vcs is None else vcs)
    return console_path, vcs_path


def test_cli_contract_option():
    assert _parser().parse_args(["run", "--contract-monitor"]).contract_monitor


def test_each_log_is_checked_not_concatenated(tmp_path):
    result = _contract_evidence(*logs(tmp_path, SUCCESS + SUMMARY))
    assert result["status"] == "PASS"
    assert len(result["logs"]) == 2


@pytest.mark.parametrize("content", [
    SUCCESS, SUCCESS + SUMMARY + SUMMARY,
    SUCCESS + SUMMARY.replace("requests=2", "requests=0"),
    SUCCESS + SUMMARY.replace("protocol_errors=0", "protocol_errors=1"),
    SUCCESS + SUMMARY.replace("outstanding=0", "outstanding=1"),
    SUCCESS + SUMMARY + "Error: a prior assertion reported an error\n",
    SUCCESS + SUMMARY + "[ARA_CONTRACT_ERROR] duplicate ID\n",
])
def test_core_success_cannot_mask_protocol_failures(tmp_path, content):
    assert _contract_evidence(*logs(tmp_path, content))["status"] == "FAIL"


def test_different_successful_summaries_are_rejected(tmp_path):
    console, vcs = logs(tmp_path, SUCCESS + SUMMARY,
                        SUCCESS + SUMMARY.replace("=2", "=3"))
    result = _contract_evidence(console, vcs)
    assert "console and VCS protocol summaries disagree" in result["issues"]


def test_errors_in_only_vcs_log_still_fail(tmp_path):
    result = _contract_evidence(*logs(tmp_path, SUCCESS + SUMMARY,
                                      SUCCESS + SUMMARY + "Fatal: test failed\n"))
    assert result["status"] == "FAIL"


def test_missing_run_log_rejected(tmp_path):
    console, vcs = logs(tmp_path, SUCCESS + SUMMARY)
    vcs.unlink()
    assert _contract_evidence(console, vcs)["status"] == "FAIL"


def test_existing_output_preserved(tmp_path):
    runner = RegressionRunner(options(tmp_path), [], [])
    runner.output_root.mkdir()
    sentinel = runner.output_root / "summary.json"
    sentinel.write_text("old evidence")
    with pytest.raises(ValueError, match="existing results preserved"):
        runner.prepare()
    assert sentinel.read_text() == "old evidence"


def test_second_owner_rejected(tmp_path):
    runner = RegressionRunner(options(tmp_path), [], [])
    runner.prepare()
    with pytest.raises(ValueError):
        RegressionRunner(options(tmp_path), [], []).prepare()


def test_output_symlink_rejected(tmp_path):
    (tmp_path / "actual").mkdir()
    (tmp_path / "out").symlink_to(tmp_path / "actual", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        RegressionRunner(options(tmp_path), [], []).prepare()


def test_colliding_test_names_rejected(tmp_path):
    cases = [Case(name, "rvv", "test", tmp_path / "elf", "test", 2)
             for name in ("rvv:a/b", "rvv:a_b")]
    with pytest.raises(ValueError, match="distinct"):
        RegressionRunner(options(tmp_path), cases, []).prepare()


def test_compile_command_includes_monitor_without_losing_extra_probes(tmp_path):
    runner = RegressionRunner(options(tmp_path, simv=None, skip_build=False), [], [])
    with patch.dict(os.environ, {"verify_extra_sources": "/tmp/probe.sv /old/ara_acc_contract_monitor.sv"}):
        with patch("ara_verify.runner.resolve_bender", return_value=None):
            command = runner._build_commands()[1]
    arg = next(str(arg) for arg in command if str(arg).startswith("verify_extra_sources="))
    assert "/tmp/probe.sv" in arg
    assert "/old/" not in arg
    assert str(tmp_path / "out/inputs/ara_acc_contract_monitor.sv") in arg


def test_monitor_snapshot_does_not_claim_reused_simv_source(tmp_path):
    source = tmp_path / "verification/uvm/ara_acc_contract_monitor.sv"
    source.parent.mkdir(parents=True)
    source.write_text("// monitor source\n")
    (tmp_path / "simv").write_text("simulator")
    runner = RegressionRunner(options(tmp_path), [], [])
    runner.prepare()
    runner.build()
    meta = json.loads((runner.output_root / "run.json").read_text())
    assert meta["contract_monitor_source"]["compiled_by_this_run"] is False
    assert Path(meta["contract_monitor_source"]["path"]).read_bytes() == source.read_bytes()


@pytest.mark.parametrize("content,expected", [(SUCCESS + SUMMARY, "PASS"), (SUCCESS, "FAIL")])
def test_run_consumes_private_elf_and_enforces_requested_monitor(tmp_path, content, expected):
    binary = tmp_path / "elf"
    binary.write_bytes(b"original program")
    (tmp_path / "simv").write_bytes(b"original simulator")
    case = Case("rvv:probe", "rvv", "probe", binary, "probe", 2)
    runner = RegressionRunner(options(tmp_path), [case], [])
    runner.prepare()

    def fake_run(command, cwd, console, timeout, cancel_event=None):
        preload = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("+PRELOAD=")))
        assert preload != binary
        binary.write_bytes(b"concurrent rebuild")
        assert preload.read_bytes() == b"original program"
        console.write_text(content)
        (cwd / "run.vcs.log").write_text(content)
        return 0, 0.1, False, False

    with patch("ara_verify.runner._run_monitored", side_effect=fake_run):
        result = runner._run_test(case, tmp_path / "simv")
    assert result.status == expected
    assert json.loads((result.artifact_dir / "contract_summary.json").read_text())["status"] == expected
    assert (result.artifact_dir / "inputs.json").is_file()


def test_timeout_still_records_protocol_evidence(tmp_path):
    (tmp_path / "elf").write_bytes(b"elf")
    (tmp_path / "simv").write_bytes(b"simv")
    case = Case("rvv:probe", "rvv", "probe", tmp_path / "elf", "probe", 2)
    runner = RegressionRunner(options(tmp_path), [case], [])
    runner.prepare()

    def fake_run(command, cwd, console, timeout, cancel_event=None):
        console.write_text("incomplete run\n")
        return -15, 2.0, True, False

    with patch("ara_verify.runner._run_monitored", side_effect=fake_run):
        result = runner._run_test(case, tmp_path / "simv")
    assert result.status == "TIMEOUT"
    assert json.loads((result.artifact_dir / "contract_summary.json").read_text())["status"] == "FAIL"


@pytest.mark.parametrize("change", ["delete_simv", "mutate_library", "delete_library", "new_library"])
def test_changed_simulator_is_a_reported_failure_not_a_lost_campaign(tmp_path, change):
    (tmp_path / "elf").write_bytes(b"elf")
    simv = tmp_path / "simv"
    simv.write_bytes(b"simv")
    libraries = tmp_path / "simv.daidir"
    libraries.mkdir()
    library = libraries / "_1_archive_1.so"
    library.write_bytes(b"compiled RTL")
    case = Case("rvv:probe", "rvv", "probe", tmp_path / "elf", "probe", 2)
    runner = RegressionRunner(options(tmp_path), [case], [])

    def fake_run(command, cwd, console, timeout, cancel_event=None):
        console.write_text(SUCCESS + SUMMARY)
        (cwd / "run.vcs.log").write_text(SUCCESS + SUMMARY)
        if change == "delete_simv":
            simv.unlink()
        elif change == "mutate_library":
            library.write_bytes(b"different compiled RTL")
        elif change == "delete_library":
            library.unlink()
        else:
            (libraries / "_2_archive_1.so").write_bytes(b"new RTL")
        return 0, 0.1, False, False

    with patch.object(runner, "build", return_value=simv), \
            patch("ara_verify.runner._run_monitored", side_effect=fake_run):
        results = runner.run()
    assert results[0].status == "FAIL"
    assert "simulator" in results[0].reason
    assert json.loads((runner.output_root / "summary.json").read_text())[0]["status"] == "FAIL"


def test_worker_exception_does_not_discard_other_results(tmp_path):
    cases = [Case(f"rvv:{name}", "rvv", name, tmp_path / name, name, 2)
             for name in ("one", "two")]
    runner = RegressionRunner(options(tmp_path), cases, [])
    with patch.object(runner, "build", return_value=tmp_path / "simv"), \
            patch.object(runner, "_run_test", side_effect=OSError("missing input")):
        results = runner.run()
    assert len(results) == 2
    assert all(result.status == "ERROR" for result in results)
    assert len(json.loads((runner.output_root / "summary.json").read_text())) == 2


def test_failed_build_not_left_running(tmp_path):
    runner = RegressionRunner(options(tmp_path), [], [])
    with patch.object(runner, "build", side_effect=RuntimeError("compile failed")):
        with pytest.raises(RuntimeError, match="compile failed"):
            runner.run()
    assert json.loads((runner.output_root / "run.json").read_text())["status"] == "BUILD_ERROR"


def test_build_only_not_claimed_as_test_pass(tmp_path):
    runner = RegressionRunner(options(tmp_path, build_only=True), [], [])
    with patch.object(runner, "build", return_value=tmp_path / "simv"):
        assert runner.run() == []
    assert json.loads((runner.output_root / "run.json").read_text())["status"] == "BUILT"
    assert not (runner.output_root / "summary.json").exists()


def test_audit_rechecks_monitor_logs_and_hashes(tmp_path):
    artifact = tmp_path / "tests/probe"
    artifact.mkdir(parents=True)
    (artifact / "work").mkdir()
    console = artifact / "console.log"
    vcs = artifact / "work/run.vcs.log"
    for path in (console, vcs):
        path.write_text(SUCCESS + SUMMARY)
    (artifact / "command.json").write_text("{}")
    (artifact / "contract_summary.json").write_text(json.dumps(_contract_evidence(console, vcs)))
    (tmp_path / "run.json").write_text(json.dumps({
        "status": "COMPLETE", "invocation": ["run"], "git": {"commit": "abc"},
        "contract_monitor": True,
    }))
    (tmp_path / "summary.json").write_text(json.dumps([
        {"name": "rvv:probe", "status": "PASS", "artifact_dir": str(artifact)},
    ]))
    assert audit_run(tmp_path)["status"] == "PASS"
    console.write_text(SUCCESS + SUMMARY + "unexpected appended output\n")
    assert audit_run(tmp_path)["status"] == "FAIL"
    console.write_text(SUCCESS + SUMMARY + "Error: protocol violation\n")
    result = audit_run(tmp_path)
    assert result["status"] == "FAIL"
    assert any("simulator diagnostic" in issue for issue in result["errors"])


def test_monitored_process_reaps_its_private_group(tmp_path):
    # This is a host-process lifecycle test, not an RTL test or a simulation.
    child_pid_file = tmp_path / "child.pid"
    code = ("import os, signal, time\n"
            "pid = os.fork()\n"
            "if pid == 0:\n"
            " signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            " while True: time.sleep(1)\n"
            f"open({str(child_pid_file)!r}, 'w').write(str(pid))\n"
            "print('parent exited', flush=True)\n")
    child = None
    try:
        rc, _, timeout, _ = _run_monitored([sys.executable, "-c", code], tmp_path,
                                           tmp_path / "console.log", 3)
        child = int(child_pid_file.read_text())
        assert rc == 0 and not timeout
        # A killed child can briefly remain a zombie until the host init reaps it.
        stat = Path(f"/proc/{child}/stat")
        for _ in range(50):
            if not stat.exists() or stat.read_text().split(") ", 1)[1].startswith("Z "):
                break
            import time
            time.sleep(0.01)
        else:
            pytest.fail("private-session child survived parent completion")
    finally:
        if child:
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass

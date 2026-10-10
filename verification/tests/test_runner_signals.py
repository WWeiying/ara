"""Host-only runner lifecycle tests; no compiler, VCS, or RTL is executed."""

import csv
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import pytest


pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="process-group assertions require Linux /proc"
)

VERIFICATION = Path(__file__).resolve().parents[1]
START_TIMEOUT = 10
STOP_TIMEOUT = 8


DRIVER = r"""
import fcntl
import json
from pathlib import Path
import signal
import sys
from unittest.mock import patch

from ara_verify.model import TestCase
from ara_verify.runner import RegressionRunner, RunOptions

root, mode, output = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
if mode == 'signals':
    names = ['complete', 'active-a', 'active-b', 'queued-a', 'queued-b']
elif mode == 'lock-wait':
    names = ['waiting', 'queued']
elif mode == 'worker-error':
    names = ['complete', 'worker-error', 'remaining']
elif mode.startswith('image-'):
    names = ['complete', mode]
else:
    names = ['complete', 'remaining']
cases = [TestCase(name, 'host', name, root / 'program.elf', name, 120)
         for name in names]
options = RunOptions(
    repo_root=root, output_root=output, config='default',
    jobs=2 if mode == 'signals' else 1, seed=1, dry_run=False,
    build_only=False, skip_build=True, simv=root / 'simv',
    commit_trace=False, timeout_s=120, contract_monitor=False,
)
runner = RegressionRunner(options, cases, ['host-only-runner-test', mode])
runner.build = lambda: root / 'simv'
lock_operations = []
if mode == 'lock-wait':
    original_flock = fcntl.flock
    def observed_flock(fd, operation):
        lock_operations.append(operation)
        if operation & fcntl.LOCK_EX:
            (root / 'lock-attempted').touch()
        try:
            return original_flock(fd, operation)
        except BlockingIOError:
            (root / 'lock-contended').touch()
            raise
    fcntl.flock = observed_flock
if mode == 'worker-error':
    original_run_test = runner._run_test
    def run_test(test, simv):
        if test.name == 'worker-error':
            raise OSError('injected host worker failure')
        return original_run_test(test, simv)
    runner._run_test = run_test
previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
try:
    with patch('ara_verify.runner._git_metadata', return_value={'commit': 'host-test'}):
        results = runner.run()
finally:
    restored = {sig.name: signal.getsignal(sig) == handler
                for sig, handler in previous.items()}
    (root / 'handlers-restored.json').write_text(json.dumps(restored))
    if mode == 'lock-wait':
        (root / 'lock-operations.json').write_text(json.dumps(lock_operations))
sys.exit(0 if all(result.status == 'PASS' for result in results) else 1)
"""


SIMULATOR = r"""
import json
import os
from pathlib import Path
import signal
import sys
import time

root = Path(__file__).resolve().parent
case = next(arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('+TESTCASE='))
started = root / 'started'
temporary = started / (case + '.pid.tmp')
temporary.write_text(str(os.getpid()))
temporary.replace(started / (case + '.pid'))
if case.startswith('active-') or case.startswith('queued-'):
    # Both generations resist TERM so cleanup must reach the group's KILL path.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    read_fd, write_fd = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read_fd)
        os.write(write_fd, b'ready')
        os.close(write_fd)
        while True:
            time.sleep(1)
    os.close(write_fd)
    assert os.read(read_fd, 5) == b'ready'
    os.close(read_fd)
    record = {'pid': os.getpid(), 'child': child, 'pgid': os.getpgrp(),
              'child_pgid': os.getpgid(child)}
    temporary = started / (case + '.ready.tmp')
    temporary.write_text(json.dumps(record))
    temporary.replace(started / (case + '.ready.json'))
    print('host process tree ready', flush=True)
    while True:
        time.sleep(1)
library = root / 'simv.daidir/nested/_host_archive.so'
if case == 'image-change-library':
    library.write_bytes(b'changed compiled host image')
elif case == 'image-delete-library':
    library.unlink()
elif case == 'image-delete-executable':
    Path(__file__).unlink()
success = 'Core Test *** SUCCESS ***\n'
Path('run.vcs.log').write_text(success)
print(success, end='', flush=True)
"""


def _process_info(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
    except (FileNotFoundError, ProcessLookupError):
        return None
    return fields[0], int(fields[1]), int(fields[2])


def _terminal(pid):
    info = _process_info(pid)
    # Orphaned grandchildren may remain zombies until the host init reaps them.
    return info is None or info[0] in {"Z", "X"}


def _cleanup(process, root):
    """Contain failures even when the runner has not implemented cancellation."""
    if process.poll() is None:
        try:
            os.kill(process.pid, signal.SIGSTOP)
        except ProcessLookupError:
            pass
    groups = {process.pid}
    groups.update(int(path.read_text()) for path in (root / "started").glob("*.pid"))
    # Cover a launch interrupted before the shim could publish its PID marker.
    processes = {}
    for path in Path("/proc").glob("[0-9]*/stat"):
        pid = int(path.parent.name)
        info = _process_info(pid)
        if info is not None:
            processes[pid] = info
    descendants = {process.pid}
    while True:
        children = {pid for pid, (_, ppid, _) in processes.items() if ppid in descendants}
        if children <= descendants:
            break
        descendants.update(children)
    groups.update(processes[pid][2] for pid in descendants if pid in processes)
    for group in groups:
        assert group != os.getpgrp(), "test cleanup must never signal pytest's group"
        try:
            os.killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=3)


@pytest.fixture
def campaign(tmp_path):
    (tmp_path / "started").mkdir()
    (tmp_path / "program.elf").write_bytes(b"host-only placeholder, never parsed as ELF")
    simv = tmp_path / "simv"
    simv.write_text(f"#!{sys.executable}\n" + SIMULATOR)
    simv.chmod(0o755)
    libraries = tmp_path / "simv.daidir"
    (libraries / "nested").mkdir(parents=True)
    (libraries / "_root_archive.so").write_bytes(b"root compiled host image")
    (libraries / "nested/_host_archive.so").write_bytes(b"nested compiled host image")
    processes = []

    def launch(mode="success", output=None):
        log = tmp_path / f"driver-{len(processes)}.log"
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        env["PYTHONPATH"] = str(VERIFICATION) + os.pathsep + env.get("PYTHONPATH", "")
        with log.open("wb") as stream:
            process = subprocess.Popen(
                [sys.executable, "-B", "-c", DRIVER, str(tmp_path), mode,
                 str(output or tmp_path / "out")],
                cwd=tmp_path, env=env, stdout=stream, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        processes.append(process)
        return process, log

    yield launch
    for process in reversed(processes):
        _cleanup(process, tmp_path)


def _wait_for_active(process, log, root):
    paths = [root / "started" / f"active-{suffix}.ready.json" for suffix in ("a", "b")]
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if all(path.is_file() for path in paths):
            return [json.loads(path.read_text()) for path in paths]
        if process.poll() is not None:
            pytest.fail(f"runner exited before active workers were ready:\n{log.read_text()}")
        time.sleep(0.02)
    pytest.fail(f"host workers did not become ready:\n{log.read_text()}")


def _wait_for_exit(process, log):
    try:
        return process.wait(timeout=STOP_TIMEOUT)
    except subprocess.TimeoutExpired:
        pytest.fail(f"runner did not terminate within {STOP_TIMEOUT}s:\n{log.read_text()}")


def _wait_for_lock_attempt(process, log, root, contended=False):
    marker = root / ("lock-contended" if contended else "lock-attempted")
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if marker.is_file():
            return
        if process.poll() is not None:
            pytest.fail(f"runner exited before attempting the snapshot lock:\n{log.read_text()}")
        time.sleep(0.02)
    pytest.fail(f"worker did not attempt the snapshot lock:\n{log.read_text()}")


def _assert_reports(output, expected):
    rows = json.loads((output / "summary.json").read_text())
    assert len(rows) == len(expected)
    assert {row["name"]: row["status"] for row in rows} == expected
    with (output / "summary.csv").open(newline="") as stream:
        assert {row["name"]: row["status"] for row in csv.DictReader(stream)} == expected
    suite = ET.parse(output / "junit.xml").getroot()
    assert int(suite.get("tests")) == len(expected)
    failures = {case.get("name") for case in suite.findall("testcase")
                if case.find("failure") is not None}
    assert failures == {name for name, status in expected.items() if status != "PASS"}
    metadata = json.loads((output / "run.json").read_text())
    assert metadata["status"] == (
        "INTERRUPTED" if "CANCELLED" in expected.values() else "COMPLETE"
    )
    assert metadata["status_counts"] == {
        status: list(expected.values()).count(status) for status in set(expected.values())
    }
    assert metadata.get("completed_at")
    for row in rows:
        if row["status"] != "PASS":
            assert row["reason"], row
    return rows


def _tree_contents(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def test_host_simulator_and_image_provenance(campaign, tmp_path):
    process, log = campaign()
    assert _wait_for_exit(process, log) == 0, log.read_text()
    rows = _assert_reports(tmp_path / "out", {"complete": "PASS", "remaining": "PASS"})
    images = [tmp_path / "simv", *sorted((tmp_path / "simv.daidir").rglob("*.so"))]
    for row in rows:
        provenance = json.loads((Path(row["artifact_dir"]) / "inputs.json").read_text())
        recorded = json.dumps(provenance)
        for image in images:
            assert hashlib.sha256(image.read_bytes()).hexdigest() in recorded, image


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM], ids=["SIGINT", "SIGTERM"])
def test_signal_cancels_active_and_queued_cases(campaign, tmp_path, signum):
    process, log = campaign("signals")
    active = _wait_for_active(process, log, tmp_path)
    assert len(list((tmp_path / "started").glob("*.pid"))) == 3
    for record in active:
        assert record["pid"] == record["pgid"] == record["child_pgid"]
        assert record["pgid"] != process.pid
        assert not _terminal(record["pid"])
        assert not _terminal(record["child"])

    start = time.monotonic()
    os.killpg(process.pid, signum)
    assert _wait_for_exit(process, log) == 1, log.read_text()
    pids = [record[key] for record in active for key in ("pid", "child")]
    while time.monotonic() - start < STOP_TIMEOUT and not all(map(_terminal, pids)):
        time.sleep(0.02)
    assert all(map(_terminal, pids)), f"live simulator descendants after {signum.name}: {pids}"
    assert time.monotonic() - start < STOP_TIMEOUT
    expected = {"complete": "PASS", "active-a": "CANCELLED", "active-b": "CANCELLED",
                "queued-a": "CANCELLED", "queued-b": "CANCELLED"}
    _assert_reports(tmp_path / "out", expected)
    assert not list((tmp_path / "started").glob("queued-*.pid"))
    assert json.loads((tmp_path / "handlers-restored.json").read_text()) == {
        "SIGINT": True, "SIGTERM": True,
    }

    previous = _tree_contents(tmp_path / "out")
    launches = _tree_contents(tmp_path / "started")
    retry, retry_log = campaign("signals")
    assert _wait_for_exit(retry, retry_log) == 1, retry_log.read_text()
    assert _tree_contents(tmp_path / "out") == previous
    assert _tree_contents(tmp_path / "started") == launches


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM], ids=["SIGINT", "SIGTERM"])
def test_signal_cancels_snapshot_lock_wait(campaign, tmp_path, signum):
    import fcntl
    from ara_verify.runner import _apps_build_lock

    # The independent owner keeps the real lock until cancellation is reported.
    with _apps_build_lock(tmp_path):
        process, log = campaign("lock-wait")
        _wait_for_lock_attempt(process, log, tmp_path)
        assert not list((tmp_path / "started").iterdir())
        os.killpg(process.pid, signum)
        assert _wait_for_exit(process, log) == 1, log.read_text()
        _assert_reports(tmp_path / "out", {"waiting": "CANCELLED", "queued": "CANCELLED"})
        assert not list((tmp_path / "started").iterdir())
        assert not list((tmp_path / "out").rglob("input.elf"))
        operations = json.loads((tmp_path / "lock-operations.json").read_text())
        assert operations and all(op == fcntl.LOCK_EX | fcntl.LOCK_NB for op in operations)
        assert json.loads((tmp_path / "handlers-restored.json").read_text()) == {
            "SIGINT": True, "SIGTERM": True,
        }


def test_snapshot_lock_retries_after_owner_releases(campaign, tmp_path):
    from ara_verify.runner import _apps_build_lock

    with _apps_build_lock(tmp_path):
        process, log = campaign("lock-wait")
        _wait_for_lock_attempt(process, log, tmp_path, contended=True)
        assert not list((tmp_path / "started").iterdir())
    assert _wait_for_exit(process, log) == 0, log.read_text()
    _assert_reports(tmp_path / "out", {"waiting": "PASS", "queued": "PASS"})


def test_snapshot_lock_cancel_wait_does_not_spin_or_unlock(tmp_path):
    import errno
    import fcntl
    import threading
    from unittest.mock import patch
    from ara_verify.runner import _apps_build_lock

    event = threading.Event()
    with patch("ara_verify.runner.fcntl.flock", side_effect=BlockingIOError(errno.EAGAIN, "held")) as flock:
        with patch.object(event, "wait", side_effect=lambda timeout: event.set()) as wait:
            with _apps_build_lock(tmp_path, event) as acquired:
                assert acquired is False
        wait.assert_called_once_with(0.1)
    assert len(flock.call_args_list) == 1
    assert flock.call_args.args[1] == fcntl.LOCK_EX | fcntl.LOCK_NB


def test_snapshot_lock_already_cancelled_does_not_touch_lock(tmp_path):
    import threading
    from unittest.mock import patch
    from ara_verify.runner import _apps_build_lock

    event = threading.Event()
    event.set()
    with patch("ara_verify.runner.fcntl.flock") as flock:
        with _apps_build_lock(tmp_path, event) as acquired:
            assert acquired is False
    flock.assert_not_called()


@pytest.mark.parametrize("cancellable", [False, True], ids=["build", "snapshot"])
def test_apps_lock_releases_after_body_error(tmp_path, cancellable):
    import fcntl
    import threading
    from unittest.mock import patch
    from ara_verify.runner import _apps_build_lock

    event = threading.Event() if cancellable else None
    with patch("ara_verify.runner.fcntl.flock", wraps=fcntl.flock) as flock:
        with pytest.raises(RuntimeError, match="body failure"):
            with _apps_build_lock(tmp_path, event) as acquired:
                assert acquired is True
                raise RuntimeError("body failure")
    assert [call.args[1] for call in flock.call_args_list] == [
        fcntl.LOCK_EX | (fcntl.LOCK_NB if cancellable else 0), fcntl.LOCK_UN,
    ]


def test_existing_output_is_not_overwritten(campaign, tmp_path):
    output = tmp_path / "old-output"
    output.mkdir()
    (output / "summary.json").write_text('[{"name":"old","status":"PASS"}]\n')
    (output / "run.json").write_text('{"status":"COMPLETE"}\n')
    (output / "console.log").write_text("old verification evidence\n")
    previous = _tree_contents(output)
    process, log = campaign(output=output)
    assert _wait_for_exit(process, log) == 1, log.read_text()
    assert _tree_contents(output) == previous
    assert not list((tmp_path / "started").iterdir())


def test_worker_exception_preserves_other_results(campaign, tmp_path):
    process, log = campaign("worker-error")
    assert _wait_for_exit(process, log) == 1, log.read_text()
    rows = _assert_reports(tmp_path / "out", {
        "complete": "PASS", "worker-error": "ERROR", "remaining": "PASS",
    })
    error = next(row for row in rows if row["name"] == "worker-error")
    assert "injected host worker failure" in error["reason"]
    assert not (tmp_path / "started/worker-error.pid").exists()


@pytest.mark.parametrize("mode", [
    "image-change-library", "image-delete-library", "image-delete-executable",
])
def test_image_mutation_is_a_case_failure_not_a_lost_campaign(campaign, tmp_path, mode):
    process, log = campaign(mode)
    assert _wait_for_exit(process, log) == 1, log.read_text()
    _assert_reports(tmp_path / "out", {"complete": "PASS", mode: "FAIL"})

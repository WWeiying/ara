#!/usr/bin/env python3
"""Bounded integration check, no subprocess/DVE; writes evidence only beside it."""
import contextlib
import io
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard
import support as s


def main():
    wrapper = guard.module("csr_readonly_cli", guard.COVERAGE / "run_reviewed_csr_dve_20261004.py")
    old = {str(p): s.sha(p) for p in guard.COVERAGE.rglob("*") if p.is_file()
           and not p.is_relative_to(HERE) and p.name != "run_reviewed_csr_dve_20261004.py"}
    implementation = {str(p): s.sha(p) for p in [guard.COVERAGE / "run_reviewed_csr_dve_20261004.py",
        *HERE.glob("*.py"), *HERE.glob("*.tcl"), HERE / "README.md"]}
    started, capture = time.monotonic(), io.StringIO()
    error, code = None, None
    try:
        with patch("subprocess.Popen", side_effect=AssertionError("All subprocess launches forbidden")), \
                patch.object(wrapper.workflow, "session", side_effect=AssertionError("DVE forbidden")), \
                contextlib.redirect_stdout(capture):
            code = wrapper.main(["check", "--baseline", str(guard.OUT / "gap48-current-20261004-01")])
        s.require(code == 0, "Read-only CLI failed")
        s.verify_hashes(old)
        s.verify_hashes(implementation)
    except Exception as failure:
        error = str(failure)
    transcript = capture.getvalue()
    result = dict(status="PASS_READONLY_ADMISSION_NOT_APPLICATION_APPROVAL" if error is None else "FAIL",
        elapsed_seconds=round(time.monotonic() - started, 3), error=error, cli_returncode=code,
        real_dve_launches=0, all_subprocess_launches_forbidden=True,
        implementation_sha256=implementation, old_coverage_file_hashes_unchanged=old,
        cli_stdout=transcript)
    (HERE / "latest-check.json").write_text(json.dumps(result, indent=2) + "\n")
    print(transcript, end="")
    print(result["status"], "elapsed_seconds=" + str(result["elapsed_seconds"]))
    if error:
        print(error, file=sys.stderr)
    return 0 if error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())

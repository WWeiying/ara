#!/usr/bin/env python3
"""One bounded latest-tip offline admission; deny all subprocess launches."""
import json
import signal
import subprocess
import sys
import time
from unittest.mock import patch

sys.dont_write_bytecode = True
import operand_guard as g


def main():
    started = time.monotonic()
    paths = [*g.COVERAGE.glob("reviewed_csr_20261004/*.py"), *g.COVERAGE.glob("reviewed_csr_20261004/*.tcl"),
             *g.COVERAGE.glob("reviewed_20261004/*.py"), *g.COVERAGE.glob("reviewed_20261004/*.json"),
             g.COVERAGE / "run_reviewed_csr_dve_20261004.py", g.COVERAGE / "run_reviewed_dve_20261004.py"]
    before = {str(p): g.sha(p) for p in paths}
    def alarm(signum, frame):
        raise TimeoutError("Offline admission exceeded600 seconds")
    old = signal.signal(signal.SIGALRM, alarm)
    signal.alarm(600)
    error, context = None, None
    try:
        with patch.object(subprocess, "Popen", side_effect=AssertionError("NO SUBPROCESS IN READONLY ADMISSION")):
            context = g.build_context()
            g.verify_hashes(before)
    except Exception as exc:
        error = repr(exc)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
    result = dict(status="PASS_READONLY_NOT_APPLICATION_APPROVAL" if error is None else "REJECTED",
                  error=error, elapsed_seconds=round(time.monotonic() - started, 3), DVE_launches=0,
                  old_helper_hashes=before, old_helpers_unchanged=all(g.sha(p) == h for p, h in before.items()))
    if context:
        result.update(baseline=context["baseline"], tests=context["tests"], baseline_collection_sha256=context["baseline_collection_sha256"],
            operand_points=1144, exact_union_points=1345, observers=10, retained_review_coordinates=1269,
            retained_current_missing=context["retained_current_missing_count"], new_target_hits=context["operand_raw_audit"]["selected_hits"],
            all36_raw_union_equals_latest_cache=True, native_full1144_qualified=False,
            raw_top=g.csr.csv_rows(context["raw_reference"])[0], pins_checked=len(context["pins"]))
        (g.HERE / "admission-context.json").write_text(json.dumps(context, sort_keys=True, indent=2) + "\n")
        result["admission_context_sha256"] = g.sha(g.HERE / "admission-context.json")
    (g.HERE / "admission-results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "old_helper_hashes"}, indent=2))
    return int(error is not None)


if __name__ == "__main__":
    raise SystemExit(main())

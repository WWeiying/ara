"""Two independent approvals: native discovery, then one composed full report."""
import os
import shutil
import signal
import subprocess
import time
import operand_guard as guard
from operand_support import *

PREPARE_MAX_SECONDS = 300
PRELAUNCH_MAX_SECONDS = 40
CAPTURE_DVE_MAX_SECONDS = 880
REPORT_DVE_MAX_SECONDS = 880
POSTCHECK_RESERVE_SECONDS = 15
CLEANUP_RESERVE_SECONDS = 3
RUN_MAX_SECONDS = 900


def run_bounds(stage):
    require(stage in ("capture", "report"), "Unknown budget stage")
    dve = CAPTURE_DVE_MAX_SECONDS if stage == "capture" else REPORT_DVE_MAX_SECONDS
    return dve, RUN_MAX_SECONDS


def locations(output):
    output = Path(output).resolve()
    require(output.parent == guard.OUT, "Fresh output must be direct child of verification/out")
    return output, Path(str(output) + ".tools")


def literal(value):
    require(not any(c in value for c in "{}\\\r\n\t"), "Unsafe Tcl literal")
    return "{" + value + "}"


def selection(context):
    text = "set oq_stage " + literal(context["stage"]) + "\nset oq_scopes {\n"
    text += "".join(literal(s) + "\n" for s in context["session_keys"]) + "}\n"
    for name, values in (("oq_keys", context["session_keys"]), ("oq_targets", context["session_targets"])):
        text += "array set " + name + " {\n"
        text += "".join(literal(s) + " {" + " ".join(keys) + "}\n" for s, keys in values.items()) + "}\n"
    text += "set oq_observers {\n" + "".join(literal(p["scope"]) + "\n" for p in context["observers"]) + "}\n"
    return text


def load_capture(path, digest, context):
    require(path is not None and digest and sha(path) == digest, "Full1144 native capture SHA required; pilot18 is insufficient")
    record = jread(path)
    require(record["status"] == "NATIVE_1144_CAPTURE_VERIFIED_NOT_APPLICATION_APPROVAL" and record["operand_points"] == 1144,
            "Not a full1144 capture certificate")
    require(record["baseline_collection_sha256"] == context["baseline_collection_sha256"], "Capture corpus differs")
    root = Path(path).resolve().parent
    require(root.parent == guard.OUT, "Capture must be in integration out")
    required = {"first.el", "second.el", "initial-empty.el", "reset-empty.el", "final-empty.el",
                "execution.json", "independent-review.json", "integrity-before.json", "integrity-after.json",
                "selected_tests.txt", "DVEfiles/dve_gui.log", "state-audit.json"}
    required.update("states_" + phase + ".tsv" for phase in ("before", "selected", "reset", "reloaded", "final"))
    require({str(root / name) for name in required} <= set(record["files"]), "Capture certificate omits required artifact pins")
    require(record["native_file"] == str(root / "first.el"), "Capture native path differs")
    for name, h in record["files"].items():
        p = Path(name)
        require(p.is_relative_to(root) and p.resolve().is_relative_to(root) and not p.is_symlink(), "Foreign capture member")
        require(sha(p) == h, "Capture artifact changed")
    bundle = Path(str(root) + ".tools")
    captured = verify_snapshot(bundle, record["snapshot_sha256"])
    require(captured["stage"] == "capture" and captured["operand_targets"] == context["operand_targets"], "Capture coordinate authority differs")
    require(captured["baseline_collection_sha256"] == record["baseline_collection_sha256"] and
            captured["output"] == str(root), "Capture snapshot corpus/output differs")
    require((captured["dve_max_seconds"], captured["total_bound_seconds"]) == run_bounds("capture"),
            "Capture snapshot budget differs from reviewed implementation")
    execution = jread(root / "execution.json")
    timeout = execution.get("timeout_seconds")
    elapsed = execution.get("elapsed_seconds")
    require(execution["dve_launch_count"] == 1 and execution["returncode"] == 0 and not execution["timed_out"] and
            type(timeout) in (int, float) and 0 < timeout <= captured["dve_max_seconds"] and
            type(elapsed) in (int, float) and 0 <= elapsed <= min(captured["total_bound_seconds"], timeout + 3),
            "Capture execution not qualified")
    receipt = jread(root / "independent-review.json")
    approval(receipt, record["snapshot_sha256"], captured)
    require(sha(root / "independent-review.json") == record["independent_review_copy_sha256"], "Capture review changed")
    require(len(captured["inputs"]) == 2 and captured["session_tests"] == 1 and
            captured["inputs"][0] == captured["design"], "Capture must bind exactly one PASS input")
    vdb = Path(captured["inputs"][1])
    testdirs = list((vdb / "snps/coverage/db/testdata").iterdir())
    require(len(testdirs) == 1 and testdirs[0].is_dir() and not testdirs[0].is_symlink(),
            "Capture PASS test directory differs")
    expected_tests = {str(vdb.with_suffix("") / testdirs[0].name)}
    actual_tests = (root / "selected_tests.txt").read_text().splitlines()
    require(len(actual_tests) == 1 and set(actual_tests) == expected_tests, "Capture selected PASS population differs")
    states = state_proof(root, captured, record["snapshot_sha256"])
    saved = jread(root / "state-audit.json")
    require(set(saved) == {"points", "count"} and type(saved["count"]) is int and
            saved["count"] == len(states) and isinstance(saved["points"], list) and
            len(saved["points"]) == len(states), "Capture saved state audit count differs")
    # Compare complete proof records by coordinate, independent of list/dict order.
    expected_states = {(p["scope"], p["coordinate"]): p for p in states}
    found = set()
    for point in saved["points"]:
        require(isinstance(point, dict), "Capture saved state audit record malformed")
        key = (point.get("scope"), point.get("coordinate"))
        require(all(isinstance(k, str) for k in key) and key in expected_states and key not in found,
                "Capture saved state audit identity differs")
        require(json.dumps(point, sort_keys=True) == json.dumps(expected_states[key], sort_keys=True),
                "Capture saved state audit proof differs")
        found.add(key)
    before = jread(root / "integrity-before.json")
    require(before.get("checked") is True and before.get("pins") == captured["pins"] and
            before.get("input_tree") == captured["input_tree"], "Capture before-integrity proof incomplete")
    for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
        require((root / name).read_bytes() == b"", "Capture reset evidence not empty")
    integrity = jread(root / "integrity-after.json")
    require(integrity.get("unchanged") is True and integrity["pins"] == captured["pins"] and
            integrity["input_tree"] == captured["input_tree"], "Capture integrity proof incomplete")
    data = (root / "first.el").read_bytes()
    pair(data, (root / "second.el").read_bytes(), captured)
    require(sha(root / "first.el") == record["native_sha256"], "Capture native signature seal differs")
    # Parent's later report receipt binds the complete captured root, not a new self-issued approval.
    context["pins"].update(record["files"])
    context["pins"][str(Path(path).resolve())] = digest
    context["pins"][str(bundle / "snapshot.json")] = record["snapshot_sha256"]
    for rel, h in jread(bundle / "snapshot.json").items():
        context["pins"][str(bundle / rel)] = h
    return data


def snapshot(output, context, stage, capture=None, capture_sha=None):
    output, bundle = locations(output)
    require(stage in ("capture", "report") and not output.exists() and not bundle.exists(), "Fresh stage/output required")
    dve_seconds, run_seconds = run_bounds(stage)
    context = dict(context, stage=stage, output=str(output), session_tests=context["tests"],
                   dve_max_seconds=dve_seconds, total_bound_seconds=run_seconds,
                   phase_budget_seconds=dict(prepare=PREPARE_MAX_SECONDS, prelaunch_ceiling=PRELAUNCH_MAX_SECONDS,
                       dve_ceiling=dve_seconds, postcheck_reserve=POSTCHECK_RESERVE_SECONDS,
                       cleanup_reserve=CLEANUP_RESERVE_SECONDS, run_total=run_seconds))
    native = None
    if stage == "capture":
        rows = jread(Path(context["baseline"]) / "all-passed-outcomes.json")
        row = [r for r in rows if r["name"] == "qbs_gap45_context"]
        require(len(row) == 1, "Capture independent PASS missing")
        ev = guard.csr_guard.legacy.coverage_evidence.Evidence()
        ev.baseline_row(row[0], context["image"], jread(Path(context["baseline"]) / "plan.json")["simv"])
        context["pins"].update(ev.files)
        context["inputs"] = [context["design"], row[0]["vdb"]]
        context["session_tests"] = 1
    else:
        native = load_capture(capture, capture_sha, context)
        context["native_capture_sha256"] = capture_sha
        context["policy"] = compose_policy(context, native)
        context["operand_native_blocks"] = {}
        for (scope, point), record in validate_operand(native, context).items():
            context["operand_native_blocks"].setdefault(scope, {})[point] = record["raw"]
    context["session_keys"], context["session_targets"] = guard.session_population(context, stage)
    context["session_keys"] = dict(sorted(context["session_keys"].items()))
    context["session_targets"] = {s: context["session_targets"][s] for s in context["session_keys"]}
    require(all(not output.is_relative_to(Path(p)) and not Path(p).is_relative_to(output) for p in context["input_membership"]), "Output overlaps inputs")
    bundle.mkdir()
    copies = {"csr_support.py": guard.COVERAGE / "reviewed_csr_20261004/support.py",
              "audit_readonly.py": guard.COVERAGE / "reviewed_20261004/audit_readonly.py",
              "export_dve_coverage.tcl": guard.COVERAGE / "dve_hierarchy/export_dve_coverage.tcl"}
    copies.update({name: HERE / name for name in ("operand_support.py", "operand_runtime.py", "dve_operand.tcl", "capture_entry.tcl")})
    for name, source in copies.items():
        require(context["pins"].get(str(source)) == sha(source), "Unpinned executable snapshot member")
        shutil.copyfile(source, bundle / name)
    if native is not None:
        old = dict(context["policy"], allowed_points=context["policy"]["allowed_points"][:94])
        union = guard.csr_guard.legacy.native_points(old).encode() + Path(context["csr_native_path"]).read_bytes() + native
        validate_composed(union, context, guard.csr_guard.legacy.audit, False)
        (bundle / "union.el").write_bytes(union)
    (bundle / "context.json").write_text(json.dumps(context, sort_keys=True, indent=2) + "\n")
    (bundle / "selection.tcl").write_text(selection(context))
    (bundle / "snapshot.json").write_text(json.dumps({str(p.relative_to(bundle)): sha(p) for p in sorted(bundle.rglob("*")) if p.is_file()}, indent=2) + "\n")
    verify_snapshot(bundle, sha(bundle / "snapshot.json"))
    return bundle


def load_approval(output, path, digest):
    output, bundle = locations(output)
    require(not output.exists() and bundle.is_dir(), "Unclaimed prepared snapshot required")
    require(Path(path).resolve().is_relative_to(guard.ROOT), "Review outside integration")
    raw = Path(path).read_bytes()
    require(csr.hashlib.sha256(raw).hexdigest() == digest, "Explicit approval hash differs")
    receipt = csr.json_bytes(raw)
    context = verify_snapshot(bundle, receipt.get("snapshot_sha256"))
    approval(receipt, receipt["snapshot_sha256"], context)
    require((context["dve_max_seconds"], context["total_bound_seconds"]) == run_bounds(context["stage"]),
            "Prepared run budget differs from reviewed implementation")
    require(context["output"] == str(output), "Snapshot output differs")
    return output, bundle, context, receipt, raw


def session(command, output, env, timeout):
    context = verify_snapshot(env["OPERAND_BUNDLE"], env["OPERAND_SNAPSHOT_SHA256"])
    require(0 < timeout <= context["dve_max_seconds"], "DVE bound differs")
    started, process, code, timed_out = time.monotonic(), None, None, False
    try:
        with (output / "launcher.log").open("x") as log:
            process = subprocess.Popen(command, cwd=output, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
    finally:
        if process:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=3)
        (output / "execution.json").write_text(json.dumps(dict(command=command, dve_launch_count=int(process is not None),
            process_group=process.pid if process else None, elapsed_seconds=round(time.monotonic() - started, 3),
            timeout_seconds=timeout, returncode=code, timed_out=timed_out), indent=2) + "\n")
    require(code == 0 and not timed_out, "DVE failure/timeout; no retries")


def run(output, approval_path, approval_sha):
    started = time.monotonic()
    budget_expired = False
    def expired(signum, frame):
        nonlocal budget_expired
        budget_expired = True
        raise TimeoutError("Reviewed session total work budget exhausted; no extension")
    old_handler = signal.signal(signal.SIGALRM, expired)
    signal.alarm(RUN_MAX_SECONDS - CLEANUP_RESERVE_SECONDS)
    try:
        output, bundle, context, receipt, receipt_bytes = load_approval(output, approval_path, approval_sha)
    except BaseException:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
        raise
    root = receipt["snapshot_sha256"]
    try:
        remaining_total = int(context["total_bound_seconds"] - CLEANUP_RESERVE_SECONDS - (time.monotonic() - started))
        require(remaining_total > 0, "No run budget remains after approval validation")
        verify_inputs(context)
        guard.csr_guard.latest_corpus(Path(context["design"]), context["image"], Path(context["baseline"]))
        require(sha(approval_path) == approval_sha, "Review changed")
        output.mkdir()
        (output / "integrity-before.json").write_text(json.dumps(dict(pins=context["pins"],
            input_tree=context["input_tree"], checked=True), sort_keys=True, indent=2) + "\n")
        (output / "inputs.txt").write_text("\n".join(context["inputs"]) + "\n")
        (output / "independent-review.json").write_bytes(receipt_bytes)
        (output / "home").mkdir()
        (output / "tmp").mkdir()
        entry = "capture_entry.tcl" if context["stage"] == "capture" else "export_dve_coverage.tcl"
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", DVE_COVERAGE_OUTPUT=str(output),
                   DVE_REVIEWED_WAIVERS=str(bundle / "dve_operand.tcl"), OPERAND_BUNDLE=str(bundle),
                   OPERAND_SNAPSHOT_SHA256=root, HOME=str(output / "home"), TMPDIR=str(output / "tmp"))
        command = ["/usr/bin/xvfb-run", "-a", "-e", str(output / "xvfb.log"), "-s", "-screen 0 1280x1024x24",
                   str(guard.DVE), "-full64", "-cov", "-script", str(bundle / entry)]
        verify_snapshot(bundle, root)
        require(time.monotonic() - started <= PRELAUNCH_MAX_SECONDS,
                "Prelaunch budget exceeded; no shortened DVE attempt")
        remaining = min(context["dve_max_seconds"], int(context["total_bound_seconds"] -
            POSTCHECK_RESERVE_SECONDS - CLEANUP_RESERVE_SECONDS - (time.monotonic() - started)))
        require(remaining > 0, "No DVE budget remains; no launch")
        session(command, output, env, remaining)
        verify_snapshot(bundle, root)
        verify_inputs(context)
        runtime = module("operand_verified_runtime", bundle / "operand_runtime.py")
        # runtime's support constants refer only to copied immutable snapshot files.
        runtime.HERE = bundle
        status = runtime.finish(output, context, root)
        guard.csr_guard.latest_corpus(Path(context["design"]), context["image"], Path(context["baseline"]))
        require(sha(approval_path) == approval_sha, "Review changed during session")
        verify_snapshot(bundle, root)
        verify_inputs(context)
        after = {p: sha(p) for p in context["pins"]}
        trees = {p: tree(p) for p in context["input_tree"]}
        require(after == context["pins"] and trees == context["input_tree"], "Final preservation check failed")
        (output / "integrity-after.json").write_text(json.dumps(dict(pins=after, input_tree=trees,
            unchanged=True), sort_keys=True, indent=2) + "\n")
        status.update(snapshot_sha256=root, baseline_collection_sha256=context["baseline_collection_sha256"],
                      independent_review_copy_sha256=sha(output / "independent-review.json"), independent_review_sha256=approval_sha)
        if context["stage"] == "report":
            shutil.copyfile(output / "summary_waived.csv.partial", output / "summary_waived.csv")
        status["files"] = {str(p): sha(p) for p in sorted(output.rglob("*")) if p.is_file()}
        name = "capture-certificate.json" if context["stage"] == "capture" else "supplemental-status.json"
        verify_snapshot(bundle, root)
        require(time.monotonic() - started < context["total_bound_seconds"] - 3, "No publication budget remains")
        (output / name).write_text(json.dumps(status, indent=2) + "\n")
        return status
    except BaseException as error:
        if output.exists():
            (output / "rejection.json").write_text(json.dumps(dict(status="REJECTED_NO_SUCCESS_CLAIM", error=str(error), retry=False), indent=2) + "\n")
        raise
    finally:
        try:
            if output.exists() and not (output / "integrity-after.json").exists():
                # Failed preservation checks must not mask the original failure.
                preservation = dict(status="INCOMPLETE_REQUIRES_OFFLINE_RECHECK", unchanged=None)
                if not budget_expired:
                    try:
                        actual = {p: sha(p) if Path(p).is_file() else None for p in context["pins"]}
                        trees = {p: tree(p) for p in context["input_tree"]}
                        preservation = dict(pins=actual, input_tree=trees,
                            unchanged=actual == context["pins"] and trees == context["input_tree"])
                    except (TimeoutError, OSError, ValueError) as error:
                        preservation["error"] = str(error)
                try:
                    (output / "integrity-after.json").write_text(json.dumps(preservation, sort_keys=True, indent=2) + "\n")
                except OSError:
                    pass
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

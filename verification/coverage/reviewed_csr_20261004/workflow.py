"""Review-gated snapshot and single process-group-bounded DVE execution."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import guard
from support import *

HERE, COVERAGE, OUT = guard.HERE, guard.COVERAGE, guard.OUT


def literal(value):
    require(not any(c in value for c in "{}\\\r\n"), "Unsafe Tcl literal")
    return "{" + value + "}"


def selection_tcl(context):
    lines = ["set csr_scope " + literal(context["csr_scope"]), "set csr_design " + literal(context["design"]),
             "set csr_targets {"]
    lines += ["    {" + f"{p['spec']} {p['vector']} {p['meta']} {p['path']}" + "}" for p in context["csr_selection"]]
    lines += ["}", "set csr_all_keys {"] + ["    " + literal(k) for k in context["csr_all_keys"]] + ["}"]
    return "\n".join(lines) + "\n"


def locations(output):
    output = Path(output).resolve()
    require(output.parent == OUT, "Report must be a fresh direct child of verification/out")
    return output, Path(str(output) + ".tools")


def snapshot(output, context):
    output, bundle = locations(output)
    require(not output.exists() and not bundle.exists(), "Fresh output/snapshot required")
    require(all(not output.is_relative_to(Path(vdb)) and not Path(vdb).is_relative_to(output)
                for vdb in context["input_membership"]), "Output overlaps an input VDB")
    require(not output.is_relative_to(Path(context["baseline"])), "Output cannot modify the frozen corpus")
    bundle.mkdir(parents=True)
    (bundle / "dve_hierarchy").mkdir()
    (bundle / "waivers").mkdir()
    copies = {
        "waiver_base.py": COVERAGE / "prepare_dve_waivers.py",
        "legacy_adapter.py": COVERAGE / "reviewed_20261004/prepare_native.py",
        "audit_readonly.py": COVERAGE / "reviewed_20261004/audit_readonly.py",
        "prepare_dve_waivers.py": HERE / "prepare_native.py",
        "support.py": HERE / "support.py", "dve_waivers.tcl": HERE / "dve_csr.tcl",
        "dve_hierarchy/export_dve_coverage.tcl": COVERAGE / "dve_hierarchy/export_dve_coverage.tcl",
    }
    for target, source in copies.items():
        require(context["pins"].get(str(source)) == sha(source), "Unpinned snapshot source: " + str(source))
        shutil.copyfile(source, bundle / target)
    context = dict(context, output=str(output))
    (bundle / "context.json").write_text(json.dumps(context, indent=2) + "\n")
    old = dict(context["policy"], allowed_points=context["policy"]["allowed_points"][:94])
    union = guard.legacy.native_points(old).encode() + Path(context["csr_native_path"]).read_bytes()
    validate_union(union, context, guard.legacy.audit, False)
    (bundle / "waivers/operand_flush.el").write_bytes(union)
    shutil.copyfile(context["csr_native_path"], bundle / "csr107.original.el")
    (bundle / "csr_selection.tcl").write_text(selection_tcl(context))
    hashes = {str(p.relative_to(bundle)): sha(p) for p in sorted(bundle.rglob("*")) if p.is_file()}
    (bundle / "snapshot.json").write_text(json.dumps(hashes, indent=2) + "\n")
    return bundle


def load_snapshot(output, approval_file, approval_sha):
    output, bundle = locations(output)
    require(not output.exists() and bundle.is_dir(), "Prepare snapshot first; report must not exist")
    require(re.fullmatch(r"[0-9a-f]{64}", approval_sha or ""), "Explicit review SHA256 required")
    require(Path(approval_file).resolve().is_relative_to(guard.ROOT), "Review must be in this worktree")
    receipt_bytes = Path(approval_file).read_bytes()
    require(hashlib.sha256(receipt_bytes).hexdigest() == approval_sha, "Approval hash differs")
    record = json_bytes(receipt_bytes)
    context = verify_snapshot(bundle, record.get("snapshot_sha256"))
    approval(record, record["snapshot_sha256"], context["baseline_collection_sha256"])
    require(context["output"] == str(output), "Snapshot targets a different output")
    return output, bundle, context, record


def session(command, output, env, timeout):
    require(0 < timeout <= 150, "DVE timeout exceeds bounded budget")
    verify_snapshot(env["CSR_REVIEW_BUNDLE"], env["CSR_SNAPSHOT_SHA256"])
    started = time.monotonic()
    process = None
    code, timed_out = None, False
    try:
        with (output / "launcher.log").open("x") as stream:
            process = subprocess.Popen(command, cwd=output, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=3)
            record = dict(dve_launch_count=1, process_group=process.pid, timeout_seconds=timeout,
                elapsed_seconds=round(time.monotonic() - started, 3), timed_out=timed_out, returncode=code,
                cleanup="Unconditional kill of dedicated process group, including Xvfb and Python callbacks")
            (output / "execution.json").write_text(json.dumps(record, indent=2) + "\n")
    require(code == 0 and not timed_out, "DVE failed or timed out; no retry")


def run(output, approval_file, approval_sha, started):
    output, bundle, context, receipt = load_snapshot(output, approval_file, approval_sha)
    reviewed_root = receipt["snapshot_sha256"]
    # Independent review binds the prepared raw audit and code. Rehashing EVERY
    # input proves those exact raw bytes still have the checked values; no cache-
    # only inference and no second full XML replay before the bounded DVE session.
    verify_hashes(context["pins"])
    guard.verify_membership(context)
    require(context["csr_raw_audit"]["samples"] == context["tests"] and
            context["csr_raw_audit"]["selected_hits"] == 0, "Prepared raw admission incomplete")
    zero_targets(context["csr_raw_audit"]["bits"], context["csr_targets"])
    for row in context["csr_raw_audit"]["files"]:
        require(context["pins"].get(row["path"]) == row["sha256"], "Raw zero witness not pinned")
    require(len(context["csr_raw_audit"]["files"]) == context["tests"], "Raw witness population differs")
    require(sha(approval_file) == approval_sha, "Approval changed during admission")
    guard.latest_corpus(Path(context["design"]), context["image"], Path(context["baseline"]))
    remaining = min(150, int(160 - (time.monotonic() - started)))
    require(remaining > 0, "No bounded DVE time remains after admission")
    # Fresh output is the single-attempt claim. Failed reports cannot be retried.
    output.mkdir()
    (output / "inputs.txt").write_text("\n".join(context["inputs"]) + "\n")
    (output / "independent-review.json").write_text(json.dumps(receipt, indent=2) + "\n")
    try:
        verify_snapshot(bundle, reviewed_root)
        adapter = guard.module("csr_runtime_snapshot", bundle / "prepare_dve_waivers.py")
        argv = ["--design", context["design"], "--output", str(output), "--snapshot-sha256", reviewed_root]
        adapter.main(argv)
        command = ["xvfb-run", "-a", "-e", str(output / "xvfb.log"), "-s", "-screen 0 1280x1024x24",
                   "dve", "-full64", "-cov", "-script", str(bundle / "dve_hierarchy/export_dve_coverage.tcl")]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", DVE_COVERAGE_OUTPUT=str(output),
                   DVE_REVIEWED_WAIVERS=str(bundle / "dve_waivers.tcl"), CSR_REVIEW_BUNDLE=str(bundle),
                   CSR_SNAPSHOT_SHA256=reviewed_root)
        remaining = min(remaining, int(160 - (time.monotonic() - started)))
        session(command, output, env, remaining)
        verify_snapshot(bundle, reviewed_root)
        log = (output / "DVEfiles/dve_gui.log").read_text() + (output / "launcher.log").read_text()
        fresh_state(log, context)
        require("DVE_COVERAGE_EXPORT_DONE" in log and "DVE_WAIVER_EXPORT_DONE" in log, "Missing report completion")
        for name in ("summary.csv", "summary_waived.csv"):
            (output / (name + ".partial")).rename(output / name)
        status = adapter.main(argv + ["--finalize"])
        guard.verify_membership(context)
        verify_hashes(context["pins"])
        guard.latest_corpus(Path(context["design"]), context["image"], Path(context["baseline"]))
        require(sha(approval_file) == approval_sha, "Review changed during session")
        verify_snapshot(bundle, reviewed_root)
        status.update(snapshot_sha256=reviewed_root, independent_review_sha256=approval_sha,
                      baseline_collection_sha256=context["baseline_collection_sha256"])
        (output / "waiver_status.json").write_text(json.dumps(status, indent=2) + "\n")
        print("Supplemental report verified; raw retained separately; not final signoff", flush=True)
    except BaseException as error:
        (output / "waiver_status.json").write_text(json.dumps(dict(status="REJECTED_NO_SUCCESS_CLAIM",
            error=str(error), retry_allowed=False, final_coverage_application=False), indent=2) + "\n")
        raise


def dispatch(args):
    started = time.monotonic()
    if args.command == "run":
        run(args.output, args.approval, args.approval_sha256, started)
        return 0
    context = guard.build_context(args.baseline)
    result = dict(status="ADMITTED_PENDING_INDEPENDENT_APPLICATION_REVIEW", baseline=context["baseline"],
        tests=context["tests"], csr_raw_selected_hits=context["csr_raw_audit"]["selected_hits"],
        existing_points=94, csr_points=107, observers=10, new_dve_launches=0,
        old_strict_status=context["old_strict_status"], baseline_collection_sha256=context["baseline_collection_sha256"],
        design_sha256=context["policy"]["design_sha256"], csr_native_sha256=context["csr_native_sha256"],
        qualified_manifest_sha256=context["qualified_manifest_sha256"], raw_summary_sha256=context["raw_reference_sha256"],
        raw_top=csv_rows(context["raw_reference"])[0])
    if args.command == "prepare":
        bundle = snapshot(args.output, context)
        result.update(snapshot=str(bundle), snapshot_sha256=sha(bundle / "snapshot.json"))
    print(json.dumps(result, indent=2), flush=True)
    return 0

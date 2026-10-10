#!/usr/bin/env python3
"""Report proven PASS DUT-retired activity from one batch checkpoint snapshot.

Offline only: invokes objdump, never a generator, compiler, simulator or replay.
Partial reports are useful but are not batch PASS or functional/code coverage.
"""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from ara_verify.artifacts import simulation_image
from ara_verify.coverage_matrix import ACCEPTED_EVIDENCE, summarize_activity
from ara_verify.dynamic_coverage import audit_case, digest, disassemble
from ara_verify.plan import audit_run
from ara_verify.vcs_source_manifest import collect
from ara_verify.vstart_activity import collect_vstart


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OBJDUMP = ROOT / "install/riscv-gcc/bin/riscv64-unknown-elf-objdump"
TARGET_PLAN = ROOT / "verification/verification_plan.json"
# The single prior wrapper revision authorized by the continuation schema.
PRIOR_WRAPPER = "954c17424af6ee24a6f5698786027bb63e17b701c67f436f55d7771e1b91f420"


def read(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def snapshot(path):
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def prove_identity(batch, identity):
    """Rehash recorded inputs now; do not invent missing execution-time proof."""
    require(identity.get("files") and identity.get("sources"), "empty identity inventory")
    require(str(batch / "plan.json") in identity["files"], "batch plan is not pinned")
    manifest_path = Path(identity["source_manifest"])
    require(str(manifest_path) in identity["files"], "source manifest is not pinned")
    config = Path(identity["image"]).parent / "simulator.conf"
    require(str(config) in identity["files"], "simulator config is not pinned")
    for path, expected in identity["files"].items():
        require(digest(Path(path)) == expected, f"input drift: {path}")
    for path, expected in identity.get("reused_evidence", {}).items():
        require(digest(Path(path)) == expected, f"reused evidence drift: {path}")
    manifest = read(manifest_path)
    require(manifest["files"] == identity["sources"], "source inventories disagree")
    current = collect(Path(manifest["filelist"]), Path(manifest["repo_root"]),
                      [Path(p) for p in manifest["extra_sources"]])
    require(current == identity["sources"], "source inventory/hash drift")
    image = identity["images"][identity["image"]]
    require(bool(image), "empty image inventory")
    for path, expected in identity["images"].items():
        require(simulation_image(Path(path)) == expected, f"runtime image drift: {path}")
    fingerprint = hashlib.sha256(json.dumps(image, sort_keys=True).encode()).hexdigest()
    return {"status": "PROVEN", "simv_path": identity["image"],
            "fingerprint": fingerprint, "component_count": len(image),
            "config_sha256": digest(config), "runtime_sha256": image,
            "source_manifest": str(manifest_path),
            "source_manifest_sha256": digest(manifest_path),
            "source_count": len(current), "pinned_file_count": len(identity["files"]),
            "reused_evidence_file_count": len(identity.get("reused_evidence", {})),
            "scope": "Batch-recorded image/source/input identity rehashed at report time; "
                     "each counted case must independently match the recorded image."}


def reuse_context(batch, row, outcome, identity):
    """Bind a one-hop import to frozen old evidence, not arbitrary external paths."""
    continuation_path = batch / "continuation.json"
    require(identity["files"].get(str(continuation_path)) == digest(continuation_path),
            "continuation is not pinned or changed")
    continuation = read(continuation_path)
    old = Path(outcome["source_batch"]).resolve()
    require(old != batch and Path(continuation["source"]).resolve() == old,
            "source_batch differs from continuation")
    pins = identity["reused_evidence"]
    metadata = [old / name for name in ("identity.json", "checkpoint.json", "plan.json")]
    for path in metadata:
        require(pins.get(str(path)) == digest(path), f"old metadata not pinned or changed: {path}")
    prior, checkpoint, plan = [read(path) for path in metadata]
    for key in ("image", "generator", "spike", "source_manifest", "sources", "images"):
        require(prior[key] == identity[key], f"continuation identity differs: {key}")
    require(checkpoint["status"] == "STOPPED", "source batch is not stopped")
    matches = [r for r in plan["cases"] if r["name"] == row["name"]]
    require(matches == [row], "reused case differs from old normalized plan")
    original = {k: v for k, v in outcome.items() if k not in {"reused", "source_batch"}}
    require(checkpoint["cases"][row["name"]] == original, "old checkpoint/outcome disagree")
    require("reused" not in checkpoint["cases"][row["name"]], "nested reuse is not supported")
    wrapper = str(ROOT / "verification/run_batch_exploration.py")
    expected_changes = []
    for path, expected in prior["files"].items():
        if Path(path).is_relative_to(old):
            require(pins.get(path) == expected, f"historical input pin differs: {path}")
        else:
            current = identity["files"].get(path)
            require(current is not None, f"historical external input not pinned: {path}")
            if current != expected:
                require(path == wrapper and expected == PRIOR_WRAPPER,
                        f"unauthorized historical input change: {path}")
                expected_changes.append({"path": path, "before": expected, "after": current})
    changes = continuation["wrapper_changes"]
    require(sorted(changes, key=lambda x: x["path"]) ==
            sorted(expected_changes, key=lambda x: x["path"]), "wrapper change record differs")
    run = old / "cases" / row["name"]
    require(run.resolve().is_relative_to(old), "reused run escaped source batch")
    fresh_audit = batch / "reuse-audits" / (row["name"] + ".json")
    evidence = [*metadata, continuation_path, fresh_audit, old / "logs" / (row["name"] + ".log")]
    for path in [fresh_audit, evidence[-1], *(p for p in run.rglob("*") if p.is_file())]:
        require(pins.get(str(path)) == digest(path), f"reused evidence not pinned or changed: {path}")
    return run, original, evidence, fresh_audit


def check_recorded_audit(path, artifact, strict):
    recorded = read(path)
    require(recorded.get("status") == "PASS" and recorded.get("errors") == [] and
            recorded.get("case_count") == 1, "missing independent PASS audit")
    audited = recorded["cases"]
    require(len(audited) == 1 and audited[0].get("status") == "PASS" and
            audited[0].get("errors") == [] and
            Path(audited[0]["artifact_dir"]).resolve() == artifact, "audit case differs")
    for flag in (["require_complete", "require_trace"] +
                 (["require_vector", "require_full_match"] if strict else [])):
        require(recorded["policy"].get(flag) is True, f"independent audit lacks {flag}")


def case_activity(batch, row, outcome, identity, proof, objdump):
    run = batch / "cases" / row["name"]
    original, reuse_paths, fresh_audit = outcome, [], None
    if "reused" in outcome or "source_batch" in outcome:
        require(outcome.get("reused") is True, "invalid reused marker")
        run, original, reuse_paths, fresh_audit = reuse_context(batch, row, outcome, identity)
    artifact = Path(outcome["artifact_dir"]).resolve()
    require(artifact.is_relative_to(run.resolve()), "artifact escaped isolated case")
    summary_path, audit_path = run / "summary.json", run / "independent_audit.json"
    require(Path(outcome["summary"]).resolve() == summary_path.resolve(), "summary path differs")
    require(Path(outcome["audit"]).resolve() == audit_path.resolve(), "audit path differs")
    require(outcome.get("returncode") == 0, "PASS worker did not return zero")
    # Hash the evidence before and after analysis, including standalone comparison
    # files used by audit_run and embedded results used by the activity parser.
    paths = [*reuse_paths, summary_path, audit_path, run / "run.json", run / "batch_result.json",
             artifact / "inputs.json", artifact / "input.elf", artifact / "trace_summary.json"]
    paths += sorted(p for p in artifact.iterdir()
                    if p.is_file() and p.suffix in {".json", ".csv", ".log"})
    hashes = {str(p): digest(p) for p in set(paths)}
    require(read(run / "batch_result.json") == original, "checkpoint/outcome disagree")
    summary = read(summary_path)
    require(isinstance(summary, list) and len(summary) == 1, "not exactly one summary case")
    require(summary[0]["status"] == "PASS" and
            Path(summary[0]["artifact_dir"]).resolve() == artifact, "summary identity/status differs")
    strict = row["kind"] != "directed"
    check_recorded_audit(audit_path, artifact, strict)
    if fresh_audit is not None:
        check_recorded_audit(fresh_audit, artifact, strict)
    inputs = read(artifact / "inputs.json")
    require(inputs["simv"]["path"] == identity["image"] and
            inputs["simv"]["image_sha256"] == identity["images"][identity["image"]],
            "case used a different runtime image")
    elf = artifact / "input.elf"
    require(inputs["binary"]["path"] == str(elf) and
            inputs["binary"]["sha256"] == digest(elf), "private ELF differs")
    if strict:
        require(inputs["spike"]["path"] == identity["spike"] and
                inputs["spike"]["sha256"] == identity["files"][identity["spike"]],
                "reference image differs")
        result = read(artifact / "result.json")
        require(Path(result["elf"]).resolve() == elf, "activity ELF is not the private ELF")
        if row["kind"] == "random":
            require(result["seed"] == row["seed"], "result seed differs")
        for key, filename in (("comparison", "commit_comparison.json"),
                              ("vector_commit", "vector_commit_comparison.json")):
            require(result.get(key) == read(artifact / filename), f"embedded {key} differs")
    else:
        require(row["elf_sha256"] == digest(elf), "directed ELF differs from frozen plan")
        require(not (artifact / "result.json").exists(), "unexpected random result in directed case")
    rechecked = audit_run(run, require_trace=True, require_vector=strict, require_full_match=strict)
    require(rechecked["status"] == "PASS" and not rechecked["errors"],
            f"current independent audit failed: {rechecked}")
    activity = audit_case(artifact, objdump)
    require(activity["evidence_kind"] in ACCEPTED_EVIDENCE, "prefix/legacy evidence is not complete")
    decoded = disassemble(elf, objdump)
    trace = artifact / ("ara_commit_trace.csv" if strict else "commit_trace.csv")
    with trace.open(newline="") as stream:
        vstart = collect_vstart(csv.DictReader(stream), decoded)
    require(hashes == {p: digest(Path(p)) for p in hashes}, "case evidence changed while reading")
    activity.update(name=row["name"], kind=row["kind"], test=row["test"],
                    reused=outcome.get("reused", False), source_batch=outcome.get("source_batch"),
                    vstart=vstart, evidence_sha256=hashes,
                    image_identity={**proof, "provenance": "batch_and_case_recorded_inputs_rehashed"})
    return activity


def bins(targets, counts):
    return {"target_bins": len(targets),
            "observed_bins": sum(counts[t] > 0 for t in targets),
            "unobserved_bins": [t for t in targets if not counts[t]],
            "bins": {t: {"retired_instructions": counts[t]} for t in targets}}


def aggregate(records, target_plan):
    result = summarize_activity(records, target_plan)
    mnemonics, mask, vstart = Counter(), Counter(), Counter()
    for record in records:
        mnemonics.update(record["mnemonics"])
        mask["v0.t"] += record["dut_retired_masked_instructions"]
        mask["without_v0.t"] += (record["dut_retired_vector_instructions"] -
                                  record["dut_retired_configurations"] -
                                  record["dut_retired_masked_instructions"])
        for name in ("linked_known_zero", "linked_known_nonzero", "linked_unknown_value"):
            vstart[name] += record["vstart"][name]
    result["axes"]["mask_operand"] = bins(["v0.t", "without_v0.t"], mask)
    result["axes"]["mask_operand"]["scope"] = (
        "Retired non-vset operand form, not active/inactive lane execution; includes setup/signature code.")
    result["axes"]["explicit_vstart"] = bins(["linked_known_zero", "linked_known_nonzero"], vstart)
    result["axes"]["explicit_vstart"].update(
        unknown_linked_instructions=vstart["linked_unknown_value"],
        scope="Explicit vstart CSR write linked to next retired non-vset vector instruction; "
              "not implicit-zero, illegal-vstart or exception-restart functional coverage.")
    result["mnemonics"] = {"observed_bins": len(mnemonics), "target_bins": None,
                           "unobserved_bins": None, "retired_counts": dict(sorted(mnemonics.items())),
                           "scope": "Executed mnemonics only; no declared full-ISA mnemonic denominator."}
    result["retired_vector_instructions"] = sum(r["dut_retired_vector_instructions"] for r in records)
    result["source_generated_activity"] = {"included": False, "reason": "Generated source is not execution evidence."}
    return result


def report(batch, objdump=DEFAULT_OBJDUMP, target_path=TARGET_PLAN):
    batch = batch.resolve()
    checkpoint, checkpoint_hash = snapshot(batch / "checkpoint.json")
    plan, plan_hash = snapshot(batch / "plan.json")
    identity, identity_hash = snapshot(batch / "identity.json")
    targets, target_hash = snapshot(target_path)
    records, excluded, errors = [], [], []
    proof = {"status": "NOT_PROVEN"}
    try:
        proof = prove_identity(batch, identity)
        require(digest(batch / "plan.json") == plan_hash, "plan changed during identity check")
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append(f"identity: {error}")
    names = [r["name"] for r in plan["cases"]]
    require(len(names) == len(set(names)), "duplicate plan names")
    outcomes = checkpoint["cases"]
    require(not (set(outcomes) - set(names)), "checkpoint has unplanned cases")
    require(checkpoint["total"] == len(names), "checkpoint/plan totals differ")
    require(checkpoint["completed"] == len(outcomes), "checkpoint completed count differs")
    require(checkpoint["passed"] == sum(o["status"] == "PASS" for o in outcomes.values()),
            "checkpoint PASS count differs")
    for row in plan["cases"]:
        outcome = outcomes.get(row["name"], {})
        status = outcome.get("status", "NOT_COMPLETED")
        if status != "PASS" or errors:
            excluded.append({"name": row["name"], "status": status,
                             "reason": "not complete PASS" if status != "PASS" else "identity NOT_PROVEN"})
            continue
        try:
            records.append(case_activity(batch, row, outcome, identity, proof, objdump))
        except (OSError, ValueError, KeyError, TypeError) as error:
            excluded.append({"name": row["name"], "status": "NOT_PROVEN", "reason": str(error)})
    # An advancing checkpoint is expected. The initial bytes define this snapshot;
    # only identity/plan and completed-case evidence must stay unchanged.
    require(digest(batch / "identity.json") == identity_hash, "batch identity changed during report")
    require(digest(batch / "plan.json") == plan_hash, "batch plan changed during report")
    result = aggregate(records, targets)
    complete = (checkpoint["status"] in {"PASS", "COMPLETE_WITH_FAILURES"} and len(outcomes) == len(names))
    unproven = bool(errors) or any(x["status"] == "NOT_PROVEN" for x in excluded)
    result.update(schema_version=1, status="NOT_PROVEN" if unproven else "COMPLETE" if complete else "PARTIAL",
                  scope="DUT-retired activity in independently checked complete PASS cases only; "
                        "includes initialization/signature instructions, not RTL code or functional signoff.",
                  generated_at=datetime.now(timezone.utc).isoformat(), batch=str(batch),
                  campaign_status=checkpoint["status"], batch_complete=complete,
                  counts={"planned": len(names), "completed_at_snapshot": len(outcomes),
                          "checkpoint_pass": checkpoint["passed"], "accepted": len(records),
                          "excluded": len(excluded)}, proof=proof, errors=errors,
                  excluded_batch_cases=excluded,
                  cases=[{k: v for k, v in r.items() if k != "image_identity"} for r in records],
                  snapshot_sha256={"checkpoint": checkpoint_hash, "plan": plan_hash,
                                   "identity": identity_hash, "target_plan": target_hash,
                                   "objdump": digest(objdump)}, target_plan=str(target_path),
                  analyzer_sha256={str(p): digest(p) for p in
                                   [Path(__file__).resolve(), *sorted((ROOT / "verification/ara_verify").glob("*.py"))]},
                  snapshot_note="Hashes of checkpoint/evidence are captured now, not asserted to have been frozen before execution.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--objdump", type=Path, default=DEFAULT_OBJDUMP)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output exists: {args.output}; choose a new snapshot filename")
    try:
        result = report(args.batch, args.objdump.resolve())
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"status": "NOT_PROVEN", "errors": [str(error)], "batch": str(args.batch)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({k: result[k] for k in ("status", "counts", "errors") if k in result}))
    return 1 if result["status"] == "NOT_PROVEN" else 0


if __name__ == "__main__":
    raise SystemExit(main())

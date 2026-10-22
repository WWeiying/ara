"""Aggregate checked real-DUT UVM observations into explicit coverage bins."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from .artifacts import simulation_image
from .uvm_dut import check_real_uvm_log


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _hit(observed: dict[str, int | None], name: str, minimum: int = 1) -> bool:
    value = observed.get(name)
    return isinstance(value, int) and value >= minimum


def custom_instruction_activity(trace: Path) -> dict[str, int]:
    names = ("qbs_m1", "akv_v2_fill", "akv_v2_column",
             "akv_value_load", "akv_release")
    counts = {name: 0 for name in names}
    counts.update({f"{name}_completed": 0 for name in names})
    pending: dict[tuple[str, str], tuple[str, int]] = {}
    with trace.open(encoding="utf-8", errors="replace") as stream:
        for row in csv.reader(stream):
            if len(row) >= 2 and row[1] == "reset":
                pending.clear()
                continue
            if len(row) < 7 or row[1] not in ("alloc", "done"):
                continue
            try:
                instruction = int(row[6], 16)
            except ValueError:
                continue
            key = (row[2], row[3])
            name = None
            if instruction == 0x00b5045b:
                name = "qbs_m1"
            elif instruction & 0x7f == 0x5b:
                name = {3: "akv_value_load", 5: "akv_release",
                        6: "akv_v2_fill", 7: "akv_v2_column"}.get(
                            (instruction >> 12) & 0x7)
            if name is None:
                continue
            if row[1] == "alloc":
                counts[name] += 1
                pending[key] = (name, instruction)
            elif pending.get(key) == (name, instruction):
                counts[f"{name}_completed"] += 1
                del pending[key]
    return counts


def bins_for(result: dict[str, object]) -> dict[str, bool]:
    observed = result.get("coverage_observations") or {}
    if not isinstance(observed, dict):
        observed = {}
    reads = result.get("axi_read_counts") or {}
    writes = result.get("axi_write_counts") or {}
    cvxif = result.get("uvm_counts") or {}
    custom = result.get("custom_instruction_activity") or {}
    if not isinstance(reads, dict):
        reads = {}
    if not isinstance(writes, dict):
        writes = {}
    if not isinstance(cvxif, dict):
        cvxif = {}
    if not isinstance(custom, dict):
        custom = {}
    clean_reads = reads.get("aborted") == 0 and reads.get("pending") == 0
    clean_writes = (writes.get("aborted") == 0 and writes.get("pending") == 0 and
                    writes.get("w_bursts") == writes.get("matched"))
    completed_reads = observed.get("axi_read_completed")
    completed_writes = observed.get("axi_write_matched_bursts")
    return {
        "cvxif_request": _hit(observed, "cvxif_requests"),
        "cvxif_atomic_req_resp": (
            isinstance(cvxif.get("requests"), int) and cvxif["requests"] > 0 and
            cvxif["requests"] == cvxif.get("responses") == cvxif.get("immediate") and
            cvxif.get("aborted") == 0 and cvxif.get("reused") == 0),
        "backend_concurrent_vid": _hit(observed, "backend_vid_max_live", 2),
        "axi_read_complete": _hit(observed, "axi_read_completed"),
        "axi_read_multibeat": bool(clean_reads and isinstance(completed_reads, int) and
                                   _hit(observed, "axi_read_r_beats", completed_reads + 1)),
        "axi_write_complete": _hit(observed, "axi_write_completed"),
        "axi_write_multibeat": bool(clean_writes and isinstance(completed_writes, int) and
                                    _hit(observed, "axi_write_w_beats", completed_writes + 1)),
        "axi_ar_backpressure": _hit(observed, "axi_ar_stall_cycles"),
        "axi_r_backpressure": _hit(observed, "axi_r_stall_cycles"),
        "axi_aw_backpressure": _hit(observed, "axi_aw_stall_cycles"),
        "axi_w_backpressure": _hit(observed, "axi_w_stall_cycles"),
        "axi_b_always_ready": (
            isinstance(writes.get("b"), int) and writes["b"] > 0 and
            observed.get("axi_b_stall_cycles") == 0),
        "axi_reset_aborts_read": result.get("reset_kind") == "read" and
                                 isinstance(reads.get("aborted"), int) and reads["aborted"] > 0,
        "axi_reset_aborts_write": result.get("reset_kind") == "write" and
                                  isinstance(writes.get("aborted"), int) and writes["aborted"] > 0,
        "qbs_m1_allocated": _hit(custom, "qbs_m1"),
        "akv_v2_fill_allocated": _hit(custom, "akv_v2_fill"),
        "akv_v2_column_allocated": _hit(custom, "akv_v2_column"),
        "akv_value_load_allocated": _hit(custom, "akv_value_load"),
        "akv_release_allocated": _hit(custom, "akv_release"),
        **{f"{name}_completed": _hit(custom, f"{name}_completed")
           for name in ("qbs_m1", "akv_v2_fill", "akv_v2_column",
                        "akv_value_load", "akv_release")},
    }


def audit_evidence(path: Path) -> tuple[dict[str, object] | None, list[str]]:
    errors = []
    path = path.resolve()
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return None, [f"cannot read {path}: {error}"]
    if not isinstance(saved, dict) or saved.get("status") != "PASS" or saved.get("issues"):
        return None, [f"{path}: real-DUT UVM audit is not PASS"]
    work = path.parent / "work"
    log, elf, vector = (work / "run.vcs.log", work / "input.elf",
                        work / "vector_trace.csv")
    images = saved.get("sim_image_sha256")
    simv_paths = [Path(name) for name in images or {}
                  if Path(name).name == "simv"] if isinstance(images, dict) else []
    if len(simv_paths) != 1:
        return None, [f"{path}: VCS launcher identity is missing or ambiguous"]
    simv = simv_paths[0]
    for name, source, expected in (
        ("log", log, saved.get("log_sha256")),
        ("ELF", elf, saved.get("elf_sha256")),
        ("vector trace", vector, saved.get("vector_trace_sha256")),
    ):
        if not source.is_file() or not isinstance(expected, str) or _digest(source) != expected:
            errors.append(f"{path}: {name} is missing or changed")
    contract = "[DUT_BOUNDARY_CONTRACT] atomic_cvxif=1 b_always_ready=1"
    if log.is_file() and contract not in log.read_text(errors="replace"):
        errors.append(f"{path}: real-DUT boundary contract assertions are not evidenced")
    try:
        if simulation_image(simv) != images:
            errors.append(f"{path}: VCS executable image changed")
    except OSError as error:
        errors.append(f"{path}: cannot verify VCS image: {error}")
    if errors:
        return None, errors
    reset_kind = saved.get("reset_kind")
    if reset_kind not in (None, "read", "write"):
        return None, [f"{path}: invalid reset test kind"]
    fresh = check_real_uvm_log(log, require_events=True, require_backend=True,
                               vector_trace=vector, reset_kind=reset_kind)
    if fresh["status"] != "PASS":
        errors.extend(f"{path}: {issue}" for issue in fresh["issues"])
    if fresh.get("axi_read_counts") is None:
        errors.append(f"{path}: AXI read summary is missing")
    if fresh.get("axi_write_counts") is None:
        errors.append(f"{path}: AXI write summary is missing")
    if fresh.get("axi_stall_counts") is None:
        errors.append(f"{path}: five-channel AXI stall summary is missing")
    fresh["custom_instruction_activity"] = custom_instruction_activity(vector)
    for key in ("uvm_counts", "backend_counts", "axi_read_counts", "axi_write_counts",
                "axi_stall_counts", "uvm_event_sha256", "contract_event_sha256",
                "uvm_backend_event_sha256", "vector_backend_event_sha256", "reset_kind"):
        if fresh.get(key) != saved.get(key):
            errors.append(f"{path}: saved {key} differs from source log")
    fresh["sim_image_identity"] = hashlib.sha256(
        json.dumps(images, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return (fresh if not errors else None), errors


def collect(paths: list[Path]) -> dict[str, object]:
    records = []
    errors = []
    hits: dict[str, int] = {}
    groups: dict[str, dict[str, object]] = {}
    for path in paths:
        result, issues = audit_evidence(path)
        errors.extend(issues)
        if result is None:
            continue
        bins = bins_for(result)
        identity = result.get("sim_image_identity")
        if not isinstance(identity, str):
            errors.append(f"{path}: audited VCS image identity is missing")
            continue
        records.append({"audit": str(path.resolve()), "bins": bins,
                        "observations": result["coverage_observations"],
                        "custom_instruction_activity":
                            result.get("custom_instruction_activity", {}),
                        "log_sha256": result["log_sha256"],
                        "sim_image_identity": identity})
        group = groups.setdefault(identity, {"run_count": 0, "bin_hits": {}})
        group["run_count"] += 1
        for name, hit in bins.items():
            hits[name] = hits.get(name, 0) + int(hit)
            group["bin_hits"][name] = group["bin_hits"].get(name, 0) + int(hit)
    for name in bins_for({}):
        hits.setdefault(name, 0)
        for group in groups.values():
            group["bin_hits"].setdefault(name, 0)
    missing = sorted(name for name, count in hits.items() if count == 0)
    for group in groups.values():
        group["missing_bins"] = sorted(name for name, count in group["bin_hits"].items()
                                        if count == 0)
    closed_images = sorted(identity for identity, group in groups.items()
                           if not group["missing_bins"])
    return {"status": "PASS" if records and not errors and closed_images else "INCOMPLETE",
            "run_count": len(records), "bin_hits": hits, "missing_bins": missing,
            "image_groups": groups, "closed_images": closed_images,
            "excluded_unreachable_bins": {
                "axi_b_backpressure": "Ara VSTU acknowledges every valid B; QBS/AKV take AXI ownership only after normal VLSU drain",
                "cvxif_same_cycle_id_reuse": "Ara holds CVXIF requests until their matching response is accepted in the same cycle",
            },
            "errors": errors, "runs": records}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    best = max((len(result["bin_hits"]) - len(group["missing_bins"])
                for group in result["image_groups"].values()), default=0)
    print(f"real-DUT UVM coverage: {result['status']} "
          f"(best single image {best}/{len(result['bin_hits'])} bins)")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

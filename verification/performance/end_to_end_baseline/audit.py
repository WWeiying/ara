#!/usr/bin/env python3
"""Read-only replay of existing evidence; never launches an EDA tool or board job."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def verify_pins(pins):
    require(bool(pins), "Empty pin inventory")
    for name, expected in pins.items():
        require(digest(name) == expected, "Source drift: " + name)
    return len(pins)


def verify_collection(observer):
    receipt = read(observer / "collection_receipt.json")
    require(receipt.get("hashes_checked") is True, "Unchecked collection")
    metadata = receipt["metadata"]
    require(bool(metadata["pins"]) and all(
        row["expected"] == row["actual"] for row in metadata["pins"]),
        "Remote collection pin mismatch")
    root = Path(receipt["root"]).resolve()
    require(bool(metadata["files"]), "Empty collection")
    seen = set()
    for row in metadata["files"]:
        relative = Path(row["relative"])
        require(not relative.is_absolute() and ".." not in relative.parts,
                "Unsafe collected path")
        path = (root / relative).resolve()
        require(path.is_relative_to(root) and path not in seen,
                "Escaping or duplicate collected path")
        seen.add(path)
        require(digest(path) == row["sha256"], "Collected artifact drift: " + str(path))
    result = read(observer / "result.json")
    require(result.get("worker_source_pins_match") is True, "Worker pins unaccepted")
    local_count = verify_pins(read(observer / "source-pins.json"))
    return root, result, dict(local_pins=local_count, artifacts=len(seen),
        receipt_sha256=digest(observer / "collection_receipt.json"),
        result_sha256=digest(observer / "result.json"))


def checker(path):
    spec = importlib.util.spec_from_file_location("e2e_replay_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check


def agrees(recomputed, recorded):
    require(all(key in recorded and recorded[key] == value
                for key, value in recomputed.items()), "Checker result differs from receipt")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def repository(repo, tag):
    dirty = git(repo, "diff", "--name-only", "HEAD").splitlines()
    return dict(path=str(repo), head=git(repo, "rev-parse", "HEAD"),
        branch=git(repo, "branch", "--show-current"),
        delivery=git(repo, "rev-parse", tag + "^{commit}"),
        dirty_tracked_files={p: digest(repo / p) if (repo / p).is_file() else None
                             for p in dirty},
        build_policy="Use explicit commits and reviewed dependency locks, not dirty checkout",
        untracked_files_are_build_inputs=False)


def replay_board(board):
    anchor_path = board / "goal_requirements_audit_02/result.json"
    anchor = read(anchor_path)
    verify_pins(anchor["source_pins"])
    sys.path[:0] = [str(board), str(board.parent / "qwen3_perf_diagnosis_20261104_01")]
    jobs = {
        "final_e2e_observer_01": "check_final_e2e_v1.py",
        "m4_observer_02": "check_m4_pair_v1.py",
        "native_answer_observer_06": "check_quant_native_answer_v2.py",
        "native_followup_observer_04": "check_quant_native_grid_v2.py",
    }
    audited = {r["observer"]: r for r in anchor["collection_audits"]}
    results = {}
    for name, script in jobs.items():
        root, recorded, hashes = verify_collection(board / name)
        for field in ("receipt_sha256", "result_sha256"):
            require(hashes[field] == audited[name][field], "Audit identity differs: " + name)
        check = checker(board / script)
        if name == "native_followup_observer_04":
            for fmt in ("q4_0", "q8_0"):
                require(check((root / ("grid_" + fmt) / "uart.bin").read_bytes()) ==
                        recorded["quantized_grids"][fmt], "Grid replay mismatch")
        else:
            agrees(check(root), recorded)
        # Check again after replay; reports remain external and read-only.
        verify_pins(read(board / name / "source-pins.json"))
        require(digest(board / name / "result.json") == hashes["result_sha256"],
                "Receipt changed during replay")
        results[name] = dict(state="COLLECTION_HASHES_AND_CHECKER_REPLAY_PASS", **hashes)
    final = read(board / "final_e2e_observer_01/result.json")
    answer = read(board / "native_answer_observer_06/result.json")
    m4 = read(board / "m4_observer_02/result.json")
    return dict(state="EXISTING_BOARD_EVIDENCE_REPLAY_PASS", collections=results,
        audit_sha256=digest(anchor_path), bitstream_sha256=anchor["bitstream_sha256"],
        production_binary_sha256=anchor["production_runtime_sha256"],
        experimental_binary_sha256=anchor["candidate_runtime_sha256"],
        candidate_promoted=False, isolated_rtl_speedup=False,
        f16=dict(speedups=final["aggregate_speedups"], totals=final["totals"],
            cases=[{k: row[k] for k in ("name", "prompt_tokens", "generated_tokens",
                    "metrics", "speedups", "full_logits_baseline_compared")}
                   for row in final["cases"]], limits=final["limits"]),
        m4=dict(speedups=m4["speedups"]),
        quantized_answer=dict(speedups=answer["speedups"],
            prompt_tokens=answer["prompt_tokens"], generated_tokens=answer["generated_tokens"],
            full_logits_bitwise_compared=answer["full_logits_bitwise_compared"],
            runs={key: {k: value[k] for k in ("metrics", "projection_coverage",
                                           "actual_quant_counts")}
                  for key, value in answer["runs"].items()}, limits=answer["limits"]),
        latest_hardware_stage_time_fractions=None)


def replay_graph(root, ara):
    run = root / "verification/out/graph-schedule-model-20261029-01"
    result = read(run / "result.json")
    require(result["state"] == "PASS" and result["post_pins_match"], "Graph receipt rejected")
    require(digest(run / "source-pins.json") == result["source_pins_sha256"], "Graph pins differ")
    sys.path.insert(0, str(ara / "verification/qbs/graph_cycles"))
    recomputed = checker(ara / "verification/qbs/graph_cycles/schedule_check.py")(
        (run / "qemu.log").read_text())
    require(recomputed == result["measured"], "Graph replay mismatch")
    return dict(state="HISTORICAL_LOG_CHECKER_REPLAY_PASS", measured=recomputed,
        result_sha256=digest(run / "result.json"), log_sha256=digest(run / "qemu.log"),
        all_historical_build_inputs_revalidated=False,
        interpretation="QEMU functional records only; no hardware timing inference")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ara", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--llama", type=Path, default=Path("/home/wangwy/llama/llama.cpp"))
    parser.add_argument("--verification", type=Path,
                        default=Path("/home/wangwy/openproject/ara_dsa_signoff_integration"))
    parser.add_argument("--board", type=Path,
                        default=Path("/home/wangwy/fpga_runs/optimization_board_proof_20261105_01"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    result = dict(schema=1, state="INCOMPLETE", created_utc=datetime.now(timezone.utc).isoformat(),
                  new_simulations=0, hardware_changed=False, production_software_changed=False)
    try:
        tag = "qbs-akv-validated-20261029"
        result["repositories"] = {"ara": repository(args.ara, tag),
                                  "llama": repository(args.llama, tag)}
        result["board"] = replay_board(args.board)
        result["graph"] = replay_graph(args.verification, args.ara)
        result["remaining_gates"] = [
            "Review/pin experimental SDK candidate before using it as a new production baseline",
            "Measure current hardware per-stage times, including probe overhead, not QEMU timestamps",
            "Match current RTL configuration and locked dependencies to any new simulator image",
            "Do not combine F16 and quantized-KV cohorts or multiply their speedups",
        ]
        result["state"] = "EVIDENCE_REPLAY_PASS_STAGE_ATTRIBUTION_PENDING"
    except Exception as exc:
        result["state"] = "FAIL"
        result["error"] = repr(exc)
        raise
    finally:
        result["audit_script_sha256"] = digest(__file__)
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(result["state"])


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()

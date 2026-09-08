#!/usr/bin/env python3
"""Revalidate a completed D256 model cohort without rerunning or editing it."""

import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import re

from run_d256_admission import require_admission
from run_portability_stage2 import sha
from summarize_portability_stage2 import model_records


CASES = ("gemma_enabled", "gemma_default", "qwen_existing", "gemma_long_enabled")
MODES = ("RVV", "QBS_ONLY", "QBS_AKV_V2")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def metric(text, name):
    values = re.findall(r"^" + re.escape(name) + r"=([^\r\n]+)$", text, re.MULTILINE)
    require(len(values) == 1, f"missing or duplicate metric: {name}")
    return values[0]


def number(text, name):
    value = float(metric(text, name))
    require(math.isfinite(value), f"nonfinite metric: {name}")
    return value


def validate_log(text, plan):
    text = text.replace("\r", "")
    boundaries = re.findall(r"^AKV_TOKEN_RUN_(BEGIN|EXIT)=([^\n]+)$", text, re.MULTILINE)
    expected = [(event, mode if event == "BEGIN" else mode + ":0")
                for mode in MODES for event in ("BEGIN", "EXIT")]
    require(boundaries == expected, "incomplete, duplicate, or failed model runs")
    require(metric(text, "LLAMA_GUEST_EXIT") == "0", "guest did not succeed")
    require(metric(text, "MODEL_NUMERICAL_CONTRACT") == "decision-preserving-v1",
            "unexpected numerical contract")
    for key, value in (("MAX_KL", 0.02), ("MIN_COSINE", 0.98), ("MIN_TOP5_OVERLAP", 0.8)):
        require(number(text, f"MODEL_LOGITS_{key}_TOLERANCE") == value,
                "model tolerance changed")
    for prefix in ("QBS_RVV", "AKV"):
        for suffix in ("RECORDS", "COMPARABLE_RECORDS"):
            require(number(text, f"{prefix}_LOGITS_{suffix}") == 3,
                    "expected all three comparable logits records")
        for suffix in ("LOGITS_TOP1_EQUAL", "TOKEN_OUTPUT_EQUAL"):
            require(number(text, f"{prefix}_{suffix}") == 1, "token decision changed")
        require(0 <= number(text, f"{prefix}_LOGITS_MAX_KL") <= 0.02, "KL gate failed")
        require(0.98 <= number(text, f"{prefix}_LOGITS_MIN_COSINE") <= 1, "cosine gate failed")
        require(0.8 <= number(text, f"{prefix}_LOGITS_MIN_TOP5_OVERLAP") <= 1, "top5 gate failed")
        require(number(text, f"{prefix}_LOGITS_MAX_ABS") >= 0, "invalid absolute error")

    admission = require_admission(text, plan)
    records = model_records(text)
    require(len(records["coverage"]) == 1, "expected one combined AKV coverage record")
    coverage = {k: int(v) for k, v in records["coverage"][0].items()}
    require(all(v >= 0 for v in coverage.values()), "negative coverage count")
    phases = Counter(e["mode"] for e in records["execution"])
    require(set(phases) <= {"decode", "prefill"}, "unknown execution phase")
    require(coverage["executed_ops"] == len(records["execution"]) == coverage["executed_v2"],
            "AKV execution count mismatch")
    require(coverage["executed_v1"] == 0, "unexpected AKV v1 execution")
    for phase in ("decode", "prefill"):
        require(coverage[f"executed_{phase}"] == phases[phase], "phase count mismatch")
    fallback = records["fallback_by_phase"]
    reasons = Counter()
    for key, count in fallback.items():
        phase, reason = key.split(":")
        require(phase in ("decode", "prefill"), "unknown fallback phase")
        require(f"fallback_{reason}" in coverage, "unaccounted fallback reason")
        reasons[reason] += count
    for key, count in coverage.items():
        if key.startswith("fallback_"):
            require(count == reasons[key.removeprefix("fallback_")], "fallback count mismatch")
    require(coverage["candidate_ops"] == coverage["executed_ops"] + sum(fallback.values()),
            "AKV candidates do not equal executions plus fallbacks")

    qbs_exec = [r for r in records["qbs"] if r["record"] == "GGML_RISCV_QBS_EXEC"]
    qbs_cover = [r for r in records["qbs"] if r["record"] == "GGML_RISCV_QBS_COVERAGE"]
    for group in (qbs_exec, qbs_cover):
        require(group and len({r["type"] for r in group}) == len(group),
                "missing or duplicate QBS profile records")
    require({r["type"] for r in qbs_exec} == {r["type"] for r in qbs_cover},
            "QBS coverage/execution profiles disagree")
    for record in qbs_cover:
        require(int(record["candidate_tensors"]) == int(record["selected_tensors"]) > 0,
                "QBS tensor selection incomplete")
        require(int(record["candidate_elements"]) == int(record["selected_elements"]) > 0,
                "QBS element selection incomplete")
        require(all(int(v) == 0 for k, v in record.items() if k.startswith("fallback_")),
                "unexpected QBS fallback")
    for record in qbs_exec:
        require(int(record["native_qbexec"]) > 0 and int(record["emulated_commands"]) == 0,
                "QBS did not use native instructions")
    prompt_counts = re.findall(r"^.*prompt eval time.*?/\s*([0-9]+)\s*tokens.*$",
                               text, re.MULTILINE)
    require(len(prompt_counts) == 3 and len(set(prompt_counts)) == 1, "prompt counts disagree")
    summary = {
        **admission, "prompt_tokens": int(prompt_counts[0]),
        "candidate_ops": coverage["candidate_ops"],
        "prefill_executed": phases["prefill"],
        "prefill_fallback": sum(n for key, n in fallback.items() if key.startswith("prefill:")),
        "native_qbexec": sum(int(r["native_qbexec"]) for r in qbs_exec),
        "qbs_rvv_max_abs": number(text, "QBS_RVV_LOGITS_MAX_ABS"),
        "qbs_rvv_max_kl": number(text, "QBS_RVV_LOGITS_MAX_KL"),
        "qbs_rvv_min_cosine": number(text, "QBS_RVV_LOGITS_MIN_COSINE"),
        "qbs_rvv_min_top5_overlap": number(text, "QBS_RVV_LOGITS_MIN_TOP5_OVERLAP"),
        "akv_qbs_max_abs": number(text, "AKV_LOGITS_MAX_ABS"),
        "token_equal": True,
    }
    return summary, records


def collect(root):
    state = json.loads((root / "status.json").read_text())
    plans = {p["name"]: p for p in json.loads((root / "plan.json").read_text())}
    require(state["status"] == "PASS" and state["return_code"] == 0, "cohort is not complete PASS")
    require(set(state["cases"]) == set(plans) == set(CASES), "wrong or incomplete cohort")
    require(sha(root / "llama-simple") == state["llama_binary_sha256"], "guest binary hash changed")
    rows, details = [], {}
    hashes = {name: sha(root / name) for name in ("status.json", "plan.json", "llama-simple")}
    for name in CASES:
        stage = json.loads((root / name / "stage.json").read_text())
        require(stage == state["cases"][name], f"stage and cohort status disagree: {name}")
        require(stage["status"] == "PASS" and stage["return_code"] == 0, f"case failed: {name}")
        env, plan = stage["environment"], plans[name]
        require(env["AKV_MODEL_D256"] == str(int(plan["enabled"])) and
                env["AKV_MODEL_TOKENS"] == "3" and env["AKV_MODEL_PROMPT"] == plan["prompt"],
                f"case configuration disagrees: {name}")
        text = (root / name / "qemu.log").read_text(errors="replace")
        summary, records = validate_log(text, plan)
        for key in ("decode_executed", "decode_fallback", "active_kv", "execution"):
            require(summary[key] == stage[key], f"log and stage disagree: {name}/{key}")
        rows.append({"case": name, "model": plan["model"]["id"], "status": "PASS",
                     "d256_enabled": plan["enabled"], **summary})
        details[name] = records
        for file in ("qemu.log", "stage.json", "worker.launcher.sh", "manifest.txt"):
            relative = f"{name}/{file}"
            hashes[relative] = sha(root / relative)
    return {"status": "PASS", "source_run": str(root), "run_revision": state["revision"],
            "started_at": state["started_at"], "finished_at": state["finished_at"],
            "binary_sha256": state["llama_binary_sha256"], "qemu_sha256": state["qemu_sha256"],
            "adapter_sha256": state["llama_adapter_sha256"], "source_sha256": hashes,
            "cases": rows, "records": details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = collect(args.run_root.resolve())
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "models.json").write_text(json.dumps(result, indent=2) + "\n")
    rows = result["cases"]
    with (args.output / "models.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({**r, "active_kv": ";".join(map(str, r["active_kv"]))} for r in rows)
    print(f"PASS: {len(rows)}/{len(CASES)} model cases revalidated; {args.output}")


if __name__ == "__main__":
    main()

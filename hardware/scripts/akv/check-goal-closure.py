#!/usr/bin/env python3

"""Audit QBS+AKV model, fallback, RTL, traffic, and regression evidence."""

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = Path(__file__).with_name("goal-closure-manifest.json")
FALLBACK_FIELDS = (
    "fallback_runtime", "fallback_capability", "fallback_threading",
    "fallback_feature", "fallback_shape", "fallback_layout", "fallback_mask",
)
QBS_FALLBACK_PREFIX = "fallback_"
AKV_PERF_PREFIX = "[AKV_PERF] "


class ClosureError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ClosureError(message)


def integer(mapping, key):
    require(key in mapping, f"missing field {key}")
    return int(mapping[key])


def resolve(path):
    result = Path(path)
    return result if result.is_absolute() else REPO_ROOT / result


def read_json(path):
    path = resolve(path)
    require(path.is_file(), f"missing JSON artifact: {path}")
    return json.loads(path.read_text())


def read_one_csv(path):
    path = resolve(path)
    require(path.is_file(), f"missing CSV artifact: {path}")
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 1, f"expected one data row in {path}, found {len(rows)}")
    return rows[0]


def file_sha256(path):
    digest = hashlib.sha256()
    with resolve(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_conf(path):
    result = {}
    for line in resolve(path).read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def parse_key_values(line):
    return {key: int(value) for key, value in re.findall(r"(\w+)=(-?\d+)", line)}


def check_shape_matrix(spec):
    summary = read_json(spec["summary"])
    cases = {
        f"akv-v2/derived-real/d{dimension}-g{gqa}-kv{kv}"
        for dimension in spec["head_dims"]
        for gqa in spec["gqa_rows"]
        for kv in spec["kv_lengths"]
    }
    modes = set(spec["modes"])
    expected_pairs = {(case, mode) for case in cases for mode in modes}
    actual_pairs = {(row["case"], row["mode"]) for row in summary["results"]}
    require(summary["status"] == "completed", "AKV shape matrix is not complete")
    require(set(summary["cases"]) == cases, "AKV shape matrix case set differs from manifest")
    require(set(summary["modes"]) == modes, "AKV shape matrix mode set differs from manifest")
    require(actual_pairs == expected_pairs, "AKV shape matrix has missing or duplicate case/mode pairs")
    require(integer(summary, "expected_results") == len(expected_pairs), "AKV expected result count is wrong")
    require(integer(summary, "completed_results") == len(expected_pairs), "AKV completed result count is wrong")
    require(integer(summary, "passed") == len(expected_pairs), "AKV shape matrix contains a failure")
    require(integer(summary, "failed") == 0 and integer(summary, "remaining") == 0,
            "AKV shape matrix is not a zero-failure terminal run")
    require(all(row["passed"] and row["build_rc"] == 0 and row["run_rc"] == 0
                for row in summary["results"]), "AKV shape matrix has a non-passing record")
    return {
        "cases": len(cases), "modes": len(modes), "results": len(expected_pairs),
        "status": "PASS", "artifact": spec["summary"],
    }


def check_qbs_profile(profile, coverage, execution):
    require(profile in coverage, f"model trace lacks QBS coverage for {profile}")
    require(profile in execution, f"model trace lacks QBS execution for {profile}")
    cov = coverage[profile]
    exe = execution[profile]
    require(integer(cov, "candidate_tensors") == integer(cov, "selected_tensors"),
            f"{profile} candidate/selected tensor mismatch")
    require(integer(cov, "candidate_elements") == integer(cov, "selected_elements"),
            f"{profile} candidate/selected element mismatch")
    for key, value in cov.items():
        if key.startswith(QBS_FALLBACK_PREFIX):
            require(int(value) == 0, f"{profile} unexpectedly used {key}")
    require(integer(exe, "native_qbexec") > 0, f"{profile} issued no native QBS command")
    require(integer(exe, "emulated_commands") == 0, f"{profile} used emulated QBS commands")
    require(integer(exe, "dot_elements") == integer(exe, "command_dot_elements"),
            f"{profile} command work differs from high-level dot work")


def check_model(spec):
    summary = read_json(spec["summary"])
    provenance = summary["provenance"]
    require(provenance["tool"]["sha256"] ==
            file_sha256("hardware/scripts/akv/summarize-model-closure.py"),
            f"{spec['name']} summary was produced by a different summarizer")
    require(provenance["qbs_abi"]["sha256"] == file_sha256("config/qbs_abi.json"),
            f"{spec['name']} summary used a different QBS ABI")
    manifest = provenance["run_manifest"]
    functional = summary["functional"]
    require(manifest["MODEL_GUEST_PATH"] == spec["model_guest_path"],
            f"{spec['name']} model path differs from manifest")
    require(manifest["MODEL_TOKENS"] == "2", f"{spec['name']} is not the fixed two-token run")
    require(integer(functional, "guest_exit") == 0, f"{spec['name']} guest failed")
    require(functional["output_equal"] is True, f"{spec['name']} QBS+AKV output differs from QBS")
    require(str(functional["logits_top1_equal"]) == "1", f"{spec['name']} AKV Top-1 differs")
    require(functional["qbs_rvv"]["QBS_RVV_TOKEN_OUTPUT_EQUAL"] == "1",
            f"{spec['name']} QBS/RVV token output differs")
    require(functional["qbs_rvv"]["QBS_RVV_LOGITS_TOP1_EQUAL"] == "1",
            f"{spec['name']} QBS/RVV Top-1 differs")
    require(summary["graphs"] == {"prefill": 1, "decode": 1},
            f"{spec['name']} did not record one Prefill and one Decode graph")
    qbs = summary["qbs"]
    require(integer(qbs, "nodes") == spec["qbs_nodes"], f"{spec['name']} QBS node count changed")
    require(set(qbs["coverage"]) == set(spec["qbs_profiles"]),
            f"{spec['name']} QBS profile set changed")
    for profile in spec["qbs_profiles"]:
        check_qbs_profile(profile, qbs["coverage"], qbs["execution"])

    akv = summary["akv_v2"]
    coverage = akv["coverage"]
    candidate = integer(coverage, "candidate_ops")
    executed = integer(coverage, "executed_ops")
    fallbacks = sum(integer(coverage, key) for key in FALLBACK_FIELDS)
    require(candidate == spec["akv_candidate_ops"], f"{spec['name']} AKV candidate count changed")
    require(executed == spec["akv_executed_ops"], f"{spec['name']} AKV execution count changed")
    require(integer(coverage, "fallback_shape") == spec["akv_fallback_shape"],
            f"{spec['name']} AKV shape fallback count changed")
    require(candidate == executed + fallbacks,
            f"{spec['name']} AKV execution plus fallback does not cover every candidate")
    require(integer(akv, "calls") == executed, f"{spec['name']} AKV call count differs from coverage")
    require(integer(coverage, "attention_macs") == integer(akv, "attention_macs"),
            f"{spec['name']} AKV MAC count differs from coverage")
    if "akv_shape" in spec:
        require(len(akv["shapes"]) == 1, f"{spec['name']} expected one Decode AKV shape")
        shape = akv["shapes"][0]
        for key, value in spec["akv_shape"].items():
            require(integer(shape, key) == value, f"{spec['name']} AKV {key} changed")
        require(integer(akv, "query_payload_bytes") > 0 and integer(akv, "kv_payload_bytes") > 0,
                f"{spec['name']} executed AKV without dynamic Q/KV payload")
    else:
        require(not akv["shapes"] and integer(akv, "attention_macs") == 0,
                f"{spec['name']} unsupported AKV shape partially executed")

    return {
        "model": spec["name"], "qbs_profiles": "/".join(spec["qbs_profiles"]),
        "qbs_nodes": integer(qbs, "nodes"), "qbs_weight_bytes": integer(qbs, "weight_payload_bytes"),
        "qbs_activation_bytes": integer(qbs, "per_operation_quantized_activation_bytes"),
        "akv_candidates": candidate, "akv_executed": executed,
        "akv_fallbacks": fallbacks, "akv_q_bytes": integer(akv, "query_payload_bytes"),
        "akv_kv_bytes": integer(akv, "kv_payload_bytes"), "status": "PASS",
        "artifact": spec["summary"],
    }


def check_lifetime(spec):
    model = read_json(spec["summary"])
    rtl = read_json(spec["controlled_rtl"])
    require(model["provenance"]["tool"]["sha256"] ==
            file_sha256("hardware/scripts/qbs/compare_activation_lifetime_runs.py"),
            "QBS lifetime summary was produced by a different comparator")
    require(model["semantic_command_stream_equal"] is True,
            "cross-operator QBS changed the semantic command work")
    baseline = model["baseline"]
    optimized = model["cross_operator"]
    eliminated = model["eliminated_quantizations"]
    quantizations_saved = integer(baseline, "quantizations") - integer(optimized, "quantizations")
    activation_saved = integer(baseline, "activation_bytes") - integer(optimized, "activation_bytes")
    input_saved = (integer(baseline, "quantization_input_bytes") -
                   integer(optimized, "quantization_input_bytes"))
    require(quantizations_saved == integer(optimized, "quantizations_eliminated") == len(eliminated),
            "cross-operator quantization count is inconsistent")
    require(activation_saved == integer(optimized, "activation_bytes_eliminated") ==
            sum(integer(row, "quantized_bytes") for row in eliminated),
            "cross-operator activation-byte count is inconsistent")
    require(input_saved == integer(optimized, "quantization_input_bytes_eliminated") ==
            sum(integer(row, "input_bytes") for row in eliminated),
            "cross-operator F32 input-byte count is inconsistent")
    identity_fields = {
        "activation_profile", "family", "graph_epoch", "input_bytes", "input_elements",
        "k", "m", "n", "op", "quantized_bytes", "weight", "weight_type",
    }
    require(all(identity_fields <= set(row) for row in eliminated),
            "cross-operator evidence lacks strict identity/lifetime fields")
    require(set(model["families"]) == {"attention_qkv", "ffn_gate_up"},
            "cross-operator evidence contains an unexpected reuse family")
    require(sum(integer(row, "removable_quantizations") for row in model["families"].values()) ==
            quantizations_saved, "reuse-family totals differ from eliminated quantizations")

    require(rtl["status"] == "PASS", "controlled QBS cross-operator RTL run failed")
    require(integer(rtl, "baseline_quantizations") - integer(rtl, "cross_op_quantizations") ==
            integer(rtl, "quantizations_eliminated"), "controlled RTL quantization count is inconsistent")
    require(integer(rtl, "quantization_input_bytes_saved") + integer(rtl, "activation_axi_bytes_saved") ==
            integer(rtl, "logical_read_bytes_saved"), "controlled RTL byte accounting is inconsistent")
    require(integer(rtl, "baseline_cycles") > integer(rtl, "cross_op_cycles"),
            "controlled RTL cross-operator reuse did not reduce cycles")
    require(float(rtl["cycle_reduction"]) > 0.0 and float(rtl["speedup"]) > 1.0,
            "controlled RTL speedup fields are invalid")
    return {
        "model_quantizations_before": integer(baseline, "quantizations"),
        "model_quantizations_after": integer(optimized, "quantizations"),
        "model_quantizations_saved": quantizations_saved,
        "model_f32_bytes_saved": input_saved,
        "model_q8_bytes_saved": activation_saved,
        "rtl_quantizations_before": integer(rtl, "baseline_quantizations"),
        "rtl_quantizations_after": integer(rtl, "cross_op_quantizations"),
        "rtl_f32_bytes_saved": integer(rtl, "quantization_input_bytes_saved"),
        "rtl_q8_bytes_saved": integer(rtl, "activation_axi_bytes_saved"),
        "rtl_cycles_before": integer(rtl, "baseline_cycles"),
        "rtl_cycles_after": integer(rtl, "cross_op_cycles"),
        "rtl_speedup": float(rtl["speedup"]), "status": "PASS",
    }


def check_qbs_representative(spec):
    baseline = read_one_csv(spec["baseline"])
    current = read_one_csv(spec["current"])
    require(baseline["case"] == current["case"], f"{spec['name']} case mismatch")
    for row, label in ((baseline, "baseline"), (current, "current")):
        require(row["result"] == "PASS", f"{spec['name']} {label} failed")
        require(integer(row, "mismatches") == 0, f"{spec['name']} {label} has mismatches")
    baseline_cycles = integer(baseline, "timed_cycles")
    current_cycles = integer(current, "timed_cycles")
    regression = current_cycles / baseline_cycles - 1.0
    require(regression <= float(spec["max_regression"]),
            f"{spec['name']} regressed {regression:.2%}, limit is {spec['max_regression']:.2%}")
    console = resolve(spec["current_console"]).read_text(errors="replace")
    expected_context = "activation_context=1" if spec["required_context"] else "activation_context=0"
    require(expected_context in console, f"{spec['name']} did not run the required context mode")
    perf = read_one_csv(spec["current_perf"])
    if spec["required_context"]:
        require(integer(perf, "context_fill_count") == 1,
                f"{spec['name']} must contain one context fill")
        require(integer(perf, "context_reuse_count") == integer(current, "tiles") - 1,
                f"{spec['name']} context reuse count differs from tile count")
        require(integer(perf, "context_read_bytes") == integer(perf, "activation_axi_bytes_saved") > 0,
                f"{spec['name']} context byte accounting is inconsistent")
    else:
        for key in ("context_fill_count", "context_reuse_count", "context_read_bytes",
                    "activation_axi_bytes_saved"):
            require(integer(perf, key) == 0, f"{spec['name']} unexpectedly used {key}")
    return {
        "point": spec["name"], "baseline_cycles": baseline_cycles,
        "current_cycles": current_cycles, "regression": regression,
        "context": int(spec["required_context"]), "status": "PASS",
    }


def check_qbs_rtl_tests(specs):
    rows = []
    for spec in specs:
        path = resolve(spec["log"])
        require(path.is_file(), f"missing QBS RTL log: {path}")
        text = path.read_text(errors="replace")
        require(spec["marker"] in text, f"QBS RTL test {spec['name']} lacks PASS marker")
        require("Error:" not in text and "Fatal:" not in text,
                f"QBS RTL test {spec['name']} contains an error")
        rows.append({"test": spec["name"], "status": "PASS", "artifact": spec["log"]})
    return rows


def check_ordinary_rvv(spec):
    text = resolve(spec["log"]).read_text(errors="replace")
    pattern = re.compile(rf"LLAMA_OPERATOR {re.escape(spec['case'])} PASS cycles=(\d+) mismatches=0")
    match = pattern.search(text)
    require(match is not None, "ordinary RVV representative point did not pass")
    require("Core Test *** SUCCESS ***" in text, "ordinary RVV representative lacks core success")
    return {"case": spec["case"], "cycles": int(match.group(1)), "status": "PASS"}


def check_akv_rtl(spec):
    conf = parse_conf(spec["run_conf"])
    require(conf.get("case_id") == spec["case"], f"{spec['case']} run.conf case mismatch")
    require(int(conf.get("effective_kv", -1)) == spec["kv_length"],
            f"{spec['case']} run.conf KV mismatch")
    text = resolve(spec["log"]).read_text(errors="replace")
    final_pattern = re.compile(
        rf"LLAMA_OPERATOR {re.escape(spec['case'])}/akv_v2 PASS cycles=(\d+) mismatches=0")
    final = final_pattern.search(text)
    require(final is not None and "Core Test *** SUCCESS ***" in text,
            f"{spec['case']} RTL result is not a zero-mismatch PASS")
    rows = [parse_key_values(line) for line in text.splitlines()
            if line.startswith(AKV_PERF_PREFIX)]
    require(rows, f"{spec['case']} has no AKV_PERF records")
    sums = {key: sum(row.get(key, 0) for row in rows) for key in {
        key for row in rows for key in row
    }}
    for key in ("fault", "validation_fault", "read_fault", "v2_rejected"):
        require(sums.get(key, 0) == 0, f"{spec['case']} has nonzero {key}")
    require(sums.get("success", 0) == len(rows), f"{spec['case']} has an unsuccessful command")

    dimension = spec["head_dim"]
    gqa = spec["gqa_rows"]
    kv = spec["kv_length"]
    tiles = math.ceil(kv / 64)
    sharing = 1 if spec["shared_k_across_gqa"] else gqa
    expected = {
        "v2_full": 1,
        "v2_refill": tiles - 1,
        "v2_row_load": kv * sharing,
        "v2_column_load": tiles * dimension * sharing,
        "release": 1,
        "q_external_bytes": gqa * dimension * 2,
        "kv_external_bytes": kv * dimension * 4,
        "replay_bytes": kv * dimension * sharing * 4,
    }
    for key, value in expected.items():
        require(sums.get(key, 0) == value,
                f"{spec['case']} {key}={sums.get(key, 0)}, expected {value}")
    expected_commands = sum(expected[key] for key in
                            ("v2_full", "v2_refill", "v2_row_load", "v2_column_load", "release"))
    require(len(rows) == expected_commands, f"{spec['case']} command count is inconsistent")
    expected_payload = expected["q_external_bytes"] + expected["kv_external_bytes"] + 64
    require(sums.get("read_payload_bytes", 0) == expected_payload,
            f"{spec['case']} external read payload is inconsistent")
    return {
        "case": spec["case"], "head_dim": dimension, "gqa_rows": gqa,
        "kv_length": kv, "cycles": int(final.group(1)), "commands": len(rows),
        "q_bytes": expected["q_external_bytes"], "kv_bytes": expected["kv_external_bytes"],
        "read_payload_bytes": expected_payload, "replay_bytes": expected["replay_bytes"],
        "status": "PASS", "artifact": spec["log"],
    }


def read_projection(path):
    with resolve(path).open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    decode = [row for row in rows if row["phase"] == "decode"]
    require(decode, "Qwen cycle projection lacks Decode rows")
    total = sum(int(row["projected_cycles"]) for row in decode)
    require(abs(sum(float(row["share_of_calibrated_cycles"]) for row in decode) - 1.0) < 1e-9,
            "Qwen Decode cycle shares do not sum to one")
    return [{
        "category": row["category"], "instances": int(row["instances"]),
        "projected_cycles": int(row["projected_cycles"]),
        "share": float(row["share_of_calibrated_cycles"]), "decode_total": total,
    } for row in decode]


def check_projection_ablation(no_lifetime_path, lifetime_path):
    baseline = read_projection(no_lifetime_path)
    optimized = read_projection(lifetime_path)
    baseline_by_category = {row["category"]: row for row in baseline}
    optimized_by_category = {row["category"]: row for row in optimized}
    require(set(baseline_by_category) == set(optimized_by_category),
            "Qwen lifetime ablation changed the Decode category set")
    for category, before in baseline_by_category.items():
        after = optimized_by_category[category]
        require(before["instances"] == after["instances"],
                f"Qwen lifetime ablation changed {category} instance count")
        if category != "qbs":
            require(before["projected_cycles"] == after["projected_cycles"],
                    f"Qwen lifetime ablation changed non-QBS category {category}")
    before_total = baseline[0]["decode_total"]
    after_total = optimized[0]["decode_total"]
    cycles_saved = before_total - after_total
    require(cycles_saved > 0, "Qwen lifetime reuse did not reduce Decode cycles")
    require(baseline_by_category["qbs"]["projected_cycles"] -
            optimized_by_category["qbs"]["projected_cycles"] == cycles_saved,
            "Qwen lifetime cycle saving is not isolated to QBS")
    return {
        "cycles_before": before_total,
        "cycles_after": after_total,
        "cycles_saved": cycles_saved,
        "cycle_reduction": cycles_saved / before_total,
        "speedup": before_total / after_total,
    }


def build_ablation_rows(lifetime, projection_ablation, spec):
    return [
        {
            "scope": "controlled_qbs_chain3_rtl", "configuration": "per_operation",
            "cycles": lifetime["rtl_cycles_before"],
            "quantizations": lifetime["rtl_quantizations_before"],
            "cycles_saved": 0, "f32_input_bytes_saved": 0,
            "q8_activation_bytes_saved": 0, "speedup": 1.0,
            "evidence": spec["controlled_rtl"],
        },
        {
            "scope": "controlled_qbs_chain3_rtl", "configuration": "cross_operator",
            "cycles": lifetime["rtl_cycles_after"],
            "quantizations": lifetime["rtl_quantizations_after"],
            "cycles_saved": lifetime["rtl_cycles_before"] - lifetime["rtl_cycles_after"],
            "f32_input_bytes_saved": lifetime["rtl_f32_bytes_saved"],
            "q8_activation_bytes_saved": lifetime["rtl_q8_bytes_saved"],
            "speedup": lifetime["rtl_speedup"], "evidence": spec["controlled_rtl"],
        },
        {
            "scope": "qwen_decode_projection", "configuration": "per_operation",
            "cycles": projection_ablation["cycles_before"],
            "quantizations": lifetime["model_quantizations_before"],
            "cycles_saved": 0, "f32_input_bytes_saved": 0,
            "q8_activation_bytes_saved": 0, "speedup": 1.0,
            "evidence": "matched no-lifetime Decode projection",
        },
        {
            "scope": "qwen_decode_projection", "configuration": "cross_operator",
            "cycles": projection_ablation["cycles_after"],
            "quantizations": lifetime["model_quantizations_after"],
            "cycles_saved": projection_ablation["cycles_saved"],
            "f32_input_bytes_saved": lifetime["model_f32_bytes_saved"],
            "q8_activation_bytes_saved": lifetime["model_q8_bytes_saved"],
            "speedup": projection_ablation["speedup"], "evidence": spec["summary"],
        },
    ]


def build_support_rows(abi, shape_spec, models, qbs_tests, rvv):
    model_profiles = {}
    for model in models:
        for profile in model["qbs_profiles"].split("/"):
            model_profiles.setdefault(profile, []).append(model["model"])
    profile_test = next(row for row in qbs_tests if row["test"] == "profiles")
    rows = []
    for profile, description in abi["weight_profiles"].items():
        trace_name = "Q8_0" if profile == "Q8_0_WEIGHT" else profile
        observed = ";".join(model_profiles.get(trace_name, [])) or "not observed in selected models"
        rows.append({
            "mechanism": "QBS", "capability": f"weight_profile:{profile}",
            "disposition": "implemented", "verified_scope": "RTL profile regression",
            "boundary": f"activation={','.join(description['activation_profiles'])}",
            "model_evidence": observed, "evidence": profile_test["artifact"],
        })
    context = abi["activation_context"]
    rows.append({
        "mechanism": "QBS", "capability": "activation_context",
        "disposition": "implemented", "verified_scope": "Qwen trace plus controlled RTL",
        "boundary": (
            f"count={context['count']}; M<={context['max_m']}; "
            f"K_blocks<={context['max_k_blocks']}; "
            f"profiles={','.join(context['activation_profiles'])}; "
            f"layouts={','.join(context['activation_layouts'])}"
        ),
        "model_evidence": "Qwen attention_qkv and ffn_gate_up",
        "evidence": "hardware/qbs_cross_op_rtl_ablation_20260831/summary.json",
    })
    rows.append({
        "mechanism": "AKV-v2", "capability": "tested_shape_matrix",
        "disposition": "admitted", "verified_scope": "scalar-reference and RVV functional matrix",
        "boundary": (
            f"D={'/'.join(map(str, shape_spec['head_dims']))}; "
            f"GQA={'/'.join(map(str, shape_spec['gqa_rows']))}; "
            f"KV={'/'.join(map(str, shape_spec['kv_lengths']))}"
        ),
        "model_evidence": "Qwen D128/G6; TinyLlama D64/G8",
        "evidence": shape_spec["summary"],
    })
    smol = next(model for model in models if model["model"].startswith("SmolLM2"))
    rows.append({
        "mechanism": "AKV-v2", "capability": "GQA=3",
        "disposition": "ordinary_RVV_fallback", "verified_scope": "real model Prefill+Decode",
        "boundary": "unsupported GQA ratio; no partial AKV execution",
        "model_evidence": f"{smol['akv_candidates']} candidates, {smol['akv_fallbacks']} fallbacks",
        "evidence": smol["artifact"],
    })
    phase_fallback_models = [model for model in models if model["akv_executed"] > 0]
    rows.append({
        "mechanism": "AKV-v2", "capability": "Prefill",
        "disposition": "ordinary_RVV_fallback", "verified_scope": "real model execution",
        "boundary": "current AKV-v2 profile admits Decode only",
        "model_evidence": ";".join(
            f"{model['model']}:{model['akv_fallbacks']}" for model in phase_fallback_models),
        "evidence": ";".join(model["artifact"] for model in phase_fallback_models),
    })
    rows.append({
        "mechanism": "RVV", "capability": "fallback_path",
        "disposition": "preserved", "verified_scope": "representative RTL leaf",
        "boundary": "used whenever QBS/AKV capability or full contract is not admitted",
        "model_evidence": f"{rvv['case']} zero-mismatch PASS",
        "evidence": "hardware/qbs_akv_final_regress_rvv/decode_attention_core_rvv_kv16_20260831_145528/ara.log",
    })
    return rows


def write_csv(path, rows, fields):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path,
                        default=REPO_ROOT / "hardware/qbs_akv_model_closure_20260831")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    require(manifest["schema_version"] == 1, "unsupported closure manifest schema")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    abi = read_json(manifest["qbs_abi"])
    require(abi["architecture_version"] == 2, "closure expects QBS ABI v2")
    require(len(abi["weight_profiles"]) == 9, "closure expects all nine QBS weight profiles")
    shape = check_shape_matrix(manifest["shape_matrix"])
    models = [check_model(spec) for spec in manifest["models"]]
    lifetime = check_lifetime(manifest["qbs_lifetime"])
    qbs_points = [check_qbs_representative(spec) for spec in manifest["qbs_representative_points"]]
    qbs_tests = check_qbs_rtl_tests(manifest["qbs_rtl_tests"])
    rvv = check_ordinary_rvv(manifest["ordinary_rvv"])
    akv_points = [check_akv_rtl(spec) for spec in manifest["akv_rtl_points"]]
    qwen_spec = next(spec for spec in manifest["models"] if "cycle_projection" in spec)
    projection = read_projection(qwen_spec["cycle_projection"])
    projection_ablation = check_projection_ablation(
        qwen_spec["cycle_projection_no_lifetime"], qwen_spec["cycle_projection"])
    ablation = build_ablation_rows(lifetime, projection_ablation, manifest["qbs_lifetime"])
    support = build_support_rows(abi, manifest["shape_matrix"], models, qbs_tests, rvv)

    artifact_paths = [manifest["qbs_abi"], manifest["shape_matrix"]["summary"],
                      manifest["qbs_lifetime"]["summary"],
                      manifest["qbs_lifetime"]["controlled_rtl"],
                      manifest["ordinary_rvv"]["log"]]
    artifact_paths += [spec["summary"] for spec in manifest["models"]]
    artifact_paths += [spec["cycle_projection"] for spec in manifest["models"]
                       if "cycle_projection" in spec]
    artifact_paths += [spec["cycle_projection_no_lifetime"] for spec in manifest["models"]
                       if "cycle_projection_no_lifetime" in spec]
    artifact_paths += [spec[key] for spec in manifest["qbs_representative_points"]
                       for key in ("baseline", "current", "current_perf", "current_console")]
    artifact_paths += [spec["log"] for spec in manifest["qbs_rtl_tests"]]
    artifact_paths += [spec[key] for spec in manifest["akv_rtl_points"]
                       for key in ("run_conf", "log")]
    artifacts = [{"path": path, "sha256": file_sha256(path)}
                 for path in dict.fromkeys(artifact_paths)]

    summary = {
        "schema_version": 1,
        "status": "PASS",
        "scope": "functional, numerical, coverage, traffic, and RTL-cycle closure; no physical closure",
        "qbs_abi": {"architecture_version": 2, "weight_profiles": list(abi["weight_profiles"])},
        "akv_shape_matrix": shape,
        "models": models,
        "qbs_activation_lifetime": lifetime,
        "qbs_representative_points": qbs_points,
        "qbs_rtl_tests": qbs_tests,
        "ordinary_rvv": rvv,
        "akv_rtl_points": akv_points,
        "decode_cycle_projection": projection,
        "qbs_lifetime_ablation": projection_ablation,
        "support_matrix": support,
        "artifacts": artifacts,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    write_csv(output / "models.csv", models, list(models[0]))
    write_csv(output / "qbs_regression.csv", qbs_points, list(qbs_points[0]))
    write_csv(output / "akv_rtl_points.csv", akv_points, list(akv_points[0]))
    write_csv(output / "decode_cycle_projection.csv", projection, list(projection[0]))
    write_csv(output / "ablation.csv", ablation, list(ablation[0]))
    write_csv(output / "support_matrix.csv", support, list(support[0]))
    write_csv(output / "artifacts.csv", artifacts, ["path", "sha256"])

    readme = [
        "# QBS + AKV Model Closure", "",
        "Status: **PASS**", "",
        "This index audits functional, numerical, coverage, command, logical-traffic,",
        "and representative RTL-cycle evidence. It does not contain synthesis, PPA,",
        "place-and-route, or full-model RTL timing claims.", "",
        f"- AKV shape matrix: {shape['results']}/{shape['results']} PASS.",
        f"- QBS profiles: {len(abi['weight_profiles'])} RTL profiles covered.",
        f"- Real models: {len(models)} fixed-prompt Prefill+Decode executions.",
        f"- Representative AKV RTL points: {len(akv_points)} zero-mismatch PASS.",
        f"- QBS cross-operator model quantizations: "
        f"{lifetime['model_quantizations_before']} -> {lifetime['model_quantizations_after']}.",
        f"- Qwen Decode projection: {projection_ablation['cycles_before']} -> "
        f"{projection_ablation['cycles_after']} cycles.",
        "- `ablation.csv` records controlled-RTL and model-projection deltas.",
        "- `support_matrix.csv` separates accelerated, fallback, and preserved paths.",
        "", "Run:", "",
        "```bash",
        "python3 hardware/scripts/akv/check-goal-closure.py",
        "```", "",
        "The manifest binds every conclusion to a relative artifact path; `artifacts.csv`",
        "records SHA-256 hashes of all consumed raw evidence.",
    ]
    (output / "README.md").write_text("\n".join(readme) + "\n")
    print(f"PASS: wrote {output}")


if __name__ == "__main__":
    main()

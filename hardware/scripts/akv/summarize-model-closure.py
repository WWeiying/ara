#!/usr/bin/env python3

"""Summarize one combined QBS + AKV-v2 llama.cpp model run.

Dynamic coverage is measured directly from the guest log. Cycle attribution is
an explicitly labelled projection that weights representative RTL measurements
by the dynamic shapes. QEMU wall time is never used as a hardware-cycle proxy.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


FIELD_RE = re.compile(r"([A-Za-z0-9_]+)=([^\s]+)")
OPERATOR_RE = re.compile(
    r"LLAMA_OPERATOR\s+(\S+)\s+(PASS|FAIL)\s+cycles=(\d+)\s+mismatches=(\d+)"
)
SUPPORTED_QBS_TYPES = {
    "Q2_K",
    "Q3_K",
    "Q4_K",
    "Q5_K",
    "Q6_K",
    "Q4_0",
    "Q5_0",
    "Q8_0",
    "IQ4_NL",
}
SUPPORTED_QBS_OPS = {"MUL_MAT", "MUL_MAT_ID"}
PROJECTION_METHOD_VERSION = 2
QBS_ABI_PATH = Path(__file__).resolve().parents[3] / "config/qbs_abi.json"
QBS_TRACE_TO_ABI_PROFILE = {"Q8_0": "Q8_0_WEIGHT"}
F16_BYTES = 2
F32_BYTES = 4
AKV_PREFILL_QUERY_BLOCK_TOKENS = 64
AKV_PREFILL_CALIBRATION_SCHEMA_MIN = 6
AKV_PREFILL_STRICT_COUNTER_FIELDS_MIN = 14
AKV_PREFILL_RETAINED_STRATEGY = "akv_qblock64_q2_panel4_kv_outer"
AKV_PREFILL_SHAPE_FIELDS = (
    "head_dim",
    "query_tokens",
    "past_tokens",
    "query_heads",
    "kv_heads",
    "gqa_rows",
    "kv_capacity",
)
NUMERICAL_METRIC_SUFFIXES = (
    "LOGITS_RECORDS",
    "LOGITS_COMPARABLE_RECORDS",
    "LOGITS_MAX_ABS",
    "LOGITS_MAX_REL",
    "LOGITS_MEAN_ABS",
    "LOGITS_MEAN_RMSE",
    "LOGITS_MEAN_KL",
    "LOGITS_MEAN_COSINE",
    "LOGITS_TOP5_OVERLAP",
    "LOGITS_MAX_KL",
    "LOGITS_MIN_COSINE",
    "LOGITS_MIN_TOP5_OVERLAP",
    "LOGITS_TOP1_EQUAL",
)


def load_qbs_abi(path: Path = QBS_ABI_PATH) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("weight_profiles"), dict) or not isinstance(
        data.get("activation_profiles"), dict
    ):
        raise ValueError(f"malformed QBS ABI description: {path}")
    return data


QBS_ABI = load_qbs_abi()


def qbs_profile_geometry(profile: str, kind: str = "weight") -> tuple[int, int]:
    if kind == "weight":
        profile = QBS_TRACE_TO_ABI_PROFILE.get(profile, profile)
        profiles = QBS_ABI["weight_profiles"]
    elif kind == "activation":
        profiles = QBS_ABI["activation_profiles"]
    else:
        raise ValueError(f"unsupported QBS profile kind: {kind}")
    record = profiles.get(profile)
    if not isinstance(record, dict):
        raise ValueError(f"missing QBS {kind} profile geometry for {profile}")
    block_bytes = int(record.get("block_bytes", 0))
    block_elements = int(record.get("block_elements", 0))
    if block_bytes <= 0 or block_elements <= 0:
        raise ValueError(f"invalid QBS {kind} profile geometry for {profile}")
    return block_bytes, block_elements


def qbs_activation_profile(weight_profile: str) -> str:
    abi_profile = QBS_TRACE_TO_ABI_PROFILE.get(weight_profile, weight_profile)
    record = QBS_ABI["weight_profiles"].get(abi_profile)
    activations = record.get("activation_profiles", []) if isinstance(record, dict) else []
    if not isinstance(activations, list) or len(activations) != 1:
        raise ValueError(f"QBS weight profile {weight_profile} has no unique activation profile")
    return str(activations[0])


def blocked_payload_bytes(
    elements_per_row: int,
    rows: int,
    calls: int,
    block_bytes: int,
    block_elements: int,
    label: str,
) -> int:
    if min(elements_per_row, rows, calls, block_bytes, block_elements) <= 0:
        raise ValueError(f"{label} has a non-positive payload dimension")
    if elements_per_row % block_elements != 0:
        raise ValueError(
            f"{label} K={elements_per_row} is not divisible by block size {block_elements}"
        )
    return calls * rows * (elements_per_row // block_elements) * block_bytes


def fields(line: str) -> dict[str, str]:
    return dict(FIELD_RE.findall(line))


def integer(values: dict[str, str], key: str, default: int = 0) -> int:
    return int(values.get(key, default))


def validate_numerical_metrics(values: dict[str, str], prefix: str) -> None:
    keys = tuple(f"{prefix}_{suffix}" for suffix in NUMERICAL_METRIC_SUFFIXES)
    missing = [key for key in keys if key not in values]
    if missing:
        raise ValueError(
            f"{prefix} numerical observation lacks metrics: {', '.join(missing)}"
        )
    records = integer(values, f"{prefix}_LOGITS_RECORDS")
    comparable = integer(values, f"{prefix}_LOGITS_COMPARABLE_RECORDS")
    if records <= 0 or comparable <= 0 or comparable > records:
        raise ValueError(
            f"{prefix} has invalid logits record counts: {comparable}/{records}"
        )
    nonnegative = (
        "LOGITS_MAX_ABS",
        "LOGITS_MAX_REL",
        "LOGITS_MEAN_ABS",
        "LOGITS_MEAN_RMSE",
        "LOGITS_MEAN_KL",
        "LOGITS_MAX_KL",
    )
    for suffix in nonnegative:
        value = float(values[f"{prefix}_{suffix}"])
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"{prefix}_{suffix} is not finite and nonnegative")
    bounded = (
        "LOGITS_MEAN_COSINE",
        "LOGITS_MIN_COSINE",
        "LOGITS_TOP5_OVERLAP",
        "LOGITS_MIN_TOP5_OVERLAP",
    )
    for suffix in bounded:
        value = float(values[f"{prefix}_{suffix}"])
        lower = -1.0 if "COSINE" in suffix else 0.0
        if not math.isfinite(value) or not lower <= value <= 1.0:
            raise ValueError(f"{prefix}_{suffix} is outside [{lower:g}, 1]")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(errors="replace").splitlines():
        key, separator, value = line.partition("=")
        if separator and key:
            values[key] = value
    return values


LIFETIME_MANIFEST_KEYS = (
    "LLAMA_REVISION",
    "LLAMA_BINARY_SHA256",
    "QEMU_BINARY_SHA256",
    "MODEL_DISK_SHA256",
    "MODEL_GUEST_PATH",
    "MODEL_TOKENS",
    "MODEL_PROMPT",
)


def load_qbs_lifetime_summary(
    path: Path | None,
    model_manifest: dict[str, str],
) -> dict[str, object] | None:
    if path is None:
        return None
    if not path.is_file():
        raise ValueError(f"QBS lifetime summary does not exist: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("semantic_command_stream_equal") is not True:
        raise ValueError("QBS lifetime summary does not preserve the semantic command stream")
    baseline = data.get("baseline", {})
    optimized = data.get("cross_operator", {})
    eliminated = data.get("eliminated_quantizations", [])
    if not isinstance(baseline, dict) or not isinstance(optimized, dict) or not isinstance(eliminated, list):
        raise ValueError("QBS lifetime summary has malformed work sections")
    required_positive = (
        (baseline, "quantizations"),
        (baseline, "activation_bytes"),
        (baseline, "quantization_input_elements"),
        (optimized, "quantizations"),
        (optimized, "activation_bytes"),
        (optimized, "quantizations_eliminated"),
        (optimized, "activation_bytes_eliminated"),
        (optimized, "quantization_input_elements_eliminated"),
    )
    for section, key in required_positive:
        if int(section.get(key, 0)) <= 0:
            raise ValueError(f"QBS lifetime summary has invalid {key}")
    if int(baseline["quantizations"]) - int(optimized["quantizations"]) != int(
        optimized["quantizations_eliminated"]
    ):
        raise ValueError("QBS lifetime quantization totals are inconsistent")
    if len(eliminated) != int(optimized["quantizations_eliminated"]):
        raise ValueError("QBS lifetime detail count does not match eliminated quantizations")
    if sum(int(record["quantized_bytes"]) for record in eliminated) != int(
        optimized["activation_bytes_eliminated"]
    ):
        raise ValueError("QBS lifetime detail bytes do not match eliminated activation bytes")
    if sum(int(record["input_elements"]) for record in eliminated) != int(
        optimized["quantization_input_elements_eliminated"]
    ):
        raise ValueError("QBS lifetime detail elements do not match eliminated input elements")

    provenance = data.get("provenance", {})
    lifetime_manifest = provenance.get("manifest", {}).get("values", {}) \
        if isinstance(provenance, dict) else {}
    if not isinstance(lifetime_manifest, dict) or not lifetime_manifest:
        raise ValueError("QBS lifetime summary lacks run-manifest provenance")
    for key in LIFETIME_MANIFEST_KEYS:
        if not model_manifest.get(key) or lifetime_manifest.get(key) != model_manifest.get(key):
            raise ValueError(f"QBS lifetime run differs from model run in {key}")

    return {
        "source": {
            "path": str(path.resolve()),
            "sha256": sha256(path),
        },
        **data,
    }


def normalized_qbs_type(value: str) -> str:
    return value.upper()


def normalize_tensor_name(value: str) -> str:
    value = re.sub(r"blk[._-]?\d+", "blk.*", value, flags=re.IGNORECASE)
    value = re.sub(r"layer[._-]?\d+", "layer.*", value, flags=re.IGNORECASE)
    return value


@dataclass
class Graph:
    graph_id: int
    declared_nodes: int
    nodes: list[dict[str, str]] = field(default_factory=list)
    qbs_calls: list[dict[str, str]] = field(default_factory=list)
    akv_calls: list[dict[str, str]] = field(default_factory=list)
    closed: bool = False

    @property
    def phase(self) -> str:
        if self.akv_calls:
            modes = {call.get("mode", "decode") for call in self.akv_calls}
            if len(modes) == 1:
                return modes.pop()
            return "mixed"
        if any(call.get("mode") == "gemm" for call in self.qbs_calls):
            return "prefill"
        if any(call.get("mode") == "gemv" for call in self.qbs_calls):
            return "decode"
        return "unknown"


@dataclass
class ParsedRun:
    graphs: list[Graph]
    qbs_coverage: dict[str, dict[str, str]]
    qbs_exec: dict[str, dict[str, str]]
    akv_coverage: dict[str, str]
    logits: dict[str, str]
    qbs_rvv: dict[str, str]
    output_equal: bool
    guest_exit: int
    optimized_exit: int


def optimized_region(lines: list[str]) -> list[str]:
    marker = "AKV_TOKEN_RUN_BEGIN=QBS_AKV_V2"
    starts = [index for index, line in enumerate(lines) if line.strip() == marker]
    if len(starts) != 1:
        raise ValueError(f"expected exactly one {marker}, found {len(starts)}")
    start = starts[0] + 1
    for end in range(start, len(lines)):
        if lines[end].strip().startswith("AKV_TOKEN_RUN_EXIT=QBS_AKV_V2:"):
            return lines[start : end + 1]
    raise ValueError("optimized model run has no exit marker")


def parse_log(path: Path) -> ParsedRun:
    all_lines = [line.rstrip("\r\n") for line in path.read_text(errors="replace").splitlines()]
    lines = optimized_region(all_lines)
    graphs: list[Graph] = []
    current: Graph | None = None
    qbs_coverage: dict[str, dict[str, str]] = {}
    qbs_exec: dict[str, dict[str, str]] = {}
    akv_coverage: dict[str, str] = {}
    logits: dict[str, str] = {}
    qbs_rvv: dict[str, str] = {}
    output_equal = False
    guest_exit = -1
    optimized_exit = -1

    for line in lines:
        if line.startswith("GGML_RISCV_MODEL_GRAPH_BEGIN "):
            if current is not None:
                raise ValueError(f"nested model graph at id={current.graph_id}")
            values = fields(line)
            current = Graph(integer(values, "id"), integer(values, "nodes"))
            graphs.append(current)
        elif line.startswith("GGML_RISCV_MODEL_GRAPH_END "):
            values = fields(line)
            if current is None or integer(values, "id", -1) != current.graph_id:
                raise ValueError("model graph end does not match active graph")
            current.closed = True
            current = None
        elif line.startswith("GGML_RISCV_MODEL_NODE "):
            if current is None:
                raise ValueError("model node observed outside graph boundary")
            current.nodes.append(fields(line))
        elif line.startswith("GGML_RISCV_QBS_CALL "):
            if current is None:
                raise ValueError("QBS call observed outside graph boundary")
            if not current.nodes:
                raise ValueError("QBS call observed before its model node")
            values = fields(line)
            values["_node_index"] = str(len(current.nodes) - 1)
            current.qbs_calls.append(values)
        elif line.startswith("GGML_RISCV_AKV_EXEC "):
            if current is None:
                raise ValueError("AKV call observed outside graph boundary")
            if not current.nodes:
                raise ValueError("AKV call observed before its model node")
            values = fields(line)
            values["_node_index"] = str(len(current.nodes) - 1)
            current.akv_calls.append(values)
        elif line.startswith("GGML_RISCV_QBS_COVERAGE "):
            values = fields(line)
            qbs_coverage[normalized_qbs_type(values["type"])] = values
        elif line.startswith("GGML_RISCV_QBS_EXEC "):
            values = fields(line)
            qbs_exec[normalized_qbs_type(values["type"])] = values
        elif line.startswith("GGML_RISCV_AKV_COVERAGE "):
            akv_coverage = fields(line)

        if line.startswith("AKV_TOKEN_RUN_EXIT=QBS_AKV_V2:"):
            optimized_exit = int(line.rpartition(":")[2])

    for line in all_lines:
        if line.startswith("AKV_LOGITS_"):
            key, _, value = line.partition("=")
            logits[key] = value
        elif line.startswith("QBS_RVV_"):
            key, _, value = line.partition("=")
            qbs_rvv[key] = value
        elif line.strip() == "AKV_TOKEN_OUTPUT_EQUAL=1":
            output_equal = True
        elif line.startswith("LLAMA_GUEST_EXIT="):
            guest_exit = int(line.partition("=")[2])

    if current is not None or any(not graph.closed for graph in graphs):
        raise ValueError("unterminated model graph in optimized run")
    return ParsedRun(
        graphs,
        qbs_coverage,
        qbs_exec,
        akv_coverage,
        logits,
        qbs_rvv,
        output_equal,
        guest_exit,
        optimized_exit,
    )


def validate_dynamic(run: ParsedRun) -> None:
    if not run.graphs:
        raise ValueError("no model graphs were traced")
    phases = Counter(graph.phase for graph in run.graphs)
    if phases["prefill"] == 0 or phases["decode"] == 0:
        raise ValueError(f"expected prefill and decode graphs, got {dict(phases)}")
    if run.optimized_exit != 0:
        raise ValueError(f"optimized model child exited with {run.optimized_exit}")
    if run.guest_exit != 0 or not run.output_equal:
        raise ValueError("combined model run did not preserve functional output")
    validate_numerical_metrics(run.logits, "AKV")
    validate_numerical_metrics(run.qbs_rvv, "QBS_RVV")
    if run.logits.get("AKV_LOGITS_TOP1_EQUAL") != "1":
        raise ValueError("combined model run changed top-1 logits result")
    if integer(run.qbs_rvv, "QBS_RVV_LOGITS_RECORDS") == 0 or \
       integer(run.qbs_rvv, "QBS_RVV_LOGITS_COMPARABLE_RECORDS") == 0:
        raise ValueError("QBS/RVV model-quality observation has no comparable logits record")

    qbs_calls: defaultdict[str, int] = defaultdict(int)
    for graph in run.graphs:
        qbs_nodes = {
            index
            for index, node in enumerate(graph.nodes)
            if node.get("op") in SUPPORTED_QBS_OPS
            and normalized_qbs_type(node.get("src0", "")) in SUPPORTED_QBS_TYPES
        }
        called_qbs_nodes: set[int] = set()
        for call in graph.qbs_calls:
            profile = normalized_qbs_type(call["type"])
            node_index = integer(call, "_node_index", -1)
            if node_index < 0 or node_index >= len(graph.nodes):
                raise ValueError("QBS call has no valid model-node owner")
            node = graph.nodes[node_index]
            if node.get("op") not in SUPPORTED_QBS_OPS or normalized_qbs_type(
                node.get("src0", "")
            ) != profile:
                raise ValueError("QBS call/model-node association is inconsistent")
            called_qbs_nodes.add(node_index)
            qbs_calls[profile] += (
                integer(call, "k") * integer(call, "input_rows") * integer(call, "output_rows")
            )
        if qbs_nodes != called_qbs_nodes:
            raise ValueError(
                f"QBS graph coverage mismatch for graph {graph.graph_id}: "
                f"eligible={sorted(qbs_nodes)} called={sorted(called_qbs_nodes)}"
            )
    for profile, dot_elements in qbs_calls.items():
        summary = run.qbs_exec.get(profile)
        if summary is None:
            raise ValueError(f"missing QBS execution summary for {profile}")
        if integer(summary, "dot_elements") != dot_elements:
            raise ValueError(
                f"QBS call/summary dot mismatch for {profile}: {dot_elements} vs "
                f"{summary.get('dot_elements')}"
            )
        if integer(summary, "command_dot_elements") != dot_elements:
            raise ValueError(
                f"QBS command work mismatch for {profile}: {dot_elements} vs "
                f"{summary.get('command_dot_elements')}"
            )
        if integer(summary, "native_qbexec") == 0 or integer(summary, "emulated_commands") != 0:
            raise ValueError(f"{profile} did not execute natively")
        coverage = run.qbs_coverage.get(profile)
        if coverage is None:
            raise ValueError(f"missing QBS coverage summary for {profile}")
        if integer(coverage, "candidate_tensors") != integer(coverage, "selected_tensors") or \
           integer(coverage, "candidate_elements") != integer(coverage, "selected_elements"):
            raise ValueError(f"{profile} did not select every candidate tensor and element")
        if any(integer(coverage, key) for key in coverage if key.startswith("fallback_")):
            raise ValueError(f"{profile} unexpectedly used a QBS fallback")

    akv_calls = []
    flash_nodes = 0
    akv_groups = 0
    akv_group_tokens = 0
    akv_macs = 0
    decode_calls = 0
    prefill_calls = 0
    prefill_query_tokens = 0
    prefill_attention_pairs = 0
    for graph in run.graphs:
        flash_node_indices = {
            index
            for index, node in enumerate(graph.nodes)
            if node.get("op") == "FLASH_ATTN_EXT"
        }
        flash_nodes += len(flash_node_indices)
        called_nodes: Counter[int] = Counter()
        for call in graph.akv_calls:
            node_index = integer(call, "_node_index", -1)
            if node_index < 0 or node_index >= len(graph.nodes):
                raise ValueError("AKV call has no valid model-node owner")
            mode = call.get("mode", "decode")
            if mode not in ("decode", "prefill") or graph.phase != mode or \
                    graph.nodes[node_index].get("op") != "FLASH_ATTN_EXT":
                raise ValueError("AKV call/model-node association is inconsistent")
            called_nodes[node_index] += 1
            akv_calls.append(call)
            if call.get("kernel") != "v2":
                raise ValueError("an accelerated attention call did not use AKV-v2")

            kv_heads = integer(call, "kv_heads")
            head_dim = integer(call, "head_dim")
            attention_macs = integer(call, "attention_macs")
            if mode == "decode":
                q_heads = integer(call, "q_rows")
                gqa_rows = integer(call, "gqa_rows")
                active_kv = integer(call, "active_kv")
                if min(kv_heads, q_heads, gqa_rows, head_dim, active_kv) <= 0:
                    raise ValueError("AKV Decode call has a non-positive shape field")
                if q_heads != kv_heads * gqa_rows:
                    raise ValueError("AKV Decode q-head/GQA identity is inconsistent")
                expected_macs = 2 * kv_heads * gqa_rows * head_dim * active_kv
                if attention_macs != expected_macs:
                    raise ValueError("AKV Decode MAC count is inconsistent with its shape")
                decode_calls += 1
                akv_groups += kv_heads
                akv_group_tokens += kv_heads * active_kv
            else:
                query_tokens = integer(call, "M")
                past_tokens = integer(call, "P", -1)
                kv_capacity = integer(call, "kv_capacity")
                q_heads = integer(call, "q_heads")
                gqa_rows = integer(call, "q_rows")
                groups = integer(call, "groups")
                attention_pairs = integer(call, "attention_pairs")
                if min(query_tokens, kv_capacity, kv_heads, q_heads, gqa_rows, head_dim) <= 0 or past_tokens < 0:
                    raise ValueError("AKV Prefill call has a non-positive shape field")
                if query_tokens < 15 or head_dim not in (64, 96, 128) or gqa_rows > 8:
                    raise ValueError("AKV Prefill call violates the selected hardware profile")
                if q_heads != kv_heads * gqa_rows or past_tokens + query_tokens > kv_capacity:
                    raise ValueError("AKV Prefill causal shape identity is inconsistent")
                expected_pairs_per_head = (
                    query_tokens * (past_tokens + 1)
                    + query_tokens * (query_tokens - 1) // 2
                )
                expected_pairs = q_heads * expected_pairs_per_head
                expected_groups = kv_heads * (
                    (query_tokens + AKV_PREFILL_QUERY_BLOCK_TOKENS - 1)
                    // AKV_PREFILL_QUERY_BLOCK_TOKENS
                )
                expected_group_tokens = sum(
                    kv_heads * (past_tokens + min(token_start + AKV_PREFILL_QUERY_BLOCK_TOKENS, query_tokens))
                    for token_start in range(0, query_tokens, AKV_PREFILL_QUERY_BLOCK_TOKENS)
                )
                expected_macs = 2 * expected_pairs * head_dim
                if attention_pairs != expected_pairs:
                    raise ValueError("AKV Prefill attention-pair count is inconsistent with its causal shape")
                if groups != expected_groups:
                    raise ValueError("AKV Prefill group count is inconsistent with its blocked schedule")
                if attention_macs != expected_macs:
                    raise ValueError("AKV Prefill MAC count is inconsistent with its shape")
                prefill_calls += 1
                prefill_query_tokens += query_tokens
                prefill_attention_pairs += attention_pairs
                akv_groups += groups
                akv_group_tokens += expected_group_tokens
            akv_macs += attention_macs
        if not set(called_nodes).issubset(flash_node_indices) or any(
            count != 1 for count in called_nodes.values()
        ):
            raise ValueError(
                f"AKV graph coverage mismatch for graph {graph.graph_id}: "
                f"flash={sorted(flash_node_indices)} called={dict(sorted(called_nodes.items()))}"
            )
    if integer(run.akv_coverage, "attention_macs") != akv_macs:
        raise ValueError("AKV call/coverage MAC count mismatch")
    if integer(run.akv_coverage, "executed_v1") != 0:
        raise ValueError("combined run unexpectedly executed AKV-v1")
    if integer(run.akv_coverage, "candidate_ops") != flash_nodes or \
       integer(run.akv_coverage, "executed_ops") != len(akv_calls) or \
       integer(run.akv_coverage, "executed_v2") != len(akv_calls):
        raise ValueError("AKV candidate/execution coverage is inconsistent with traced graph nodes")
    if integer(run.akv_coverage, "groups") != akv_groups or \
       integer(run.akv_coverage, "groups_v2") != akv_groups or \
       integer(run.akv_coverage, "kv_group_tokens") != akv_group_tokens:
        raise ValueError("AKV coverage traffic is inconsistent with per-call shapes")
    optional_totals = {
        "executed_decode": decode_calls,
        "executed_prefill": prefill_calls,
        "prefill_query_tokens": prefill_query_tokens,
        "prefill_attention_pairs": prefill_attention_pairs,
    }
    for field_name, expected in optional_totals.items():
        if field_name in run.akv_coverage and integer(run.akv_coverage, field_name) != expected:
            raise ValueError(f"AKV coverage {field_name} is inconsistent with per-call shapes")
    akv_fallbacks = sum(
        integer(run.akv_coverage, key)
        for key in run.akv_coverage
        if key.startswith("fallback_")
    )
    if akv_fallbacks != flash_nodes - len(akv_calls):
        raise ValueError("AKV fallback count does not explain every non-executed candidate")


def write_csv(path: Path, rows: list[dict[str, object]], leading: Iterable[str]) -> None:
    leading = list(leading)
    remaining = sorted({key for row in rows for key in row} - set(leading))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=leading + remaining)
        writer.writeheader()
        writer.writerows(rows)


def aggregate_call_counts_by_mode(rows: Iterable[dict[str, object]]) -> dict[str, int]:
    """Count actual AKV invocations rather than aggregated shape rows."""
    counts: Counter[str] = Counter()
    for row in rows:
        counts[str(row["mode"])] += int(row["calls"])
    return dict(counts)


def node_semantic(nodes: list[dict[str, str]], index: int) -> str:
    node = nodes[index]
    op = node.get("op", "").upper()
    name = node.get("name", "").lower()
    next_name = nodes[index + 1].get("name", "").lower() if index + 1 < len(nodes) else ""

    if op == "RMS_NORM":
        if next_name.startswith("qcur"):
            return "attention_norm"
        if next_name.startswith("ffn_gate"):
            return "ffn_norm"
        if next_name.startswith("result_output"):
            return "final_norm"
    elif op == "ROPE":
        if name.startswith("qcur"):
            return "rope_q"
        if name.startswith("kcur"):
            return "rope_k"
    elif op == "ADD":
        if name.startswith("ffn_inp"):
            return "attention_residual"
        if name.startswith("l_out"):
            return "ffn_residual"
    elif op == "GLU" and name.startswith("ffn_swiglu"):
        return "ffn_activation"
    return ""


def dynamic_rows(run: ParsedRun):
    qbs_groups: Counter[tuple[object, ...]] = Counter()
    akv_groups: Counter[tuple[object, ...]] = Counter()
    node_groups: Counter[tuple[object, ...]] = Counter()
    for graph in run.graphs:
        phase = graph.phase
        for call in graph.qbs_calls:
            node_index = integer(call, "_node_index")
            key = (
                graph.graph_id,
                phase,
                node_index,
                normalize_tensor_name(graph.nodes[node_index].get("name", "")),
                graph.nodes[node_index].get("op", ""),
                normalized_qbs_type(call["type"]),
                call["mode"],
                integer(call, "k"),
                integer(call, "input_rows"),
                integer(call, "output_rows"),
                integer(call, "split_k"),
            )
            qbs_groups[key] += 1
        for call in graph.akv_calls:
            mode = call.get("mode", "decode")
            if mode == "prefill":
                query_tokens = integer(call, "M")
                past_tokens = integer(call, "P")
                kv_capacity = integer(call, "kv_capacity")
                kv_heads = integer(call, "kv_heads")
                q_heads = integer(call, "q_heads")
                gqa_rows = integer(call, "q_rows")
                head_dim = integer(call, "head_dim")
                groups = integer(call, "groups")
                attention_pairs = integer(call, "attention_pairs")
                active_kv = past_tokens + query_tokens
                kv_group_tokens = sum(
                    kv_heads * (past_tokens + min(token_start + AKV_PREFILL_QUERY_BLOCK_TOKENS, query_tokens))
                    for token_start in range(0, query_tokens, AKV_PREFILL_QUERY_BLOCK_TOKENS)
                )
            else:
                query_tokens = 1
                past_tokens = None
                kv_heads = integer(call, "kv_heads")
                q_heads = integer(call, "q_rows")
                gqa_rows = integer(call, "gqa_rows")
                head_dim = integer(call, "head_dim")
                active_kv = integer(call, "active_kv")
                kv_capacity = None
                groups = kv_heads
                attention_pairs = q_heads * active_kv
                kv_group_tokens = kv_heads * active_kv
            key = (
                graph.graph_id,
                phase,
                mode,
                call["kernel"],
                query_tokens,
                past_tokens,
                kv_capacity,
                kv_heads,
                q_heads,
                gqa_rows,
                head_dim,
                active_kv,
                groups,
                attention_pairs,
                kv_group_tokens,
                integer(call, "attention_macs"),
            )
            akv_groups[key] += 1
        for index, node in enumerate(graph.nodes):
            key = (
                graph.graph_id,
                phase,
                node_semantic(graph.nodes, index),
                node.get("op", ""),
                node.get("type", ""),
                integer(node, "ne0"),
                integer(node, "ne1"),
                integer(node, "ne2"),
                integer(node, "ne3"),
                node.get("src0", ""),
                node.get("src1", ""),
                integer(node, "fused_followers"),
                node.get("fused_next", ""),
                normalize_tensor_name(node.get("name", "")),
            )
            node_groups[key] += 1

    qbs_rows = []
    for key, count in sorted(qbs_groups.items()):
        (
            graph_id, phase, node_index, node_name, operation, profile,
            mode, k, input_rows, output_rows, split_k,
        ) = key
        weight_block_bytes, weight_block_elements = qbs_profile_geometry(profile)
        activation_profile = qbs_activation_profile(profile)
        activation_block_bytes, activation_block_elements = qbs_profile_geometry(
            activation_profile, "activation"
        )
        qbs_rows.append(
            {
                "graph_id": graph_id,
                "phase": phase,
                "node_index": node_index,
                "node_name": node_name,
                "operation": operation,
                "type": profile,
                "mode": mode,
                "k": k,
                "input_rows": input_rows,
                "output_rows": output_rows,
                "split_k": split_k,
                "calls": count,
                "activation_profile": activation_profile,
                "activation_row_uses": count * input_rows,
                "activation_element_uses": count * k * input_rows,
                "quantized_activation_bytes": blocked_payload_bytes(
                    k,
                    input_rows,
                    count,
                    activation_block_bytes,
                    activation_block_elements,
                    f"QBS {profile} activation",
                ),
                "weight_payload_bytes": blocked_payload_bytes(
                    k,
                    output_rows,
                    count,
                    weight_block_bytes,
                    weight_block_elements,
                    f"QBS {profile} weight",
                ),
                "output_elements": count * input_rows * output_rows,
                "dot_elements": count * k * input_rows * output_rows,
            }
        )

    qbs_node_rows = []
    for graph in run.graphs:
        calls_by_node: defaultdict[int, list[dict[str, str]]] = defaultdict(list)
        for call in graph.qbs_calls:
            calls_by_node[integer(call, "_node_index")].append(call)
        for node_index, calls in sorted(calls_by_node.items()):
            node = graph.nodes[node_index]
            profiles = {normalized_qbs_type(call["type"]) for call in calls}
            modes = {call["mode"] for call in calls}
            k_values = {integer(call, "k") for call in calls}
            if len(profiles) != 1 or len(k_values) != 1:
                raise ValueError("one QBS model node produced inconsistent call shapes")
            profile = profiles.pop()
            k = k_values.pop()
            input_rows = integer(node, "ne1") * integer(node, "ne2", 1) * integer(node, "ne3", 1)
            operation = node.get("op", "")
            if operation not in SUPPORTED_QBS_OPS:
                raise ValueError(f"unsupported QBS model operation: {operation}")
            activation_rows = input_rows
            activation_accounting = "exact_output_rows"
            if operation == "MUL_MAT_ID":
                source_shape_fields = ("src1_ne1", "src1_ne2", "src1_ne3")
                if all(field in node for field in source_shape_fields):
                    activation_rows = (
                        integer(node, "src1_ne1")
                        * integer(node, "src1_ne2")
                        * integer(node, "src1_ne3")
                    )
                    if activation_rows <= 0 or input_rows % activation_rows:
                        raise ValueError("MUL_MAT_ID activation/output row topology is inconsistent")
                    activation_accounting = "exact_source_shape"
                else:
                    # Legacy guest traces omit src1_ne*. Calls still prove
                    # routed matrix work, but they cannot distinguish a shared
                    # gate/up activation from per-route down activations.
                    activation_rows = None
                    activation_accounting = "unavailable_legacy_source_shape"
            output_rows = integer(node, "ne0")
            if modes == {"gemm", "gemv"} and input_rows > 1:
                mode = "gemm+gemv_tail"
            elif len(modes) == 1:
                mode = modes.pop()
            else:
                raise ValueError("one QBS model node produced an unsupported mode combination")
            output_elements = sum(
                integer(call, "input_rows") * integer(call, "output_rows") for call in calls
            )
            dot_elements = sum(
                integer(call, "k") * integer(call, "input_rows") * integer(call, "output_rows")
                for call in calls
            )
            expected_output_elements = input_rows * output_rows
            if output_elements != expected_output_elements or dot_elements != k * expected_output_elements:
                raise ValueError(
                    f"QBS node work mismatch for graph {graph.graph_id} node {node_index}: "
                    f"output {output_elements}/{expected_output_elements}, dot {dot_elements}/{k * expected_output_elements}"
                )
            weight_block_bytes, weight_block_elements = qbs_profile_geometry(profile)
            activation_profile = qbs_activation_profile(profile)
            activation_block_bytes, activation_block_elements = qbs_profile_geometry(
                activation_profile, "activation"
            )
            weight_payload_bytes = sum(
                blocked_payload_bytes(
                    integer(call, "k"),
                    integer(call, "output_rows"),
                    1,
                    weight_block_bytes,
                    weight_block_elements,
                    f"QBS {profile} weight",
                )
                for call in calls
            )
            activation_elements = k * activation_rows if activation_rows is not None else None
            quantized_activation_bytes = (
                blocked_payload_bytes(
                    k,
                    activation_rows,
                    1,
                    activation_block_bytes,
                    activation_block_elements,
                    f"QBS {profile} activation",
                )
                if activation_rows is not None
                else None
            )
            qbs_node_rows.append(
                {
                    "graph_id": graph.graph_id,
                    "phase": graph.phase,
                    "node_index": node_index,
                    "node_name": normalize_tensor_name(node.get("name", "")),
                    "operation": operation,
                    "type": profile,
                    "mode": mode,
                    "k": k,
                    "input_rows": input_rows,
                    "activation_rows": activation_rows,
                    "activation_accounting": activation_accounting,
                    "output_rows": output_rows,
                    "call_chunks": len(calls),
                    "activation_profile": activation_profile,
                    "activation_elements": activation_elements,
                    "quantized_activation_bytes": quantized_activation_bytes,
                    "weight_payload_bytes": weight_payload_bytes,
                    "output_elements": output_elements,
                    "dot_elements": dot_elements,
                }
            )
    akv_rows = []
    for key, count in sorted(akv_groups.items()):
        (graph_id, phase, mode, kernel, query_tokens, past_tokens, kv_capacity,
         kv_heads, q_heads, gqa_rows, head_dim, active_kv, groups,
         attention_pairs, kv_group_tokens, attention_macs) = key
        query_elements = count * query_tokens * q_heads * head_dim
        streamed_kv_bytes = count * 2 * kv_group_tokens * head_dim * F16_BYTES
        unique_kv_bytes = count * 2 * kv_heads * active_kv * head_dim * F16_BYTES
        akv_rows.append(
            {
                "graph_id": graph_id,
                "phase": phase,
                "mode": mode,
                "kernel": kernel,
                "query_tokens": query_tokens,
                "past_tokens": past_tokens,
                "kv_capacity": kv_capacity,
                "kv_heads": kv_heads,
                "q_heads": q_heads,
                "gqa_rows": gqa_rows,
                "head_dim": head_dim,
                "active_kv": active_kv,
                "groups": groups,
                "attention_pairs": attention_pairs,
                "kv_group_tokens": kv_group_tokens,
                "calls": count,
                "query_source_f32_bytes": query_elements * F32_BYTES,
                "query_payload_bytes": query_elements * F16_BYTES,
                "unique_kv_payload_bytes": unique_kv_bytes,
                "kv_payload_bytes": streamed_kv_bytes,
                "kv_reread_factor": streamed_kv_bytes / unique_kv_bytes,
                "attention_macs": count * attention_macs,
            }
        )
    node_rows = []
    for key, count in sorted(node_groups.items()):
        (
            graph_id,
            phase,
            semantic,
            op,
            result_type,
            ne0,
            ne1,
            ne2,
            ne3,
            src0,
            src1,
            fused_followers,
            fused_next,
            name,
        ) = key
        node_rows.append(
            {
                "graph_id": graph_id,
                "phase": phase,
                "semantic": semantic,
                "op": op,
                "type": result_type,
                "ne0": ne0,
                "ne1": ne1,
                "ne2": ne2,
                "ne3": ne3,
                "src0": src0,
                "src1": src1,
                "fused_followers": fused_followers,
                "fused_next": fused_next,
                "name": name,
                "count": count,
            }
        )
    return qbs_rows, qbs_node_rows, akv_rows, node_rows


def load_qbs_calibration(path: Path) -> list[dict[str, object]]:
    points = []
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("result") != "PASS":
                continue
            case = row["case"]
            if "ffn_down" in case:
                profile = "Q6_K"
            elif "attn_q" in case or "ffn_gate" in case:
                profile = "Q4_K"
            else:
                continue
            k = int(row["k"])
            m = int(row["inputs"])
            n = int(row["outputs"])
            points.append(
                {
                    "case": case,
                    "profile": profile,
                    "k": k,
                    "m": m,
                    "n": n,
                    "quantize_cycles": int(row["quantize_cycles"]),
                    "matmul_cycles": int(row["matmul_cycles"]),
                    "quant_cycles_per_element": int(row["quantize_cycles"]) / (k * m),
                    "matmul_cycles_per_dot": int(row["matmul_cycles"]) / (k * m * n),
                }
            )
    if not points:
        raise ValueError(f"no QBS calibration points in {path}")
    return points


def nearest_qbs_point(call: dict[str, object], points: list[dict[str, object]]) -> dict[str, object]:
    profile = str(call["type"])
    candidates = [point for point in points if point["profile"] == profile]
    if not candidates:
        raise ValueError(f"no QBS RTL calibration for {profile}")

    def distance(point: dict[str, object]) -> float:
        return (
            abs(math.log(int(call["k"]) / int(point["k"])))
            + 2.0 * abs(math.log(int(call["input_rows"]) / int(point["m"])))
            + 0.1 * abs(math.log(int(call["output_rows"]) / int(point["n"])))
        )

    return min(candidates, key=distance)


def load_akv_calibration(path: Path) -> list[dict[str, int]]:
    unique: dict[int, int] = {}
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("implementation") != "akv_v2" or row.get("phase") != "total" or row.get("status") != "PASS":
                continue
            unique[int(row["effective_kv"])] = int(row["kernel_cycles"])
    if len(unique) < 2:
        raise ValueError(f"need at least two AKV-v2 calibration points in {path}")
    return [{"active_kv": key, "cycles": value} for key, value in sorted(unique.items())]


def interpolate_akv_cycles(active_kv: int, points: list[dict[str, int]]) -> float:
    if active_kv <= points[0]["active_kv"]:
        lhs, rhs = points[0], points[1]
    elif active_kv >= points[-1]["active_kv"]:
        lhs, rhs = points[-2], points[-1]
    else:
        lhs, rhs = next(
            (lhs, rhs)
            for lhs, rhs in zip(points, points[1:])
            if lhs["active_kv"] <= active_kv <= rhs["active_kv"]
        )
    slope = (rhs["cycles"] - lhs["cycles"]) / (rhs["active_kv"] - lhs["active_kv"])
    return lhs["cycles"] + slope * (active_kv - lhs["active_kv"])


def describe_akv_calibration(points: list[dict[str, int]]) -> str:
    kv_points = "/".join(f"KV{point['active_kv']}" for point in points)
    return f"piecewise AKV-v2 {kv_points} RTL"


def _prefill_shape_key(values: dict[str, object]) -> tuple[int, ...]:
    aliases = {"query_heads": "q_heads"}
    return tuple(
        int(values[field] if field in values else values[aliases[field]])
        for field in AKV_PREFILL_SHAPE_FIELDS
    )


def _validate_prefill_source_hashes(
    summary: dict[str, object],
    summary_path: Path,
    shape: dict[str, int],
) -> dict[str, object]:
    case_path = Path(str(summary.get("case", "")))
    if not case_path.is_file():
        raise ValueError(f"Prefill calibration case does not exist: {case_path}")
    provenance = summary.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError(f"Prefill calibration lacks provenance: {summary_path}")
    if provenance.get("case_sha256") != sha256(case_path):
        raise ValueError(f"Prefill calibration case hash mismatch: {summary_path}")

    case = json.loads(case_path.read_text(encoding="utf-8"))
    source_fields = {
        "query_sha256": (
            "input_a", "f32",
            [shape["head_dim"], shape["query_tokens"], shape["query_heads"], 1],
        ),
        "key_sha256": (
            "key", "f16",
            [shape["head_dim"], shape["kv_capacity"], shape["kv_heads"], 1],
        ),
        "value_sha256": (
            "value", "f16",
            [shape["head_dim"], shape["kv_capacity"], shape["kv_heads"], 1],
        ),
        "mask_sha256": (
            "mask", "f16",
            [shape["kv_capacity"], shape["query_tokens"], 1, 1],
        ),
        "golden_sha256": (
            "golden", "f32",
            [shape["head_dim"] * shape["query_heads"], shape["query_tokens"], 1, 1],
        ),
    }
    sources: dict[str, object] = {
        "summary": {"path": str(summary_path.resolve()), "sha256": sha256(summary_path)},
        "case": {"path": str(case_path.resolve()), "sha256": sha256(case_path)},
    }
    for hash_field, (case_field, expected_type, expected_shape) in source_fields.items():
        relative = case.get(case_field)
        if not isinstance(relative, str) or not relative:
            raise ValueError(f"Prefill calibration case lacks {case_field}: {case_path}")
        metadata_path = (case_path.parent / relative).resolve()
        if not metadata_path.is_file():
            raise ValueError(f"Prefill calibration metadata does not exist: {metadata_path}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        payload = metadata_path.with_suffix(".bin")
        if not payload.is_file():
            raise ValueError(f"Prefill calibration payload does not exist: {payload}")
        element_bytes = F32_BYTES if expected_type == "f32" else F16_BYTES
        expected_strides = [element_bytes]
        for dimension in expected_shape[:-1]:
            expected_strides.append(expected_strides[-1] * dimension)
        expected_nbytes = math.prod(expected_shape) * element_bytes
        if str(metadata.get("type", "")).lower() != expected_type or \
                [int(value) for value in metadata.get("shape", [])] != expected_shape or \
                [int(value) for value in metadata.get("strides", [])] != expected_strides or \
                int(metadata.get("nbytes", -1)) != expected_nbytes or \
                payload.stat().st_size != expected_nbytes:
            raise ValueError(f"Prefill calibration {case_field} metadata mismatch: {metadata_path}")
        digest = sha256(payload)
        if provenance.get(hash_field) != digest:
            raise ValueError(f"Prefill calibration {case_field} hash mismatch: {summary_path}")
        sources[case_field] = {
            "metadata_path": str(metadata_path),
            "metadata_sha256": sha256(metadata_path),
            "payload_path": str(payload.resolve()),
            "payload_sha256": digest,
        }
    return sources


def load_akv_prefill_calibration(paths: Iterable[Path]) -> list[dict[str, object]]:
    points: list[dict[str, object]] = []
    keys: set[tuple[int, ...]] = set()
    for path in paths:
        path = path.resolve()
        if not path.is_file():
            raise ValueError(f"Prefill calibration summary does not exist: {path}")
        summary = json.loads(path.read_text(encoding="utf-8"))
        if int(summary.get("schema_version", 0)) < AKV_PREFILL_CALIBRATION_SCHEMA_MIN or summary.get("status") != "PASS":
            raise ValueError(f"Prefill calibration is not a passing schema-v6 summary: {path}")

        shape = summary.get("shape")
        work = summary.get("work")
        if not isinstance(shape, dict) or not isinstance(work, dict):
            raise ValueError(f"Prefill calibration lacks shape/work accounting: {path}")
        try:
            key = _prefill_shape_key(shape)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Prefill calibration has an incomplete shape: {path}") from error
        shape_values = dict(zip(AKV_PREFILL_SHAPE_FIELDS, key))
        positive_shape_fields = set(AKV_PREFILL_SHAPE_FIELDS) - {"past_tokens"}
        if any(shape_values[field] <= 0 for field in positive_shape_fields) or \
                shape_values["past_tokens"] < 0 or int(shape.get("batch", 0)) != 1:
            raise ValueError(f"Prefill calibration has an invalid shape: {path}")
        if shape_values["query_heads"] != shape_values["kv_heads"] * shape_values["gqa_rows"] or \
                shape_values["past_tokens"] + shape_values["query_tokens"] > shape_values["kv_capacity"]:
            raise ValueError(f"Prefill calibration shape identities are inconsistent: {path}")
        expected_prefixes = list(
            range(
                shape_values["past_tokens"] + 1,
                shape_values["past_tokens"] + shape_values["query_tokens"] + 1,
            )
        )
        if shape.get("active_prefixes") != expected_prefixes:
            raise ValueError(f"Prefill calibration causal prefixes are inconsistent: {path}")
        expected_pairs = shape_values["query_heads"] * sum(expected_prefixes)
        expected_macs = 2 * expected_pairs * shape_values["head_dim"]
        if int(work.get("active_query_head_kv_pairs", -1)) != expected_pairs or \
                int(work.get("attention_macs", -1)) != expected_macs:
            raise ValueError(f"Prefill calibration mathematical work is inconsistent: {path}")
        if shape_values["head_dim"] != 128 or shape_values["gqa_rows"] != 6:
            raise ValueError(
                f"retained Panel4 calibration requires D128/GQA6, got "
                f"D{shape_values['head_dim']}/GQA{shape_values['gqa_rows']}: {path}"
            )

        sources = _validate_prefill_source_hashes(summary, path, shape_values)
        measurements = summary.get("measurements")
        if not isinstance(measurements, list):
            raise ValueError(f"Prefill calibration lacks measurements: {path}")
        retained = [
            measurement
            for measurement in measurements
            if isinstance(measurement, dict)
            and measurement.get("strategy") == AKV_PREFILL_RETAINED_STRATEGY
        ]
        if len(retained) != 1:
            raise ValueError(f"Prefill calibration must contain one retained Panel4 measurement: {path}")
        measurement = retained[0]
        if int(measurement.get("cycles", 0)) <= 0 or int(measurement.get("mismatches", -1)) != 0 or \
                measurement.get("strict_counter_status") != "PASS" or \
                int(measurement.get("strict_counter_checked_fields", 0)) < AKV_PREFILL_STRICT_COUNTER_FIELDS_MIN:
            raise ValueError(f"Prefill calibration measurement is not strict PASS: {path}")

        log_path = Path(str(measurement.get("log", "")))
        if not log_path.is_file() or measurement.get("log_sha256") != sha256(log_path):
            raise ValueError(f"Prefill calibration log provenance mismatch: {path}")
        matches = OPERATOR_RE.findall(log_path.read_text(errors="replace"))
        if len(matches) != 1:
            raise ValueError(f"Prefill calibration log has no unique operator result: {log_path}")
        case_name, status, cycles, mismatches = matches[0]
        if status != "PASS" or int(mismatches) != 0 or int(cycles) != int(measurement["cycles"]) or \
                case_name != measurement.get("case_name"):
            raise ValueError(f"Prefill calibration log/result mismatch: {path}")
        if key in keys:
            raise ValueError(f"duplicate exact Prefill calibration shape: {key}")
        keys.add(key)
        sources["log"] = {"path": str(log_path.resolve()), "sha256": sha256(log_path)}
        points.append(
            {
                **shape_values,
                "batch": 1,
                "strategy": AKV_PREFILL_RETAINED_STRATEGY,
                "cycles": int(measurement["cycles"]),
                "case_name": case_name,
                "attention_pairs": expected_pairs,
                "attention_macs": expected_macs,
                "source": sources,
            }
        )
    return sorted(points, key=_prefill_shape_key)


def exact_akv_prefill_point(
    call: dict[str, object], points: list[dict[str, object]]
) -> dict[str, object] | None:
    call_key = _prefill_shape_key(call)
    return next((point for point in points if _prefill_shape_key(point) == call_key), None)


def load_rvv_calibration(
    directories: Iterable[Path],
) -> tuple[dict[str, int], list[dict[str, object]]]:
    values: dict[str, int] = {}
    selected_paths: dict[str, Path] = {}
    for directory in directories:
        if not directory.is_dir():
            raise ValueError(f"RVV calibration directory does not exist: {directory}")
        for path in sorted(directory.glob("*.ara.log")):
            match = OPERATOR_RE.search(path.read_text(errors="replace"))
            if match and match.group(2) == "PASS" and int(match.group(4)) == 0:
                case = match.group(1)
                values[case] = int(match.group(3))
                selected_paths[case] = path.resolve()
    if not values:
        raise ValueError("no passing RVV leaf calibration was found")
    sources = [
        {
            "case": case,
            "cycles": values[case],
            "path": str(path),
            "sha256": sha256(path),
        }
        for case, path in sorted(selected_paths.items())
    ]
    return values, sources


def default_rvv_calibration_dirs(root: Path) -> list[Path]:
    compute_only = (
        root
        / "hardware/model_closure_rvv_calibration_compute_only_full_v2/operator_ara_latest"
    )
    if compute_only.is_dir() and (compute_only / "complete").is_file():
        return [compute_only]
    directories = [
        root / "hardware/llama_benchmark_runs/operator_ara_l2_16m_20260813_034827"
    ]
    supplemental = root / "hardware/model_closure_rvv_calibration"
    if supplemental.is_dir():
        directories.extend(
            path
            for path in sorted(supplemental.iterdir())
            if path.is_dir() and any(path.glob("*.ara.log"))
        )
    return directories


def classify_rvv_node(row: dict[str, object]) -> tuple[str, str] | None:
    semantic = str(row.get("semantic", ""))
    phase = str(row.get("phase", ""))
    op = str(row.get("op", "")).upper()
    shape = tuple(int(row.get(f"ne{axis}", 0)) for axis in range(4))
    result_type = normalized_qbs_type(str(row.get("type", "")))
    src0 = normalized_qbs_type(str(row.get("src0", "")))
    src1 = normalized_qbs_type(str(row.get("src1", "")))
    mapping = {
        "attention_norm": ((1536, 1, 1, 1), "rvv_norm", f"operator/{phase}/attention_norm"),
        "ffn_norm": ((1536, 1, 1, 1), "rvv_norm", f"operator/{phase}/ffn_norm"),
        "final_norm": ((1536, 1, 1, 1), "rvv_norm", "operator/decode/attention_norm"),
        "rope_q": ((128, 12, 1, 1), "rvv_rope", f"operator/{phase}/rope_q"),
        "rope_k": ((128, 2, 1, 1), "rvv_rope", f"operator/{phase}/rope_k"),
        "attention_residual": ((1536, 1, 1, 1), "rvv_residual", f"operator/{phase}/attention_residual"),
        "ffn_residual": ((1536, 1, 1, 1), "rvv_residual", f"operator/{phase}/ffn_residual"),
        "ffn_activation": ((8960, 1, 1, 1), "rvv_activation", f"operator/{phase}/ffn_activation"),
    }
    if semantic in mapping:
        expected_shape, category, case_id = mapping[semantic]
        if result_type == "F32" and shape == expected_shape:
            return category, case_id
        return None
    if (phase == "decode" and op == "ADD" and result_type == "F32" and
            src0 == "F32" and src1 == "F32" and shape in ((256, 1, 1, 1), (1536, 1, 1, 1))):
        return ("rvv_bias", f"calibration/decode/qkv_bias_{shape[0]}")
    if (phase == "decode" and op == "SET_ROWS" and result_type == "F16" and
            src0 == "F32" and src1 == "I64" and shape == (256, 256, 1, 1)):
        return ("rvv_cache_update", "calibration/decode/cache_set_rows_f32_f16")
    if (phase == "decode" and op == "GET_ROWS" and result_type == "F32" and
            src0 in ("F32", "Q4_K") and src1 == "I32" and shape == (1536, 1, 1, 1)):
        case = "get_rows_q4_k" if src0 == "Q4_K" else "get_rows_f32"
        return ("rvv_row_gather", f"calibration/decode/{case}")
    return None


def cycle_projection(
    qbs_node_rows: list[dict[str, object]],
    akv_rows: list[dict[str, object]],
    node_rows: list[dict[str, object]],
    qbs_points: list[dict[str, object]],
    akv_points: list[dict[str, int]],
    rvv_points: dict[str, int],
    qbs_lifetime: dict[str, object] | None = None,
    akv_prefill_points: list[dict[str, object]] | None = None,
):
    rows: list[dict[str, object]] = []
    akv_prefill_points = akv_prefill_points or []
    akv_calibration = describe_akv_calibration(akv_points)
    eliminated = Counter()
    if qbs_lifetime is not None:
        for record in qbs_lifetime["eliminated_quantizations"]:
            eliminated[
                (
                    str(record["op"]),
                    normalized_qbs_type(str(record["weight_type"])),
                    int(record["m"]),
                    int(record["n"]),
                    int(record["k"]),
                )
            ] += 1
    for node in qbs_node_rows:
        if node["activation_elements"] is None:
            raise ValueError(
                "RTL cycle projection requires exact per-node activation rows; "
                "the guest trace omits MUL_MAT_ID source shapes"
            )
        point = nearest_qbs_point(node, qbs_points)
        signature = (
            str(node["node_name"]),
            normalized_qbs_type(str(node["type"])),
            int(node["input_rows"]),
            int(node["output_rows"]),
            int(node["k"]),
        )
        quantization_applied = 1
        if eliminated[signature]:
            eliminated[signature] -= 1
            quantization_applied = 0
        quantize_cycles = (
            quantization_applied
            * int(node["activation_elements"])
            * float(point["quant_cycles_per_element"])
        )
        matmul_cycles = int(node["dot_elements"]) * float(point["matmul_cycles_per_dot"])
        cycles = quantize_cycles + matmul_cycles
        rows.append(
            {
                "phase": node["phase"],
                "category": "qbs",
                "detail": f"{node['node_name']} {node['type']} {node['mode']} K{node['k']} M{node['input_rows']} N{node['output_rows']}",
                "instances": 1,
                "projected_cycles": round(cycles),
                "quantization_applied": quantization_applied,
                "quantize_projected_cycles": round(quantize_cycles),
                "matmul_projected_cycles": round(matmul_cycles),
                "calibration": point["case"],
                "basis": (
                    "exact lifetime quantization decision plus exact dot work x representative RTL rates"
                    if qbs_lifetime is not None
                    else "per-node activation plus exact dot work x representative RTL rates"
                ),
            }
        )
    unmatched = {signature: count for signature, count in eliminated.items() if count}
    if unmatched:
        raise ValueError(f"QBS lifetime eliminations do not match dynamic model nodes: {unmatched}")
    accelerated_flash_nodes: Counter[tuple[int, str]] = Counter()
    for call in akv_rows:
        accelerated_flash_nodes[(int(call["graph_id"]), str(call["phase"]))] += int(call["calls"])
        if call["mode"] == "prefill":
            point = exact_akv_prefill_point(call, akv_prefill_points)
            if point is not None:
                rows.append(
                    {
                        "phase": call["phase"],
                        "category": "akv_v2_prefill",
                        "detail": (
                            f"AKV-v2 Prefill D{call['head_dim']} M{call['query_tokens']} "
                            f"P{call['past_tokens']} Hq{call['q_heads']} Hkv{call['kv_heads']}"
                        ),
                        "instances": call["calls"],
                        "projected_cycles": int(point["cycles"]) * int(call["calls"]),
                        "calibration": point["case_name"],
                        "basis": "exact shape-matched full-operator Prefill RTL x dynamic call count",
                    }
                )
                continue
            rows.append(
                {
                    "phase": call["phase"],
                    "category": "uncalibrated",
                    "detail": (
                        f"AKV-v2 Prefill D{call['head_dim']} M{call['query_tokens']} "
                        f"P{call['past_tokens']} Hq{call['q_heads']} Hkv{call['kv_heads']}"
                    ),
                    "instances": call["calls"],
                    "projected_cycles": "",
                    "calibration": "",
                    "basis": "matching full-operator Prefill RTL calibration required",
                }
            )
            continue
        per_call = interpolate_akv_cycles(int(call["active_kv"]), akv_points)
        rows.append(
            {
                "phase": call["phase"],
                "category": "akv_v2",
                "detail": (
                    f"D{call['head_dim']} KV{call['active_kv']} "
                    f"Hq{call['q_heads']} Hkv{call['kv_heads']} GQA{call['gqa_rows']}"
                ),
                "instances": call["calls"],
                "projected_cycles": round(per_call * int(call["calls"])),
                "calibration": akv_calibration,
                "basis": "dynamic active-KV x RTL interpolation",
            }
        )

    uncalibrated: Counter[tuple[str, str]] = Counter()
    for node in node_rows:
        phase = str(node["phase"])
        op = str(node["op"]).upper()
        src0 = normalized_qbs_type(str(node["src0"]))
        count = int(node["count"])
        if op == "MUL_MAT" and src0 in SUPPORTED_QBS_TYPES:
            continue
        if op == "FLASH_ATTN_EXT":
            accelerated_key = (int(node["graph_id"]), phase)
            accelerated = min(count, accelerated_flash_nodes[accelerated_key])
            accelerated_flash_nodes[accelerated_key] -= accelerated
            count -= accelerated
            if count == 0:
                continue
        classification = classify_rvv_node(node)
        if classification is None:
            uncalibrated[(phase, op)] += count
            continue
        category, case_id = classification
        if phase != "decode" or case_id not in rvv_points:
            uncalibrated[(phase, op)] += count
            continue
        rows.append(
            {
                "phase": phase,
                "category": category,
                "detail": case_id,
                "instances": count,
                "projected_cycles": rvv_points[case_id] * count,
                "calibration": case_id,
                "basis": "dynamic node count x real-model RTL leaf",
            }
        )
    for (phase, op), count in sorted(uncalibrated.items()):
        rows.append(
            {
                "phase": phase,
                "category": "uncalibrated",
                "detail": op,
                "instances": count,
                "projected_cycles": "",
                "calibration": "",
                "basis": "dynamic node count only",
            }
        )
    unmatched_attention = {
        key: count for key, count in accelerated_flash_nodes.items() if count
    }
    if unmatched_attention:
        raise ValueError(f"AKV calls do not match traced Flash-Attention nodes: {unmatched_attention}")
    return rows


def aggregate_projection(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    totals: defaultdict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"instances": 0, "cycles": 0})
    phase_cycles: Counter[str] = Counter()
    for row in rows:
        if row["projected_cycles"] == "":
            continue
        key = (str(row["phase"]), str(row["category"]))
        totals[key]["instances"] += int(row["instances"])
        totals[key]["cycles"] += int(row["projected_cycles"])
        phase_cycles[str(row["phase"])] += int(row["projected_cycles"])
    return [
        {
            "phase": phase,
            "category": category,
            "instances": values["instances"],
            "projected_cycles": values["cycles"],
            "share_of_calibrated_cycles": values["cycles"] / phase_cycles[phase] if phase_cycles[phase] else 0.0,
        }
        for (phase, category), values in sorted(totals.items())
    ]


def aggregate_components(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    incomplete_phases = {
        str(row["phase"])
        for row in rows
        if row["category"] == "uncalibrated"
    }
    totals: defaultdict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"instances": 0, "cycles": 0}
    )
    phase_cycles: Counter[str] = Counter()
    for row in rows:
        phase = str(row["phase"])
        if phase in incomplete_phases or row["projected_cycles"] == "":
            continue
        category = str(row["category"])
        component = category if category in {"qbs", "akv_v2"} else "rvv_remaining"
        key = (phase, component)
        totals[key]["instances"] += int(row["instances"])
        totals[key]["cycles"] += int(row["projected_cycles"])
        phase_cycles[phase] += int(row["projected_cycles"])
    return [
        {
            "phase": phase,
            "component": component,
            "instances": values["instances"],
            "projected_cycles": values["cycles"],
            "share_of_phase_cycles": values["cycles"] / phase_cycles[phase],
        }
        for (phase, component), values in sorted(totals.items())
    ]


def make_dynamic_summary(
    log: Path,
    run: ParsedRun,
    qbs_call_rows: list[dict[str, object]],
    qbs_node_rows: list[dict[str, object]],
    akv_rows: list[dict[str, object]],
    node_rows: list[dict[str, object]],
    qbs_lifetime: dict[str, object] | None,
) -> dict[str, object]:
    unresolved_activation_nodes = [
        row for row in qbs_node_rows if row["activation_elements"] is None
    ]
    known_activation_nodes = [
        row for row in qbs_node_rows if row["activation_elements"] is not None
    ]
    activation_accounting = {
        "complete": not unresolved_activation_nodes,
        "known_unique_activation_elements": sum(
            int(row["activation_elements"]) for row in known_activation_nodes
        ),
        "known_per_operation_quantized_activation_bytes": sum(
            int(row["quantized_activation_bytes"]) for row in known_activation_nodes
        ),
        "unresolved_nodes": len(unresolved_activation_nodes),
        "unresolved_operations": dict(Counter(
            str(row["operation"]) for row in unresolved_activation_nodes
        )),
    }
    akv_unique_kv_bytes = sum(int(row["unique_kv_payload_bytes"]) for row in akv_rows)
    akv_streamed_kv_bytes = sum(int(row["kv_payload_bytes"]) for row in akv_rows)
    return {
        "provenance": {
            "tool": {
                "path": str(Path(__file__).resolve()),
                "sha256": sha256(Path(__file__).resolve()),
                "projection_method_version": PROJECTION_METHOD_VERSION,
            },
            "dynamic_log": {
                "path": str(log.resolve()),
                "sha256": sha256(log),
            },
            "qbs_abi": {
                "path": str(QBS_ABI_PATH.resolve()),
                "sha256": sha256(QBS_ABI_PATH),
                "architecture_version": QBS_ABI.get("architecture_version"),
            },
            "run_manifest": read_manifest(log.parent / "manifest.txt"),
        },
        "functional": {
            "guest_exit": run.guest_exit,
            "output_equal": run.output_equal,
            "logits_top1_equal": run.logits.get("AKV_LOGITS_TOP1_EQUAL"),
            "logits_max_abs": run.logits.get("AKV_LOGITS_MAX_ABS"),
            "akv_qbs": run.logits,
            "qbs_rvv": run.qbs_rvv,
        },
        "graphs": dict(Counter(graph.phase for graph in run.graphs)),
        "qbs": {
            "nodes": len(qbs_node_rows),
            "operations": dict(Counter(str(row["operation"]) for row in qbs_node_rows)),
            "call_chunks": sum(int(row["calls"]) for row in qbs_call_rows),
            "unique_activation_elements": (
                activation_accounting["known_unique_activation_elements"]
                if activation_accounting["complete"] else None
            ),
            "output_elements": sum(int(row["output_elements"]) for row in qbs_node_rows),
            "dot_elements": sum(int(row["dot_elements"]) for row in qbs_node_rows),
            "per_operation_quantized_activation_bytes": (
                activation_accounting["known_per_operation_quantized_activation_bytes"]
                if activation_accounting["complete"] else None
            ),
            "activation_accounting": activation_accounting,
            "weight_payload_bytes": sum(
                int(row["weight_payload_bytes"]) for row in qbs_call_rows
            ),
            "weight_payload_bytes_by_phase": {
                phase: sum(
                    int(row["weight_payload_bytes"])
                    for row in qbs_call_rows
                    if row["phase"] == phase
                )
                for phase in ("prefill", "decode")
            },
            "weight_payload_bytes_by_profile": {
                profile: sum(
                    int(row["weight_payload_bytes"])
                    for row in qbs_call_rows
                    if row["type"] == profile
                )
                for profile in sorted({str(row["type"]) for row in qbs_call_rows})
            },
            "coverage": run.qbs_coverage,
            "execution": run.qbs_exec,
            "activation_lifetime": qbs_lifetime,
        },
        "akv_v2": {
            "calls": sum(int(row["calls"]) for row in akv_rows),
            "calls_by_mode": aggregate_call_counts_by_mode(akv_rows),
            "attention_macs": sum(int(row["attention_macs"]) for row in akv_rows),
            "attention_pairs": sum(int(row["attention_pairs"]) for row in akv_rows),
            "query_source_f32_bytes": sum(
                int(row["query_source_f32_bytes"]) for row in akv_rows
            ),
            "query_payload_bytes": sum(
                int(row["query_payload_bytes"]) for row in akv_rows
            ),
            "unique_kv_payload_bytes": akv_unique_kv_bytes,
            "kv_payload_bytes": akv_streamed_kv_bytes,
            "kv_reread_factor": (
                akv_streamed_kv_bytes / akv_unique_kv_bytes
                if akv_unique_kv_bytes else None
            ),
            "shapes": akv_rows,
            "coverage": run.akv_coverage,
        },
        "model_nodes": sum(int(row["count"]) for row in node_rows),
    }


def write_dynamic_markdown(
    path: Path,
    run: ParsedRun,
    qbs_call_rows: list[dict[str, object]],
    qbs_node_rows: list[dict[str, object]],
    akv_rows: list[dict[str, object]],
    manifest: dict[str, str],
    qbs_lifetime: dict[str, object] | None,
) -> None:
    lines = [
        "# QBS + AKV-v2 Dynamic Model Closure",
        "",
        f"Model: `{manifest.get('MODEL_GUEST_PATH', 'unknown')}`",
        "",
        "All counts below come from the traced guest execution. No QEMU wall time",
        "or shape-mismatched RTL calibration is interpreted as hardware cycles.",
        "",
        "| Phase | Graphs | QBS nodes | QBS chunks | QBS weight bytes | QBS dot elements | AKV calls | AKV Q bytes | AKV K/V bytes | AKV MACs |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for phase in ("prefill", "decode"):
        graphs = [graph for graph in run.graphs if graph.phase == phase]
        lines.append(
            f"| {phase} | {len(graphs)} | "
            f"{sum(row['phase'] == phase for row in qbs_node_rows)} | "
            f"{sum(int(row['calls']) for row in qbs_call_rows if row['phase'] == phase)} | "
            f"{sum(int(row['weight_payload_bytes']) for row in qbs_call_rows if row['phase'] == phase)} | "
            f"{sum(int(row['dot_elements']) for row in qbs_node_rows if row['phase'] == phase)} | "
            f"{sum(int(row['calls']) for row in akv_rows if row['phase'] == phase)} | "
            f"{sum(int(row['query_payload_bytes']) for row in akv_rows if row['phase'] == phase)} | "
            f"{sum(int(row['kv_payload_bytes']) for row in akv_rows if row['phase'] == phase)} | "
            f"{sum(int(row['attention_macs']) for row in akv_rows if row['phase'] == phase)} |"
        )
    lines.extend(
        [
            "",
            "| Phase | Mode | Kernel | D | M | P | GQA | Q heads | KV heads | Active KV | Calls | Q F32 bytes | Q context bytes | Unique K/V bytes | Streamed K/V bytes | K/V reread | MACs |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in akv_rows:
        lines.append(
            f"| {row['phase']} | {row['mode']} | {row['kernel']} | {row['head_dim']} | "
            f"{row['query_tokens']} | {row['past_tokens'] if row['past_tokens'] is not None else '-'} | "
            f"{row['gqa_rows']} | {row['q_heads']} | {row['kv_heads']} | {row['active_kv']} | "
            f"{row['calls']} | {row['query_source_f32_bytes']} | {row['query_payload_bytes']} | "
            f"{row['unique_kv_payload_bytes']} | {row['kv_payload_bytes']} | "
            f"{float(row['kv_reread_factor']):.3f} | {row['attention_macs']} |"
        )
    if qbs_lifetime is not None:
        baseline = qbs_lifetime["baseline"]
        optimized = qbs_lifetime["cross_operator"]
        lines.extend(
            [
                "",
                "Exact QBS activation-lifetime accounting:",
                "",
                "| Metric | Per-operation | Cross-operator | Eliminated |",
                "|---|---:|---:|---:|",
                f"| Quantizations | {baseline['quantizations']} | {optimized['quantizations']} | {optimized['quantizations_eliminated']} |",
                f"| Quantized activation bytes | {baseline['activation_bytes']} | {optimized['activation_bytes']} | {optimized['activation_bytes_eliminated']} |",
                f"| F32 quantization-input bytes | {baseline['quantization_input_bytes']} | {optimized['quantization_input_bytes']} | {optimized['quantization_input_bytes_eliminated']} |",
            ]
        )
    lines.extend(
        [
            "",
            "Functional gates:",
            "",
            f"- guest exit: `{run.guest_exit}`",
            f"- output equal: `{int(run.output_equal)}`",
            f"- logits top-1 equal: `{run.logits.get('AKV_LOGITS_TOP1_EQUAL', 'missing')}`",
            f"- logits max absolute difference: `{run.logits.get('AKV_LOGITS_MAX_ABS', 'missing')}`",
            f"- logits mean absolute difference: `{run.logits.get('AKV_LOGITS_MEAN_ABS', 'missing')}`",
            f"- logits mean RMSE: `{run.logits.get('AKV_LOGITS_MEAN_RMSE', 'missing')}`",
            f"- logits mean KL divergence: `{run.logits.get('AKV_LOGITS_MEAN_KL', 'missing')}`",
            f"- logits mean cosine similarity: `{run.logits.get('AKV_LOGITS_MEAN_COSINE', 'missing')}`",
            f"- logits mean Top-5 overlap: `{run.logits.get('AKV_LOGITS_TOP5_OVERLAP', 'missing')}`",
            "",
            "This artifact proves dynamic selection, numerical behavior, and work/traffic",
            "identities. Weight and Q/K/V byte counts are logical payload bytes from the",
            "QBS ABI and AKV F16 contract; descriptor, cache-line overfetch, and output traffic",
            "are not included. This artifact deliberately omits a cycle projection until matching RTL shape",
            "calibration exists.",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def write_markdown(
    path: Path,
    run: ParsedRun,
    qbs_call_rows: list[dict[str, object]],
    qbs_node_rows: list[dict[str, object]],
    akv_rows: list[dict[str, object]],
    component_summary: list[dict[str, object]],
    projection_summary: list[dict[str, object]],
    projection_rows: list[dict[str, object]],
    qbs_lifetime: dict[str, object] | None,
) -> None:
    qbs_work = Counter()
    qbs_activation_work = Counter()
    qbs_weight_bytes = Counter()
    for row in qbs_node_rows:
        qbs_work[str(row["phase"])] += int(row["dot_elements"])
        qbs_activation_work[str(row["phase"])] += int(row["activation_elements"])
    akv_work = Counter()
    akv_query_bytes = Counter()
    akv_kv_bytes = Counter()
    for row in qbs_call_rows:
        qbs_weight_bytes[str(row["phase"])] += int(row["weight_payload_bytes"])
    for row in akv_rows:
        akv_work[str(row["phase"])] += int(row["attention_macs"])
        akv_query_bytes[str(row["phase"])] += int(row["query_payload_bytes"])
        akv_kv_bytes[str(row["phase"])] += int(row["kv_payload_bytes"])
    missing = Counter()
    for row in projection_rows:
        if row["category"] == "uncalibrated":
            missing[(str(row["phase"]), str(row["detail"]))] += int(row["instances"])

    lines = [
        "# QBS + AKV-v2 Model Closure",
        "",
        "The dynamic counts below come directly from one real Qwen2.5 guest execution. The cycle table is an",
        "RTL-calibrated projection, not a full-model RTL simulation and not QEMU wall time.",
        "",
        "## Dynamic execution",
        "",
        "| Phase | Graphs | QBS nodes | QBS chunks | Unique activation elements | QBS weight bytes | QBS dot elements | AKV-v2 calls | AKV Q bytes | AKV K/V bytes | AKV attention MACs |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for phase in ("prefill", "decode"):
        graphs = [graph for graph in run.graphs if graph.phase == phase]
        lines.append(
            f"| {phase} | {len(graphs)} | {sum(1 for row in qbs_node_rows if row['phase'] == phase)} | "
            f"{sum(int(row['calls']) for row in qbs_call_rows if row['phase'] == phase)} | "
            f"{qbs_activation_work[phase]} | {qbs_weight_bytes[phase]} | {qbs_work[phase]} | "
            f"{sum(len(graph.akv_calls) for graph in graphs)} | {akv_query_bytes[phase]} | "
            f"{akv_kv_bytes[phase]} | {akv_work[phase]} |"
        )
    if qbs_lifetime is not None:
        baseline = qbs_lifetime["baseline"]
        optimized = qbs_lifetime["cross_operator"]
        lines.extend(
            [
                "",
                "## Exact activation-lifetime accounting",
                "",
                "| Metric | Per-operation | Cross-operator | Eliminated |",
                "|---|---:|---:|---:|",
                f"| Quantizations | {baseline['quantizations']} | {optimized['quantizations']} | {optimized['quantizations_eliminated']} |",
                f"| Quantized activation bytes | {baseline['activation_bytes']} | {optimized['activation_bytes']} | {optimized['activation_bytes_eliminated']} |",
                f"| F32 quantization-input bytes | {baseline['quantization_input_bytes']} | {optimized['quantization_input_bytes']} | {optimized['quantization_input_bytes_eliminated']} |",
                "",
                "The lifetime run is accepted only when its model, prompt, token count, llama binary, model image, and QEMU binary match this combined run.",
            ]
        )
    lines.extend(
        [
            "",
            "## Complete-phase component attribution",
            "",
            "Only phases with no uncalibrated traced compute node appear here.",
            "",
            "| Phase | Component | Instances | Projected cycles | Share of phase cycles |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for row in component_summary:
        lines.append(
            f"| {row['phase']} | {row['component']} | {row['instances']} | "
            f"{row['projected_cycles']} | {100.0 * float(row['share_of_phase_cycles']):.2f}% |"
        )
    lines.extend(
        [
            "",
            "## RTL-calibrated cycle projection",
            "",
            "Shares are normalized only over calibrated categories. Uncalibrated graph nodes are listed separately.",
            "",
            "| Phase | Category | Instances | Projected cycles | Share of calibrated cycles |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for row in projection_summary:
        lines.append(
            f"| {row['phase']} | {row['category']} | {row['instances']} | {row['projected_cycles']} | "
            f"{100.0 * float(row['share_of_calibrated_cycles']):.2f}% |"
        )
    lines.extend(["", "## Uncalibrated dynamic nodes", ""])
    if missing:
        lines.extend(["| Phase | GGML op | Executed nodes |", "|---|---|---:|"])
        for (phase, op), count in sorted(missing.items()):
            lines.append(f"| {phase} | {op} | {count} |")
    else:
        lines.append("All traced compute nodes have a representative calibration.")
    lines.extend(
        [
            "",
            "## Interpretation constraints",
            "",
            "- `QBS_CALL` counts execution chunks; `qbs_nodes.csv` reconstructs their owning high-level `MUL_MAT` nodes.",
            "- QBS weight and AKV Q/K/V traffic are exact logical payload bytes. They exclude descriptors, cache-line overfetch, writeback, and local context replay.",
            (
                "- Activation quantization follows the exact cross-operator lifetime trace; eliminated nodes retain their matrix work but carry zero quantization cost."
                if qbs_lifetime is not None
                else "- Activation quantization is charged once per high-level QBS node, not once per output-row chunk."
            ),
            "- QBS/RVV is a numerical-quality observation. After a free-running Top-1 divergence, later logits use different contexts and are excluded from its error extrema.",
            "- AKV equivalence is strict: QBS-only and QBS+AKV-v2 use the same generated context and must retain equal output, Top-1, and bounded logits error.",
            "- QBS dot elements and AKV MACs are exact dynamic work counts, but they are not mutually comparable cycle units.",
            "- Projection rates come from representative standalone RTL kernels with real model data.",
            "- The projection does not claim full-model RTL timing and excludes scheduler, sampling, OS, and uncalibrated-node cost.",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--qbs-calibration",
        type=Path,
        default=root / "hardware/qbs_eval_runs/latest/results.csv",
    )
    parser.add_argument(
        "--akv-calibration",
        type=Path,
        default=root / "hardware/llama_attention_runs_akv_v2/attention_core_summary.csv",
    )
    parser.add_argument(
        "--akv-prefill-calibration",
        type=Path,
        action="append",
        default=[],
        help="strict analyze_prefill_attention.py summary; repeat for exact full-operator RTL points",
    )
    parser.add_argument(
        "--rvv-calibration-dir",
        type=Path,
        action="append",
        help="RVV leaf-calibration directory; repeat to combine directories",
    )
    parser.add_argument(
        "--require-complete-phase",
        action="append",
        default=["decode"],
        help="fail when a phase still contains an uncalibrated traced compute node",
    )
    parser.add_argument(
        "--dynamic-only",
        action="store_true",
        help="write measured coverage/work artifacts without applying RTL cycle calibration",
    )
    parser.add_argument(
        "--qbs-lifetime-summary",
        type=Path,
        help="strict paired QBS lifetime summary from the same model, prompt, binaries, and QEMU",
    )
    args = parser.parse_args()
    output = args.output_dir or args.log.parent / "model_closure"
    output.mkdir(parents=True, exist_ok=True)

    run = parse_log(args.log)
    validate_dynamic(run)
    qbs_call_rows, qbs_node_rows, akv_rows, node_rows = dynamic_rows(run)
    model_manifest = read_manifest(args.log.parent / "manifest.txt")
    qbs_lifetime = load_qbs_lifetime_summary(args.qbs_lifetime_summary, model_manifest)

    write_csv(
        output / "qbs_calls.csv",
        qbs_call_rows,
        (
            "graph_id", "phase", "node_index", "node_name", "operation", "type", "mode",
            "k", "input_rows", "output_rows", "calls", "activation_profile",
            "quantized_activation_bytes", "weight_payload_bytes",
        ),
    )
    write_csv(
        output / "qbs_nodes.csv",
        qbs_node_rows,
        (
            "graph_id", "phase", "node_index", "node_name", "operation", "type", "mode",
            "k", "input_rows", "activation_rows", "activation_accounting", "output_rows",
            "call_chunks", "activation_profile",
            "quantized_activation_bytes", "weight_payload_bytes",
        ),
    )
    write_csv(
        output / "akv_calls.csv",
        akv_rows,
        (
            "graph_id", "phase", "mode", "kernel", "head_dim", "query_tokens",
            "past_tokens", "kv_capacity", "gqa_rows", "q_heads", "kv_heads",
            "active_kv", "groups", "calls", "attention_pairs",
            "query_source_f32_bytes", "query_payload_bytes",
            "unique_kv_payload_bytes", "kv_payload_bytes", "kv_reread_factor",
        ),
    )
    write_csv(
        output / "model_nodes.csv",
        node_rows,
        ("graph_id", "phase", "semantic", "op", "type", "name", "count"),
    )
    dynamic_summary = make_dynamic_summary(
        args.log, run, qbs_call_rows, qbs_node_rows, akv_rows, node_rows, qbs_lifetime
    )
    (output / "dynamic_summary.json").write_text(
        json.dumps(dynamic_summary, indent=2) + "\n"
    )
    if args.dynamic_only:
        write_dynamic_markdown(
            output / "model_closure.md",
            run,
            qbs_call_rows,
            qbs_node_rows,
            akv_rows,
            model_manifest,
            qbs_lifetime,
        )
        print(output)
        return

    qbs_points = load_qbs_calibration(args.qbs_calibration)
    akv_points = load_akv_calibration(args.akv_calibration)
    akv_prefill_points = load_akv_prefill_calibration(args.akv_prefill_calibration)
    rvv_directories = args.rvv_calibration_dir or default_rvv_calibration_dirs(root)
    rvv_points, rvv_sources = load_rvv_calibration(rvv_directories)
    projection_rows = cycle_projection(
        qbs_node_rows,
        akv_rows,
        node_rows,
        qbs_points,
        akv_points,
        rvv_points,
        qbs_lifetime,
        akv_prefill_points,
    )
    incomplete = {
        str(row["phase"])
        for row in projection_rows
        if row["category"] == "uncalibrated"
    }
    missing_required = sorted(set(args.require_complete_phase) & incomplete)
    if missing_required:
        raise ValueError(
            "uncalibrated compute nodes remain in required phase(s): "
            + ", ".join(missing_required)
        )
    projection_summary = aggregate_projection(projection_rows)
    component_summary = aggregate_components(projection_rows)

    write_csv(
        output / "cycle_projection_detail.csv",
        projection_rows,
        (
            "phase", "category", "detail", "instances", "projected_cycles",
            "quantization_applied", "quantize_projected_cycles",
            "matmul_projected_cycles", "calibration", "basis",
        ),
    )
    write_csv(
        output / "cycle_projection_summary.csv",
        projection_summary,
        ("phase", "category", "instances", "projected_cycles", "share_of_calibrated_cycles"),
    )
    write_csv(
        output / "cycle_projection_components.csv",
        component_summary,
        ("phase", "component", "instances", "projected_cycles", "share_of_phase_cycles"),
    )

    calibration_snapshot = {
        "projection_method_version": PROJECTION_METHOD_VERSION,
        "required_complete_phases": args.require_complete_phase,
        "sources": {
            "tool": {
                "path": str(Path(__file__).resolve()),
                "sha256": sha256(Path(__file__).resolve()),
            },
            "dynamic_log": {
                "path": str(args.log.resolve()),
                "sha256": sha256(args.log),
            },
            "run_manifest": {
                "path": str((args.log.parent / "manifest.txt").resolve()),
                "sha256": sha256(args.log.parent / "manifest.txt")
                if (args.log.parent / "manifest.txt").is_file()
                else None,
                "values": read_manifest(args.log.parent / "manifest.txt"),
            },
            "qbs": {"path": str(args.qbs_calibration.resolve()), "sha256": sha256(args.qbs_calibration)},
            "akv": {"path": str(args.akv_calibration.resolve()), "sha256": sha256(args.akv_calibration)},
            "akv_prefill": [point["source"] for point in akv_prefill_points],
            "rvv": rvv_sources,
        },
        "qbs_points": qbs_points,
        "akv_points": akv_points,
        "akv_prefill_points": akv_prefill_points,
        "rvv_points": rvv_points,
    }
    (output / "calibration_snapshot.json").write_text(json.dumps(calibration_snapshot, indent=2) + "\n")
    write_markdown(
        output / "model_closure.md",
        run,
        qbs_call_rows,
        qbs_node_rows,
        akv_rows,
        component_summary,
        projection_summary,
        projection_rows,
        qbs_lifetime,
    )
    print(output)


if __name__ == "__main__":
    main()

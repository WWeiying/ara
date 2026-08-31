#!/usr/bin/env python3

"""Summarize one combined QBS + AKV-v2 Qwen model run.

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


def fields(line: str) -> dict[str, str]:
    return dict(FIELD_RE.findall(line))


def integer(values: dict[str, str], key: str, default: int = 0) -> int:
    return int(values.get(key, default))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
            return "decode"
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
    if run.logits.get("AKV_LOGITS_TOP1_EQUAL") != "1":
        raise ValueError("combined model run changed top-1 logits result")
    if integer(run.qbs_rvv, "QBS_RVV_LOGITS_RECORDS") == 0 or \
       integer(run.qbs_rvv, "QBS_RVV_LOGITS_COMPARABLE_RECORDS") == 0:
        raise ValueError("QBS/RVV model-quality observation has no comparable logits record")

    qbs_calls: defaultdict[str, int] = defaultdict(int)
    for graph in run.graphs:
        for call in graph.qbs_calls:
            profile = normalized_qbs_type(call["type"])
            node_index = integer(call, "_node_index", -1)
            if node_index < 0 or node_index >= len(graph.nodes):
                raise ValueError("QBS call has no valid model-node owner")
            node = graph.nodes[node_index]
            if node.get("op") != "MUL_MAT" or normalized_qbs_type(node.get("src0", "")) != profile:
                raise ValueError("QBS call/model-node association is inconsistent")
            qbs_calls[profile] += (
                integer(call, "k") * integer(call, "input_rows") * integer(call, "output_rows")
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

    akv_calls = [call for graph in run.graphs for call in graph.akv_calls]
    if not akv_calls or any(call.get("kernel") != "v2" for call in akv_calls):
        raise ValueError("AKV-v2 did not execute for every accelerated attention call")
    akv_macs = sum(integer(call, "attention_macs") for call in akv_calls)
    if integer(run.akv_coverage, "attention_macs") != akv_macs:
        raise ValueError("AKV call/coverage MAC count mismatch")
    if integer(run.akv_coverage, "executed_v1") != 0:
        raise ValueError("combined run unexpectedly executed AKV-v1")


def write_csv(path: Path, rows: list[dict[str, object]], leading: Iterable[str]) -> None:
    leading = list(leading)
    remaining = sorted({key for row in rows for key in row} - set(leading))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=leading + remaining)
        writer.writeheader()
        writer.writerows(rows)


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
                normalized_qbs_type(call["type"]),
                call["mode"],
                integer(call, "k"),
                integer(call, "input_rows"),
                integer(call, "output_rows"),
                integer(call, "split_k"),
            )
            qbs_groups[key] += 1
        for call in graph.akv_calls:
            key = (
                graph.graph_id,
                phase,
                call["kernel"],
                integer(call, "kv_heads"),
                integer(call, "q_rows"),
                integer(call, "active_kv"),
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
        graph_id, phase, node_index, node_name, profile, mode, k, input_rows, output_rows, split_k = key
        qbs_rows.append(
            {
                "graph_id": graph_id,
                "phase": phase,
                "node_index": node_index,
                "node_name": node_name,
                "type": profile,
                "mode": mode,
                "k": k,
                "input_rows": input_rows,
                "output_rows": output_rows,
                "split_k": split_k,
                "calls": count,
                "activation_row_uses": count * input_rows,
                "activation_element_uses": count * k * input_rows,
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
            qbs_node_rows.append(
                {
                    "graph_id": graph.graph_id,
                    "phase": graph.phase,
                    "node_index": node_index,
                    "node_name": normalize_tensor_name(node.get("name", "")),
                    "type": profile,
                    "mode": mode,
                    "k": k,
                    "input_rows": input_rows,
                    "output_rows": output_rows,
                    "call_chunks": len(calls),
                    "activation_elements": k * input_rows,
                    "output_elements": output_elements,
                    "dot_elements": dot_elements,
                }
            )
    akv_rows = []
    for key, count in sorted(akv_groups.items()):
        graph_id, phase, kernel, kv_heads, q_rows, active_kv, attention_macs = key
        akv_rows.append(
            {
                "graph_id": graph_id,
                "phase": phase,
                "kernel": kernel,
                "kv_heads": kv_heads,
                "q_rows": q_rows,
                "active_kv": active_kv,
                "calls": count,
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
    mapping = {
        "attention_norm": ("rvv_norm", "operator/decode/attention_norm"),
        "ffn_norm": ("rvv_norm", "operator/decode/ffn_norm"),
        "final_norm": ("rvv_norm", "operator/decode/attention_norm"),
        "rope_q": ("rvv_rope", "operator/decode/rope_q"),
        "rope_k": ("rvv_rope", "operator/decode/rope_k"),
        "attention_residual": ("rvv_residual", "operator/decode/attention_residual"),
        "ffn_residual": ("rvv_residual", "operator/decode/ffn_residual"),
        "ffn_activation": ("rvv_activation", "operator/decode/ffn_activation"),
    }
    return mapping.get(semantic)


def cycle_projection(
    qbs_node_rows: list[dict[str, object]],
    akv_rows: list[dict[str, object]],
    node_rows: list[dict[str, object]],
    qbs_points: list[dict[str, object]],
    akv_points: list[dict[str, int]],
    rvv_points: dict[str, int],
):
    rows: list[dict[str, object]] = []
    for node in qbs_node_rows:
        point = nearest_qbs_point(node, qbs_points)
        cycles = (
            int(node["activation_elements"]) * float(point["quant_cycles_per_element"])
            + int(node["dot_elements"]) * float(point["matmul_cycles_per_dot"])
        )
        rows.append(
            {
                "phase": node["phase"],
                "category": "qbs",
                "detail": f"{node['node_name']} {node['type']} {node['mode']} K{node['k']} M{node['input_rows']} N{node['output_rows']}",
                "instances": 1,
                "projected_cycles": round(cycles),
                "calibration": point["case"],
                "basis": "unique activation plus exact dot work x representative RTL rates",
            }
        )
    for call in akv_rows:
        per_call = interpolate_akv_cycles(int(call["active_kv"]), akv_points)
        rows.append(
            {
                "phase": call["phase"],
                "category": "akv_v2",
                "detail": f"KV{call['active_kv']} Hq{call['q_rows']} Hkv{call['kv_heads']}",
                "instances": call["calls"],
                "projected_cycles": round(per_call * int(call["calls"])),
                "calibration": "piecewise AKV-v2 KV16/KV128/KV256 RTL",
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
        if op == "FLASH_ATTN_EXT" and phase == "decode":
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


def write_markdown(
    path: Path,
    run: ParsedRun,
    qbs_call_rows: list[dict[str, object]],
    qbs_node_rows: list[dict[str, object]],
    akv_rows: list[dict[str, object]],
    projection_summary: list[dict[str, object]],
    projection_rows: list[dict[str, object]],
) -> None:
    qbs_work = Counter()
    qbs_activation_work = Counter()
    for row in qbs_node_rows:
        qbs_work[str(row["phase"])] += int(row["dot_elements"])
        qbs_activation_work[str(row["phase"])] += int(row["activation_elements"])
    akv_work = Counter()
    for row in akv_rows:
        akv_work[str(row["phase"])] += int(row["attention_macs"])
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
        "| Phase | Graphs | QBS nodes | QBS chunks | Unique activation elements | QBS dot elements | AKV-v2 calls | AKV attention MACs |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for phase in ("prefill", "decode"):
        graphs = [graph for graph in run.graphs if graph.phase == phase]
        lines.append(
            f"| {phase} | {len(graphs)} | {sum(1 for row in qbs_node_rows if row['phase'] == phase)} | "
            f"{sum(int(row['calls']) for row in qbs_call_rows if row['phase'] == phase)} | "
            f"{qbs_activation_work[phase]} | {qbs_work[phase]} | "
            f"{sum(len(graph.akv_calls) for graph in graphs)} | {akv_work[phase]} |"
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
            "- Activation quantization is charged once per high-level QBS node, not once per output-row chunk.",
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
        "--rvv-calibration-dir",
        type=Path,
        action="append",
        help="RVV leaf-calibration directory; repeat to combine directories",
    )
    args = parser.parse_args()
    output = args.output_dir or args.log.parent / "model_closure"
    output.mkdir(parents=True, exist_ok=True)

    run = parse_log(args.log)
    validate_dynamic(run)
    qbs_call_rows, qbs_node_rows, akv_rows, node_rows = dynamic_rows(run)
    qbs_points = load_qbs_calibration(args.qbs_calibration)
    akv_points = load_akv_calibration(args.akv_calibration)
    rvv_directories = args.rvv_calibration_dir or default_rvv_calibration_dirs(root)
    rvv_points, rvv_sources = load_rvv_calibration(rvv_directories)
    projection_rows = cycle_projection(
        qbs_node_rows,
        akv_rows,
        node_rows,
        qbs_points,
        akv_points,
        rvv_points,
    )
    projection_summary = aggregate_projection(projection_rows)

    write_csv(
        output / "qbs_calls.csv",
        qbs_call_rows,
        (
            "graph_id",
            "phase",
            "node_index",
            "node_name",
            "type",
            "mode",
            "k",
            "input_rows",
            "output_rows",
            "calls",
        ),
    )
    write_csv(
        output / "qbs_nodes.csv",
        qbs_node_rows,
        (
            "graph_id",
            "phase",
            "node_index",
            "node_name",
            "type",
            "mode",
            "k",
            "input_rows",
            "output_rows",
            "call_chunks",
        ),
    )
    write_csv(
        output / "akv_calls.csv",
        akv_rows,
        ("graph_id", "phase", "kernel", "active_kv", "kv_heads", "q_rows", "calls"),
    )
    write_csv(
        output / "model_nodes.csv",
        node_rows,
        ("graph_id", "phase", "semantic", "op", "type", "name", "count"),
    )
    write_csv(
        output / "cycle_projection_detail.csv",
        projection_rows,
        ("phase", "category", "detail", "instances", "projected_cycles", "calibration", "basis"),
    )
    write_csv(
        output / "cycle_projection_summary.csv",
        projection_summary,
        ("phase", "category", "instances", "projected_cycles", "share_of_calibrated_cycles"),
    )

    dynamic_summary = {
        "functional": {
            "guest_exit": run.guest_exit,
            "output_equal": run.output_equal,
            "logits_top1_equal": run.logits.get("AKV_LOGITS_TOP1_EQUAL"),
            "logits_max_abs": run.logits.get("AKV_LOGITS_MAX_ABS"),
            "qbs_rvv": run.qbs_rvv,
        },
        "graphs": Counter(graph.phase for graph in run.graphs),
        "qbs": {
            "nodes": len(qbs_node_rows),
            "call_chunks": sum(int(row["calls"]) for row in qbs_call_rows),
            "unique_activation_elements": sum(
                int(row["activation_elements"]) for row in qbs_node_rows
            ),
            "output_elements": sum(int(row["output_elements"]) for row in qbs_node_rows),
            "dot_elements": sum(int(row["dot_elements"]) for row in qbs_node_rows),
            "coverage": run.qbs_coverage,
            "execution": run.qbs_exec,
        },
        "akv_v2": {
            "calls": sum(int(row["calls"]) for row in akv_rows),
            "attention_macs": sum(int(row["attention_macs"]) for row in akv_rows),
            "coverage": run.akv_coverage,
        },
        "model_nodes": sum(int(row["count"]) for row in node_rows),
    }
    (output / "dynamic_summary.json").write_text(json.dumps(dynamic_summary, indent=2) + "\n")

    calibration_snapshot = {
        "sources": {
            "qbs": {"path": str(args.qbs_calibration.resolve()), "sha256": sha256(args.qbs_calibration)},
            "akv": {"path": str(args.akv_calibration.resolve()), "sha256": sha256(args.akv_calibration)},
            "rvv": rvv_sources,
        },
        "qbs_points": qbs_points,
        "akv_points": akv_points,
        "rvv_points": rvv_points,
    }
    (output / "calibration_snapshot.json").write_text(json.dumps(calibration_snapshot, indent=2) + "\n")
    write_markdown(
        output / "model_closure.md",
        run,
        qbs_call_rows,
        qbs_node_rows,
        akv_rows,
        projection_summary,
        projection_rows,
    )
    print(output)


if __name__ == "__main__":
    main()

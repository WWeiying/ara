#!/usr/bin/env python3

"""Shared parsing and accounting for context-length model traces."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
AKV_ABI_PATH = ROOT / "config/akv_abi.json"
AKV_ABI = json.loads(AKV_ABI_PATH.read_text(encoding="utf-8"))
FIELD_RE = re.compile(r"([A-Za-z0-9_]+)=([^\s]+)")
TOKEN_COUNT_RE = re.compile(r"Total number of tokens:\s*(\d+)")
PROMPT_EVAL_RE = re.compile(r"prompt eval time\s*=.*?/\s*(\d+)\s+tokens")
SUPPORTED_QBS_TYPES = {
    "Q2_K", "Q3_K", "Q4_K", "Q5_K", "Q6_K",
    "Q4_0", "Q5_0", "Q8_0", "IQ4_NL",
}
QBS_TRACE_TO_ABI = {"Q8_0": "Q8_0_WEIGHT"}
SUPPORTED_AKV_D = set(AKV_ABI["token_axis_profile"]["head_dims"])
SUPPORTED_AKV_GQA = set(range(1, int(AKV_ABI["limits"]["max_q_rows"]) + 1))
BASE_PROMPT = (
    "Explain why low-bit vector inference benefits from packed arithmetic "
    "and data reuse."
)
TRACE_MARKERS = (
    "GGML_RISCV_MODEL_GRAPH_BEGIN ",
    "GGML_RISCV_MODEL_NODE ",
    "GGML_RISCV_MODEL_GRAPH_END ",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fields(line: str) -> dict[str, str]:
    values = dict(FIELD_RE.findall(line))
    if " name=" in line:
        values["name"] = line.split(" name=", 1)[1]
    return values


def integer(values: dict[str, str], key: str) -> int:
    try:
        return int(values[key])
    except (KeyError, ValueError) as error:
        raise ValueError(f"missing or invalid {key}: {values}") from error


def trace_record(line: str) -> tuple[str, str] | None:
    """Extract one trace record despite stdout text prefixed to stderr."""
    matches = [(line.find(marker), marker) for marker in TRACE_MARKERS if marker in line]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"multiple model trace records on one line: {line}")
    offset, marker = matches[0]
    return marker, line[offset:]


@dataclass
class Graph:
    graph_id: int
    declared_nodes: int
    nodes: list[dict[str, str]] = field(default_factory=list)
    closed: bool = False


def select_trace_region(lines: list[str], run_label: str | None = None) -> list[str]:
    if run_label is None:
        return lines
    begin = f"AKV_TOKEN_RUN_BEGIN={run_label}"
    end = f"AKV_TOKEN_RUN_EXIT={run_label}:"
    starts = [index for index, line in enumerate(lines) if line.strip() == begin]
    if len(starts) != 1:
        raise ValueError(f"expected one {begin}, found {len(starts)}")
    for index in range(starts[0] + 1, len(lines)):
        if lines[index].strip().startswith(end):
            return lines[starts[0] + 1:index + 1]
    raise ValueError(f"missing {end}")


def parse_graphs(path: Path, run_label: str | None = None) -> list[Graph]:
    lines = path.read_text(errors="replace").splitlines()
    lines = select_trace_region(lines, run_label)
    graphs: list[Graph] = []
    current: Graph | None = None
    for line in lines:
        record = trace_record(line)
        if record is None:
            continue
        marker, payload = record
        if marker == "GGML_RISCV_MODEL_GRAPH_BEGIN ":
            if current is not None:
                raise ValueError("nested model graph trace")
            values = fields(payload)
            current = Graph(integer(values, "id"), integer(values, "nodes"))
        elif marker == "GGML_RISCV_MODEL_NODE ":
            if current is None:
                raise ValueError("model node outside graph")
            current.nodes.append(fields(payload))
        elif marker == "GGML_RISCV_MODEL_GRAPH_END ":
            if current is None:
                raise ValueError("model graph end without begin")
            values = fields(payload)
            if integer(values, "id") != current.graph_id:
                raise ValueError("model graph ID changed before end")
            current.closed = True
            graphs.append(current)
            current = None
    if current is not None or not graphs or not all(graph.closed for graph in graphs):
        raise ValueError("incomplete model graph trace")
    return graphs


def normalized_type(value: str) -> str:
    return value.upper()


def product(values: list[int]) -> int:
    result = 1
    for value in values:
        result *= value
    return result


def node_shape(node: dict[str, str], prefix: str = "") -> tuple[int, int, int, int]:
    return tuple(integer(node, f"{prefix}ne{axis}") for axis in range(4))


def qbs_nodes(graph: Graph) -> list[dict[str, str]]:
    return [
        node for node in graph.nodes
        if node.get("op") in {"MUL_MAT", "MUL_MAT_ID"}
        and normalized_type(node.get("src0", "")) in SUPPORTED_QBS_TYPES
    ]


def attention_nodes(graph: Graph) -> list[dict[str, str]]:
    return [node for node in graph.nodes if node.get("op") == "FLASH_ATTN_EXT"]


def qbs_payload(node: dict[str, str], abi: dict[str, object]) -> dict[str, int | str]:
    operation = node.get("op", "")
    if operation not in {"MUL_MAT", "MUL_MAT_ID"}:
        raise ValueError(f"unsupported QBS operation: {operation}")
    profile = normalized_type(node["src0"])
    abi_profile = QBS_TRACE_TO_ABI.get(profile, profile)
    weight = abi["weight_profiles"][abi_profile]
    activations = weight["activation_profiles"]
    if len(activations) != 1:
        raise ValueError(f"{profile} does not have one activation profile")
    activation_profile = activations[0]
    activation = abi["activation_profiles"][activation_profile]
    src0_shape = node_shape(node, "src0_")
    src1_shape = node_shape(node, "src1_")
    output_shape = node_shape(node)
    k = src0_shape[0]
    n = src0_shape[1]
    m = product(list(output_shape[1:]))
    activation_rows = product(list(src1_shape[1:]))
    if k <= 0 or n <= 0 or m <= 0:
        raise ValueError(f"invalid QBS shape: {node}")
    if src1_shape[0] != k or activation_rows <= 0:
        raise ValueError(f"inconsistent QBS activation shape: {node}")
    matrix_count = 1
    if operation == "MUL_MAT":
        if src0_shape[2:] != (1, 1):
            raise ValueError(f"QBS MUL_MAT weight is not two-dimensional: {node}")
    else:
        matrix_count = src0_shape[2]
        ids_shape = node_shape(node, "src2_")
        if (
            matrix_count <= 0
            or src0_shape[3] != 1
            or normalized_type(node.get("src2", "")) != "I32"
            or ids_shape[2:] != (1, 1)
            or ids_shape[0] != output_shape[1]
            or ids_shape[1] != output_shape[2]
            or output_shape[3] != 1
            or output_shape[0] != n
            or src1_shape[2] != output_shape[2]
            or src1_shape[3] != 1
            or output_shape[1] % src1_shape[1]
        ):
            raise ValueError(f"inconsistent QBS MUL_MAT_ID topology: {node}")
    if k % int(weight["block_elements"]) or k % int(activation["block_elements"]):
        raise ValueError(f"unaligned QBS K={k} for {profile}")
    weight_matrix_bytes = n * (k // int(weight["block_elements"])) * int(weight["block_bytes"])
    return {
        "operation": operation,
        "profile": profile,
        "activation_profile": activation_profile,
        "k": k,
        "m": m,
        "n": n,
        "weight_matrices": matrix_count,
        "activation_rows": activation_rows,
        "dot_elements": k * m * n,
        # Logical traffic counts one selected expert matrix for every routed
        # output row. The unique tensor capacity counts all resident experts.
        "weight_bytes": weight_matrix_bytes * (m if operation == "MUL_MAT_ID" else 1),
        "weight_unique_tensor_bytes": weight_matrix_bytes * matrix_count,
        "activation_bytes": (
            activation_rows
            * (k // int(activation["block_elements"]))
            * int(activation["block_bytes"])
        ),
    }


def attention_shape(node: dict[str, str], effective_kv: int) -> dict[str, int | bool]:
    d, q_tokens, q_heads, q_batches = node_shape(node, "src0_")
    kd, k_capacity, kv_heads, k_batches = node_shape(node, "src1_")
    vd, v_capacity, value_heads, v_batches = node_shape(node, "src2_")
    if q_tokens != 1 or q_batches != 1 or k_batches != 1 or v_batches != 1:
        raise ValueError(f"trace is not one-token Decode attention: {node}")
    if d != kd or d != vd or kv_heads != value_heads or q_heads % kv_heads:
        raise ValueError(f"inconsistent Q/K/V topology: {node}")
    if effective_kv > k_capacity or effective_kv > v_capacity:
        raise ValueError(f"effective KV exceeds graph capacity: {node}")
    gqa_rows = q_heads // kv_heads
    dst_shape = node_shape(node)
    shape_eligible = (
        d in SUPPORTED_AKV_D
        and gqa_rows in SUPPORTED_AKV_GQA
        and normalized_type(node.get("type", "")) == "F32"
        and normalized_type(node.get("src0", "")) == "F32"
        and normalized_type(node.get("src1", "")) == "F16"
        and normalized_type(node.get("src2", "")) == "F16"
        and normalized_type(node.get("src3", "")) == "F16"
        and dst_shape == (d, q_heads, 1, 1)
    )
    return {
        "head_dim": d,
        "q_heads": q_heads,
        "kv_heads": kv_heads,
        "gqa_rows": gqa_rows,
        "effective_kv": effective_kv,
        "shape_eligible": shape_eligible,
        "query_payload_logical_bytes": q_heads * d * 2,
        "kv_payload_logical_bytes": 2 * kv_heads * effective_kv * d * 2,
        "attention_macs": 2 * q_heads * effective_kv * d,
    }


def summarize_graphs(
    graphs: list[Graph], effective_kv: int, abi: dict[str, object]
) -> dict[str, object]:
    if len(graphs) < 2:
        raise ValueError(f"expected Prefill graph(s) and one Decode graph, found {len(graphs)}")
    decode_candidates = []
    for graph in graphs:
        candidates = attention_nodes(graph)
        if candidates and all(node_shape(node, "src0_")[1] == 1 for node in candidates):
            decode_candidates.append(graph)
    if len(decode_candidates) != 1 or decode_candidates[0] is not graphs[-1]:
        raise ValueError("trace does not end in exactly one one-token Decode graph")
    decode = decode_candidates[0]
    qbs_decode = [qbs_payload(node, abi) | {"name": node.get("name", "")}
                  for node in qbs_nodes(decode)]
    attention_decode = [attention_shape(node, effective_kv) for node in attention_nodes(decode)]
    if not qbs_decode or not attention_decode:
        raise ValueError("Decode graph lacks QBS MUL_MAT or attention nodes")
    profiles = Counter(str(row["profile"]) for row in qbs_decode)
    operations = Counter(str(row["operation"]) for row in qbs_decode)
    eligible_attention = [row for row in attention_decode if bool(row["shape_eligible"])]
    fallback_attention = [row for row in attention_decode if not bool(row["shape_eligible"])]
    all_qbs = [node for graph in graphs for node in qbs_nodes(graph)]
    all_attention = [node for graph in graphs for node in attention_nodes(graph)]
    return {
        "graphs": len(graphs),
        "prefill_graphs": len(graphs) - 1,
        "graph_declared_node_counts": [graph.declared_nodes for graph in graphs],
        "graph_executed_compute_node_counts": [len(graph.nodes) for graph in graphs],
        "all_graph_qbs_candidate_compute_nodes": len(all_qbs),
        "all_graph_attention_candidate_compute_nodes": len(all_attention),
        "decode": {
            "effective_kv": effective_kv,
            "executed_compute_nodes": len(decode.nodes),
            "qbs_candidate_compute_nodes": len(qbs_decode),
            "qbs_profiles": dict(sorted(profiles.items())),
            "qbs_operations": dict(sorted(operations.items())),
            "qbs_dot_elements": sum(int(row["dot_elements"]) for row in qbs_decode),
            "qbs_weight_logical_bytes": sum(int(row["weight_bytes"]) for row in qbs_decode),
            "qbs_weight_unique_tensor_bytes": sum(
                int(row["weight_unique_tensor_bytes"]) for row in qbs_decode
            ),
            "qbs_activation_logical_bytes_without_cross_op_reuse": sum(
                int(row["activation_bytes"]) for row in qbs_decode
            ),
            "qbs_shapes": qbs_decode,
            "akv_candidate_compute_nodes": len(attention_decode),
            "akv_shape_eligible_compute_nodes": len(eligible_attention),
            "akv_shape_fallback_compute_nodes": len(fallback_attention),
            "akv_shape_eligible_groups": sum(int(row["kv_heads"]) for row in eligible_attention),
            "attention_candidate_query_payload_logical_bytes": sum(
                int(row["query_payload_logical_bytes"]) for row in attention_decode
            ),
            "attention_candidate_kv_payload_logical_bytes": sum(
                int(row["kv_payload_logical_bytes"]) for row in attention_decode
            ),
            "attention_candidate_macs": sum(
                int(row["attention_macs"]) for row in attention_decode
            ),
            "akv_shape_eligible_query_payload_logical_bytes": sum(
                int(row["query_payload_logical_bytes"]) for row in eligible_attention
            ),
            "akv_shape_eligible_kv_payload_logical_bytes": sum(
                int(row["kv_payload_logical_bytes"]) for row in eligible_attention
            ),
            "akv_shape_eligible_attention_macs": sum(
                int(row["attention_macs"]) for row in eligible_attention
            ),
            "attention_shapes": attention_decode,
            "ordinary_rvv_compute_nodes_if_akv_shape_selected": (
                len(decode.nodes) - len(qbs_decode) - len(eligible_attention)
            ),
            "ordinary_rvv_compute_nodes_without_akv": len(decode.nodes) - len(qbs_decode),
        },
    }


def validate_decode_expectation(
    summary: dict[str, object], decode_expectation: dict[str, object]
) -> None:
    decode = summary["decode"]
    expected_qbs_nodes = int(decode_expectation["qbs_candidate_compute_nodes"])
    observed_qbs_nodes = int(summary["decode"]["qbs_candidate_compute_nodes"])
    if observed_qbs_nodes != expected_qbs_nodes:
        raise ValueError(
            f"Decode QBS candidate mismatch: {observed_qbs_nodes} != {expected_qbs_nodes}"
        )
    observed_profiles = set(summary["decode"]["qbs_profiles"])
    expected_profiles = set(decode_expectation["qbs_profiles"])
    if observed_profiles != expected_profiles:
        raise ValueError(f"Decode QBS profile mismatch: {observed_profiles} != {expected_profiles}")
    if "qbs_operations" in decode_expectation:
        observed_operations = summary["decode"]["qbs_operations"]
        expected_operations = decode_expectation["qbs_operations"]
        if observed_operations != expected_operations:
            raise ValueError(
                f"Decode QBS operation mismatch: {observed_operations} != {expected_operations}"
            )

    expected_candidates = int(decode_expectation["attention_candidate_compute_nodes"])
    observed_candidates = int(decode["akv_candidate_compute_nodes"])
    if observed_candidates != expected_candidates:
        raise ValueError(
            f"Decode attention candidate mismatch: {observed_candidates} != {expected_candidates}"
        )


def validate_akv_disposition(summary: dict[str, object], disposition: str) -> None:
    decode = summary["decode"]
    candidates = int(decode["akv_candidate_compute_nodes"])
    eligible = int(decode["akv_shape_eligible_compute_nodes"])
    fallback = int(decode["akv_shape_fallback_compute_nodes"])
    if candidates <= 0 or candidates != eligible + fallback:
        raise ValueError("invalid Decode AKV candidate partition")
    if disposition == "execute":
        if eligible <= 0:
            raise ValueError("model is expected to execute AKV but has no eligible Decode shape")
    elif disposition == "fallback_shape":
        if eligible != 0 or fallback != candidates:
            raise ValueError("model is expected to fall back all AKV candidates by shape")
    else:
        raise ValueError(f"unknown AKV disposition: {disposition}")


def validate_reference(
    summary: dict[str, object],
    reference: dict[str, object],
    decode_expectation: dict[str, object],
) -> None:
    validate_decode_expectation(summary, decode_expectation)
    expected_qbs_nodes = int(decode_expectation["qbs_candidate_compute_nodes"])
    expected_profiles = set(decode_expectation["qbs_profiles"])
    if set(reference["qbs"]["coverage"]) != expected_profiles:
        raise ValueError("manifest QBS profiles disagree with the RISC-V QEMU reference")
    if int(reference["qbs"]["nodes"]) != 2 * expected_qbs_nodes:
        raise ValueError("fixed-prompt QEMU reference does not contain one Prefill and one Decode QBS graph")

    expected_candidates = int(decode_expectation["attention_candidate_compute_nodes"])
    if int(reference["akv_v2"]["coverage"]["candidate_ops"]) != 2 * expected_candidates:
        raise ValueError("fixed-prompt QEMU reference does not contain one Prefill and one Decode attention graph")
    if int(reference["akv_v2"]["calls"]) != int(
        summary["decode"]["akv_shape_eligible_compute_nodes"]
    ):
        raise ValueError("AKV shape eligibility disagrees with the RISC-V QEMU executed-call count")
    shapes = reference["akv_v2"].get("shapes", [])
    if shapes:
        observed = summary["decode"]["attention_shapes"]
        expected = shapes[0]
        for row in observed:
            for key in ("head_dim", "q_heads", "kv_heads", "gqa_rows"):
                reference_key = "q_rows" if key == "q_heads" else key
                if int(row[key]) != int(expected[reference_key]):
                    raise ValueError(f"host/QEMU AKV topology mismatch for {key}")


def tokenizer_count(tokenizer: Path, model: Path, prompt: str) -> int:
    result = subprocess.run(
        [str(tokenizer), "-m", str(model), "-p", prompt, "--show-count", "--ids"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True,
    )
    matches = TOKEN_COUNT_RE.findall(result.stdout)
    if len(matches) != 1:
        raise ValueError("tokenizer output contains no unique token count")
    return int(matches[0])


def exact_prompt(tokenizer: Path, model: Path, target_tokens: int) -> str:
    if target_tokens <= 0:
        raise ValueError("prompt token count must be positive")

    def fill(prefix: str) -> str | None:
        prefix_count = tokenizer_count(tokenizer, model, prefix) if prefix else 0
        if prefix_count > target_tokens:
            return None
        low, high = 0, target_tokens + 2
        while low <= high:
            middle = (low + high) // 2
            suffix = " ".join(["a"] * middle)
            candidate = prefix + ((" " if prefix and suffix else "") + suffix)
            count = tokenizer_count(tokenizer, model, candidate)
            if count == target_tokens:
                return candidate
            if count < target_tokens:
                low = middle + 1
            else:
                high = middle - 1
        return None

    prompt = fill(BASE_PROMPT)
    if prompt is None:
        prompt = fill("")
    if prompt is None or tokenizer_count(tokenizer, model, prompt) != target_tokens:
        raise ValueError(f"cannot construct an exact {target_tokens}-token prompt")
    return prompt


def prompt_eval_tokens(log_path: Path) -> int:
    matches = PROMPT_EVAL_RE.findall(log_path.read_text(errors="replace"))
    if len(matches) != 1:
        raise ValueError(f"expected one prompt-eval token count, found {len(matches)}")
    return int(matches[0])


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))

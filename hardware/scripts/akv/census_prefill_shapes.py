#!/usr/bin/env python3

"""Build a strict Prefill-Attention shape census from immutable GGML traces."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from context_sweep import (
    attention_nodes,
    load_json,
    node_shape,
    normalized_type,
    parse_graphs,
    prompt_eval_tokens,
    qbs_nodes,
    sha256,
)


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = Path(__file__).with_name("model-generality-manifest.json")
DEFAULT_SOURCE_ROOT = ROOT / "hardware/qbs_akv_model_generality_host_stage1_20260831"
FAST_HEAD_DIMS = {64, 96, 128}
FAST_GQA_ROWS = set(range(1, 9))


def relative_or_absolute(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def shape_text(shape: tuple[int, int, int, int]) -> str:
    return "x".join(str(value) for value in shape)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty census: {path}")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def attention_signature(node: dict[str, str]) -> tuple[object, ...]:
    return (
        node_shape(node, "src0_"),
        node_shape(node, "src1_"),
        node_shape(node, "src2_"),
        node_shape(node, "src3_"),
        node_shape(node),
        normalized_type(node.get("type", "")),
        normalized_type(node.get("src0", "")),
        normalized_type(node.get("src1", "")),
        normalized_type(node.get("src2", "")),
        normalized_type(node.get("src3", "")),
    )


def summarize_chunk(
    node: dict[str, str],
    *,
    model: dict[str, object],
    effective_kv: int,
    graph_index: int,
    graph_count: int,
    attention_node_count: int,
    qbs_profiles: list[str],
    past_tokens: int,
) -> dict[str, object]:
    q_shape = node_shape(node, "src0_")
    k_shape = node_shape(node, "src1_")
    v_shape = node_shape(node, "src2_")
    mask_shape = node_shape(node, "src3_")
    dst_shape = node_shape(node)
    d, query_tokens, q_heads, q_batches = q_shape
    kd, kv_capacity, kv_heads, k_batches = k_shape
    vd, value_capacity, value_heads, v_batches = v_shape

    if query_tokens <= 1:
        raise ValueError(f"Prefill chunk has M={query_tokens}: {node}")
    if any(batch != 1 for batch in (q_batches, k_batches, v_batches)):
        raise ValueError(f"batched Prefill is outside this census: {node}")
    if d != kd or d != vd or k_shape != v_shape:
        raise ValueError(f"inconsistent K/V topology: {node}")
    if kv_heads != value_heads or q_heads % kv_heads:
        raise ValueError(f"invalid GQA topology: {node}")
    if kv_capacity != value_capacity or kv_capacity < past_tokens + query_tokens:
        raise ValueError(f"KV capacity does not cover the chunk prefix: {node}")
    if mask_shape != (kv_capacity, query_tokens, 1, 1):
        raise ValueError(f"unexpected Prefill mask shape: {node}")
    if dst_shape != (d, q_heads, query_tokens, 1):
        raise ValueError(f"unexpected Prefill output shape: {node}")

    types = {
        "dst": normalized_type(node.get("type", "")),
        "q": normalized_type(node.get("src0", "")),
        "k": normalized_type(node.get("src1", "")),
        "v": normalized_type(node.get("src2", "")),
        "mask": normalized_type(node.get("src3", "")),
    }
    expected_types = {"dst": "F32", "q": "F32", "k": "F16", "v": "F16", "mask": "F16"}
    type_eligible = types == expected_types
    gqa_rows = q_heads // kv_heads
    shape_eligible = d in FAST_HEAD_DIMS and gqa_rows in FAST_GQA_ROWS
    fast_path_candidate = type_eligible and shape_eligible

    # The Host trace records shapes and types, but not byte strides or mask
    # payload. Causal visibility is therefore an explicitly labelled inference
    # from first-Prefill graph order, never reported as directly observed data.
    visible_pairs_per_q_head = (
        query_tokens * past_tokens + query_tokens * (query_tokens + 1) // 2
    )
    qk_macs = visible_pairs_per_q_head * q_heads * d
    pv_macs = qk_macs
    visible_kv_tokens = past_tokens + query_tokens

    return {
        "model": model["id"],
        "model_name": model["name"],
        "architecture": model["architecture"],
        "topology": model["topology"],
        "model_quantization": model["quantization"],
        "qbs_weight_profiles_in_graph": "/".join(qbs_profiles),
        "effective_kv_target": effective_kv,
        "chunk_index": graph_index,
        "chunk_count": graph_count,
        "M_query_tokens": query_tokens,
        "P_past_tokens": past_tokens,
        "visible_kv_end": visible_kv_tokens,
        "kv_capacity": kv_capacity,
        "head_dim": d,
        "q_heads": q_heads,
        "kv_heads": kv_heads,
        "gqa_rows": gqa_rows,
        "attention_nodes": attention_node_count,
        "q_type": types["q"],
        "k_type": types["k"],
        "v_type": types["v"],
        "mask_type": types["mask"],
        "output_type": types["dst"],
        "q_shape_D_M_Hq_B": shape_text(q_shape),
        "k_shape_D_K_Hkv_B": shape_text(k_shape),
        "v_shape_D_K_Hkv_B": shape_text(v_shape),
        "mask_shape_K_M_1_1": shape_text(mask_shape),
        "output_shape_D_Hq_M_B": shape_text(dst_shape),
        "layout_evidence": "GGML_shape_observed_byte_strides_not_traced",
        "mask_semantics": "causal_prefix_inferred_payload_not_traced",
        "visible_pairs_per_q_head": visible_pairs_per_q_head,
        "qk_macs": qk_macs,
        "pv_macs": pv_macs,
        "attention_macs": qk_macs + pv_macs,
        "query_payload_bytes": d * query_tokens * q_heads * 4,
        "visible_kv_payload_bytes": 2 * d * visible_kv_tokens * kv_heads * 2,
        "fast_path_disposition": (
            "candidate" if fast_path_candidate else
            "fallback_head_dim" if d not in FAST_HEAD_DIMS else
            "fallback_gqa" if gqa_rows not in FAST_GQA_ROWS else
            "fallback_type"
        ),
        "status": "PASS",
    }


def analyze_case(
    log_path: Path,
    model: dict[str, object],
    effective_kv: int,
) -> list[dict[str, object]]:
    prompt_tokens = prompt_eval_tokens(log_path)
    if prompt_tokens != effective_kv - 1:
        raise ValueError(
            f"{model['id']}/KV{effective_kv} prompt mismatch: {prompt_tokens}"
        )
    graphs = parse_graphs(log_path)
    if not attention_nodes(graphs[-1]):
        raise ValueError("trace does not end in a Decode attention graph")
    if not all(node_shape(node, "src0_")[1] == 1 for node in attention_nodes(graphs[-1])):
        raise ValueError("last graph is not one-token Decode")

    prefill_graphs = [graph for graph in graphs[:-1] if attention_nodes(graph)]
    if not prefill_graphs:
        raise ValueError("trace contains no Prefill attention graph")

    rows: list[dict[str, object]] = []
    past_tokens = 0
    for graph_index, graph in enumerate(prefill_graphs):
        nodes = attention_nodes(graph)
        signatures = {attention_signature(node) for node in nodes}
        if len(signatures) != 1:
            raise ValueError(
                f"Prefill graph {graph.graph_id} has nonuniform attention topology"
            )
        profiles = sorted({normalized_type(node["src0"]) for node in qbs_nodes(graph)})
        row = summarize_chunk(
            nodes[0],
            model=model,
            effective_kv=effective_kv,
            graph_index=graph_index,
            graph_count=len(prefill_graphs),
            attention_node_count=len(nodes),
            qbs_profiles=profiles,
            past_tokens=past_tokens,
        )
        rows.append(row)
        past_tokens += int(row["M_query_tokens"])
    if past_tokens != prompt_tokens:
        raise ValueError(
            f"Prefill chunks cover {past_tokens} tokens, expected {prompt_tokens}"
        )
    return rows


def support_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row["model"]), []).append(row)
    result = []
    for model, values in grouped.items():
        dispositions = Counter(str(row["fast_path_disposition"]) for row in values)
        result.append({
            "model": model,
            "model_name": values[0]["model_name"],
            "architecture": values[0]["architecture"],
            "model_quantization": values[0]["model_quantization"],
            "head_dims": "/".join(str(value) for value in sorted({int(row["head_dim"]) for row in values})),
            "q_heads": "/".join(str(value) for value in sorted({int(row["q_heads"]) for row in values})),
            "kv_heads": "/".join(str(value) for value in sorted({int(row["kv_heads"]) for row in values})),
            "gqa_rows": "/".join(str(value) for value in sorted({int(row["gqa_rows"]) for row in values})),
            "observed_M": "/".join(str(value) for value in sorted({int(row["M_query_tokens"]) for row in values})),
            "observed_P": "/".join(str(value) for value in sorted({int(row["P_past_tokens"]) for row in values})),
            "chunk_rows": len(values),
            "candidate_chunks": dispositions["candidate"],
            "fallback_chunks": len(values) - dispositions["candidate"],
            "dispositions": "/".join(f"{key}:{dispositions[key]}" for key in sorted(dispositions)),
            "status": "PASS",
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    output = args.output.resolve()
    if not (source_root / "complete").is_file():
        raise ValueError(f"source context sweep is not complete: {source_root}")
    if output.exists():
        raise FileExistsError(output)
    manifest = load_json(args.manifest)
    if int(manifest.get("schema_version", 0)) != 1:
        raise ValueError("unsupported model-generality manifest")

    rows: list[dict[str, object]] = []
    source_cases: list[dict[str, object]] = []
    for model in manifest["models"]:
        for effective_kv_value in manifest["kv_lengths"]:
            effective_kv = int(effective_kv_value)
            log_path = source_root / str(model["id"]) / f"kv{effective_kv}" / "host.log"
            if not log_path.is_file():
                raise FileNotFoundError(log_path)
            rows.extend(analyze_case(log_path, model, effective_kv))
            source_cases.append({
                "model": model["id"],
                "effective_kv": effective_kv,
                "host_log": relative_or_absolute(log_path),
                "host_log_sha256": sha256(log_path),
            })

    expected_cases = len(manifest["models"]) * len(manifest["kv_lengths"])
    if len(source_cases) != expected_cases:
        raise ValueError(f"found {len(source_cases)} source cases, expected {expected_cases}")
    models = support_rows(rows)
    if len(models) != len(manifest["models"]):
        raise ValueError("support matrix does not contain every model")

    output.mkdir(parents=True)
    shapes_path = output / "prefill_shapes.csv"
    support_path = output / "support_matrix.csv"
    provenance_path = output / "provenance.json"
    write_csv(shapes_path, rows)
    write_csv(support_path, models)
    provenance = {
        "schema_version": 1,
        "mode": "offline_census_of_immutable_real_llama_cpp_host_graphs",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest": relative_or_absolute(args.manifest),
        "manifest_sha256": sha256(args.manifest),
        "source_root": relative_or_absolute(source_root),
        "source_complete_sha256": sha256(source_root / "complete"),
        "tool": relative_or_absolute(Path(__file__)),
        "tool_sha256": sha256(Path(__file__)),
        "cases": source_cases,
    }
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    disposition_counts = Counter(str(row["fast_path_disposition"]) for row in rows)
    summary = {
        "schema_version": 1,
        "status": "PASS",
        "scope": (
            "shape/type/chunk census of immutable real llama.cpp Prefill graphs; "
            "mask payload, byte strides, QEMU execution, RTL cycles, and physical closure are not claimed"
        ),
        "model_count": len(models),
        "source_case_count": len(source_cases),
        "prefill_chunk_count": len(rows),
        "chunked_source_cases": sum(int(row["chunk_count"]) > 1 and int(row["chunk_index"]) == 0 for row in rows),
        "head_dims": sorted({int(row["head_dim"]) for row in rows}),
        "gqa_rows": sorted({int(row["gqa_rows"]) for row in rows}),
        "query_tokens_M": sorted({int(row["M_query_tokens"]) for row in rows}),
        "past_tokens_P": sorted({int(row["P_past_tokens"]) for row in rows}),
        "dispositions": dict(sorted(disposition_counts.items())),
        "observed_types": {
            key: sorted({str(row[key]) for row in rows})
            for key in ("q_type", "k_type", "v_type", "mask_type", "output_type")
        },
        "evidence_limits": {
            "shape_and_type": "directly_observed",
            "chunk_order_and_M_P": "derived_from_order_and_exact_prompt_token_count",
            "mask_shape": "directly_observed",
            "mask_payload_and_causal_prefix": (
                "not_traced_in_graph_logs; exact_Qwen_M15_capture_checked_separately"
            ),
            "byte_strides": "not_traced",
        },
        "artifacts": {
            "prefill_shapes": {"path": relative_or_absolute(shapes_path), "sha256": sha256(shapes_path)},
            "support_matrix": {"path": relative_or_absolute(support_path), "sha256": sha256(support_path)},
            "provenance": {"path": relative_or_absolute(provenance_path), "sha256": sha256(provenance_path)},
        },
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output / "complete").write_text("PASS\n", encoding="ascii")
    print(output)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)

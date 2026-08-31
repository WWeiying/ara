#!/usr/bin/env python3
"""Summarize strict cross-operator QBS activation-lifetime traces."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple


LIFETIME_PREFIX = "GGML_RISCV_QBS_LIFETIME "
COMMAND_PREFIX = "GGML_RISCV_QBS_COMMAND "
SUMMARY_PREFIX = "GGML_RISCV_QBS_LIFETIME_SUMMARY "
CROSS_OP_PREFIX = "GGML_RISCV_QBS_CROSS_OP "

ROLE_PATTERNS = {
    "attention_q": re.compile(r"(?:^|[._-])attn[_-]?q(?:[._-]|$)", re.IGNORECASE),
    "attention_k": re.compile(r"(?:^|[._-])attn[_-]?k(?:[._-]|$)", re.IGNORECASE),
    "attention_v": re.compile(r"(?:^|[._-])attn[_-]?v(?:[._-]|$)", re.IGNORECASE),
    "ffn_gate": re.compile(r"(?:^|[._-])ffn[_-]?gate(?:[._-]|$)", re.IGNORECASE),
    "ffn_up": re.compile(r"(?:^|[._-])ffn[_-]?up(?:[._-]|$)", re.IGNORECASE),
}

REUSE_FAMILIES = {
    "attention_qkv": ("attention_q", "attention_k", "attention_v"),
    "ffn_gate_up": ("ffn_gate", "ffn_up"),
}

# These are the advertised limits of the current QBS activation context, not
# general QBS matrix limits. Keep the estimator conservative until hardware
# exposes a wider context profile.
CONTEXT_ACTIVATION_PROFILE_Q8_K = 1
CONTEXT_BLOCK_ELEMENTS = 256
CONTEXT_MAX_K_BLOCKS = 16
CONTEXT_COMMAND_N = 32

ACTIVATION_BLOCK_ELEMENTS = {
    1: 256,  # Q8_K
    2: 32,   # Q8_0
}

INTEGER_FIELDS = {
    "seq",
    "graph_epoch",
    "weight_profile",
    "activation_profile",
    "m",
    "n",
    "k",
    "k_blocks",
    "bytes",
    "digest",
    "match_seq",
    "same_tensor",
    "same_data",
    "reusable",
    "quantize_time_valid",
    "quantize_time_us",
    "activation_seq",
    "linked",
    "access",
    "context_id",
    "context_generation",
    "segmented",
    "emulated",
    "generation",
    "quantization_skipped",
    "activation_bytes_saved",
    "next_same",
}


def parse_fields(line: str, prefix: str) -> Dict[str, object]:
    if not line.startswith(prefix):
        raise ValueError(f"line does not start with {prefix!r}")
    result: Dict[str, object] = {}
    for token in line[len(prefix) :].strip().split():
        if "=" not in token:
            raise ValueError(f"malformed trace token {token!r}")
        key, value = token.split("=", 1)
        if key in result:
            raise ValueError(f"duplicate trace field {key!r}")
        if key in INTEGER_FIELDS:
            base = 16 if key == "digest" else 10
            result[key] = int(value, base)
        else:
            result[key] = value
    return result


def require_fields(record: Mapping[str, object], fields: Iterable[str], kind: str) -> None:
    missing = [field for field in fields if field not in record]
    if missing:
        raise ValueError(f"{kind} record lacks fields: {', '.join(missing)}")


def classify_role(weight_name: str) -> str:
    matches = [role for role, pattern in ROLE_PATTERNS.items() if pattern.search(weight_name)]
    return matches[0] if len(matches) == 1 else "other"


def selected_lines(path: Path, run_label: str | None = None) -> List[str]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if run_label is None:
        return lines

    begin = f"AKV_TOKEN_RUN_BEGIN={run_label}"
    end = f"AKV_TOKEN_RUN_EXIT={run_label}:"
    inside = False
    selected: List[str] = []
    for raw_line in lines:
        line = raw_line.rstrip("\r")
        if line == begin:
            if inside:
                raise ValueError(f"duplicate run begin for {run_label}")
            inside = True
            continue
        if inside and line.startswith(end):
            return selected
        if inside:
            selected.append(line)
    raise ValueError(f"run label {run_label!r} is incomplete or absent in {path}")


def parse_log(
    path: Path, run_label: str | None = None
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]], Dict[str, object]]:
    lifetimes: List[Dict[str, object]] = []
    commands: List[Dict[str, object]] = []
    summary: Dict[str, object] = {}
    for raw_line in selected_lines(path, run_label):
        line = raw_line.rstrip("\r")
        if line.startswith(LIFETIME_PREFIX):
            record = parse_fields(line, LIFETIME_PREFIX)
            require_fields(
                record,
                (
                    "seq", "graph_epoch", "weight", "weight_type", "weight_profile", "source",
                    "activation_type", "activation_profile", "m", "n", "k", "bytes", "digest",
                    "match_seq", "same_tensor", "reusable", "quantize_time_valid", "quantize_time_us",
                    "source_id",
                ),
                "lifetime",
            )
            record["role"] = classify_role(str(record["weight"]))
            lifetimes.append(record)
        elif line.startswith(COMMAND_PREFIX):
            record = parse_fields(line, COMMAND_PREFIX)
            require_fields(
                record,
                (
                    "seq", "graph_epoch", "activation_seq", "linked", "weight_type", "weight_profile",
                    "activation_profile", "m", "n", "k_blocks", "access", "context_id",
                    "context_generation", "segmented", "emulated",
                ),
                "command",
            )
            commands.append(record)
        elif line.startswith(SUMMARY_PREFIX):
            summary = parse_fields(line, SUMMARY_PREFIX)

    if not lifetimes:
        raise ValueError(f"{path} has no QBS lifetime records")
    if not commands:
        raise ValueError(f"{path} has no QBS command records")
    if not summary:
        raise ValueError(f"{path} has no QBS lifetime summary")

    lifetime_by_seq = {int(record["seq"]): record for record in lifetimes}
    if len(lifetime_by_seq) != len(lifetimes):
        raise ValueError("duplicate lifetime sequence")
    if len({int(record["seq"]) for record in commands}) != len(commands):
        raise ValueError("duplicate command sequence")

    for record in lifetimes:
        match_seq = int(record["match_seq"])
        reusable = int(record["reusable"])
        if reusable != (match_seq != 0):
            raise ValueError(f"lifetime seq={record['seq']} has inconsistent reusable/match_seq")
        if match_seq:
            match = lifetime_by_seq.get(match_seq)
            if match is None or match_seq >= int(record["seq"]):
                raise ValueError(f"lifetime seq={record['seq']} has invalid match_seq={match_seq}")
            invariant_fields = (
                "graph_epoch", "source_id", "activation_type", "activation_profile", "m", "k", "bytes", "digest"
            )
            if any(record[field] != match[field] for field in invariant_fields):
                raise ValueError(f"lifetime seq={record['seq']} match violates strict identity")

    for command in commands:
        activation_seq = int(command["activation_seq"])
        linked = int(command["linked"])
        if linked:
            activation = lifetime_by_seq.get(activation_seq)
            if activation is None:
                raise ValueError(f"command seq={command['seq']} links missing activation {activation_seq}")
            if command["graph_epoch"] != activation["graph_epoch"]:
                raise ValueError(f"command seq={command['seq']} crosses graph epochs")
            if command["activation_profile"] != activation["activation_profile"]:
                raise ValueError(f"command seq={command['seq']} activation profile differs from activation record")
            if int(command["m"]) <= 0 or int(command["m"]) > int(activation["m"]):
                raise ValueError(f"command seq={command['seq']} row tile exceeds activation record")
            block_elements = ACTIVATION_BLOCK_ELEMENTS.get(int(activation["activation_profile"]))
            if block_elements is None or int(activation["k"]) % block_elements != 0 or \
                    int(command["k_blocks"]) != int(activation["k"]) // block_elements:
                raise ValueError(f"command seq={command['seq']} K span differs from activation record")
        elif activation_seq != 0 or int(command["graph_epoch"]) != 0:
            raise ValueError(f"unlinked command seq={command['seq']} carries a partial link")

    expected = {
        "quantizations": len(lifetimes),
        "exact_reuse_candidates": sum(int(record["reusable"]) for record in lifetimes),
        "quantized_bytes": sum(int(record["bytes"]) for record in lifetimes),
        "reusable_quantized_bytes": sum(int(record["bytes"]) for record in lifetimes if int(record["reusable"])),
        "quantizations_with_time": sum(int(record["quantize_time_valid"]) for record in lifetimes),
        "quantize_time_us": sum(
            int(record["quantize_time_us"]) for record in lifetimes if int(record["quantize_time_valid"])
        ),
        "reusable_quantize_time_us": sum(
            int(record["quantize_time_us"])
            for record in lifetimes
            if int(record["reusable"]) and int(record["quantize_time_valid"])
        ),
        "graph_epochs": len({int(record["graph_epoch"]) for record in lifetimes}),
    }
    for field, value in expected.items():
        if int(summary.get(field, -1)) != value:
            raise ValueError(f"summary {field}={summary.get(field)} does not match parsed value {value}")
    return lifetimes, commands, summary


def parse_cross_ops(path: Path, run_label: str | None = None) -> List[Dict[str, object]]:
    records: List[Dict[str, object]] = []
    for raw_line in selected_lines(path, run_label):
        line = raw_line.rstrip("\r")
        if not line.startswith(CROSS_OP_PREFIX):
            continue
        record = parse_fields(line, CROSS_OP_PREFIX)
        require_fields(
            record,
            (
                "graph_epoch", "action", "source_id", "activation_profile", "m", "k",
                "generation", "activation_seq", "quantization_skipped",
                "activation_bytes_saved", "next_same",
            ),
            "cross-op",
        )
        records.append(record)
    return records


def validate_cross_ops(
    lifetimes: Sequence[Dict[str, object]],
    commands: Sequence[Dict[str, object]],
    trace_summary: Mapping[str, object],
    cross_ops: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    lifetime_by_seq = {int(record["seq"]): record for record in lifetimes}
    commands_by_activation: MutableMapping[int, List[Dict[str, object]]] = defaultdict(list)
    for command in commands:
        if int(command["linked"]):
            commands_by_activation[int(command["activation_seq"])].append(command)

    chains: MutableMapping[Tuple[object, ...], List[Dict[str, object]]] = defaultdict(list)
    for record in cross_ops:
        key = (
            record["graph_epoch"], record["source_id"], record["activation_profile"],
            record["m"], record["k"], record["generation"],
        )
        chains[key].append(record)

    fill_count = 0
    reuse_count = 0
    release_count = 0
    skip_count = 0
    saved_bytes = 0
    for key, records in chains.items():
        actions = [str(record["action"]) for record in records]
        if len(records) < 2 or actions[0] != "fill_keep" or actions[-1] != "reuse_release":
            raise ValueError(f"cross-op chain {key} lacks fill/release boundaries: {actions}")
        if any(action not in ("reuse_keep", "reuse_release") for action in actions[1:]):
            raise ValueError(f"cross-op chain {key} has invalid middle action: {actions}")

        first = records[0]
        if int(first["quantization_skipped"]) != 0 or int(first["activation_bytes_saved"]) != 0 or \
                int(first["activation_seq"]) != 0 or int(first["next_same"]) != 1:
            raise ValueError(f"cross-op chain {key} has malformed fill record")
        fill_count += 1

        activation_sequences = set()
        for index, record in enumerate(records[1:], 1):
            final = index == len(records) - 1
            if int(record["quantization_skipped"]) != 1 or int(record["activation_bytes_saved"]) <= 0:
                raise ValueError(f"cross-op chain {key} has malformed reuse record")
            if int(record["next_same"]) != (0 if final else 1):
                raise ValueError(f"cross-op chain {key} has inconsistent next_same")
            activation_seq = int(record["activation_seq"])
            activation = lifetime_by_seq.get(activation_seq)
            if activation is None:
                raise ValueError(f"cross-op chain {key} references missing activation {activation_seq}")
            identity = (
                activation["graph_epoch"], activation["source_id"], activation["activation_profile"],
                activation["m"], activation["k"],
            )
            if identity != key[:5]:
                raise ValueError(f"cross-op chain {key} activation identity mismatch")
            activation_sequences.add(activation_seq)
            reuse_count += 1
            skip_count += 1
            saved_bytes += int(record["activation_bytes_saved"])
            if final:
                release_count += 1

        if len(activation_sequences) != 1:
            raise ValueError(f"cross-op chain {key} does not reuse one activation sequence")
        activation_seq = next(iter(activation_sequences))
        chain_commands = commands_by_activation[activation_seq]
        accesses = [int(command["access"]) for command in chain_commands]
        generations = {int(command["context_generation"]) for command in chain_commands}
        if accesses.count(1) != 1 or accesses.count(3) != 1 or any(access not in (1, 2, 3) for access in accesses):
            raise ValueError(f"cross-op chain {key} has invalid command accesses")
        if len(generations) != 1 or next(iter(generations)) != int(key[-1]):
            raise ValueError(f"cross-op chain {key} has inconsistent command generation")

    expected_summary = {
        "cross_op_fill": fill_count,
        "cross_op_reuse": reuse_count,
        "cross_op_release": release_count,
        "cross_op_quantization_skips": skip_count,
        "cross_op_activation_bytes_saved": saved_bytes,
    }
    for field, expected in expected_summary.items():
        actual = int(trace_summary.get(field, 0))
        if actual != expected:
            raise ValueError(f"summary {field}={actual} does not match cross-op trace {expected}")

    return {
        "chains": len(chains),
        "fills": fill_count,
        "reuses": reuse_count,
        "releases": release_count,
        "quantization_skips": skip_count,
        "activation_bytes_saved": saved_bytes,
    }


def build_groups(
    lifetimes: Sequence[Dict[str, object]], commands: Sequence[Dict[str, object]]
) -> List[Dict[str, object]]:
    commands_by_activation: MutableMapping[int, List[Dict[str, object]]] = defaultdict(list)
    for command in commands:
        if int(command["linked"]):
            commands_by_activation[int(command["activation_seq"])].append(command)

    groups: List[Dict[str, object]] = []
    for family, required_roles in REUSE_FAMILIES.items():
        candidate_records = [record for record in lifetimes if record["role"] in required_roles]
        buckets: MutableMapping[Tuple[object, ...], List[Dict[str, object]]] = defaultdict(list)
        for record in candidate_records:
            key = (
                record["graph_epoch"], record["source_id"], record["activation_type"],
                record["activation_profile"], record["m"], record["k"], record["bytes"], record["digest"],
            )
            buckets[key].append(record)

        for records in buckets.values():
            records.sort(key=lambda record: int(record["seq"]))
            roles = {str(record["role"]) for record in records}
            if not set(required_roles).issubset(roles):
                continue
            selected = []
            for role in required_roles:
                selected.append(next(record for record in records if record["role"] == role))
            selected.sort(key=lambda record: int(record["seq"]))
            first_seq = int(selected[0]["seq"])
            last_seq = int(selected[-1]["seq"])
            epoch = int(selected[0]["graph_epoch"])
            selected_sequences = {int(record["seq"]) for record in selected}
            intervening = [
                record for record in lifetimes
                if int(record["graph_epoch"]) == epoch and first_seq < int(record["seq"]) < last_seq
                and int(record["seq"]) not in selected_sequences
            ]
            exact_chain = all(
                index == 0 or int(record["reusable"]) == 1
                for index, record in enumerate(selected)
            )
            linked_commands = [
                command for record in selected for command in commands_by_activation[int(record["seq"])]
            ]
            all_have_commands = all(commands_by_activation[int(record["seq"])] for record in selected)
            context_shape_supported = (
                str(selected[0]["activation_type"]).lower() == "q8_k"
                and int(selected[0]["activation_profile"]) == CONTEXT_ACTIVATION_PROFILE_Q8_K
                and int(selected[0]["m"]) == 1
                and int(selected[0]["k"]) % CONTEXT_BLOCK_ELEMENTS == 0
                and int(selected[0]["k"]) // CONTEXT_BLOCK_ELEMENTS <= CONTEXT_MAX_K_BLOCKS
                and all(int(record["n"]) > CONTEXT_COMMAND_N for record in selected)
                and all(int(command.get("m", 0)) == 1 for command in linked_commands)
                and all(int(command.get("segmented", 1)) == 0 for command in linked_commands)
            )
            eligible = exact_chain and not intervening and all_have_commands and context_shape_supported
            groups.append(
                {
                    "family": family,
                    "graph_epoch": epoch,
                    "source": selected[0]["source"],
                    "source_id": selected[0]["source_id"],
                    "activation_type": selected[0]["activation_type"],
                    "activation_profile": selected[0]["activation_profile"],
                    "m": selected[0]["m"],
                    "k": selected[0]["k"],
                    "output_rows": "+".join(str(record["n"]) for record in selected),
                    "roles": "+".join(str(record["role"]) for record in selected),
                    "weights": "+".join(str(record["weight"]) for record in selected),
                    "first_seq": first_seq,
                    "last_seq": last_seq,
                    "intervening_activations": len(intervening),
                    "exact_byte_chain": int(exact_chain),
                    "all_consumers_have_commands": int(all_have_commands),
                    "context_shape_supported": int(context_shape_supported),
                    "command_count": len(linked_commands),
                    "current_quantizations": len(selected),
                    "retained_quantizations": 1,
                    "removable_quantizations": len(selected) - 1,
                    "removable_quantized_bytes": sum(int(record["bytes"]) for record in selected[1:]),
                    "removable_quantize_time_us": sum(
                        int(record["quantize_time_us"])
                        for record in selected[1:]
                        if int(record["quantize_time_valid"])
                    ),
                    "eligible_single_context": int(eligible),
                    "reject_reason": "" if eligible else (
                        "not_byte_identical" if not exact_chain else
                        "intervening_activation" if intervening else
                        "missing_command_link" if not all_have_commands else
                        "hardware_context_unsupported"
                    ),
                }
            )
    return sorted(groups, key=lambda row: (int(row["graph_epoch"]), int(row["first_seq"]), str(row["family"])))


def write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def summarize(
    lifetimes: Sequence[Dict[str, object]], commands: Sequence[Dict[str, object]], groups: Sequence[Dict[str, object]]
) -> Dict[str, object]:
    eligible = [group for group in groups if int(group["eligible_single_context"])]
    by_family = {}
    for family in REUSE_FAMILIES:
        family_groups = [group for group in eligible if group["family"] == family]
        by_family[family] = {
            "groups": len(family_groups),
            "removable_quantizations": sum(int(group["removable_quantizations"]) for group in family_groups),
            "removable_quantized_bytes": sum(int(group["removable_quantized_bytes"]) for group in family_groups),
            "removable_quantize_time_us": sum(int(group["removable_quantize_time_us"]) for group in family_groups),
        }
    return {
        "graph_epochs": len({int(record["graph_epoch"]) for record in lifetimes}),
        "quantizations": len(lifetimes),
        "quantized_bytes": sum(int(record["bytes"]) for record in lifetimes),
        "commands": len(commands),
        "linked_commands": sum(int(command["linked"]) for command in commands),
        "unlinked_commands": sum(not int(command["linked"]) for command in commands),
        "eligible_groups": len(eligible),
        "removable_quantizations": sum(int(group["removable_quantizations"]) for group in eligible),
        "removable_quantized_bytes": sum(int(group["removable_quantized_bytes"]) for group in eligible),
        "removable_quantize_time_us": sum(int(group["removable_quantize_time_us"]) for group in eligible),
        "families": by_family,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-label")
    args = parser.parse_args()

    lifetimes, commands, trace_summary = parse_log(args.log, args.run_label)
    cross_ops = parse_cross_ops(args.log, args.run_label)
    cross_summary = validate_cross_ops(lifetimes, commands, trace_summary, cross_ops)
    groups = build_groups(lifetimes, commands)
    summary = summarize(lifetimes, commands, groups)
    summary["cross_operator_context"] = cross_summary
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "activation_lifetimes.csv", lifetimes)
    write_csv(args.output_dir / "qbs_commands.csv", commands)
    write_csv(args.output_dir / "cross_operator_context.csv", cross_ops)
    write_csv(args.output_dir / "activation_reuse_groups.csv", groups)
    (args.output_dir / "activation_reuse_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Count retired RVV instructions and CVXIF exception responses in passing RTL runs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from .artifacts import check_inputs
from .plan import _full_architecture_match
from .stimulus_coverage import _VSET_RE, _family, _memory_mode
from .trace import is_vector_instruction


DISASSEMBLY = re.compile(
    r"^\s*([0-9a-fA-F]+):\s+([0-9a-fA-F]+)\s+([^\s]+)(?:\s+(.*))?$"
)

VLMUL = {0: "m1", 1: "m2", 2: "m4", 3: "m8", 5: "mf8", 6: "mf4", 7: "mf2"}
VSEW = {0: "e8", 1: "e16", 2: "e32", 3: "e64"}


def decode_committed_vtype(value: int | None) -> tuple[str, str] | None:
    if value is None or value & ~0xff:
        return None
    sew = VSEW.get((value >> 3) & 7)
    lmul = VLMUL.get(value & 7)
    if sew is None or lmul is None:
        return None
    policy = f"{'ta' if value & 0x40 else 'tu'}/{'ma' if value & 0x80 else 'mu'}"
    return f"{sew}/{lmul}", policy


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def disassemble(elf: Path, objdump: Path) -> dict[int, tuple[int, str, str]]:
    command = subprocess.run(
        [str(objdump), "-d", str(elf)], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if command.returncode:
        raise ValueError(f"objdump failed for {elf}: {command.stderr.strip()}")
    instructions = {}
    for line in command.stdout.splitlines():
        match = DISASSEMBLY.match(line)
        if match is not None:
            address, encoding, mnemonic, operands = match.groups()
            instructions[int(address, 16)] = (
                int(encoding, 16), mnemonic.lower(), operands or ""
            )
    if not instructions:
        raise ValueError(f"no disassembled instructions in {elf}")
    return instructions


def vector_writeback_evidence(result: dict, instructions: dict) -> dict:
    comparison = result.get("vector_commit")
    if not isinstance(comparison, dict):
        return {"status": "NOT_RUN", "compared_bytes": 0,
                "skipped_unknown_bytes": 0, "per_mnemonic": {}}
    if comparison.get("status") != "PASS":
        return {"status": comparison.get("status", "UNKNOWN"),
                "compared_bytes": 0, "skipped_unknown_bytes": 0,
                "per_mnemonic": {}}
    counts: dict[str, Counter[str]] = {}
    compared_bytes = 0
    skipped_bytes = 0
    records = comparison.get("instructions")
    if not isinstance(records, list):
        raise ValueError("vector writeback comparison has no instruction records")
    for record in records:
        if record.get("status") not in {"PASS", "NON_BIT_EXACT", "UNOBSERVABLE"}:
            raise ValueError("vector writeback PASS contains an invalid instruction status")
        pc = int(record["pc"], 16)
        encoding = int(record["instruction"], 16)
        decoded = instructions.get(pc)
        if decoded is None or decoded[0] != encoding:
            raise ValueError(f"vector writeback differs from ELF at 0x{pc:x}")
        checked = record["compared_bytes"]
        skipped = record["skipped_unknown_bytes"]
        if (not isinstance(checked, int) or checked < 0 or
                not isinstance(skipped, int) or skipped < 0):
            raise ValueError(f"invalid vector writeback byte count at 0x{pc:x}")
        mnemonic = decoded[1]
        entry = counts.setdefault(mnemonic, Counter())
        entry["destination_requests"] += 1
        entry["compared_bytes"] += checked
        entry["skipped_unknown_bytes"] += skipped
        if record.get("status") == "PASS" and checked > 0:
            entry["requests_with_checked_bytes"] += 1
        compared_bytes += checked
        skipped_bytes += skipped
    if (compared_bytes != comparison.get("compared_bytes") or
            skipped_bytes != comparison.get("skipped_unknown_bytes") or
            len(records) != comparison.get("compared_instructions")):
        raise ValueError("vector writeback totals differ from instruction records")
    return {"status": "PASS", "compared_bytes": compared_bytes,
            "skipped_unknown_bytes": skipped_bytes,
            "per_mnemonic": {name: dict(counts[name]) for name in sorted(counts)}}


def audit_case(case: Path, objdump: Path) -> dict[str, object]:
    result_path = case / "result.json"
    if result_path.is_file():
        trace = case / "ara_commit_trace.csv"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("status") != "PASS":
            raise ValueError(f"case is not PASS: {case}")
        comparison = result.get("comparison") or {}
        comparison_status = comparison.get("status")
        if comparison_status not in (
            "PASS", "PREFIX", "MATCH", "TERMINAL_MATCH", "TERMINAL_TOHOST_MATCH"
        ):
            raise ValueError(f"case has no accepted Spike/RTL comparison: {case}")
        if comparison_status in {"MATCH", "TERMINAL_MATCH", "TERMINAL_TOHOST_MATCH"}:
            if not _full_architecture_match(comparison):
                raise ValueError(f"case reports an incomplete architectural comparison: {case}")
        elf = Path(result["elf"]).resolve()
        evidence_kind = ("random_spike_prefix" if comparison_status == "PREFIX"
                         else "random_spike_complete_result" if comparison_status != "PASS"
                         else "random_spike_legacy_pass")
        evidence_hashes = {"result": digest(result_path)}
    else:
        result_path = case.parent.parent / "summary.json"
        trace = case / "commit_trace.csv"
        elf = case / "input.elf"
        rows = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not any(
            row.get("status") == "PASS"
            and Path(row.get("artifact_dir", "")).resolve() == case.resolve()
            for row in rows if isinstance(row, dict)
        ):
            raise ValueError(f"directed case is not PASS: {case}")
        trace_summary_path = case / "trace_summary.json"
        trace_summary = json.loads(trace_summary_path.read_text(encoding="utf-8"))
        if trace_summary.get("status") != "VALID":
            raise ValueError(f"directed case has no valid commit trace: {case}")
        inputs_path = case / "inputs.json"
        if check_inputs(json.loads(inputs_path.read_text(encoding="utf-8")), elf):
            raise ValueError(f"directed case input identity differs: {case}")
        comparison = {"status": "NOT_RUN", "matched_instructions": None}
        evidence_kind = "directed_program_selfcheck"
        evidence_hashes = {
            "summary": digest(result_path),
            "trace_summary": digest(trace_summary_path),
            "inputs": digest(inputs_path),
        }
    if not elf.is_file() or not trace.is_file():
        raise ValueError(f"ELF or commit trace is missing: {case}")
    instructions = disassemble(elf, objdump)
    writeback = vector_writeback_evidence(result, instructions) if result_path.name == "result.json" else {
        "status": "NOT_RUN", "compared_bytes": 0,
        "skipped_unknown_bytes": 0, "per_mnemonic": {}}
    families: Counter[str] = Counter()
    mnemonics: Counter[str] = Counter()
    memory_modes: Counter[str] = Counter()
    sew_lmul: Counter[str] = Counter()
    policy_pairs: Counter[str] = Counter()
    v0t_policy_pairs: Counter[str] = Counter()
    resolved_policy_pairs: Counter[str] = Counter()
    resolved_v0t_policy_pairs: Counter[str] = Counter()
    resolved_type_policy: Counter[str] = Counter()
    mnemonic_type_policy: Counter[str] = Counter()
    masked_mnemonic_type_policy: Counter[str] = Counter()
    masked = 0
    policy_unknown = 0
    vector_retired = 0
    configuration_retired = 0
    configuration_unknown = 0
    configuration_runtime_inferred = 0
    cvxif_exception_responses = 0
    active_type = None
    active_policy = None
    active_policy_source = None
    gpr_values: list[int | None] = [0] + [None] * 31
    with trace.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"event", "pc", "insn", "trap"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"commit trace has missing columns: {trace}")
        for row in reader:
            if row["event"] == "cvx_resp":
                if row["trap"] not in ("0", "1"):
                    raise ValueError(f"invalid CVXIF response trap bit in {trace}")
                cvxif_exception_responses += row["trap"] == "1"
            if row["event"] != "retire" or row["trap"] != "0":
                continue
            pc = int(row["pc"], 16)
            instruction = int(row["insn"], 16)
            source_value = gpr_values[(instruction >> 20) & 31]
            rd_text, data_text = row.get("rd"), row.get("rd_wdata")
            if rd_text and data_text:
                rd = int(rd_text)
                if 0 < rd < 32:
                    try:
                        gpr_values[rd] = int(data_text, 16)
                    except ValueError:
                        gpr_values[rd] = None
            if not is_vector_instruction(instruction):
                continue
            decoded = instructions.get(pc)
            if decoded is None or decoded[0] != instruction:
                raise ValueError(f"retired instruction differs from ELF at 0x{pc:x}")
            _, mnemonic, operands = decoded
            if not mnemonic.startswith("v"):
                continue  # Vector CSR reads are tracked by commit comparison.
            vector_retired += 1
            mnemonics[mnemonic] += 1
            families[_family(mnemonic)] += 1
            mode = _memory_mode(mnemonic)
            if mode is not None:
                memory_modes[mode] += 1
            if mnemonic.startswith("vset"):
                configuration_retired += 1
                match = _VSET_RE.search(f"{mnemonic} {operands}")
                if match is None:
                    active_type = None
                    active_policy = None
                    active_policy_source = None
                    configuration_unknown += 1
                    if mnemonic == "vsetvl":
                        resolved = decode_committed_vtype(source_value)
                        if resolved is not None:
                            active_type, active_policy = resolved
                            active_policy_source = "committed_gpr"
                            configuration_runtime_inferred += 1
                else:
                    active_type = f"{match.group(1)}/{match.group(2)}"
                    active_policy = f"{match.group(3)}/{match.group(4)}"
                    active_policy_source = "static"
            else:
                if active_type is not None:
                    sew_lmul[active_type] += 1
                    if active_policy is not None:
                        type_policy = f"{active_type}/{active_policy}"
                        resolved_type_policy[type_policy] += 1
                        mnemonic_type_policy[f"{mnemonic}/{type_policy}"] += 1
                        if "v0.t" in operands:
                            masked_mnemonic_type_policy[f"{mnemonic}/{type_policy}"] += 1
                if active_policy is not None:
                    resolved_policy_pairs[active_policy] += 1
                    if active_policy_source == "static":
                        policy_pairs[active_policy] += 1
                else:
                    policy_unknown += 1
                if "v0.t" in operands:
                    masked += 1
                    if active_policy is not None:
                        resolved_v0t_policy_pairs[active_policy] += 1
                        if active_policy_source == "static":
                            v0t_policy_pairs[active_policy] += 1
    return {
        "case": str(case.resolve()),
        "status": "PASS",
        "scope": "DUT-retired RVV and CVXIF exception-response activity; directed selfcheck is not Spike instruction matching",
        "evidence_kind": evidence_kind,
        "comparison_status": comparison["status"],
        "spike_matched_prefix_instructions": comparison.get("matched_instructions"),
        "dut_retired_vector_instructions": vector_retired,
        "cvxif_exception_responses": cvxif_exception_responses,
        "dut_retired_configurations": configuration_retired,
        "configurations_without_static_type": configuration_unknown,
        "configurations_inferred_from_committed_gpr": configuration_runtime_inferred,
        "dut_retired_masked_instructions": masked,
        "mnemonics": dict(sorted(mnemonics.items())),
        "families": dict(sorted(families.items())),
        "memory_modes": dict(sorted(memory_modes.items())),
        "sew_lmul_known": dict(sorted(sew_lmul.items())),
        "statically_selected_policy_for_retired_nonconfig": dict(sorted(policy_pairs.items())),
        "statically_selected_policy_for_retired_v0t": dict(sorted(v0t_policy_pairs.items())),
        "resolved_policy_for_retired_nonconfig": dict(sorted(resolved_policy_pairs.items())),
        "resolved_policy_for_retired_v0t": dict(sorted(resolved_v0t_policy_pairs.items())),
        "resolved_sew_lmul_policy": dict(sorted(resolved_type_policy.items())),
        "retired_mnemonic_type_policy": dict(sorted(mnemonic_type_policy.items())),
        "retired_masked_mnemonic_type_policy": dict(sorted(masked_mnemonic_type_policy.items())),
        "retired_nonconfig_with_unknown_policy": policy_unknown,
        "vector_writeback_comparison": writeback,
        "sha256": {**evidence_hashes, "elf": digest(elf),
                   "commit_trace": digest(trace), "objdump": digest(objdump)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", type=Path, required=True)
    parser.add_argument("--objdump", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = [audit_case(case.resolve(), args.objdump.resolve()) for case in args.case]
    totals = Counter()
    policy_totals = Counter()
    v0t_policy_totals = Counter()
    resolved_policy_totals = Counter()
    resolved_v0t_policy_totals = Counter()
    policy_unknown_total = 0
    runtime_inferred_total = 0
    cvxif_exception_responses_total = 0
    for case in cases:
        totals.update(case["families"])
        policy_totals.update(case["statically_selected_policy_for_retired_nonconfig"])
        v0t_policy_totals.update(case["statically_selected_policy_for_retired_v0t"])
        resolved_policy_totals.update(case["resolved_policy_for_retired_nonconfig"])
        resolved_v0t_policy_totals.update(case["resolved_policy_for_retired_v0t"])
        policy_unknown_total += case["retired_nonconfig_with_unknown_policy"]
        runtime_inferred_total += case["configurations_inferred_from_committed_gpr"]
        cvxif_exception_responses_total += case["cvxif_exception_responses"]
    report = {"status": "PASS", "scope": "retired and exception-response activity, not full functional/code coverage",
              "cases": cases, "retired_family_totals": dict(sorted(totals.items())),
              "statically_selected_policy_totals": dict(sorted(policy_totals.items())),
              "statically_selected_v0t_policy_totals": dict(sorted(v0t_policy_totals.items())),
              "resolved_policy_totals": dict(sorted(resolved_policy_totals.items())),
              "resolved_v0t_policy_totals": dict(sorted(resolved_v0t_policy_totals.items())),
              "configurations_inferred_from_committed_gpr_total": runtime_inferred_total,
              "cvxif_exception_responses_total": cvxif_exception_responses_total,
              "retired_nonconfig_with_unknown_policy_total": policy_unknown_total}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"DUT-retired RVV activity: {len(cases)} PASS cases, "
          f"{sum(totals.values())} vector instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

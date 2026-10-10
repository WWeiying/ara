"""Audit explicit vstart writes linked to retired vector instructions."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .coverage_matrix import case_image_identity
from .dynamic_coverage import audit_case, disassemble
from .trace import is_vector_instruction


def collect_vstart(rows, instructions: dict) -> dict:
    registers: list[int | None] = [0] + [None] * 31
    writes = []
    linked = []
    pending = None
    for row in rows:
        if row["event"] != "retire" or row["trap"] != "0":
            if row["trap"] != "0":
                pending = None
            continue
        pc = int(row["pc"], 16)
        insn = int(row["insn"], 16)
        funct3 = (insn >> 12) & 7
        source = (insn >> 15) & 31
        if (insn & 0x7f) == 0x73 and ((insn >> 20) & 0xfff) == 8:
            writes_csr = funct3 in (1, 5) or (funct3 in (2, 3, 6, 7) and source != 0)
            if writes_csr:
                value = (registers[source] if funct3 == 1 else source
                         if funct3 == 5 else None)
                pending = {"write_pc": f"0x{pc:x}", "value": value,
                           "operation": funct3}
                writes.append(pending)
        if (insn & 0x7f) in (0x07, 0x27, 0x57) and is_vector_instruction(insn):
            decoded = instructions.get(pc)
            if decoded is None or decoded[0] != insn:
                raise ValueError(f"retired vector instruction differs from ELF at 0x{pc:x}")
            mnemonic = decoded[1]
            if pending is not None:
                if not mnemonic.startswith("vset"):
                    linked.append({**pending, "vector_pc": f"0x{pc:x}",
                                   "mnemonic": mnemonic})
                pending = None
        rd_text, data_text = row.get("rd"), row.get("rd_wdata")
        if rd_text and data_text:
            rd = int(rd_text)
            if 0 < rd < 32:
                try:
                    registers[rd] = int(data_text, 16)
                except ValueError:
                    registers[rd] = None
    return {
        "explicit_vstart_writes": len(writes),
        "linked_nonconfig_vector_instructions": len(linked),
        "linked_known_nonzero": sum(item["value"] is not None and item["value"] > 0
                                    for item in linked),
        "linked_known_zero": sum(item["value"] == 0 for item in linked),
        "linked_unknown_value": sum(item["value"] is None for item in linked),
        "linked": linked,
    }


def audit(case: Path, objdump: Path) -> dict:
    evidence = audit_case(case, objdump)
    trace = case / ("ara_commit_trace.csv" if (case / "result.json").is_file()
                    else "commit_trace.csv")
    with trace.open(newline="", encoding="utf-8") as stream:
        activity = collect_vstart(csv.DictReader(stream), disassemble(
            Path(case / "input.elf") if (case / "input.elf").is_file()
            else Path(json.loads((case / "result.json").read_text(encoding="utf-8"))["elf"]),
            objdump))
    return {"status": "OBSERVED" if activity["linked_known_nonzero"] else "NOT_OBSERVED",
            "scope": "explicit vstart CSR write followed by a retired non-vset vector instruction; not exception/restart functional signoff",
            "case": str(case.resolve()), "evidence_kind": evidence["evidence_kind"],
            "sha256": evidence["sha256"], "image_identity": case_image_identity(case),
            **activity}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--objdump", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    report = audit(args.case.resolve(), args.objdump.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"vstart activity: {report['status']}, "
          f"{report['linked_known_nonzero']} nonzero-linked instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

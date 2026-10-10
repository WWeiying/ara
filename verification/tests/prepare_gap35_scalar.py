#!/usr/bin/env python3
"""Audit gap35 artifacts and emit a selection for the owner's unified runner."""
import argparse
import json
from pathlib import Path
import subprocess

from build_gap35_scalar import DEST, NAMES, ROOT, sha

PREFIX = "ara_tb.dut.i_ara_soc.i_system.i_ariane.id_stage_i."
COMPRESSED = PREFIX + "genblk1.genblk1[0].compressed_decoder_i"
DECODER = PREFIX + "genblk2[0].decoder_i"
BASELINE = ROOT / "verification/out/gap34-current-20261001-01"
CACHE = ROOT / "verification/out/gap35-analysis-20261004-01/baseline-bits.json"
COUNTS = dict(zip(NAMES, (301, 33, 190)))
TRAPS = {
    "addi4spn_zero": (2, 0x0000), "addiw_x0": (2, 0x2001),
    "addi16sp_zero": (2, 0x6101), "lui_zero": (2, 0x6181),
    "lwsp_x0": (2, 0x4002), "ldsp_x0": (2, 0x6002),
    "jr_x0": (2, 0x8002), "ebreak": (2, 0x9002),
    "op_funct7": (4, 0xfed605b3), "op32_funct7": (4, 0xfed605bb),
    "slli_upper": (4, 0xfc161593), "srli_upper": (4, 0xfc165593),
    "slliw_shamt": (4, 0x0206159b), "srliw_shamt": (4, 0x0206559b),
    "opimm32_funct3": (4, 0x0016259b), "store_funct3": (4, 0x00b54023),
    "load_funct3": (4, 0x00057583), "branch_funct3": (4, 0x00d62263),
    "jalr_funct3": (4, 0x000515e7), "fld_fs_off": (2, 0x2108),
    "fsd_fs_off": (2, 0xa108),
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def elf_info(path):
    raw = subprocess.check_output([str(ROOT / "install/riscv-llvm/bin/llvm-readobj"),
        "--elf-output-style=JSON", "--sections", "--symbols", str(path)], timeout=30)
    info = json.loads(raw)[0]
    sections = {x["Section"]["Index"]: x["Section"] for x in info["Sections"]}
    symbols = {x["Symbol"]["Name"]["Name"]: x["Symbol"] for x in info["Symbols"]}
    data = path.read_bytes()

    def code(symbol, size=None):
        sym = symbols[symbol]
        section = sections[sym["Section"]["Value"]]
        offset = section["Offset"] + sym["Value"] - section["Address"]
        return data[offset:offset + (sym["Size"] if size is None else size)]

    require(symbols["rvtest_init"]["Size"] > 0, "M-mode hook missing")
    return sections, symbols, code


def instruction_words(data):
    words, pos = [], 0
    while pos < len(data):
        half = int.from_bytes(data[pos:pos + 2], "little")
        width = 4 if half & 3 == 3 else 2
        require(pos + width <= len(data), "truncated probe instruction")
        words.append((width, int.from_bytes(data[pos:pos + width], "little")))
        pos += width
    return words


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", type=Path, required=True)
    args = parser.parse_args()
    out = args.preflight.resolve(strict=True)
    pins = json.loads((out / "sources.json").read_text())
    require(all(sha(Path(p)) == digest for p, digest in pins.items()), "build source drift")
    baseline = json.loads((out / "baseline-shapes.json").read_text())
    cache = json.loads(CACHE.read_text())
    require(len(cache["tests"]) == 620, "baseline membership changed")
    for report in baseline["instances"]:
        row = cache["metrics"][report["metric"]][report["instance"]]
        require(report["raw_length"] == row["width"], "baseline width drift")
        for point in report["points"]:
            hit = bool(int(row["bits"], 16) & (1 << (row["width"] - point["offset"] - 1)))
            require(hit == point["hit"], "baseline cache/shape disagreement")
    independent = out / "baseline-independent-scan.json"
    if independent.exists():
        old = json.loads(independent.read_text())
        by_key = lambda rows: {(r["instance"], r["metric"]): r for r in rows}
        require(by_key(old["instances"]) == by_key(baseline["instances"]),
                "independent 620-VDB scan differs from shared cache")

    targets = {
        COMPRESSED: {74: "c.fld enabled FPU arm", 77: "c.fld expansion",
                     361: "c.addiw rd=x0", 417: "c.lui/c.addi16sp nzimm=0",
                     792: "c.lwsp rd=x0", 812: "c.ldsp rd=x0"},
        DECODER: {759: "OP invalid funct7", 1015: "OP-32 invalid funct7",
                  1065: "SLLI invalid upper immediate", 1074: "SRLI invalid upper immediate",
                  1175: "SLLIW shamt[5]=1", 1182: "SRLIW shamt[5]=1",
                  1184: "OP-IMM-32 invalid funct3", 1227: "STORE invalid funct3",
                  1253: "LOAD invalid funct3", 1612: "BRANCH invalid funct3",
                  1626: "JALR invalid funct3", 1829: "breakpoint PC tval"},
    }
    candidates = []
    for report in baseline["instances"]:
        if report["metric"] != "line":
            continue
        for line, meaning in targets[report["instance"]].items():
            points = [p for p in report["points"] if int(p["line"]) == line and not p["hit"]]
            require(points, f"target not a baseline-zero line: {line}")
            candidates.append(dict(instance=report["instance"], line=line, meaning=meaning,
                                   raw_offsets=[p["offset"] for p in points]))

    results = json.loads((out / "ready.json").read_text())
    require([r["test"] for r in results] == ["rvv:" + n for n in NAMES], "case set differs")
    elf_audits = []
    for row in results:
        name = row["test"].split(":")[1]
        log = Path(row["spike_log"]).read_text()
        require(f"{name} checks={COUNTS[name]} failures=0" in log and
                f"PASSED: {name}" in log and row["returncode"] == 0, "Spike check count/verdict")
        pair = []
        for key in ("elf", "spike_elf"):
            path = Path(row[key])
            require(sha(path) == row["elf_sha256" if key == "elf" else "spike_sha256"], "ELF drift")
            sections, symbols, code = elf_info(path)
            alloc_end = max(s["Address"] + s["Size"] for s in sections.values()
                            if s["Flags"]["Value"] & 2)
            if key == "elf":
                require(alloc_end < 0x80100000, "Ara ELF exceeds L2")
            checked = {}
            if name.endswith("illegal"):
                for trap, (width, bits) in TRAPS.items():
                    fault, resume = f"g35_{trap}_fault", f"g35_{trap}_resume"
                    pc = symbols[fault]["Value"]
                    require(pc % 4 == 2, "fault must exercise halfword PC")
                    require(symbols[resume]["Value"] - pc == width, "incorrect resume width")
                    require(int.from_bytes(code(fault, width), "little") == bits, "wrong trap encoding")
                    checked[trap] = dict(pc=hex(pc), width=width, bits=hex(bits))
            else:
                functions = ("probe",) if name.endswith("memory") else ("stack_alu", "control")
                for function in functions:
                    words = instruction_words(code(function))
                    for width, word in words:
                        if width == 4:
                            require(word & 0x7f not in (0x57, 0x0b, 0x2b, 0x5b, 0x7b),
                                    "vector/custom instruction in scalar probe")
                    checked[function] = code(function).hex()
                if name.endswith("memory"):
                    halfs = {w for width, w in words if width == 2}
                    require({0x5e74, 0xde34, 0x7e74, 0xfa74, 0x537e, 0xdb9a, 0x737e, 0xfb9a,
                             0x3e68, 0xb668, 0x307e, 0xb782, 0x220c, 0xa60c, 0x2082, 0xa806}
                            <= halfs, "compressed memory encoding missing")
                else:
                    halfs = [w for width, w in instruction_words(code("control")) if width == 2]
                    require(all(w in halfs for w in (0x9582, 0x8582, 0x8082)), "compressed JALR/JR missing")
                    require(sum(w & 0xe003 == 0xc001 for w in halfs) == 2 and
                            sum(w & 0xe003 == 0xe001 for w in halfs) == 2, "branch outcomes missing")
            pair.append(checked)
            elf_audits.append(dict(elf=str(path), sha256=sha(path), alloc_end=hex(alloc_end),
                                   probes=checked))
        if not name.endswith("illegal"):
            require(pair[0] == pair[1], "Ara/Spike probe machine code differs")

    audit = out / "source-audit.json"
    audit.write_text(json.dumps(dict(status="SPIKE_PASS_ELF_AUDITED_RTL_NOT_RUN",
        sources=pins, cache_sha256=sha(CACHE), baseline_line_candidates=candidates,
        elves=elf_audits, checks=COUNTS,
        semantics={
            "memory": "Independent C bitwise memory oracle, all 66 words including guards; signed LW; exact FP bits including sNaN; FCSR preserved.",
            "alu_control": "Known integer constants, RV64 shifts/word sign extension, legal hints, both branch outcomes, backward J, odd JR/JALR operand and exact PC+2 link.",
            "illegal": "21 individual fixed probes; exact cause/EPC/TVAL/count, destination sentinel, resume marker, all three memory words; breakpoint TVAL is PC; all probe PCs are 2 mod 4.",
        }, limits=["No VCS run or coverage gain claim.",
                   "Linebb indices are raw diagnostics; branch layout is inferred, not an official DVE point mapping.",
                   "ALU/control is a bounded adjacency check: its decoded families already have baseline hits.",
                   "RV32, NoFPU, RVH, Zcb/Zcmp/Zcmt legal paths are excluded; FS=Off is runtime state, not NoFPU."]), indent=2) + "\n")
    rationales = {
        "scalar_gap35_memory": "Reach baseline-zero compressed_decoder L74/L77 (c.fld), with all RV64C integer and FP register/stack memory forms, maximum offsets and known-bit oracles.",
        "scalar_gap35_alu_control": "Short RV64C ALU/hint/branch/jump boundary companion. Families already hit in baseline; no incremental line gain asserted. Check shift=63, word overflow, branch outcomes and PC+2 link.",
        "scalar_gap35_illegal": "Reach compressed_decoder L361/L417/L792/L812 and decoder L759/L1015/L1065/L1074/L1175/L1182/L1184/L1227/L1253/L1612/L1626/L1829 with reserved encodings and exact traps, not disabled-config legal arms.",
    }
    cases = []
    for row in results:
        name = row["test"].split(":")[1]
        sources = [p for p in pins if "/rv64uv/" not in p or
                   p.endswith((name + ".c", "scalar_gap35_common.h"))]
        sources += [str(Path(__file__).resolve()), str(Path(__file__).with_name("build_gap35_scalar.py")),
                    str(Path(__file__).with_name("inspect_gap35_scalar.py"))]
        cases.append(dict(name=row["test"], binary=row["elf"], sources=sources,
            evidence=[str(audit), row["spike_log"], row["spike_elf"],
                      str(out / "sources.json"), str(out / "build_commands.json"),
                      str(out / "spike_results.json"), str(out / "baseline-shapes.json"),
                      str(out / (Path(row["elf"]).name + ".dis"))],
            source_audit="Independent known-value scalar C oracle and same-source Spike; " + str(audit),
            targets=[COMPRESSED, DECODER], rationale=rationales[name], timeout_s=600))
    selection = out / "selection.json"
    with selection.open("x") as stream:
        json.dump(dict(baseline=str(BASELINE), baseline_bits=str(CACHE), cases=cases), stream, indent=2)
        stream.write("\n")
    print("Audited 6 ELFs, 42 trap encodings and 524 Spike checks; RTL not run.")
    print(selection)


if __name__ == "__main__":
    main()

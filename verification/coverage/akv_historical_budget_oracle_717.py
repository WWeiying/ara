"""Original software checks plus exact ELF/protocol audits; no EDA launch."""
import csv
import re
import struct
import sys
from pathlib import Path
from types import FunctionType

import gap46_akv_oracle as skew
import gap54_akv_oracle as bare_perf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification"))
from ara_verify.contract import check_contract_log
from ara_verify.trace import validate_trace

DESCRIPTOR = "akv_gap35_descriptor"
SKEW = "akv_gap46_skew_context"
CHECKS = {DESCRIPTOR: 6751, SKEW: 3237}
DESCRIPTOR_WORDS = [0x00b5605b] * 4 + [0x00b5205b] + [0x00b5605b] * 19 + [0x0005345b, 0x0000505b]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def elf_layout(blob, ram_bytes):
    require(len(blob) >= 64 and blob[:6] == b"\x7fELF\x02\x01", "ELF64 LE required")
    h = struct.unpack_from("<HHIQQQIHHHHHH", blob, 16)
    require(h[0:3] == (2, 243, 1) and h[3] == 0x80000000 and h[8] == 56 and h[10] == 64,
            "RISC-V entry/header layout differs")
    require(0 < h[9] < 256 and h[4] + h[8] * h[9] <= len(blob), "Truncated program headers")
    require(0 < h[11] < 65535 and h[5] + h[10] * h[11] <= len(blob), "Truncated sections")
    segments = []
    for i in range(h[9]):
        kind, flags, offset, va, pa, size, memory, align = struct.unpack_from("<IIQQQQQQ", blob, h[4] + i * 56)
        if kind != 1:
            continue
        require(size <= memory and offset + size <= len(blob) and va == pa
                and 0x80000000 <= pa and pa + memory <= 0x80000000 + ram_bytes,
                "ELF PT_LOAD outside fixed-image RAM or relocated")
        segments.append(dict(vaddr=va, paddr=pa, file_bytes=size, memory_bytes=memory, flags=flags))
    require(segments and any(s["flags"] & 1 and s["vaddr"] <= h[3] < s["vaddr"] + s["file_bytes"]
                             for s in segments), "Entry not executable")
    sections = [struct.unpack_from("<IIQQQQIIQQ", blob, h[5] + i * 64) for i in range(h[11])]
    def data(s):
        require(s[4] + s[5] <= len(blob), "Truncated ELF section")
        return blob[s[4]:s[4] + s[5]]
    symbols = {}
    for s in sections:
        if s[1] != 2:
            continue
        require(s[6] < len(sections) and s[9] == 24 and s[5] % 24 == 0, "Bad ELF symbol table")
        names = data(sections[s[6]])
        for off in range(0, s[5], 24):
            n, info, _, index, value, size = struct.unpack_from("<IBBHQQ", data(s), off)
            require(n < len(names) and b"\0" in names[n:], "Bad symbol name")
            name = names[n:names.index(0, n)].decode()
            if name and index and not name.startswith("$") and info & 15 != 4:
                require(name not in symbols, "Duplicate ELF symbol")
                symbols[name] = dict(value=value, size=size)
    def code(pc, length):
        candidates = [s for s in sections if s[1] != 8 and s[2] & 4
                      and s[3] <= pc and pc + length <= s[3] + s[5]]
        require(len(candidates) == 1, "Code address not uniquely executable")
        return data(candidates[0])[pc - candidates[0][3]:pc - candidates[0][3] + length]
    # Both original ELF runtimes have this identical M-hook/U-main transition.
    require(symbols["rvtest_init"]["value"] == 0x8000015c
            and code(0x8000009e, 14) == bytes.fromhex("970200009382e20b638302008292")
            and code(0x80000164, 4) == bytes.fromhex("73105530")
            and code(0x80000080, 4) == bytes.fromhex("73500030")
            and code(0x800000c0, 4) == bytes.fromhex("73002030")
            and symbols["main"]["value"] == 0x8000016a,
            "M-mode init hook / MRET-to-U main contract differs")
    result = dict(entry=h[3], ram_base=0x80000000, ram_bytes=ram_bytes, segments=segments,
                  init_hook=0x8000015c, mtvec_install=0x80000164, mret=0x800000c0,
                  main=0x8000016a, init_mode="M", main_mode="U", symbols=symbols)
    return result, code


def privilege_log(text):
    install = re.search(r"(?m)^.*\bM 0000000080000164 [01] 30551073 csrw.*mtvec.*0000000080000104.*$", text)
    mret = re.search(r"(?m)^.*\bM 00000000800000c0 [01] 30200073 mret.*$", text)
    main = re.search(r"(?m)^.*\bU 000000008000016a [01] ", text)
    require(install and mret and main and install.start() < mret.start() < main.start(),
            "Fresh core trace lacks M-hook before MRET / U-main evidence")
    return dict(status="PASS", install_line=install[0], mret_line=mret[0], main_line=main[0])


def descriptor_log(log):
    expected = f"PASSED: {DESCRIPTOR} checks=6751 errors=0"
    require([s for s in log.splitlines() if s.startswith("PASSED:")] == [expected],
            "Descriptor full 6751-check PASS missing/duplicate")
    require(not re.search(r"(?im)^\s*(?:FAIL(?:ED)?\b|ERROR\b|Fatal\b|Assertion\b)|\$fatal", log),
            "Descriptor software failure/assertion")
    return dict(status="PASS", checks=6751, invalid_mutations=23, valid_fills=1,
                row_loads=1, releases=1, destination_halfwords_per_compare=256)


def descriptor_trace(path, core, code):
    pending, custom, retired = {}, [], []
    reqs = resps = faults = 0
    with Path(path).open() as stream:
        for row in csv.DictReader(stream):
            event, word = row["event"], int(row["insn"], 16)
            if event == "cvx_req":
                key = int(row["trans_id"])
                require(key not in pending, "Duplicate live request")
                pending[key] = (word, len(custom) if word & 127 == 91 else None)
                reqs += 1
                if word & 127 == 91:
                    custom.append(dict(word=word))
            elif event == "cvx_resp":
                key = int(row["trans_id"])
                require(key in pending, "Orphan response")
                word, index = pending.pop(key)
                fault = int(row["trap"])
                faults += fault
                resps += 1
                if index is not None:
                    custom[index]["fault"] = fault
                else:
                    require(fault == 0, "Noncustom vector fault")
            elif event == "retire" and word & 127 == 91:
                pc = int(row["pc"], 16)
                require(int.from_bytes(code(pc, 4), "little") == word and int(row["trap"]) == 0,
                        "Custom retirement differs from exact ELF")
                retired.append(word)
    require(not pending and reqs == resps and faults == 23, "Descriptor protocol conservation differs")
    require([r["word"] for r in custom] == DESCRIPTOR_WORDS
            and [r.get("fault") for r in custom] == [1] * 23 + [0] * 3,
            "Descriptor command/mutation outcome sequence differs")
    require(retired == DESCRIPTOR_WORDS[-3:], "Descriptor successful fill/load/release retirement differs")
    exceptions = re.findall(r"Exception @[^\n]*PC: ([0-9a-f]+), Cause: ([^,\n]+),\s*\n\s*tval: ([0-9a-f]+)", core)
    require(len(exceptions) == 23, "Descriptor core exception count differs")
    for (pc, cause, tval), word in zip(exceptions, DESCRIPTOR_WORDS[:23]):
        require(cause == "Illegal Instruction" and int.from_bytes(code(int(pc, 16), 4), "little") == word
                and int(tval, 16) in (0, word), "Descriptor trap cause/ELF PC/tval differs")
    return dict(status="PASS", requests=reqs, responses=resps, exceptions=faults,
                custom_requests=26, custom_words=DESCRIPTOR_WORDS, core_traps=23)


def skew_log(log, elf):
    # Private namespace: do not mutate either frozen helper. Functional checks
    # remain original gap46; the already-existing bare-address PERF gate is reused.
    namespace = dict(skew.__dict__, perf_records=bare_perf.perf_records)
    function = FunctionType(skew.validate_log.__code__, namespace, "original_gap46_full_checks")
    return function(log, False, elf)


def verify(case, output, blob, ram_bytes):
    layout, code = elf_layout(blob, ram_bytes)
    output = Path(output)
    log = (output / "run.vcs.log").read_text(errors="strict")
    console = (output / "console.log").read_text(errors="strict")
    core = (output / "trace_hart_0.log").read_text(errors="strict")
    require(log.count("Core Test *** SUCCESS ***") == 1, "Core terminal SUCCESS missing/duplicate")
    for path in (output / "console.log", output / "run.vcs.log"):
        require(not check_contract_log(path), "Complete contract/log validation rejected: " + str(path))
    trace = output / "commit_trace.csv"
    generic = validate_trace(trace)
    privilege = privilege_log(core)
    if case == DESCRIPTOR:
        uart = descriptor_log(log)
        require(descriptor_log(console) == uart, "Console/VCS descriptor oracle differs")
        protocol = descriptor_trace(trace, core, code)
    elif case == SKEW:
        elf = skew.elf_audit(blob)
        uart = skew_log(log, elf)
        require(skew_log(console, elf) == uart, "Console/VCS gap46 oracle differs")
        protocol = skew.trace_audit(trace, elf, log)
    else:
        raise ValueError("Only the two approved budget-retry cases are eligible")
    require(uart["checks"] == CHECKS[case], "Full original check count reduced")
    return dict(status="FULL_ORIGINAL_ORACLE_PASS_NOT_ADMITTED", case=case, checks=CHECKS[case],
                generic_trace=generic, uart=uart, protocol=protocol, privilege=privilege,
                elf_layout=layout, coverage_admitted=False, application_approval=False,
                data_oracle_scope="Unchanged original full software per-byte/trap/guard checks; independent ELF/protocol/CSR binding. Not a new per-byte ISA differential replay.")

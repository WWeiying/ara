"""One OPIVX VSBC vd0 host/Spike preflight, never VCS or admission."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

import run_gap95_simulation as life

ROOT, OUT = life.ROOT, life.OUT
sys.path.insert(0, str(ROOT / "verification"))
from ara_verify.random_rvv import _elf_symbol
from ara_verify.spike_trace import parse_spike_commits

NAME = "vopivx_vsbc_vd0"
APP = ROOT / "apps/riscv-tests/isa/rv64uv/vopivx_vsbc_vd0.c"
REVIEW = OUT / "rvv-dispatcher-opivx-vsbc-vd0-stimulus-review-717-20261006-01.json"
REVIEW_SEAL = "164edcbe1098354d9da0844e9d4efbe79dad58b0b3b490ea1102598c7c07c9f3"
TEMPLATE = OUT / "gap101a-nf-emul-only-preflight-715-20261006-01/compile-command.json"
TEMPLATE_SEAL = "a9abf1499893bb51291c22fa21d3599d4010fc9ae1370178e8f7e84cda7fe5f0"
LLVM = Path("/home/wangwy/openproject/ara/install/riscv-llvm/bin")
SPIKE = Path("/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike")
CHECKS = 138
SYMBOLS = ("tohost", "g75_result", "num_failed", "trap_fail", "gvs_ledger", "gvs_post",
           "gvs_restore", "gvs_traps", "gvs_dump", "gvs_bad", "gvs_recovery",
           "gvs_handler", "gvs_handler_end")


def require(value, message):
    if not value:
        raise ValueError(message)


def seed(reg, i):
    if reg == 0:
        return 10 if i == 0 else (i * 7 + 0x65) & 255
    if reg == 1:
        return [0, 3, 255, 128][i] if i < 4 else (i * 19 + 0x31) & 255
    return 0x5a


def expected_register(reg, recovery=False):
    value = bytearray(seed(reg, i) for i in range(128))
    if recovery and reg == 2:
        value[:4] = bytes((seed(1, i) - 3 - ((10 >> i) & 1)) & 255 for i in range(4))
    return bytes(value)


def store_width(instruction):
    if instruction & 3 != 3:
        require(instruction & 3 in (0, 2) and instruction >> 13 in (6, 7), "Unknown compressed store")
        return {6: 4, 7: 8}[instruction >> 13]
    opcode, width = instruction & 127, (instruction >> 12) & 7
    if opcode == 0x23:
        require(width <= 3, "Unknown scalar store")
        return 1 << width
    require(opcode == 0x27 and width in (0, 5, 6, 7), "Unknown vector store")
    return {0: 1, 5: 2, 6: 4, 7: 8}[width]


def validate(commits, symbols, trace):
    events = re.findall(r"exception ([^,\n]+), epc (0x[0-9a-fA-F]+)", trace)
    require([(n, int(pc, 16)) for n, pc in events] ==
            [("trap_illegal_instruction", symbols["gvs_bad"])] and trace.count("exception ") == 1,
            "Not exactly one illegal trap at fault PC")
    require(not any(c.pc in (symbols["gvs_bad"], symbols["trap_fail"]) for c in commits),
            "Illegal word retired or fatal handler entered")
    memory, terminal, vectors = {}, [], []
    handler_stores = []
    handler = [c for c in commits if symbols["gvs_handler"] <= c.pc < symbols["gvs_handler_end"]]
    require(handler and sum(c.pc == symbols["gvs_handler"] for c in handler) == 1,
            "Handler entry missing/repeated")
    for c in commits:
        for a, v in c.memory_accesses:
            if v is None:
                continue
            width = store_width(c.instruction)
            require(0 <= v < 1 << (8 * width), "Store value exceeds width")
            for i in range(width):
                memory[a + i] = (v >> (8 * i)) & 255
            if a == symbols["tohost"]:
                terminal.append(v)
            if c in handler:
                handler_stores.append((a, width))
        for reg, value in c.vector_writes.items():
            vectors.append((c.pc, reg, value))
    def read(name, offset=0, width=8):
        addr = symbols[name] + offset
        require(all(addr + i in memory for i in range(width)), "Missing signature bytes: " + name)
        return int.from_bytes(bytes(memory[addr + i] for i in range(width)), "little")
    require(terminal == [1] and read("g75_result", width=4) == CHECKS and
            read("g75_result", 4, 4) == read("num_failed", width=4) == 0,
            "Terminal/software result differs")
    restore = [read("gvs_restore", i * 8) for i in range(12)]
    require(all(restore[i] == restore[i + 1] for i in range(0, 12, 2)) and
            restore[0] == symbols["trap_fail"] and restore[2] == 0 and
            0x80100000 <= restore[4] < 0x80200000 and restore[4] % 16 == 0 and
            restore[6:] == [0, 0, 0, 0, 0, 0], "Context restoration differs")
    sp = restore[4]
    require([read("gvs_ledger", i * 8) for i in range(12)] ==
            [2, symbols["gvs_bad"], 0x4883c057, 4, 0, 1, 5, 1, 0x2222, 3, 117, sp],
            "Trap ledger/vstart differs")
    require([read("gvs_post", i * 8) for i in range(9)] ==
            [0x1111, 0x2222, 3, sp, 1, 4, 0, 5, 117], "Handler register/CSR side effects")
    require(read("gvs_traps") == 1, "Trap count differs")
    for phase in range(2):
        for reg in range(3):
            wanted = bytes([0xa5] * 8) + expected_register(reg, bool(phase)) + bytes([0xa5] * 8)
            actual = b"".join(read("gvs_dump", ((phase * 3 + reg) * 18 + w) * 8).to_bytes(8, "little")
                              for w in range(18))
            require(actual == wanted, "Complete VRF dump/guard differs")
    require(Counter(reg for _, reg, _ in vectors) == Counter({0: 1, 8: 1, 10: 2}),
            "VRF write population differs")
    for reg, logical in [(0, 0), (8, 1), (10, 2)]:
        actual = [(pc, v) for pc, r, v in vectors if r == reg]
        wanted = [int.from_bytes(expected_register(logical), "little")]
        if reg == 10:
            wanted.append(int.from_bytes(expected_register(2, True), "little"))
            require(actual[-1][0] == symbols["gvs_recovery"], "Recovery PC differs")
        require([v for _, v in actual] == wanted, "VRF initialization/recovery value differs")
    allowed = {(symbols["gvs_ledger"] + i * 8, 8) for i in range(12)} | {(symbols["gvs_traps"], 8)}
    require(Counter(handler_stores) == Counter(allowed), "Handler memory footprint differs")
    require(all(not c.vector_writes and not c.fpr_writes and
                set(c.gpr_writes) <= {5, 6, 7} and
                set(c.csr_writes) <= {0x300, 0x340, 0x341} for c in handler),
            "Handler touched protected register/CSR")
    return dict(status="OPIVX_VSBC_SPIKE_FULL_ORACLE_PASS_NOT_DUT", checks=CHECKS,
                illegal_traps=1, trap_vstart=1, post_mret_vstart=1, illegal_vector_write_bytes=0,
                handler_store_words=13, observed_vrf_bytes=768, guard_bytes=96,
                recovery_vector_bytes=128, coverage_admitted=False)


def verify_elf(blob, symbols):
    require(blob[:6] == b"\x7fELF\x02\x01", "Not ELF64 little endian")
    h = struct.unpack_from("<HHIQQQIHHHHHH", blob, 16)
    require(h[:3] == (2, 243, 1) and h[10] == 64 and h[5] + h[11] * 64 <= len(blob), "ELF header")
    for name, word in [("gvs_bad", 0x4883c057), ("gvs_recovery", 0x4883c557)]:
        pc = symbols[name]; owners = []
        require(pc % 4 == 0, "PC alignment")
        for i in range(h[11]):
            sec = struct.unpack_from("<IIQQQQIIQQ", blob, h[5] + i * 64)
            if sec[1] == 1 and sec[2] & 4 and sec[3] <= pc and pc + 4 <= sec[3] + sec[5]:
                owners.append(struct.unpack_from("<I", blob, sec[4] + pc - sec[3])[0])
        require(owners == [word], "Exact fault/recovery ELF word differs")


def verify(out, seal):
    pre = life.read_bound(out / "preflight-manifest.json", seal)
    require(pre["status"] == "OPIVX_VSBC_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS" and
            pre["case"] == NAME and pre["baseline_tests"] == 717 and
            pre["coverage_admitted"] is False and pre["vcs_started"] is False, "Preflight contract")
    life.check(pre["pins"])
    elf = out / "input.elf"
    symbols = {n: _elf_symbol(elf, LLVM / "llvm-readelf", n) for n in SYMBOLS}
    require(symbols == pre["symbols"], "ELF symbols differ")
    verify_elf(elf.read_bytes(), symbols)
    result = validate(parse_spike_commits(out / "spike.trace"), symbols, (out / "spike.trace").read_text())
    require(result == pre["validation"], "Full replay result differs")
    return pre


def build(out):
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct directory required")
    review = life.read_bound(REVIEW, REVIEW_SEAL)
    life.check(review["pins"])
    pins = dict(review["pins"]); pins[str(REVIEW)] = REVIEW_SEAL
    includes = ROOT / "verification/tests"
    command = life.read_bound(TEMPLATE, TEMPLATE_SEAL)
    require(command[0] == str(LLVM / "clang") and command.count(str(OUT / "gap101a-nf-emul-only-preflight-715-20261006-01/input.elf")) == 1,
            "Compile template contract")
    original = ROOT / "apps/riscv-tests/isa/rv64uv/vgap101a_nf_emul_only.c"
    require(command.count(str(original)) == 1, "Compile template source")
    command = [str(APP) if x == str(original) else str(out / "input.elf") if
               x == str(OUT / "gap101a-nf-emul-only-preflight-715-20261006-01/input.elf") else x for x in command]
    paths = [APP, TEMPLATE, includes / "opivx_vsbc_reference.h", includes / "opivx_vsbc_host_reference.c",
             includes / "gap75_start.S", includes / "gap75.ld", LLVM / "clang", LLVM / "ld.lld",
             LLVM / "llvm-readelf", SPIKE, Path(__file__).resolve(), Path(life.__file__).resolve(),
             Path(__file__).with_name("test_opivx_vsbc_preflight.py"),
             Path(__file__).with_name("run_opivx_vsbc_simulation.py"),
             ROOT / "verification/ara_verify/spike_trace.py", ROOT / "verification/ara_verify/trace.py",
             ROOT / "verification/ara_verify/random_rvv.py", Path("/usr/bin/cc").resolve()]
    pins = life.merge_pins(pins, {str(p.absolute()): life.digest(p) for p in paths})
    life.check(pins)
    out.mkdir()
    life.save(out / "input-pins.json", pins)
    life.save(out / "target-before.json", review["targets"])
    try:
        host = ["/usr/bin/cc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(includes / "opivx_vsbc_host_reference.c"), "-o", str(out / "host-reference")]
        life.save(out / "host-command.json", host)
        with (out / "host.log").open("x") as log:
            subprocess.run(host, check=True, timeout=60, stdout=log, stderr=subprocess.STDOUT)
            subprocess.run([str(out / "host-reference")], check=True, timeout=10, stdout=log, stderr=subprocess.STDOUT)
        life.save(out / "compile-command.json", command)
        with (out / "compile.log").open("x") as log:
            subprocess.run(command, check=True, timeout=120, stdout=log, stderr=subprocess.STDOUT)
        symbols = {n: _elf_symbol(out / "input.elf", LLVM / "llvm-readelf", n) for n in SYMBOLS}
        verify_elf((out / "input.elf").read_bytes(), symbols)
        spike = [str(SPIKE), "--isa=rv64gcv_zfh_zvfh_zvl1024b", "--priv=msu", "--pmpregions=0", "-l", "--log-commits", str(out / "input.elf")]
        life.save(out / "spike-command.json", spike)
        with (out / "spike.stdout").open("x") as stdout, (out / "spike.trace").open("x") as trace:
            subprocess.run(spike, check=True, timeout=120, stdout=stdout, stderr=trace)
        result = validate(parse_spike_commits(out / "spike.trace"), symbols, (out / "spike.trace").read_text())
        life.save(out / "spike-validation.json", result)
        life.check(pins)
        pins = life.merge_pins(pins, {str(p): life.digest(p) for p in out.iterdir() if p.is_file()})
        pre = dict(status="OPIVX_VSBC_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS", case=NAME, baseline_tests=717,
                   pins=pins, symbols=symbols, validation=result, targets=review["targets"],
                   input_elf=str(out / "input.elf"), checks=CHECKS, coverage_admitted=False,
                   vcs_started=False, rtl_changed=False, measured_raw_increment=None)
        life.save(out / "preflight-manifest.json", pre)
        print(json.dumps(dict(output=str(out), seal=life.digest(out / "preflight-manifest.json"), validation=result)))
    except Exception as error:
        life.save(out / "failure.json", dict(status="PREFLIGHT_FAILED_NOT_VCS", reason=str(error)))
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("build", "verify"))
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--seal")
    a = p.parse_args()
    require((a.mode == "verify") == bool(a.seal), "Only verify requires seal")
    out = a.output.absolute()
    if a.mode == "build":
        build(out)
    else:
        verify(out, a.seal)
        print("VERIFY_PASS host/Spike full replay; VCS_NOT_STARTED admitted0")


if __name__ == "__main__":
    main()

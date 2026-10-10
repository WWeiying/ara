"""Raw717 widening-accumulator cross-boundary host/Spike preflight, not DUT PASS."""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess
import sys

import build_gap101_preflight as old
from closure_point_inventory import points

s = old.shared
ROOT, OUT, require = old.ROOT, old.OUT, old.require
NAME = "vgap102_widen_acc_cross_v2"
APP = ROOT / "apps/riscv-tests/isa/rv64uv" / (NAME + ".c")
BASE = OUT / "cache-port1-offline-admitted-717-20261006-01"
BASE_SEAL = "82cd5f277d934c7b2435bfff3e2af1d4dd64cdea6435baba67b72749be183b62"
CHECKS = 723
WORD = (0b111100 << 26) | (1 << 25) | (12 << 20) | (10 << 15) | (6 << 12) | (8 << 7) | 0x57
SYMBOLS = ("tohost", "g75_result", "num_failed", "g75_trap", "trap_fail", "g102_dump",
           "g102_seed_dump", "g102_source_dump", "g102_csr", "g102_recovery_dump",
           "g102_load_seed", "g102_load_source", "g102_mac", "g102_recovery")


def images(vl=129):
    require(129 <= vl <= 256, "Not a legal crossed e16,m4 boundary")
    image = bytearray(b"".join(bytes([0x40 + r]) * 128 for r in range(32)))
    seed = b"".join((0x51000000 + 131 * i).to_bytes(4, "little") for i in range(256))
    source = b"".join(((0x1000 + 37 * i) & 0xffff).to_bytes(2, "little") for i in range(256))
    image[8*128:16*128] = seed
    seeded = bytes(image)
    image[12*128:12*128+2*vl] = source[:2*vl]
    before = bytes(image)
    # Both operands are read from the pre-instruction image, never updated in place.
    for i in range(vl):
        accumulator = int.from_bytes(before[8*128+4*i:8*128+4*i+4], "little")
        multiplicand = int.from_bytes(before[12*128+2*i:12*128+2*i+2], "little")
        image[8*128+4*i:8*128+4*i+4] = ((accumulator + 7*multiplicand) & 0xffffffff).to_bytes(4, "little")
    return dict(seeded=seeded, before=before, after=bytes(image), seed=seed, source=source)


def expected_words():
    data = images()
    result = {}
    for name, blob in (("g102_dump", data["after"]), ("g102_seed_dump", data["seed"]),
                       ("g102_source_dump", data["source"])):
        for offset in range(0, len(blob), 8):
            result[name, offset] = int.from_bytes(blob[offset:offset+8], "little")
    for i, value in enumerate([129, 10, 0, 0] * 2):
        result["g102_csr", i*8] = value
    recovery = bytearray([0xa5] * 64)
    recovery[16:20] = data["after"][8*128:8*128+4]
    for i in range(8):
        result["g102_recovery_dump", i*8] = int.from_bytes(recovery[i*8:i*8+8], "little")
    return result


def validate(commits, symbols, trace):
    require("exception " not in trace and not any(c.pc == symbols["trap_fail"] for c in commits), "Unexpected trap")
    writes = {a: v for c in commits for a, v in c.memory_accesses if v is not None}
    terminal = [v for c in commits for a, v in c.memory_accesses if a == symbols["tohost"] and v is not None]
    require(terminal == [1] and writes.get(symbols["g75_result"]) == CHECKS and
            writes.get(symbols["g75_result"] + 4) == writes.get(symbols["num_failed"]) == 0, "Software checks differ")
    for (name, offset), value in expected_words().items():
        require(writes.get(symbols[name] + offset) == value, "Independent oracle differs: %s+%d" % (name, offset))
    require([writes.get(symbols["g75_trap"] + i*8) for i in range(3)] == [0, 0, 0], "Trap ledger differs")
    data, initial, operations = images(), Counter(), Counter()
    stages = {symbols["g102_load_seed"]: (range(8,16), data["seeded"]),
              symbols["g102_load_source"]: (range(12,16), data["before"]),
              symbols["g102_mac"]: (range(8,16), data["after"])}
    mac = [c for c in commits if c.pc == symbols["g102_mac"]]
    require(len(mac) == 1 and mac[0].instruction == WORD and mac[0].vector_sew == 16 and
            mac[0].vector_lmul == "m4" and mac[0].vector_vl == 129 and mac[0].vector_vstart == 0 and
            mac[0].vector_tail_agnostic is False and mac[0].vector_mask_agnostic is False, "MAC identity/policy differs")
    require(set(range(8,13)) <= mac[0].vector_writes.keys(), "Missing active MAC register result")
    for c in commits:
        if c.pc in stages:
            operations[c.pc] += 1
            allowed, expected = stages[c.pc]
            require(c.vector_writes, "Missing vector stage")
            for reg, value in c.vector_writes.items():
                require(reg in allowed and value == int.from_bytes(expected[reg*128:(reg+1)*128], "little"),
                        "Vector stage bytes differ")
        else:
            for reg, value in c.vector_writes.items():
                require(reg in range(32) and value == int.from_bytes(bytes([0x40+reg])*128, "little"),
                        "Unexpected vector side effect")
                initial[reg] += 1
    require(initial == Counter({r:1 for r in range(32)}) and operations == Counter(stages.keys()),
            "Initialization/operation population differs")
    require(len([c for c in commits if c.pc == symbols["g102_recovery"]]) == 1, "Recovery store missing/duplicate")
    return dict(status="GAP102_SPIKE_INDEPENDENT_FULL_VRF_ORACLE_PASS_NOT_DUT", checks=CHECKS,
                mac_opcode=hex(WORD), vl=129, source_start_wide_element=128, active_result_bytes=516,
                full_vrf_bytes=4096, source_guard_bytes=1536, csr_snapshots=2, recovery_guard_bytes=64,
                illegal_traps=0, coverage_admitted=False, measured_raw_increment=None)


def target_evidence():
    pins = {}
    def pin(path, expected=None):
        path = Path(path).absolute()
        actual = s.sha(path)
        require(expected is None or actual == expected, "Source/input identity differs: " + str(path))
        pins.update(s.merge_pins(pins, {str(path): actual}))
        return path
    manifest = json.loads(pin(BASE / "admission-manifest.json", BASE_SEAL).read_bytes())
    state = json.loads(pin(BASE / "status.json", manifest["output_pins"][str(BASE / "status.json")]).read_bytes())
    bits = json.loads(pin(BASE / "combined-bits.json", manifest["output_pins"][str(BASE / "combined-bits.json")]).read_bytes())
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and state["aggregate_passed"] == 717 and
            len(bits["tests"]) == len(set(bits["tests"])) == 717, "Not frozen717")
    require(pin(BASE / "combined-inputs.txt", manifest["output_pins"][str(BASE / "combined-inputs.txt")]).read_text().splitlines()
            == [str(old.BUILD / "sim/simv.vdb"), *bits["tests"]], "717 membership differs")
    sources = json.loads(pin(old.BUILD / "build-source-pins.json",
        "6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b").read_bytes())
    original = ROOT / "hardware/src/ara_dispatcher.sv"
    snapshot = pin(OUT / "old-image-source-evidence-20261006-01/ara_dispatcher.sv", sources[str(original)])
    require(s.sha(snapshot) == "9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43", "Wrong old dispatcher")
    for path in (ROOT / "hardware/include/ara_pkg.sv", ROOT / "hardware/src/lane/vmfpu.sv"):
        pin(path, sources[str(path)])
    design = s.Design(old.BUILD / "sim/simv.vdb")
    require(design.source(old.SCOPE)["resolved_path"] == str(original), "Wrong dispatcher source owner")
    for relative, expected in bits["design"].items():
        pin(design.db / relative, expected)
    for relative in ("auxiliary/verilog.sourceinfo.xml", "shape/branch.verilog.info.xml",
                     "shape/line.verilog.info.xml", "shape/tgl.verilog.info.xml", "shape/tgl.verilog.shape.xml"):
        pin(design.db / relative)
    record = bits["metrics"]["branch"][old.SCOPE]
    definition = design.definition(old.SCOPE, "branch")
    require(record["checksum"] == definition.get("chksum") == "1558979345", "Branch checksum differs")
    point = next(p for p in points("branch", definition, record["width"]) if p["raw_index"] == 127)
    require(point["native_id"] == "25" and point["vector"] == "1002" and
            point["attributes"]["chksum"] == "3771491581", "Target native identity differs")
    exps = {e["id"]: e for e in point["expressions"]}
    require(exps["5843"]["index"] == "1259" and exps["5829"]["index"] == "1254" and
            point["native_vector"]["vector"][-1259] == "0" and point["native_vector"]["vector"][-1254] == "1",
            "Not the accumulator boundary false arm")
    require(not int(record["bits"],16) & (1 << (record["width"]-128)), "Target already hit717")
    s.check(pins)
    return dict(status="GAP102_RAW717_TARGET_ZERO_NOT_COVERAGE_PROMISE", baseline_tests=717, pins=pins,
                targets=[dict(scope=old.SCOPE, metric="branch", point=point, width=record["width"],
                              checksum=record["checksum"], hit_before=False)],
                hypothesis="VL129 exceeds overlap_source_base wide-element128; if the overlap MAC path is reached, line5843 false arm executes.",
                source_path=str(original), source_read_path=str(snapshot), prior_case_vl=79,
                budget_seconds=600, exclusions_generated=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    out = p.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh output required")
    evidence = target_evidence()
    include = ROOT / "verification/tests"
    host = include / "gap102_host_reference.c"
    paths = [APP, host, include / "gap102_reference.h", include / "gap75_start.S", include / "gap75.ld",
             Path(__file__).resolve(), Path(__file__).with_name("test_build_gap102_preflight_v2.py"),
             s.LLVM / "clang", s.LLVM / "llvm-readelf", s.SPIKE, Path("/usr/bin/cc").resolve()]
    paths += [Path(m.__file__).resolve() for m in tuple(sys.modules.values())
              if getattr(m, "__file__", None) and str(ROOT / "verification") in str(m.__file__)]
    pins = s.merge_pins(evidence["pins"], {str(path):s.sha(path) for path in paths})
    s.check(pins)
    out.mkdir()
    s.save(out / "input-pins.json", pins)
    s.save(out / "target-before.json", evidence)
    try:
        command = ["/usr/bin/cc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(host), "-o", str(out / "host-reference")]
        s.save(out / "host-command.json", command)
        with (out / "host.log").open("x") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
            subprocess.run([str(out / "host-reference")], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=10)
        elf = out / "input.elf"
        command = [str(s.LLVM / "clang"), "--target=riscv64-unknown-elf", "-march=rv64gcv_zfh_zvfh", "-mabi=lp64d",
            "-mcmodel=medany", "-mno-relax", "-msmall-data-limit=0", "-O2", "-fno-vectorize", "-fno-slp-vectorize",
            "-ffreestanding", "-DVLEN=1024", "-DNR_LANES=4", "-I"+str(include), "-fuse-ld=lld", "-nostdlib",
            "-T"+str(include / "gap75.ld"), str(include / "gap75_start.S"), str(APP), "-o", str(elf)]
        s.save(out / "compile-command.json", command)
        with (out / "compile.log").open("x") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        symbols = {name:s._elf_symbol(elf, s.LLVM / "llvm-readelf", name) for name in SYMBOLS}
        blob = elf.read_bytes()
        header = struct.unpack_from("<HHIQQQIHHHHHH", blob, 16)
        words = []
        for i in range(header[11]):
            sec = struct.unpack_from("<IIQQQQIIQQ", blob, header[5]+i*64)
            pc = symbols["g102_mac"]
            if sec[1] == 1 and sec[2]&4 and sec[3] <= pc and pc+4 <= sec[3]+sec[5]:
                words.append(struct.unpack_from("<I", blob, sec[4]+pc-sec[3])[0])
        require(words == [WORD], "ELF MAC opcode differs")
        command = [str(s.SPIKE), "--isa=rv64gcv_zfh_zvfh_zvl1024b", "--priv=msu", "--pmpregions=0", "-l", "--log-commits", str(elf)]
        s.save(out / "spike-command.json", command)
        with (out / "spike.stdout").open("x") as stdout, (out / "spike.trace").open("x") as trace:
            subprocess.run(command, stdout=stdout, stderr=trace, check=True, timeout=120)
        result = validate(s.parse_spike_commits(out / "spike.trace"), symbols, (out / "spike.trace").read_text())
        s.save(out / "spike-validation.json", result)
        s.check(pins)
        pins = s.merge_pins(pins, {str(f):s.sha(f) for f in out.iterdir() if f.is_file()})
        s.save(out / "preflight-manifest.json", dict(status="GAP102_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS", case=NAME,
            baseline_tests=717, checks=CHECKS, symbols=symbols, pins=pins, validation=result,
            input_elf=str(elf), input_spike_trace=str(out / "spike.trace"), target_before=str(out / "target-before.json"),
            target_unhit_count=1, coverage_admitted=False, rtl_changed=False, vcs_started=False, measured_raw_increment=None))
        print(json.dumps(dict(output=str(out), seal=s.sha(out / "preflight-manifest.json"), opcode=hex(WORD))))
    except Exception as error:
        s.save(out / "failure.json", dict(status="GAP102_PREFLIGHT_FAILED", reason=str(error)))
        raise


if __name__ == "__main__":
    main()

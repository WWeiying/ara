"""Raw717 nonzero-vstart widening-accumulator host/Spike preflight, not DUT PASS."""
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
NAME = "vgap102b_widen_acc_vstart"
APP = ROOT / "apps/riscv-tests/isa/rv64uv" / (NAME + ".c")
BASE = OUT / "cache-port1-offline-admitted-717-20261006-01"
BASE_SEAL = "82cd5f277d934c7b2435bfff3e2af1d4dd64cdea6435baba67b72749be183b62"
CHECKS = 723
WORD = (0b111100 << 26) | (1 << 25) | (12 << 20) | (10 << 15) | (6 << 12) | (8 << 7) | 0x57
SYMBOLS = ("tohost", "g75_result", "num_failed", "g75_trap", "trap_fail", "g102b_dump",
           "g102b_seed_dump", "g102b_source_dump", "g102b_csr", "g102b_recovery_dump",
           "g102b_load_seed", "g102b_load_source", "g102b_mac", "g102b_recovery")


def images(vl=129, vstart=128):
    require(vl == 129 and vstart == 128, "Not the exact nonzero-vstart boundary")
    image = bytearray(b"".join(bytes([0x40 + r]) * 128 for r in range(32)))
    seed = b"".join((0x51000000 + 131 * i).to_bytes(4, "little") for i in range(256))
    source = b"".join(((0x1000 + 37 * i) & 0xffff).to_bytes(2, "little") for i in range(256))
    image[8*128:16*128] = seed
    seeded = bytes(image)
    image[12*128+2*vstart:12*128+2*vl] = source[2*vstart:2*vl]
    before = bytes(image)
    for i in range(vstart,vl):
        accumulator = int.from_bytes(before[8*128+4*i:8*128+4*i+4], "little")
        multiplicand = int.from_bytes(before[12*128+2*i:12*128+2*i+2], "little")
        image[8*128+4*i:8*128+4*i+4] = ((accumulator + 7*multiplicand) & 0xffffffff).to_bytes(4,"little")
    return dict(seeded=seeded, before=before, after=bytes(image), seed=seed, source=source)


def expected_words():
    data = images()
    result = {}
    for name, blob in (("g102b_dump", data["after"]), ("g102b_seed_dump", data["seed"]),
                       ("g102b_source_dump", data["source"])):
        for offset in range(0, len(blob), 8):
            result[name, offset] = int.from_bytes(blob[offset:offset+8], "little")
    for i, value in enumerate([129, 10, 128, 0, 129, 10, 0, 0]):
        result["g102b_csr", i*8] = value
    recovery = bytearray([0xa5] * 64)
    recovery[16:20] = data["after"][12*128:12*128+4]
    for i in range(8):
        result["g102b_recovery_dump", i*8] = int.from_bytes(recovery[i*8:i*8+8], "little")
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
    stages = {symbols["g102b_load_seed"]: (range(8,16), data["seeded"]),
              symbols["g102b_load_source"]: (range(14,15), data["before"]),
              symbols["g102b_mac"]: (range(12,13), data["after"])}
    mac = [c for c in commits if c.pc == symbols["g102b_mac"]]
    require(len(mac) == 1 and mac[0].instruction == WORD and mac[0].vector_sew == 16 and
            mac[0].vector_lmul == "m4" and mac[0].vector_vl == 129 and mac[0].vector_vstart == 128 and
            mac[0].vector_tail_agnostic is False and mac[0].vector_mask_agnostic is False, "MAC identity/policy differs")
    require(set(mac[0].vector_writes) == {12}, "Missing or extra active MAC register result")
    for c in commits:
        if c.pc in stages:
            operations[c.pc] += 1
            if c.pc == symbols["g102b_load_seed"]:
                require(c.vector_vstart == 0 and c.vector_vl == 256 and c.vector_sew == 32 and
                        c.vector_lmul == "m8" and c.vector_tail_agnostic is False and
                        c.vector_mask_agnostic is False and set(c.vector_writes) == set(range(8,16)),
                        "Complete wide seed load identity/policy/register differs")
            if c.pc == symbols["g102b_load_source"]:
                require(c.vector_vstart == 128 and c.vector_vl == 129 and c.vector_sew == 16 and
                        c.vector_lmul == "m4" and c.vector_tail_agnostic is False and
                        c.vector_mask_agnostic is False and set(c.vector_writes) == {14},
                        "Source load vstart/policy/register differs")
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
    recovery = [c for c in commits if c.pc == symbols["g102b_recovery"]]
    require(len(recovery) == 1 and recovery[0].instruction & 0x7f == 0x27 and
            (recovery[0].instruction >> 7) & 31 == 12 and recovery[0].vector_vl == 1 and
            recovery[0].vector_sew == 32 and recovery[0].vector_lmul == "m1" and
            recovery[0].vector_vstart == 0, "Recovery store identity/policy differs")
    return dict(status="GAP102B_SPIKE_INDEPENDENT_FULL_VRF_ORACLE_PASS_NOT_DUT", checks=CHECKS,
                mac_opcode=hex(WORD), vl=129, source_start_wide_element=128, vstart=128, active_result_bytes=4,
                full_vrf_bytes=4096, source_guard_bytes=1536, csr_snapshots=2, recovery_guard_bytes=64,
                illegal_traps=0, coverage_admitted=False, measured_raw_increment=None)


def gate_audit(text):
    require("reshuffle_full_vs2_group = ara_req.op inside {VRGATHER, VRGATHEREI16};" in text,
            "Unexpected full-source normalization gate")
    require("ara_req.use_vd && ara_req.use_vd_op &&" in text and
            "reshuffle_req_d[0] && !single_register_result(ara_req.op)" in text,
            "Accumulator snapshot gate differs")
    require("automatic logic [7:0] mask = active_register_mask(lmul, target_eew, vstart, vl);" in text and
            "if (mask[r] && (unsigned'(base) + r) < 32)" in text,
            "Active-only normalization differs")
    require("(ara_req.vs2 != ara_req.vd)" in text and
            "!source_snapshot_resolves_widen ||" in text,
            "Duplicate/overlap routing differs")
    return dict(vd_active=[12],vs2_active=[14],source_load_active=[14],vd12_unchanged_by_source_load=True,
        assumed_vd12_eew=32,assumed_vs2_v14_eew=16,raw_reshuffle_requests=[0,0,0],
        use_vs1=False,vm=True,full_source_normalization=False,dual_source_conflict=False,
        masked_widen_conflict=False,indexed_load_conflict=False,narrow_overlap=False,
        reduction_overlap=False,source_snapshot_expected=False,
        legal_widen_overlap_expected=True,overlap_start_element=128,
        branch5843_expected=False,predicate_values_are_static_predictions_not_measured=True)

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
    return dict(status="GAP102B_RAW717_TARGET_ZERO_NOT_COVERAGE_PROMISE", baseline_tests=717, pins=pins,
                targets=[dict(scope=old.SCOPE, metric="branch", point=point, width=record["width"],
                              checksum=record["checksum"], hit_before=False)],
                hypothesis="vstart128 leaves only vd12 wide active and vs2 v14 narrow active; no snapshot conflict expected, so VL129 exceeds overlap_start128.",
                source_path=str(original), source_read_path=str(snapshot), prior_case_vstart=0,
                gate_audit=gate_audit(snapshot.read_text()),
                budget_seconds=600, exclusions_generated=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    out = p.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh output required")
    evidence = target_evidence()
    include = ROOT / "verification/tests"
    host = include / "gap102b_host_reference.c"
    paths = [APP, host, include / "gap102b_reference.h", include / "gap75_start.S", include / "gap75.ld",
             Path(__file__).resolve(), Path(__file__).with_name("test_build_gap102b_preflight.py"),
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
            pc = symbols["g102b_mac"]
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
        s.save(out / "preflight-manifest.json", dict(status="GAP102B_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS", case=NAME,
            baseline_tests=717, checks=CHECKS, symbols=symbols, pins=pins, validation=result,
            input_elf=str(elf), input_spike_trace=str(out / "spike.trace"), target_before=str(out / "target-before.json"),
            target_unhit_count=1, coverage_admitted=False, rtl_changed=False, vcs_started=False, measured_raw_increment=None))
        print(json.dumps(dict(output=str(out), seal=s.sha(out / "preflight-manifest.json"), opcode=hex(WORD))))
    except Exception as error:
        s.save(out / "failure.json", dict(status="GAP102B_PREFLIGHT_FAILED", reason=str(error)))
        raise


if __name__ == "__main__":
    main()

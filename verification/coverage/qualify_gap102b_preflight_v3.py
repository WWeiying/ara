"""Strict successor audit of actual GAP102B host/Spike02; never rerun or admit."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import build_gap102b_preflight_v2 as frozen

s, ROOT, OUT, require = frozen.s, frozen.ROOT, frozen.OUT, frozen.require
NAME, CHECKS, WORD, SYMBOLS = frozen.NAME, frozen.CHECKS, frozen.WORD, frozen.SYMBOLS
images, expected_words = frozen.images, frozen.expected_words
PRE = OUT / "gap102b-widen-acc-vstart-preflight-717-20261006-02"
FIXED = {
    str(PRE / "input-pins.json"): "8b1c7a8d6b16951bf425916c4214c7f6433c17b1f958ca51ec579669696f0583",
    str(PRE / "input.elf"): "5f27f7052c5805c46f80c859713350d15d5037754a2784a75039e245f7a593bd",
    str(PRE / "spike.trace"): "d7a46558b80ca3a6c11a396325b764828f085c2f55d619eea2714680bbfc8ea6",
    str(PRE / "host.log"): "206ceaf24464ed96f7abd911d82ca6025d783d612d2b2904c78a1bf9fbda0bd7",
    str(Path(frozen.__file__).resolve()): "faeda36281a1db92d24e9ce54cbe904caeaaebd401b818a6272baed596a3289c",
}

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
              symbols["g102b_mac"]: ([10,12], data["after"])}
    mac = [c for c in commits if c.pc == symbols["g102b_mac"]]
    require(len(mac) == 1 and mac[0].instruction == WORD and mac[0].vector_sew == 16 and
            mac[0].vector_lmul == "m4" and mac[0].vector_vl == 129 and mac[0].vector_vstart == 128 and
            mac[0].vector_tail_agnostic is False and mac[0].vector_mask_agnostic is False, "MAC identity/policy differs")
    require(set(mac[0].vector_writes) == {10,12}, "Missing or extra exact MAC register declaration")
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
    require(mac[0].vector_writes[10] == int.from_bytes(data["before"][1280:1408],"little"),
            "Declared preserved v10 bytes changed")
    require(sum(bool(c.vector_writes) for c in commits) == 35 and
            sum(len(c.vector_writes) for c in commits) == 43, "Exact Spike vector declaration population differs")
    return dict(status="GAP102B_SPIKE_INDEPENDENT_FULL_VRF_ORACLE_PASS_NOT_DUT", checks=CHECKS,
                mac_opcode=hex(WORD), vl=129, source_start_wide_element=128, vstart=128, active_result_bytes=4,
                declared_preserved_registers=[10], preserved_declaration_bytes_checked=128,
                vector_write_instructions=35, vector_register_declarations=43, vector_declared_bytes=5504,
                full_vrf_bytes=4096, source_guard_bytes=1536, csr_snapshots=2, recovery_guard_bytes=64,
                illegal_traps=0, coverage_admitted=False, measured_raw_increment=None)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    out = parser.parse_args(argv).output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh successor output required")
    pins = {}
    def read(path, expected=None):
        path = Path(path).absolute()
        require(path.resolve() == path and not path.is_symlink(), "Aliased input")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        require(expected is None or digest == expected, "Expected pin differs: " + str(path))
        pins.update(s.merge_pins(pins, {str(path):digest}))
        return raw
    for path,h in FIXED.items(): read(path,h)
    pins.update(s.merge_pins(pins,json.loads(read(PRE / "input-pins.json",FIXED[str(PRE / "input-pins.json")]))))
    s.check(pins)
    require("GAP102B_HOST_INDEPENDENT_REFERENCE_PASS full4096 source2 MAC4 vstart128" in
            read(PRE / "host.log",FIXED[str(PRE / "host.log")]).decode(), "Actual host reference not PASS")
    for path in sorted(PRE.iterdir()):
        if path.is_file(): read(path)
    symbols = {name:s._elf_symbol(PRE / "input.elf",s.LLVM / "llvm-readelf",name) for name in SYMBOLS}
    trace = read(PRE / "spike.trace",FIXED[str(PRE / "spike.trace")]).decode()
    result = validate(s.parse_spike_commits(PRE / "spike.trace"),symbols,trace)
    target = frozen.target_evidence()
    require(target == json.loads(read(PRE / "target-before.json")), "Original target/source binding differs")
    pins.update(s.merge_pins(pins,target["pins"]))
    for path in (Path(__file__).resolve(),Path(__file__).with_name("test_qualify_gap102b_preflight_v3.py")):
        read(path)
    for module in tuple(sys.modules.values()):
        filename=getattr(module,"__file__",None)
        if filename and str(ROOT / "verification") in filename: read(Path(filename).resolve())
    s.check(pins)
    out.mkdir()
    s.save(out / "spike-validation.json",result)
    s.save(out / "target-before.json",target)
    pins = s.merge_pins(pins,{str(out / name):s.sha(out / name) for name in ("spike-validation.json","target-before.json")})
    s.save(out / "preflight-manifest.json",dict(status="GAP102B_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS",
        schema="GAP102B_PREFLIGHT_STRICT_SUCCESSOR_V3",case=NAME,baseline_tests=717,checks=CHECKS,
        symbols=symbols,pins=pins,validation=result,input_elf=str(PRE / "input.elf"),
        input_spike_trace=str(PRE / "spike.trace"),target_before=str(out / "target-before.json"),
        target_unhit_count=1,original_failed_outputs_preserved=True,
        reused_own_gap102b_raw_spike_without_rerun=True,coverage_admitted=False,
        rtl_changed=False,vcs_started=False,measured_raw_increment=None,
        budget_seconds=600,spike_declared_v10_preserved_bytes_verified_not_skipped=True))
    print(json.dumps(dict(output=str(out),seal=s.sha(out / "preflight-manifest.json"),
                          elf_sha=FIXED[str(PRE / "input.elf")],pins=len(pins),validation=result)))


if __name__ == "__main__": main()

"""Single legal narrowing alias + high shift view; host/Spike only, no DUT."""
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
NAME = "vgap103_narrow_prefix"
APP = ROOT / "apps/riscv-tests/isa/rv64uv" / (NAME + ".c")
BASE = OUT / "gap102b-offline-admitted-719-20261006-01"
BASE_SEAL = "0edf5405a8139eea50d82af6181f7d53ccb70699c2b232c8e3001add0ec242bb"
CHECKS = 1245
WORD = (0b101100 << 26) | (1 << 25) | (8 << 20) | (12 << 15) | (8 << 7) | 0x57
SYMBOLS = ("tohost","g75_result","num_failed","g75_trap","trap_fail","g103_before_dump",
           "g103_after_dump","g103_seed_dump","g103_shift_dump","g103_csr",
           "g103_recovery_dump","g103_load_seed","g103_load_shift","g103_narrow","g103_recovery")


def images(vl=129, vstart=13):
    require((vl,vstart) == (129,13), "Not the exact narrowing boundary")
    seed = b"".join((0x51a70329+131*i).to_bytes(4,"little") for i in range(256))
    shifts = b"".join((0x1200 | ((5*i+3)&31)).to_bytes(2,"little") for i in range(256))
    image = bytearray(b"".join(bytes([0x40+r])*128 for r in range(32)))
    image[1024:2048] = seed
    seeded = bytes(image)
    image[1536:2048] = shifts
    before = bytes(image)
    # Both operands are read from the immutable architectural loaded preimage.
    for i in range(vstart,vl):
        wide = int.from_bytes(before[1024+4*i:1024+4*i+4],"little")
        shift = int.from_bytes(before[1536+2*i:1536+2*i+2],"little") & 31
        image[1024+2*i:1024+2*i+2] = ((wide >> shift)&65535).to_bytes(2,"little")
    guard = lambda i: (0x9e37a5c35a6bd081 ^ ((0x0103070b11171d25*i)&((1<<64)-1))).to_bytes(8,"little")
    recovery = bytearray([0xa5]*64); recovery[16:18] = image[1024:1026]
    return dict(seeded=seeded,before=before,after=bytes(image),
                seed=b"".join(guard(i) for i in (0,1))+seed+b"".join(guard(i) for i in (2,3)),
                shifts=b"".join(guard(i) for i in (4,5))+shifts+b"".join(guard(i) for i in (6,7)),
                recovery=bytes(recovery))


def expected_words():
    data = images()
    result = {}
    for name,blob in (("g103_before_dump",data["before"]),("g103_after_dump",data["after"]),
                      ("g103_seed_dump",data["seed"]),("g103_shift_dump",data["shifts"]),
                      ("g103_recovery_dump",data["recovery"])):
        for offset in range(0,len(blob),8):
            result[name,offset] = int.from_bytes(blob[offset:offset+8],"little")
    for i,value in enumerate((129,10,13,0,0,129,10,0,0,0)):
        result["g103_csr",i*8] = value
    return result


def validate(commits,symbols,trace):
    require("exception " not in trace and not any(c.pc == symbols["trap_fail"] for c in commits),
            "Unexpected trap")
    writes = {a:v for c in commits for a,v in c.memory_accesses if v is not None}
    terminal = [v for c in commits for a,v in c.memory_accesses if a == symbols["tohost"] and v is not None]
    require(terminal == [1] and writes.get(symbols["g75_result"]) == CHECKS and
            writes.get(symbols["g75_result"]+4) == writes.get(symbols["num_failed"]) == 0,
            "Software checks/terminal differ")
    for (name,offset),value in expected_words().items():
        require(writes.get(symbols[name]+offset) == value,"Independent canonical oracle differs: %s+%d"%(name,offset))
    require([writes.get(symbols["g75_trap"]+i*8) for i in range(3)] == [0,0,0],"Trap ledger differs")
    data, initial, operations = images(), Counter(), Counter()
    stages = {symbols["g103_load_seed"]:(0x02066407,32,"m8",256,0,set(range(8,16)),data["seeded"]),
              symbols["g103_load_shift"]:(0x02065607,16,"m4",256,0,set(range(12,16)),data["before"]),
              symbols["g103_narrow"]:(WORD,16,"m4",129,13,{8,9,10},data["after"])}
    for commit in commits:
        if commit.pc in stages:
            operations[commit.pc] += 1
            word,sew,lmul,vl,vstart,regs,image = stages[commit.pc]
            mask = 0xffffffff if word == WORD else (0xffffffff ^ (31 << 15))
            require(commit.instruction & mask == word & mask and commit.vector_sew == sew and
                    commit.vector_lmul == lmul and commit.vector_vl == vl and
                    commit.vector_vstart == vstart and commit.vector_tail_agnostic is False and
                    commit.vector_mask_agnostic is False and set(commit.vector_writes) == regs,
                    "Vector stage opcode/policy/register differs")
            for reg,value in commit.vector_writes.items():
                require(value == int.from_bytes(image[reg*128:(reg+1)*128],"little"),
                        "Canonical vector stage bytes differ")
        else:
            for reg,value in commit.vector_writes.items():
                require(reg in range(32) and value == int.from_bytes(bytes([0x40+reg])*128,"little"),
                        "Unexpected vector side effect")
                initial[reg] += 1
    require(initial == Counter({r:1 for r in range(32)}) and operations == Counter(stages.keys()),
            "Initialization/operation population differs")
    recovery = [c for c in commits if c.pc == symbols["g103_recovery"]]
    require(len(recovery) == 1 and recovery[0].instruction & (0xffffffff ^ (31<<15)) == 0x02005427 and
            (recovery[0].instruction >> 7)&31 == 8 and recovery[0].vector_vl == 1 and
            recovery[0].vector_sew == 16 and recovery[0].vector_lmul == "m1" and
            recovery[0].vector_vstart == 0,"Recovery store identity differs")
    return dict(status="GAP103_SPIKE_CANONICAL_FULL_VRF_ORACLE_PASS_NOT_DUT",checks=CHECKS,
                opcode=hex(WORD),vl=129,vstart=13,active_destination_bytes=232,
                before_vrf_bytes=4096,after_vrf_bytes=4096,source_and_guard_bytes=1600,
                csr_snapshots=2,recovery_guard_bytes=64,illegal_traps=0,
                vector_write_instructions=35,vector_declared_bytes=4096+1024+512+384,
                coverage_admitted=False,measured_raw_increment=None)


def target_evidence():
    pins = {}
    def pin(path, expected=None):
        path = Path(path).absolute()
        require(path.resolve() == path and not path.is_symlink(),"Aliased evidence")
        actual = s.sha(path)
        require(expected is None or actual == expected,"Expected identity differs: "+str(path))
        pins.update(s.merge_pins(pins,{str(path):actual}))
        return path
    manifest = json.loads(pin(BASE/"admission-manifest.json",BASE_SEAL).read_bytes())
    def base(name):
        return pin(BASE/name,manifest["output_pins"][str(BASE/name)])
    state = json.loads(base("status.json").read_bytes())
    bits = json.loads(base("combined-bits.json").read_bytes())
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and state["aggregate_passed"] == 719 and
            len(bits["tests"]) == len(set(bits["tests"])) == 719,"Not frozen719")
    require(base("combined-inputs.txt").read_text().splitlines() ==
            [str(old.BUILD/"sim/simv.vdb"),*bits["tests"]],"719 membership differs")
    sources = json.loads(pin(old.BUILD/"build-source-pins.json",
        "6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b").read_bytes())
    original = ROOT/"hardware/src/ara_dispatcher.sv"
    snapshot = pin(OUT/"old-image-source-evidence-20261006-01/ara_dispatcher.sv",sources[str(original)])
    require(s.sha(snapshot) == "9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43","Wrong old dispatcher")
    for path in (ROOT/"hardware/include/ara_pkg.sv",ROOT/"hardware/include/rvv_pkg.sv"):
        pin(path,sources[str(path)])
    design = s.Design(old.BUILD/"sim/simv.vdb")
    require(design.source(old.SCOPE)["resolved_path"] == str(original),"Wrong compiled owner")
    for relative,expected in bits["design"].items(): pin(design.db/relative,expected)
    for relative in ("auxiliary/verilog.sourceinfo.xml","shape/branch.verilog.info.xml",
                     "shape/line.verilog.info.xml","shape/tgl.verilog.info.xml","shape/tgl.verilog.shape.xml"):
        pin(design.db/relative)
    targets = []
    for metric,index,ident,vector,check,line,exprindex in (
            ("branch",138,"25","991","3771491581","5789",1248),
            ("branch",105,"24","12","1445690029","1284",19),
            ("branch",100,"24","17","1445690029","1330",27),
            ("line",202,"194","","3588353522","1288",0)):
        record = bits["metrics"][metric][old.SCOPE]
        definition = design.definition(old.SCOPE,metric)
        require(record["checksum"] == definition.get("chksum") ==
                ("1558979345" if metric == "branch" else "1316526434"),"Metric checksum differs")
        point = next(p for p in points(metric,definition,record["width"]) if p["raw_index"] == index)
        require((point["native_id"],point["vector"],point["attributes"]["chksum"]) ==
                (ident,vector,check),"Compiled coordinate identity differs")
        if metric == "branch":
            leaf = next(e for e in point["expressions"] if e["id"] == line)
            require(int(leaf["index"]) == exprindex and
                    point["native_vector"]["vector"][-exprindex] == "1","Not target true arm")
        else:
            require(point["attributes"]["line_num"] == line,"Wrong line target")
        require(not int(record["bits"],16)&(1<<(record["width"]-1-index)),"Target already hit719")
        targets.append(dict(scope=old.SCOPE,metric=metric,point=point,width=record["width"],
                            checksum=record["checksum"],hit_before=False))
    text = snapshot.read_text()
    for token in ("dual_source_layout_conflict = ara_req.use_vs1 && ara_req.use_vs2 &&",
                  "dual_source_snapshot_vs1 = dual_source_layout_conflict &&",
                  "legal_narrow_overlap = narrow_low_overlap_alias && reshuffle_req_d[0]",
                  "legal_narrow_overlap && !reshuffle_req_d[1] &&",
                  "legal_narrow_overlap &&\n              !source_snapshot_preserves_narrow_vd",
                  "overlap_prefix_vl_d != '0"):
        require(token in text,"Frozen gate source differs")
    s.check(pins)
    return dict(status="GAP103_RAW719_TARGETS_ZERO_STATIC_HYPOTHESIS_NOT_MEASURED",
        baseline_tests=719,pins=pins,targets=targets,source_path=str(original),source_read_path=str(snapshot),
        gate_predictions=dict(initial_vs1_active=[12,13,14],initial_vs2_active=[8,9,10,11,12],
            initial_vd_active=[8,9,10],initial_reshuffle_vd_vs2_vs1=[1,1,0],
            dual_source_conflict=True,snapshot_source=12,snapshot_eew=16,
            source_snapshot_preserves_narrow_vd=False,prefix_elements=13,prefix_bytes=26,
            boundary_register=10,boundary_active_bytes=2,
            expected_branches=[138,105,100],expected_line=[202],not_direct_internal_state_measurement=True),
        oracle_origin="immutable canonical loaded preimage plus RVV vnsrl logical shift low5 rule",
        budget_seconds=600,exclusions_generated=False,vcs_started=False)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    out = p.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh output required")
    evidence = target_evidence()
    include = ROOT / "verification/tests"
    host = include / "gap103_host_reference_v2.c"
    paths = [APP, host, include / "gap103_reference.h", include / "gap75_start.S", include / "gap75.ld",
             Path(__file__).resolve(), Path(__file__).with_name("test_build_gap103_preflight_v2.py"),
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
            pc = symbols["g103_narrow"]
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
        s.save(out / "preflight-manifest.json", dict(status="GAP103_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS", case=NAME,
            baseline_tests=719, checks=CHECKS, symbols=symbols, pins=pins, validation=result,
            input_elf=str(elf), input_spike_trace=str(out / "spike.trace"), target_before=str(out / "target-before.json"),
            target_unhit_count=4, coverage_admitted=False, rtl_changed=False, vcs_started=False, measured_raw_increment=None))
        print(json.dumps(dict(output=str(out), seal=s.sha(out / "preflight-manifest.json"), opcode=hex(WORD))))
    except Exception as error:
        s.save(out / "failure.json", dict(status="GAP103_PREFLIGHT_FAILED", reason=str(error)))
        raise


if __name__ == "__main__":
    main()


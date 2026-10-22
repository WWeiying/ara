#!/usr/bin/env python3
"""One short old-image case; strict PASS-only new-VDB diagnostic delta, no DVE."""
import argparse
import csv
import json
from pathlib import Path
import struct
import subprocess

import run_gap75_operand_batch as h
import apply_lzc_historical as lzc
from ara_verify.spike_trace import parse_ara_retire, _packed_store_value

ROOT,OUT,HERE = lzc.ROOT,lzc.OUT,lzc.HERE
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name("test_run_gap83_old_image.py")
SOURCE = ROOT/"apps/riscv-tests/isa/rv64uv/vgap83_midmant16.c"
PREFLIGHT = OUT/"gap83-midmant-preflight-20261006-01"
BASELINE = OUT/"gap82-raw-union-689-20261006-01"
RETAINED = OUT/"lzc-retained-689-20261006-01.json"
NAME = "vgap83_midmant16"
require,save,seals = lzc.require,lzc.save,lzc.seals


def signature(writes,tohost,result):
    require(writes.get(tohost) == 1 and writes.get(result) == 262
            and writes.get(result+4) == 0,"Strict262/0 signature or tohost failed")


def targets(inventory):
    rows = [r["point"] for r in inventory["retained"] if r["hit"] is False and r["point"]["line"] == "93"]
    expected = {(2,0,8,"01"),(3,1,8,"01"),(3,1,28,"10")}
    coords = set()
    for p in rows:
        match = lzc.capture.re.fullmatch(r"ara_tb\.dut\.i_ara_soc\.i_system\.i_ara\.gen_lanes\[(\d)\]\.i_lane\.i_operand_queues\.i_operand_queue_mfpu_c\.genblk3\.genblk1\[(\d)\]\.leading_zero_e16_i",p["scope"])
        require(match is not None and p["metric_checksum"] == "3513283519","Unexpected retained target scope")
        coords.add((*map(int,match.groups()),p["raw_index"],p["vector"]))
    require(len(rows) == len(coords) == 3 and coords == expected,"Not exact3 reachable targets")
    return rows


def bit(bitmap,p):
    value = bitmap["metrics"]["cond"][p["scope"]]
    require(str(value["checksum"]) == p["metric_checksum"] and value["width"] > p["raw_index"],"Target shape differs")
    return (int(value["bits"],16) >> (value["width"]-1-p["raw_index"])) & 1


def prepare(output):
    output = output.absolute()
    require(not output.exists() and output.parent == OUT,"Fresh independent output required")
    seal = seals.FileSeal()
    plan = seal.read(seals.old.CURRENT/"plan.json")
    seal.hashes(plan["image"])
    provenance = seal.read(BASELINE/"provenance.json")
    require(provenance["status"] == "RAW_DIAGNOSTIC_UNION_COMPLETE" and provenance["historical_tests"] == 689,
            "Historical689 raw baseline required")
    seal.hashes(provenance["outputs"])
    before = seal.read(BASELINE/"combined-bits.json")
    require(before["design"] == plan["design_vdb"] and len(before["tests"]) == 689,"Foreign baseline image/population")
    ts = targets(seal.read(RETAINED))
    require(all(bit(before,p) == 0 for p in ts),"Retained targets not historical zeros")
    build = seal.read(OUT/"repaired-aligned-build-20260930-01/build-source-pins.json")
    old_sources = OUT/"old-image-source-evidence-20261006-01"
    for rel in ("hardware/src/ara_dispatcher.sv","hardware/src/lane/lane_sequencer.sv"):
        seal.pin(old_sources/Path(rel).name,build[str(ROOT/rel)])
    for rel in ("hardware/src/lane/operand_queue.sv","hardware/include/ara_pkg.sv",
                "hardware/deps/common_cells/src/lzc.sv"):
        seal.pin(ROOT/rel,build[str(ROOT/rel)])
    compiler = Path("/home/wangwy/openproject/ara/install/riscv-llvm/bin/clang")
    readelf = compiler.parent/"llvm-readelf"
    startup,linker = ROOT/"verification/tests/gap75_start.S",ROOT/"verification/tests/gap75.ld"
    for p in (SCRIPT,TEST,SOURCE,PREFLIGHT/"input.elf",PREFLIGHT/"spike.trace",compiler,readelf,startup,linker,
              h.SPIKE,Path(h.__file__),Path(lzc.__file__),Path(seals.__file__),Path(seals.bitmaps.__file__),
              ROOT/"verification/ara_verify/spike_trace.py",ROOT/"verification/ara_verify/vector_commit.py",
              ROOT/"verification/ara_verify/trace.py",ROOT/"verification/ara_verify/contract.py",
              ROOT/"verification/ara_verify/random_rvv.py"):
        seal.pin(p)
    seal.tree(ROOT/"apps/riscv-tests/isa/macros")
    output.mkdir()
    command = [str(compiler),"--target=riscv64-unknown-elf","-march=rv64gcv_zfh_zvfh","-mabi=lp64d",
        "-mcmodel=medany","-mno-relax","-msmall-data-limit=0","-O2","-fno-vectorize","-fno-slp-vectorize",
        "-ffreestanding","-DG75_NO_PRINT","-D__SPIKE__","-DVLEN=1024","-DNR_LANES=4",
        "-I"+str(ROOT/"apps/riscv-tests/isa/macros/vector"),"-I"+str(ROOT/"apps/riscv-tests/env"),
        "-I"+str(ROOT/"apps/common"),"-fuse-ld=lld","-nostdlib","-T"+str(linker),
        str(startup),str(SOURCE),"-o",str(output/"input.elf")]
    save(output/"compile.command.json",dict(command=command,cwd=str(ROOT),timeout_s=120))
    with (output/"compile.log").open("x") as stream:
        subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=120,check=True)
    elf = output/"input.elf"
    require(elf.read_bytes() == (PREFLIGHT/"input.elf").read_bytes(),"Independent compile differs from parent ELF")
    data = elf.read_bytes()
    require(struct.unpack_from("<Q",data,24)[0] == 0x80000000,"Wrong boot entry")
    phoff = struct.unpack_from("<Q",data,32)[0]
    phsize,phnum = struct.unpack_from("<HH",data,54)
    for i in range(phnum):
        s = struct.unpack_from("<IIQQQQQQ",data,phoff+i*phsize)
        require(s[0] != 1 or not s[5] or s[4]%128 == 0,"Unaligned ELF preload")
    tohost = h._elf_symbol(elf,readelf,"tohost")
    result = h._elf_symbol(elf,readelf,"g75_result")
    commits = h.parse_spike_commits(PREFLIGHT/"spike.trace")
    require(sum(c.instruction == 0xc2821857 for c in commits) == 2,"Spike not exact2 vfwadd")
    writes = {addr:value for c in commits for addr,value in c.memory_accesses if value is not None}
    signature(writes,tohost,result)
    for p in (elf,output/"compile.command.json",output/"compile.log"):seal.pin(p)
    seal.finish()
    manifest = dict(schema="gap83-old-single-v1",image=plan["simv"],design=plan["design_vdb"],
        sourcepins=seal.files,targets=ts,tohost=tohost,result=result,
        checks=262,expected_fp32_bits=["36000000","36800000"],tail_bits="40e00000",
        baseline=str(BASELINE),spike_trace=str(PREFLIGHT/"spike.trace"),name=NAME,
        historical_only=True,new_RTL_signoff=False,aggregate_admitted=False,dve_run=False)
    save(output/"manifest.json",manifest)
    return dict(status="PREPARED",manifest_sha256=seals.sha_bytes((output/"manifest.json").read_bytes()))


def run(output,digest):
    require(isinstance(digest,str) and lzc.capture.re.fullmatch(r"[0-9a-f]{64}",digest),"Explicit manifest SHA required")
    output = output.resolve(strict=True)
    require(output.parent == OUT and not (output/"rtl.command.json").exists(),"Fresh prepared execution required")
    seal = seals.FileSeal()
    m = seal.read(output/"manifest.json",digest)
    require(m["schema"] == "gap83-old-single-v1" and m["name"] == NAME and m["checks"] == 262,"Foreign manifest")
    seal.hashes(m["sourcepins"])
    command = [m["image"],"-l","run.vcs.log","+NO_FSDB","+ntb_random_seed=1",
        "+PRELOAD="+str(output/"input.elf"),"+TESTCASE="+NAME,"+COMMIT_TOHOST=%x"%m["tohost"],
        "+COMMIT_TRACE="+str(output/"commit_trace.csv"),"+VECTOR_TRACE="+str(output/"vector_trace.csv"),
        "-cm","line+cond+fsm+tgl+branch","-cm_dir",str(output/"code.vdb"),"-cm_name",NAME]
    save(output/"rtl.command.json",dict(command=command,cwd=str(output),timeout_s=600))
    try:
        print(json.dumps(dict(phase="VCS_STARTING",case=NAME)),flush=True)
        with (output/"console.log").open("x") as stream:
            subprocess.run(command,cwd=output,stdout=stream,stderr=subprocess.STDOUT,timeout=600,check=True)
        trace = h.validate_trace(output/"commit_trace.csv")
        scalar = h.compare_commit_prefix(Path(m["spike_trace"]),output/"commit_trace.csv",0x80000000,
            terminal_tohost_address=m["tohost"],rvfi_store_data_layout="unshifted")
        vector = h.compare_vector_commits(Path(m["spike_trace"]),output/"commit_trace.csv",
            output/"vector_trace.csv",0x80000000)
        save(output/"scalar-comparison.json",scalar)
        save(output/"vector-comparison.json",vector)
        require(scalar["status"] == "TERMINAL_TOHOST_MATCH" and scalar["ara_trap_events"] == 0
                and scalar["skipped_unobservable_register_values"] == 0
                and scalar["stopped_at_unobservable"] is None
                and scalar["matched_instructions"] == scalar["ara_retired_instructions"],"Incomplete scalar comparison")
        require(vector["status"] == "PASS","Full vector differential failed")
        retired = parse_ara_retire(output/"commit_trace.csv")
        require(sum(r.instruction == 0xc2821857 for r in retired) == 2,"DUT not exact2 vfwadd")
        writes = {r.mem_addr:_packed_store_value(r.mem_wmask,r.mem_wdata,"unshifted")
                  for r in retired if r.mem_wmask and r.mem_wdata is not None}
        signature(writes,m["tohost"],m["result"])
        require(not h.check_contract_log(output/"run.vcs.log") and
                "Core Test *** SUCCESS ***" in (output/"run.vcs.log").read_text(),"DUT/contract failed")
        save(output/"runtime-audit.json",dict(status="PASS",trace=trace,checks=262,failures=0,
            vfwadd_instructions=2,VL_fflags_vstart="fixture exact checks with scalar/vector comparison"))
        with (output/"new-inputs.txt").open("x") as stream:
            stream.write(m["design"]+"\n"+str(output/"code.vdb")+"\n")
        sample = seals.bitmaps.collect(output/"new-inputs.txt")
        before = seal.read(BASELINE/"combined-bits.json")
        require(sample["tests"] == [str(output/"code.vdb")],"Foreign new VDB population")
        lzc.assert_zero(sample,seal.read(lzc.capture.CANDIDATES)["candidates"])
        combined = seals.bitmaps.combine(before,sample)
        measurement = [dict(scope=p["scope"],raw_index=p["raw_index"],vector=p["vector"],
            before=bit(before,p),single=bit(sample,p),after=bit(combined,p)) for p in m["targets"]]
        save(output/"target-measurement.json",dict(targets=measurement,all_targets_hit=all(r["single"] == 1 for r in measurement)))
        save(output/"new-bits.json",sample)
        save(output/"raw-bitmap-delta.json",seals.bitmaps.delta(before,combined))
        seal.hashes(sample["input_hashes"])
        seal.finish()
        artifacts = {str(p):seals.sha_bytes(p.read_bytes()) for p in output.iterdir() if p.is_file()}
        save(output/"evidence-pins.json",dict(inputs=seal.files,artifacts=artifacts))
        status = dict(status="PASS_SINGLE_CASE_DIAGNOSTIC",case=NAME,checks=262,failures=0,
            all_targets_hit=all(r["single"] == 1 for r in measurement),historical_only=True,
            aggregate_admitted=False,dve_run=False,waivers_applied=False,new_RTL_signoff=False)
        save(output/"status.json",status)
        return status
    except Exception as error:
        save(output/"status.json",dict(status="FAIL",reason=f"{type(error).__name__}: {error}",aggregate_admitted=False))
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command",choices=("prepare","run"))
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--manifest-sha256")
    args = p.parse_args()
    print(json.dumps(prepare(args.output) if args.command == "prepare" else run(args.output,args.manifest_sha256),indent=2),flush=True)

#!/usr/bin/env python3
"""Preserve the archived whole-register oracle and prepare its full1134 matrix."""
import difflib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "integration"
sys.path.insert(0, str(BASE))
import prepare as common

CAMP = Path("/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01")
ARCH = CAMP / "rvv_whole_detail01"
SOURCE = Path("/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix")
CC = Path("/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc")
SPIKE = Path("/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike")
OUT = HERE / "prepared01"
save, sha = common.save, common.sha


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def command(args, log, timeout=60):
    with log.open("w") as stream:
        result = subprocess.run(list(map(str, args)), stdout=stream, stderr=subprocess.STDOUT,
                                timeout=timeout, check=False)
    require(result.returncode == 0, f"Command failed {result.returncode}: {log}")


def geometry(first, end, vlenb=128):
    cases, skipped = [], []
    for seed in range(3):
        for op in range(first, end):
            for mode in range(5):
                n = 1 << (op // 4 if op < 16 else op - 16)
                width = 1 << (op % 4 if op < 16 else mode)
                if op >= 16 and mode == 4:
                    width = 1
                evl = n * vlenb // width
                for index, start in enumerate((0, 1, evl // 2, evl, evl + 1)):
                    row = dict(seed=seed, op=op, mode=mode, index=index, start=start,
                               bytes=width, registers=n, evl=evl)
                    (skipped if start > evl or start >= 8*vlenb or op >= 16 and mode == 4
                     else cases).append(row)
    return cases, skipped


def marker(first, end, vlenb=128):
    cases, skipped = geometry(first, end, vlenb)
    return f"RVV_WHOLE_PASS cases={len(cases)} skips={len(skipped)} errors=0"


def host(port, destination, first=0, end=20, vlenb=128, mutation=0):
    text = port.replace('__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));',
                        f'vlenb={vlenb}; /* host oracle test only */')
    require("__asm__" not in text, "Unknown host instruction boundary")
    emulation = f'''
#include <stdio.h>
#include <stdlib.h>
long replay_write(long n,long fd,long p,long z){{if(n!=64 || fd!=1)abort();return fwrite((void*)p,1,z,stdout);}}
static unsigned long emulate(unsigned op,const void *aa,void *oo,unsigned long start,unsigned long mode){{
 const unsigned char *a=aa;unsigned char *o=oo;
 unsigned n=1U<<(op<16?op/4:op-16),width=1U<<(op<16?op%4:mode);
 for(unsigned i=start*width;i<n*{vlenb};++i)o[i]=a[i];
 if(op==16 && mode==1 && start==1){{
  if({mutation}==1)o[0]^=1;
  if({mutation}==2)o[start*width]^=1;
  if({mutation}==3)o[n*{vlenb}]^=1;
  if({mutation}==4)o[-1]^=1;
  if({mutation}==5)return (start<<32)|1;
  if({mutation}==6)return (start+1)<<32;
 }}
 return start<<32;
}}
'''
    for op in range(20):
        emulation += (f"unsigned long op_{op}(const void*a,void*o,unsigned long s,unsigned long m)"
                      f"{{return emulate({op},a,o,s,m);}}\n")
    emulation += "int main(void){return whole_original_main();}\n"
    path = destination / f"host_vb{vlenb}_op{first}_{end}_mutation{mutation}.c"
    path.write_text(text + emulation)
    binary = path.with_suffix("")
    command(["/usr/bin/gcc", "-O2", "-Wall", "-Wextra", "-Werror", "-DDETAIL_BYTES=1",
             f"-DWHOLE_OP_BEGIN={first}", f"-DWHOLE_OP_END={end}", "-I"+str(OUT / "original"),
             path, "-o", binary], path.with_suffix(".compile.log"))
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
    path.with_suffix(".log").write_text(result.stdout + result.stderr)
    if mutation:
        require(result.returncode == 1 and "RVV_WHOLE_FAIL" in result.stdout,
                "Original oracle did not reject injected error")
    else:
        require(result.returncode == 0 and marker(first, end, vlenb) in result.stdout and
                "FAIL" not in result.stdout, "Host oracle/count mismatch")
    return dict(first=first,end=end,vlenb=vlenb,mutation=mutation,
                status="EXPECTED_REJECTION" if mutation else "PASS",returncode=result.returncode)


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    original = OUT / "original"
    original.mkdir()
    pins = {}
    def pin(path, expected=None):
        digest = sha(path)
        require(expected is None or digest == expected, "Original identity drift: " + str(path))
        pins[str(path)] = digest
    manifest_path = ARCH / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    pin(manifest_path)
    for name, digest in manifest["source_sha256"].items():
        pin(SOURCE / name, digest)
        shutil.copyfile(SOURCE / name, original / name)
    expected_elf = manifest["cases"][0]["sha256"]
    for elf in (ARCH / "overlay/opt/ara-tests/rvv_whole_registers_detail",
                CAMP / "rvv_additions07/binaries/rvv_whole_registers_detail"):
        pin(elf, expected_elf)
    spec = importlib.util.spec_from_file_location("archived_whole", original / "whole.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    require(generator.assembly() == (ARCH / "whole.S").read_text(), "Original assembly differs")
    for name in ("whole.S", "operations.h"):
        pin(ARCH / name)
        shutil.copyfile(ARCH / name, original / name)
    for name in ("startup.S", "runtime.c", "replay.ld"):
        pin(BASE / name)
        shutil.copyfile(BASE / name, OUT / name)
    source = (original / "whole_oracle.c").read_text()
    port = common.adapt(source, "whole_original")
    before = "for(unsigned op=0;op<20;++op)"
    require(port.count(before) == 1, "Unknown original operation loop")
    port = port.replace(before, "for(unsigned op=WHOLE_OP_BEGIN;op<WHOLE_OP_END;++op)")
    oracle = source[source.index("        unsigned n="):source.index('    text(errors ? "RVV_WHOLE_FAIL')]
    require(oracle in port, "Original setup/target/oracle changed")
    (OUT / "case.c").write_text(port)
    (OUT / "wrapper.diff").write_text("".join(difflib.unified_diff(source.splitlines(True),port.splitlines(True),
                                                             fromfile="whole_oracle.c",tofile="case.c")))
    all_cases, skipped = geometry(0,20)
    require(len(all_cases)==1134 and len(skipped)==366, "Original matrix membership changed")
    partitions = [geometry(op,op+1)[0] for op in range(20)]
    key = lambda r:(r["seed"],r["op"],r["mode"],r["index"])
    require(sorted(map(key,all_cases)) == sorted(key(row) for part in partitions for row in part),
            "Partition union differs from full original matrix")
    save(OUT / "tuples.json",dict(cases=all_cases,skipped=skipped,partition_counts=[len(x) for x in partitions]))
    hostdir = OUT / "host"
    hostdir.mkdir()
    host_results = [host(port,hostdir,vlenb=vb) for vb in (32,64,128)]
    host_results += [host(port,hostdir,op,op+1) for op in range(20)]
    host_results += [host(port,hostdir,16,17,mutation=m) for m in range(1,7)]
    save(OUT / "host.json",dict(status="PASS_ORIGINAL_ORACLE_AND_NEGATIVES",results=host_results))
    for path in (Path(__file__),BASE / "prepare.py",CC.resolve(),SPIKE,Path("/usr/bin/gcc").resolve()):
        pin(path)
    flags = ["-Os","-march=rv64gcv","-mabi=lp64d","-mcmodel=medany","-ffreestanding",
             "-fno-builtin","-fno-stack-protector","-fno-tree-vectorize","-fno-tree-slp-vectorize",
             "-msmall-data-limit=0","-ffunction-sections","-fdata-sections","-Wall","-Wextra","-Werror",
             "-nostdlib","-static","-Wl,--build-id=none","-Wl,--gc-sections","-DDETAIL_BYTES=1",
             "-T",OUT / "replay.ld","-I"+str(original)]
    programs, references = {}, []
    selections = [("whole_all",0,20)] + [(f"whole_op{op:02d}",op,op+1) for op in range(20)]
    for backend in ("spike","soc"):
        directory = OUT / backend
        directory.mkdir()
        entries = {}
        for name,first,end in selections:
            wrapper = directory / (name+"_main.c")
            wrapper.write_text('extern int whole_original_main(void);\nextern void replay_text(const char*);\n'
                'int main(void){unsigned long vb;__asm__ volatile("csrr %0,vlenb":"=r"(vb));'
                'if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\\n");return 90;}'
                'if(whole_original_main()){replay_text("BOARD_CASE_FAIL\\n");return 1;}'
                f'replay_text("BOARD_CASE_PASS {name}\\nBOARD_REPLAY_PASS\\n");return 0;}}\n')
            elf = directory / (name+".elf")
            defines = [f"-DWHOLE_OP_BEGIN={first}",f"-DWHOLE_OP_END={end}"]
            if backend=="spike":
                defines.append("-DSPIKE_REFERENCE=1")
            command([CC,*flags,*defines,OUT / "case.c",original / "whole.S",wrapper,
                     OUT / "startup.S",OUT / "runtime.c","-lgcc","-o",elf],elf.with_suffix(".compile.log"))
            nm = subprocess.check_output([str(CC.with_name(CC.name.removesuffix("gcc")+"nm")),str(elf)],text=True)
            symbols = {n:int(a,16) for a,_,n in (line.split() for line in nm.splitlines() if len(line.split())==3)}
            entries[name] = dict(path=str(elf),sha256=sha(elf),cases=[name],
                pass_markers=[marker(first,end),f"BOARD_CASE_PASS {name}","BOARD_REPLAY_PASS"],
                first_op=first,end_op=end,original_cases=len(geometry(first,end)[0]),
                original_skips=len(geometry(first,end)[1]))
            if backend=="spike":
                debug = elf.with_suffix(".cmd")
                debug.write_text(f'until pc 0 {symbols["replay_exit"]:x}\nreg 0 a0\n'
                                 f'str {symbols["replay_log"]:x}\nrs\n')
                log = elf.with_suffix(".spike.log")
                command([SPIKE,"-d","--debug-cmd="+str(debug),"--isa=rv64gcv_zvl1024b","-m2",elf],log,90)
                raw = log.read_text()
                values = re.findall(r"^0x([0-9a-f]+)$",raw,re.M)
                require(values==["0000000000000000"] and all(m in raw for m in entries[name]["pass_markers"])
                        and "FAIL" not in raw and "TRAP" not in raw, "Spike oracle/exit failed: "+name)
                references.append(dict(name=name,status="PASS",elf_sha256=sha(elf),log_sha256=sha(log)))
        save(directory / "programs.json",dict(programs=entries,backend=backend))
        programs[backend]=entries
    for path,digest in pins.items():
        require(sha(Path(path))==digest,"Input changed during preparation")
    save(OUT / "source_pins.json",pins)
    save(OUT / "complete.json",dict(status="HOST_SPIKE_FULL1134_AND_20_PARTITIONS_PASS_NOT_DUT",
        original_linux_sha256=expected_elf,original_cases=1134,original_skips=366,
        reference_results=references,programs=programs,
        scope="Original full matrix and operation-partitioned source ports; no Linux execution or DUT result"))
    print("HOST_SPIKE_FULL1134_AND_20_PARTITIONS_PASS_NOT_DUT",flush=True)


if __name__=="__main__":
    main()

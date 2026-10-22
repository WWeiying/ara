#!/usr/bin/env python3
"""Recover19 genuine RVV12 singles; runtime-only port, host oracle check, Spike."""
import difflib
from fractions import Fraction
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "comparison_alias_original"))
import prepare19 as base
save, sha, read, require = base.prepare.save, base.prepare.sha, base.read, base.require
OUT = HERE / "prepared01"
SELECTED = "rvv_small_masks_scalar_restart_e8_m2"


def host(case, name, sew, cap, flags, dest, mutation=0):
    text = (case / "case.c").read_text()
    csr = '__asm__ volatile("csrr %0,vlenb":"=r"(max_start));'
    require(text.count(csr) == 1, "Unknown host CSR boundary")
    text = text.replace(csr, "max_start=128; /* Host fixture VLENB, not the DUT source. */")
    source = dest / (name + f"_host{mutation}.c")
    source.write_text('#include <stdio.h>\n#include <stdlib.h>\n' + text + '\n' +
        f'unsigned long capacity(void){{return {cap};}}\n' +
        'long replay_write(long n,long x,long y,long z){(void)x;if(n!=64)abort();return (long)fwrite((void*)y,1,(size_t)z,stdout);}\n' +
        'static unsigned long emulate(unsigned op,const void *aa,const void *bb,void *oo,unsigned long vl,unsigned long cap,const void *pp,unsigned long start){\n'
        '(void)bb;if(op!=0 || vl>cap)abort();const word *a=aa;unsigned char *o=oo;const unsigned char *p=pp;\n'
        'for(unsigned long i=start;i<vl;++i)if((p[i/8]>>(i%8))&1){unsigned char m=1u<<(i%8);if(a[i]==(word)-3)o[i/8]|=m;else o[i/8]&=(unsigned char)~m;}\n' +
        ("o[start/8]^=1u<<(start%8);\n" if mutation == 1 else "") +
        ("o[0]^=1;\n" if mutation == 2 else "") +
        ("((uint64_t*)oo)[-1]^=1;\n" if mutation == 3 else "") +
        f'return {1 if mutation == 4 else 0};}}\n' +
        '\n'.join(f'unsigned long op_{i}(const void *a,const void*b,void*o,unsigned long vl,unsigned long cap,const void*p,unsigned long start){{return emulate({i},a,b,o,vl,cap,p,start);}}' for i in range(12)) +
        f'\nint main(void){{return {name}_main();}}\n')
    binary = source.with_suffix("")
    base.command(["/usr/bin/gcc", "-O2", *flags, "-I"+str(case / "original"), source, "-o", binary], binary.with_suffix(".compile.log"))
    command = [str(binary)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    log = binary.with_suffix(".log")
    log.write_text(result.stdout + result.stderr)
    marker = f"RVV_MASK_PASS sew={sew} cases=1 errors=0"
    require((result.returncode == 0 and marker in result.stdout and not base.FAIL.search(result.stdout)) if not mutation
            else (result.returncode == 1 and "RVV_MASK_FAIL" in result.stdout), "Host oracle self-check failed")
    return dict(name=name, mutation=mutation, returncode=result.returncode, log_sha256=sha(log),
        status="PASS" if not mutation else "EXPECTED_ORACLE_REJECTION")


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    pins = {}
    def pin(path, expected=None):
        digest = sha(path)
        require(expected is None or expected == digest, "Source identity mismatch: " + str(path))
        pins[str(path)] = digest
    manifest_path = base.ARCH / "manifest.json"
    pin(manifest_path, "eaafd63d14aa2a0d2019a49bb566d1983b2a1b94c15cbfbe17619185b9936ae8")
    manifest = read(manifest_path)
    symptoms_path = base.CAMP / "rvv_mask_symptoms02/symptoms.json"
    pin(symptoms_path, "1c7017790bd6953d6a6095ff793d1744d4a6c08a2ebca4d5d11a8cb7372f4409")
    symptoms = read(symptoms_path)
    pin(base.ARCH / "prefix_board_report.json", symptoms["prefix_report_sha256"])
    pin(symptoms_path.parent / "sampled_report.json", symptoms["report_sha256"])
    records = [x for x in manifest["cases"] if "masks_scalar_restart" in x["name"]]
    require(len(records) == 19, "Exact scalar19 not recovered")
    records.sort(key=lambda x:(x["name"] != SELECTED,x["sew"],x["lmul"]))
    prepared = OUT / "prepared"
    prepared.mkdir()
    for n in ("startup.S","runtime.c","replay.ld"):
        pin(base.BASE / n)
        shutil.copyfile(base.BASE / n, prepared / n)
    entries, tuples = [], []
    for record in records:
        name = record["name"]
        stimulus = record["measured_stimulus"]
        symptom = next(x for x in symptoms["cases"] if x["name"] == name)
        require(symptom["confirmed"] and symptom["single_detail"] == symptom["prefix_detail"] == record["prefix_failure_detail"], "Archived symptom mismatch")
        require(stimulus["seed"] == stimulus["op"] == stimulus["mask"] == stimulus["returned_vstart"] == 0, "Not recovered tuple")
        pin(base.ARCH / "binaries" / name, record["sha256"])
        pin(base.CAMP / "rvv_additions35/binaries" / record["original_name"], record["original_elf_sha256"])
        prefix = base.CAMP / "rvv_mask_first_trace01" / record["prefix_name"]
        pin(prefix / "original_rebuilt.elf", record["original_elf_sha256"])
        pin(prefix.parent / "binaries" / record["prefix_name"], record["prefix_elf_sha256"])
        case = prepared / name
        original = case / "original"
        original.mkdir(parents=True)
        for n,digest in record["scenario_sources"].items():
            pin(base.ARCH / name / n,digest)
            shutil.copyfile(base.ARCH / name / n, original / n)
        require((original / "scenario.S").read_bytes() == (prefix / "scenario.S").read_bytes(), "Single/prefix asm differs")
        pin(prefix / "scenario.S")
        source = (original / "scenario.c").read_text()
        require(f'unsigned lengths[]={{{stimulus["vl"]}}};' in source and f'start={stimulus["vstart"]};' in source
            and all(x in source for x in ("seed<1", "raw_op<1", "l<1", "mode<1", "trial<1U")), "Source tuple differs")
        port = base.adapt(source,name)
        require(source[source.index("            unsigned long returned="):source.index("probe_done:\n")] in port, "Oracle changed")
        (case / "case.c").write_text(port)
        (case / "wrapper.diff").write_text("".join(difflib.unified_diff(source.splitlines(True),port.splitlines(True),fromfile="original/scenario.c",tofile="case.c")))
        flags = [f"SEW={record['sew']}","SCALAR_FORMS=1","ALIASES=0","COMPARISON_ALIASES=0","CARRY_FORMS=0","RESTART_MASKS=1"]
        entries.append(dict(id=name,defines=flags,assembly="scenario.S",include_combined=False))
        lmul = Fraction(1,int(record["lmul"][2:])) if record["lmul"].startswith("mf") else Fraction(int(record["lmul"][1:]))
        tuples.append(dict(name=name,sew=record["sew"],lmul=record["lmul"],capacity=int(1024*lmul/record["sew"]),
            original_elf=record["original_name"],original_sha256=record["original_elf_sha256"],single_sha256=record["sha256"],
            asm="vmseq.vx v24,v8,t3,v0.t; t3=-3",vd_initial="0x5b repeated via vlm.v v24",**stimulus,
            first_wrong_bit=record["prefix_failure_detail"]))
    for file in (Path(__file__),Path(base.__file__),base.BASE / "prepare.py",base.BASE / "run.py",base.CC.resolve(),base.SPIKE,Path("/usr/bin/gcc").resolve()):
        pin(file)
    save(OUT / "source_pins.json",pins)
    save(OUT / "tuples.json",tuples)
    save(prepared / "provenance.json",dict(schema_version=1,cases=entries,records=records,
        scope="19 archived scalar-restart singles only; not parent matrices or Linux ELF replay",
        files={str(x.relative_to(prepared)):sha(x) for x in prepared.rglob("*") if x.is_file()}))
    hostdir = OUT / "host"
    hostdir.mkdir()
    host_results = []
    for entry,t in zip(entries,tuples):
        host_results.append(host(prepared / t["name"],t["name"],t["sew"],t["capacity"],["-D"+x for x in entry["defines"]],hostdir))
    for mutation in range(1,5):
        t, entry = tuples[0], entries[0]
        host_results.append(host(prepared / t["name"],t["name"],t["sew"],t["capacity"],["-D"+x for x in entry["defines"]],hostdir,mutation))
    save(OUT / "host.json",dict(status="PASS_19_HOST_PLUS_4_ORACLE_REJECTIONS",results=host_results,
        limitation="Host emulation tests original oracle/wrapper only, not architecture or RTL; host-only CSR constant replacement is isolated"))
    flags = ["-Os","-march=rv64gcv","-mabi=lp64d","-mcmodel=medany","-ffreestanding","-fno-builtin",
        "-fno-stack-protector","-fno-tree-vectorize","-fno-tree-slp-vectorize","-msmall-data-limit=0",
        "-ffunction-sections","-fdata-sections","-Wall","-Wextra","-Werror","-nostdlib","-static",
        "-Wl,--build-id=none","-Wl,--gc-sections","-T",prepared / "replay.ld"]
    maps, references = {}, []
    for backend in ("spike","soc"):
        dest = OUT / backend
        dest.mkdir()
        programs = {}
        for entry,t in zip(entries,tuples):
            name = t["name"]
            case = prepared / name
            main = dest / (name+"_main.c")
            main.write_text('extern void replay_text(const char*);\nextern int '+name+'_main(void);\n'
                'int main(void){unsigned long vb;__asm__ volatile("csrr %0,vlenb":"=r"(vb));if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\\n");return 90;}\n'
                f'if({name}_main()){{replay_text("BOARD_CASE_FAIL {name}\\n");return 1;}}\n'
                f'replay_text("BOARD_CASE_PASS {name}\\nBOARD_REPLAY_PASS\\n");return 0;}}\n')
            elf = dest / (name+".elf")
            defines = ["-D"+x for x in entry["defines"]] + (["-DSPIKE_REFERENCE=1"] if backend == "spike" else [])
            base.command([base.CC,*flags,*defines,"-I"+str(case / "original"),case / "case.c",case / "original/scenario.S",
                main,prepared / "startup.S",prepared / "runtime.c","-lgcc","-o",elf],dest / (name+".compile.log"))
            dis = elf.with_suffix(".dis")
            base.command([base.CC.with_name(base.CC.name.removesuffix("gcc")+"objdump"),"-d",elf],dis)
            matches = re.findall(r"^\s*([0-9a-f]+):\s+608e4c57\s+vmseq\.vx\s+v24,v8,t3,v0.t",dis.read_text(),re.M)
            require(len(matches) == 1,"Missing op0 target")
            nm = subprocess.check_output([str(base.CC.with_name(base.CC.name.removesuffix("gcc")+"nm")),str(elf)],text=True)
            symbols = {n:a for a,_,n in (x.split() for x in nm.splitlines())}
            save(dest / (name+".symbols.json"),symbols)
            maps.setdefault(name,{})[backend] = dict(target_pc="0x"+matches[0],opcode="608e4c57",elf_sha256=sha(elf))
            markers = [f'RVV_MASK_PASS sew={t["sew"]} cases=1 errors=0',f"BOARD_CASE_PASS {name}","BOARD_REPLAY_PASS"]
            programs[name] = dict(path=str(elf),sha256=sha(elf),cases=[name],pass_markers=markers)
            if backend == "spike":
                debug = dest / (name+".cmd")
                debug.write_text("until pc 0 "+matches[0]+"\npc 0\ninsn 0\nreg 0 vl\nreg 0 vstart\nreg 0 t3\nuntil pc 0 "+symbols["replay_exit"]+"\nreg 0 a0\nstr "+symbols["replay_log"]+"\nrs\n")
                log = dest / (name+".spike.log")
                base.command([base.SPIKE,"-d","--debug-cmd="+str(debug),"--isa=rv64gcv_zvl1024b","-m2",elf],log,30)
                text = log.read_text()
                values = re.findall(r"^0x([0-9a-f]+)$",text,re.M)
                require(len(values) == 5 and [int(x,16) for x in values[1:]] == [t["vl"],t["vstart"],(1<<64)-3,0],"Spike architectural tuple differs")
                require(base.oracle(programs[name],text),"Spike oracle failed")
                references.append(dict(name=name,status="PASS",log_sha256=sha(log),vl=t["vl"],vstart=t["vstart"],scalar=-3))
        save(dest / "programs.json",dict(schema_version=1,programs=programs,prepared=str(prepared),
            provenance_sha256=sha(prepared / "provenance.json"),backend="spike-htif" if backend == "spike" else "vcs-soc"))
    for path,digest in pins.items():
        require(sha(Path(path)) == digest,"Source drift: "+path)
    save(OUT / "address_map.json",maps)
    save(OUT / "reference.json",dict(status="SPIKE_19_PASS_NOT_DUT",results=references,source_pins_unchanged=True))
    print("HOST_AND_SPIKE_19_PASS_NOT_DUT",flush=True)


if __name__ == "__main__":
    main()

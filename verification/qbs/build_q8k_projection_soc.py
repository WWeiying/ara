#!/usr/bin/env python3
"""Build an unchanged-QBS real full-projection preparation comparison."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

from build_q8k_prepare_soc import extract
from run_half_scale_soc import ROOT, atomic_json, digest, hashes


def check_data(data):
    report = json.loads((data/"data.json").read_text())
    pins = json.loads((data/"manifest.json").read_text())
    if (report["state"] != "READY_NOT_RTL_VERIFIED" or
        (report["m"],report["n"],report["k"],report["outputs"]) != (4,1536,1536,6144) or
        (report["oracle_atol"],report["oracle_rtol"]) != (2e-4,2e-5) or
        digest(data/"manifest.json") != report["manifest_sha256"] or
        hashes(map(Path,pins)) != pins or hashes(map(Path,report["artifacts"])) != report["artifacts"]):
        raise ValueError("Projection data or acceptance contract drift")
    expected = {"activation_f32.bin":24576,"activation_q8k_m4.bin":7008,
                "weight_r4.bin":1327104,"oracle_f32.bin":24576}
    if {Path(p).name for p in report["artifacts"]} != set(expected):
        raise ValueError("Missing/extra data artifacts")
    for name,size in expected.items():
        if str(data/name) not in report["artifacts"] or (data/name).stat().st_size != size:
            raise ValueError("Wrong data location/shape")
    return pins,report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("data","golden-run","output"):
        p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args()
    data,golden_run=a.data.resolve(strict=True),a.golden_run.resolve(strict=True)
    inherited,report=check_data(data)
    golden=json.loads((golden_run/"golden.json").read_text())
    provenance=json.loads((golden_run/"manifest.json").read_text())
    if (golden["state"]!="PASS" or golden["k"]!=1536 or golden["m"]!=4 or not 0<=golden["fcsr"]<=31
        or golden["vcsr"]!=5 or digest(golden_run/"manifest.json")!=golden["manifest_sha256"]
        or digest(golden_run/"golden.bin")!=golden["golden_sha256"]
        or digest(data/"activation_q8k_m4.bin")!=golden["golden_sha256"]
        or digest(data/"activation_f32.bin")!=golden["capture_sha256"]
        or hashes(map(Path,provenance))!=provenance):
        raise ValueError("Production golden identity drift")
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    common,source=ROOT/"apps/common",ROOT/"verification/qbs"
    ggml=Path("/home/wangwy/llama/llama.cpp/ggml")
    repack=ggml/"src/ggml-cpu/repack.cpp"
    gcc=Path("/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc")
    cxx=gcc.with_name("riscv64-unknown-elf-g++");objdump=gcc.with_name("riscv64-unknown-elf-objdump")
    helper=ROOT/"apps/llama_qwen25_q8_0_prefill_m4_direct_qbs/script/build_pair.py"
    spec=importlib.util.spec_from_file_location("pair",helper);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    startup=[common/n for n in ("crt0.S","printf.c","string.c","serial.c","util.c","print_trap_cause.c")]
    native=ROOT/"software/qbs/src/qbs_native_riscv.c"
    pins={**provenance,**inherited,**report["artifacts"]}
    pins.update(hashes([Path(__file__),source/"build_q8k_prepare_soc.py",source/"q8k_projection_soc.cpp",
        source/"ggml_q8k_m4_prepare_candidate.h",data/"manifest.json",data/"data.json",golden_run/"golden.json",
        golden_run/"manifest.json",repack,helper,gcc.resolve(),cxx.resolve(),objdump.resolve(),
        *[Path(subprocess.check_output([gcc,"-print-file-name="+n],text=True).strip()).resolve(strict=True) for n in ("libm.a","libgcc.a")],
        *startup,*common.glob("*.h"),common/"arch.link.ld",native,
        *ggml.rglob("*.h"),*ROOT.glob("software/qbs/include/**/*.h")]))
    atomic_json(out/"manifest.json",pins)
    text=repack.read_text()
    nearest=extract(text,"static inline int nearest_int(","\n// Functions to create")
    body=extract(text,"\nvoid ggml_quantize_mat_q8_K_4x1_ara_generic(","\nvoid ggml_quantize_mat_q8_0_4x4_generic(")
    oracle=out/"oracle.cpp";oracle.write_text('#include "ggml_q8k_m4_prepare_candidate.h"\n'+nearest+'\nextern "C" {\n'+body+'\n}\n')
    assembly=out/"data.S"
    assembly.write_text('.section .rodata\n'+''.join(f'.balign 64\n.global {s}\n{s}:\n.incbin "{data/n}"\n' for s,n in
        (("projection_input","activation_f32.bin"),("projection_weights","weight_r4.bin"),
         ("projection_packed_golden","activation_q8k_m4.bin"),("projection_oracle","oracle_f32.bin"))))
    (out/"golden_state.h").write_text(f'#define Q8K_GOLDEN_FCSR {golden["fcsr"]}U\n')
    link=out/"link.ld";link.write_text((common/"arch.link.ld").read_text().replace("ALIGNMENT","16").replace("LENGTH = 0x00100000","LENGTH = 0x01000000"))
    flags=["-march=rv64gcv","-mabi=lp64d","-mcmodel=medany","-mno-relax","-O3","-DNDEBUG",
        "-fno-fast-math","-ffunction-sections","-fdata-sections","-DNR_LANES=4","-DVLEN=1024",
        *["-I"+str(d) for d in (common,out,ROOT/"apps/include",source,ROOT/"software/qbs/include")],
        *[s for d in (ggml/"include",ggml/"src",ggml/"src/ggml-cpu") for s in ("-isystem",str(d))]]
    commands,objects=[],[]
    def run(cmd,label):
        cmd=list(map(str,cmd));commands.append(cmd);atomic_json(out/"commands.json",commands)
        with (out/(label+".log")).open("x") as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
    for i,path in enumerate([source/"q8k_projection_soc.cpp",oracle,assembly,*startup,native]):
        cpp=path.suffix==".cpp";obj=out/f"{i}.o"
        extra=["-std=gnu++17","-fno-exceptions","-fno-rtti"] if cpp else ["-std=gnu11"]
        if path==common/"string.c":extra += ["-ffreestanding","-fno-builtin","-fno-tree-loop-distribute-patterns"]
        run([cxx if cpp else gcc,*flags,*extra,"-c",path,"-o",obj],f"compile-{i}")
        if path==common/"string.c":module.check_libc_calls(subprocess.check_output([objdump,"-dr",obj],text=True))
        objects.append(obj)
    elf=out/"qbs_q8k_projection_soc"
    run([gcc,*flags,"-static","-nostartfiles","-nostdlib",*objects,"-Wl,--gc-sections","-Wl,-Map="+str(out/"link.map"),"-T",link,"-lm","-lgcc","-o",elf],"link")
    sections=module.allocated_sections(elf)
    if min(s["address"] for s in sections)<0x80000000 or max(s["address"]+s["bytes"] for s in sections)>0x81000000-65536:raise ValueError("ELF address range")
    disasm=subprocess.check_output([objdump,"-d",elf],text=True);(out/"disassembly.txt").write_text(disasm)
    fused=subprocess.check_output([objdump,"-d","--disassemble=ggml_quantize_mat_q8_K_4x1_ara_generic",elf],text=True)
    if "fmadd.s" not in fused or "vsse8.v" not in disasm:raise ValueError("Missing fused reference/vector candidate")
    if hashes(map(Path,pins))!=pins:raise ValueError("Source drift")
    atomic_json(out/"build.json",dict(state="BUILT_NOT_EXECUTED",elf_sha256=digest(elf),manifest_sha256=digest(out/"manifest.json"),
        sections=sections,scope="Same QBS M4/N1536/K1536 full projection; only preparation differs"))


if __name__ == "__main__":main()

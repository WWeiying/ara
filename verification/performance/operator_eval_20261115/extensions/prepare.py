#!/usr/bin/env python3
"""Cross-compile real Prefill/quantKV tests only. Never invokes a simulator."""
import argparse
import io
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
from contract import (HERE, ROOT, OUT, REV, CC, LLAMA, F16_CAPTURE, QUANT_CAPTURE,
                      QUANT_AUDIT, require, sha, read, save, verify)

QUANT_HELPER = "verification/akv/quantized_kv/prefill"
OWN = ("contract.py", "prepare.py", "check.py", "prefill_main.c", "seal.py", "test_extensions.py", "README.md")


def extract(repo, revision, paths, destination, receipt):
    archive = subprocess.check_output(["git", "-C", str(repo), "archive", revision, *paths], timeout=60)
    receipt.write_bytes(archive)
    destination.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        require(all((m.isfile() or m.isdir()) and not Path(m.name).is_absolute() and
                    ".." not in Path(m.name).parts for m in tar.getmembers()), "Unsafe archive")
        tar.extractall(destination)


def quant_driver(source):
    # Retain every arithmetic call and the existing final drain; add only ROI
    # markers and post-call integrity/architectural-state evidence.
    edits = {
        "    uint64_t start = cycles();":
        '    __asm__ volatile("csrr zero,cycle" ::: "memory");\n    uint64_t start = cycles();',
        "    uint64_t elapsed = cycles()-start;":
        '    uint64_t elapsed = cycles()-start;\n    __asm__ volatile("csrr zero,cycle" ::: "memory");',
        "  const unsigned order[] = {0,1,1,0};":
        "  const uint64_t original_hash = extensions_quant_hash();\n  const unsigned order[] = {0,1,1,0};",
        "    unsigned errors = status != AKV_QUANT_OK":
        '    uintptr_t vs; __asm__ volatile("csrr %0,vstart":"=r"(vs));\n'
        '    printf("EXT_QUANT_STATE trial=%u vstart=%lu inputs=%u\\n", trial, (unsigned long)vs, '
        '(unsigned)(extensions_quant_hash() == original_hash));\n'
        '    unsigned errors = vs != 0 || extensions_quant_hash() != original_hash || status != AKV_QUANT_OK',
    }
    for before, after in edits.items():
        require(source.count(before) == 1, "Checked native driver drift: " + before)
        source = source.replace(before, after)
    return ('#include <stdint.h>\nextern const unsigned char fixture_begin[],fixture_end[];\n'
            'static uint64_t extensions_quant_hash(void) {\n'
            '  uint64_t h=UINT64_C(14695981039346656037);\n'
            '  for (const unsigned char *p=fixture_begin;p<fixture_end;++p)\n'
            '    h=(h^*p)*UINT64_C(1099511628211);\n  return h;\n}\n' + source)


def f16_slice(blobs, first, queries, kvhead):
    require(queries in (4, 16, 64) and 0 <= first <= 136-queries and 0 <= kvhead < 8,
            "Bounded captured coordinates required")
    q = blobs["attn_q_input-0"]
    gold = blobs["kqv_out-0"]
    return dict(
        query=b"".join(q[(h*136+first)*512:(h*136+first+queries)*512]
                       for h in range(kvhead*2, kvhead*2+2)),
        key=blobs["attn_k_input-0"][kvhead*65536:(kvhead+1)*65536],
        value=blobs["attn_v_input-0"][kvhead*65536:(kvhead+1)*65536],
        mask=blobs["attn_mask_input-0"][first*512:(first+queries)*512],
        golden=b"".join(gold[(t*16+kvhead*2)*512:(t*16+kvhead*2+2)*512]
                        for t in range(first, first+queries)))


def fixture(kind, first, queries, kvhead, pin):
    if kind == "f16":
        root = F16_CAPTURE
        report = read(root/"result.json")
        require(report["state"] == "REAL_QWEN3_F16_BOUNDARIES_CAPTURED_NOT_RTL_ACCEPTED",
                "Wrong real-model producer")
        recorded = report["capture_files"] if "capture_files" in report else report["artifacts"]
        block = root/"capture/prefill/block"
        pin(root/"result.json"); pin(root/"source-pins.json"); pin(root/"commands.json")
    else:
        root = QUANT_CAPTURE/kind
        require(read(QUANT_AUDIT/"result.json")["state"] == "PASS", "Quant capture audit")
        recorded = read(QUANT_AUDIT/"manifest.json")
        for p in (QUANT_AUDIT/"result.json", QUANT_AUDIT/"manifest.json", root/"command.json"):
            pin(p)
        block = root/"prefill/block"
        require((first, queries, kvhead) == (16, 4, 0), "Quant harness fixed checked coordinates")
    blobs, metadata = {}, {}
    for name in ("attn_q_input-0", "attn_k_input-0", "attn_v_input-0", "attn_mask_input-0", "kqv_out-0"):
        for suffix in (".bin", ".json"):
            path = block/(name+suffix)
            require(recorded.get(str(path)) == sha(path), "Producer pin mismatch: " + str(path))
            pin(path)
        m = read(block/(name+".json")); raw = (block/(name+".bin")).read_bytes()
        require(len(raw) == m["nbytes"], "Tensor extent")
        blobs[name], metadata[name] = raw, m
    q, k, v, mask, g = (metadata[n] for n in blobs)
    n = 136 if kind == "f16" else 20
    key_row = 256 if kind == "f16" else 72 if kind == "q4_0" else 136
    val_row = 256 if kind == "f16" else 136
    expected = (("f32", [128,n,16,1], [4,512,n*512,n*8192]),
                (kind, [128,256,8,1], [2 if kind == "f16" else key_row//4,key_row,key_row*256,key_row*2048]),
                ("f16" if kind == "f16" else "q8_0", [128,256,8,1],
                 [2 if kind == "f16" else 34,val_row,val_row*256,val_row*2048]),
                ("f16", [256,n,1,1], [2,512,n*512,n*512]),
                ("f32", [2048,n,1,1], [4,8192,n*8192,n*8192]))
    for m, (dtype, shape, strides) in zip((q,k,v,mask,g), expected):
        require((m["type"],m["shape"],m["strides"]) == (dtype,shape,strides), "Tensor geometry: " + m["role"])
    for t in range(n):
        words = struct.unpack_from("<256H", blobs["attn_mask_input-0"], t*512)
        require(all(x == (0 if i <= t else 0xfc00) for i,x in enumerate(words)), "Complete causal mask")
    params_path = block/"attention_params-0.json"
    pin(params_path)
    require(recorded.get(str(params_path)) == sha(params_path), "Parameter producer pin")
    params = read(params_path)
    require(params["scale"] == .0883883 and params["max_bias"] == params["logit_softcap"] == 0,
            "Attention parameter contract")
    if kind == "f16":
        data = f16_slice(blobs, first, queries, kvhead)
    else:
        data = {role:blobs[name] for role,name in zip(("query","key","value","mask","golden"),blobs)}
    return data, dict(model="Qwen3-1.7B-Q4_K_M", provenance="exact real-model coordinate slice",
        kind=kind, first_query=first, queries=queries, kv_head=kvhead, dimension=128,
        query_heads=2, kv_heads=1, kv_capacity=256, visible_prefixes=list(range(first+1,first+queries+1)),
        original_queries=n, original_query_heads=16, original_kv_heads=8,
        softmax_k_truncated=False, scale_bits="3db504f3", outputs=queries*256,
        tolerance=dict(atol=.004 if kind == "f16" else 2e-5, rtol=.002 if kind == "f16" else 2e-5),
        whole_model=False, actual_ggml_dispatch=False, runtime_admission=False)


def assembly(inputs, data, kind, first, queries):
    lines = ['.section .rodata.extensions,"a",@progbits', '.balign 64',
             '.global fixture_begin', 'fixture_begin:']
    for role, blob in data.items():
        path = inputs/(role+".bin"); path.write_bytes(blob)
        symbol = "llama_input_" + dict(query="a",key="b",value="c",mask="d").get(role, "") + "_start"
        if role == "golden": symbol = "llama_golden_start"
        lines += ['.balign 64', '.global '+symbol, symbol+':', '.global prefill_'+role,
                  'prefill_'+role+':', '.incbin "'+str(path)+'"']
    lines += ['.global fixture_end', 'fixture_end:', '.balign 4',
              '.global prefill_scale', 'prefill_scale: .word 0x3db504f3',
              '.global prefill_q4', 'prefill_q4: .word '+str(int(kind == "q4_0"))]
    if kind == "f16":
        # Exact case_config_t layout from the archived operator, no arithmetic rewrite.
        cfg = [0,0,7,0,128,queries,2,256,1,0,0,0]
        lines += ['.balign 64', '.global llama_case_config', 'llama_case_config:',
                  '.word '+','.join(map(str,cfg)), '.word 0,0,0x3db504f3,0,0,0,0,0', '.zero 100',
                  '.section .bss.extensions,"aw",@nobits', '.balign 64',
                  '.global output_before', 'output_before: .zero 64',
                  '.global llama_attention_output_start', 'llama_attention_output_start:',
                  '.zero '+str(queries*256*4), '.global llama_attention_output_end',
                  'llama_attention_output_end:', '.global output_after', 'output_after: .zero 64']
        (inputs/"fixture.h").write_text(f"#define EXT_FIRST {first}u\n#define EXT_QUERIES {queries}u\n#define EXT_OUTPUTS {queries*256}u\n")
    lines += ['.section .note.GNU-stack,"",@progbits']
    (inputs/"data.S").write_text("\n".join(lines)+"\n")


def build(output, kind, first=16, queries=4, kvhead=0):
    output = Path(output).absolute()
    require(output == output.resolve() and output.parent == OUT.resolve() and
            re.fullmatch(r"operator_extensions_prepare_20261115_[A-Za-z0-9_.-]+", output.name)
            and not output.exists(), "Fresh independently owned signoff output required")
    for key in ("CPATH","C_INCLUDE_PATH","CPLUS_INCLUDE_PATH","LIBRARY_PATH","LD_PRELOAD",
                "LD_LIBRARY_PATH","GCC_EXEC_PREFIX","COMPILER_PATH","CFLAGS","LDFLAGS"):
        require(not os.environ.get(key), "Compiler injection: " + key)
    output.mkdir(); inputs = output/"inputs"; inputs.mkdir()
    pins, commands = {}, []
    env = dict(PATH="/usr/bin:/bin", HOME=str(output), LC_ALL="C", TZ="UTC", PYTHONDONTWRITEBYTECODE="1")
    report = dict(state="FAIL", rtl_executed=False, target_executed=False, performance_measured=False)

    def pin(p):
        p = Path(p).resolve(strict=True); digest = sha(p)
        require(str(p) not in pins or pins[str(p)] == digest, "Input drift: " + str(p))
        pins[str(p)] = digest

    def run(label, argv):
        argv = list(map(str,argv))
        result = subprocess.run(argv,cwd=output,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        (output/(label+".log")).write_bytes(result.stdout)
        commands.append(dict(label=label,argv=argv,returncode=result.returncode))
        save(output/"commands.json",commands)
        require(result.returncode == 0, label+": "+result.stdout[-2000:].decode(errors="replace"))
        return result.stdout.decode().strip()

    try:
        require(run("head",["git","-C",ROOT,"rev-parse","HEAD"]) == REV, "Current main revision changed")
        for name in OWN:
            pin(HERE/name); shutil.copyfile(HERE/name,inputs/name)
        pin(CC); pin(sys.executable)
        archive_paths = ["software/akv","software/qbs","apps/common","apps/llama_q4km_operator",
                         "apps/llama_q4km_micro/micro_kernels.h",QUANT_HELPER,
                         "verification/akv/quantized_kv/pv_primitives.c"]
        sdk = inputs/"sdk"
        extract(ROOT,REV,archive_paths,sdk,inputs/"sdk.tar")
        native_asm = sdk/"software/akv/src/akv_v2_attention_rvv.S"
        report.update(sdk_commit=REV,sdk_overlays={},dirty_asm_excluded=True,archive_native_assembly_sha256=sha(native_asm))
        data, geometry = fixture(kind,first,queries,kvhead,pin)
        assembly(inputs,data,kind,first,queries)
        save(inputs/"fixture.json",geometry)
        common = sdk/"apps/common"
        link = (common/"arch.link.ld").read_text()
        require(link.count("LENGTH = 0x00100000") == 1, "Linker template drift")
        (inputs/"link.ld").write_text(link.replace("ALIGNMENT","16").replace("LENGTH = 0x00100000","LENGTH = 0x01000000"))
        flags = ["-march=rv64gcv_zfh_zvfh","-mabi=lp64d","-mcmodel=medany","-mno-relax",
                 "-O3","-std=gnu11","-fno-fast-math","-ffp-contract=off","-fno-tree-vectorize",
                 "-ffunction-sections","-fdata-sections","-DNR_LANES=4","-DVLEN=1024",
                 "-I"+str(sdk),"-I"+str(common),"-I"+str(inputs),
                 "-I"+str(sdk/"software/akv/include"),"-I"+str(sdk/"software/qbs/include")]
        sources = [(common/n,[]) for n in ("crt0.S","printf.c","string.c","serial.c","util.c","print_trap_cause.c")]
        sources += [(inputs/"data.S",[])]
        if kind == "f16":
            sources += [(inputs/"prefill_main.c",[])]
            sources += [(sdk/"software/akv/src"/n,[]) for n in
                ("akv_runtime.c","akv_features.c","akv_native_riscv.c","akv_prefill_reference.c",
                 "akv_v2_native_riscv.c","akv_attention_rvv.S","akv_v2_attention_rvv.S")]
            required_symbols = ("extensions_full_prefill","akv_attention_execute_v2_prefill_native",
                                "akv_experimental_pv_f32_pair")
        else:
            original = sdk/QUANT_HELPER/"native_main.c"
            (inputs/"quant_main.c").write_text(quant_driver(original.read_text()))
            llama_rev = run("llama-head",["git","-C",LLAMA,"rev-parse","HEAD"])
            extract(LLAMA,llama_rev,["ggml"],inputs/"llama",inputs/"llama.tar")
            report["llama_commit"] = llama_rev
            ggml = inputs/"llama/ggml"
            fast = ["-DNDEBUG","-ffp-contract=fast","-ftree-vectorize","-I"+str(ggml/"include"),
                    "-I"+str(ggml/"src"),"-I"+str(ggml/"src/ggml-cpu")]
            sources += [(inputs/"quant_main.c",["-I"+str(sdk/QUANT_HELPER)])]
            sources += [(sdk/"software/qbs/src"/n,[]) for n in ("qbs_runtime.c","qbs_native_riscv.c")]
            sources += [(ggml/"src"/n,fast) for n in ("ggml-quants.c","ggml-cpu/arch/riscv/quants.c")]
            sources += [(sdk/"verification/akv/quantized_kv/pv_primitives.c",fast)]
            required_symbols = ("qbs_native_execute_command","quantize_row_q8_0","quant_kv_ggml_mad_f32")
        for library in ("libm.a","libc.a","libgcc.a","libnosys.a"):
            pin(run("locate-"+library,[CC,*flags[:2],"-print-file-name="+library]))
        for tool in ("cc1","as","ld"):
            pin(run("locate-"+tool,[CC,"-print-prog-name="+tool]))
        for p in inputs.rglob("*"):
            if p.is_file(): pin(p)
        objects = []
        for i,(source,extra) in enumerate(sources):
            dep = output/(f"{i:02d}.d")
            run(f"deps-{i:02d}",[CC,*flags,*extra,"-M","-MF",dep,source])
            for path in shlex.split(dep.read_text().replace("\\\n"," ").split(":",1)[1]):
                path = Path(path).resolve(strict=True)
                require(not path.is_relative_to(ROOT/"software"), "Live SDK input")
                pin(path)
            obj = output/f"{i:02d}.o"
            special = ["-ffreestanding","-fno-builtin","-fno-tree-loop-distribute-patterns"] if source.name == "string.c" else []
            run(f"compile-{i:02d}",[CC,*flags,*extra,*special,"-c",source,"-o",obj])
            objects.append(obj)
        elf = output/"prefill.elf"
        run("link",[CC,*flags[:4],"-static","-nostdlib","-nostartfiles",*objects,"-Wl,--gc-sections",
            "-Wl,-Map="+str(output/"link.map"),"-T",inputs/"link.ld","-Wl,--start-group",
            "-lm","-lc","-lgcc","-lnosys","-Wl,--end-group","-o",elf])
        objdump = CC.with_name(CC.name.replace("gcc","objdump")); pin(objdump)
        dis = run("objdump",[objdump,"-d","-M","no-aliases,numeric",elf])
        for symbol in required_symbols:
            require(re.search(r"<"+symbol+r"(?:\.constprop\.[0-9]+)?>:", dis), "Missing native symbol: " + symbol)
        if kind != "f16":
            require("<qbs_ref_execute>:" not in dis and "<dequantize_row_q8_0>:" not in dis, "Reference/scalar binding")
        require(re.search(r"csrrs\s+x0,cycle,x0",dis), "Missing ROI toggle")
        elf_reader = ROOT/"verification/performance/resident_rvv/qk_shared/qk_boundary/elf.py"
        pin(elf_reader)
        from contract import module
        reader = module(elf_reader,"extensions_elf")
        parsed = reader.contract(elf.read_bytes())
        raw = elf.read_bytes()
        phoff = struct.unpack_from("<Q",raw,32)[0]
        phsize, phnum = struct.unpack_from("<HH",raw,54)
        require(phsize == 56 and phoff+phsize*phnum <= len(raw), "ELF program table")
        segments = [struct.unpack_from("<IIQQQQQQ",raw,phoff+i*phsize) for i in range(phnum)]
        allocated = [s for s in segments if s[0] == 1 and s[6]]
        require(allocated and all(0x80000000 <= s[3] and s[3]+s[6] < 0x81000000-65536
                                  for s in allocated), "Firmware outside simulation RAM")
        require(parsed["symbols"]["main"]["type"] == 2, "No firmware entry function")
        report["allocated_segments"] = [dict(address=s[3],bytes=s[6]) for s in allocated]
        main_symbol = parsed["symbols"]["main"]
        toggles = [pc for pc,word in parsed["words"].items() if word == 0xc0002073 and
                   main_symbol["address"] <= pc < main_symbol["address"]+main_symbol["size"]]
        require(len(toggles) == 2, "Expected exactly two main-loop ROI marker sites")
        report["main_roi_toggle_pcs"] = sorted(toggles)
        verify(pins)
        save(output/"source-pins.json",pins)
        checker = [str(Path(sys.executable).resolve()),"-B",str(inputs/"check.py"),"--build",str(output),
                   "--run","{run}","--log","{log}","--result","{result}"]
        case_id = f"qwen3_{kind}_prefill_q{first}_{first+queries-1}_kv{kvhead}"
        save(output/"cases.json",dict(cases=[dict(id=case_id,category="prefill_attention" if kind == "f16" else "quantkv_support",
            elf=str(elf),elf_sha256=sha(elf),source_pins=str(output/"source-pins.json"),checker=checker,
            timeout_seconds=10800,plusargs=["+AKV_PERF","+AKV_SUMMARY"] if kind == "f16" else ["+QBS_PERF"])]))
        report.update(state="BUILT_NOT_EXECUTED",elf=str(elf),elf_sha256=sha(elf),fixture=geometry,
            source_pins_sha256=sha(output/"source-pins.json"),post_pins_match=True,
            scopes=dict(group5="existing Q64/KV64 tiled RVV vs native full causal Prefill" if kind == "f16" else None,
                        group6="native QBS per-query GQA vs cross-query V sharing" if kind != "f16" else None),
            monitor_markers="two CSRRS cycle rd=x0 per trial, outside software cycle reads",
            protocol_gate="parent current-RTL runner required", native_sdk_overlays=False)
    except Exception as exc:
        report["error"] = str(exc)
    report["artifacts"] = {str(p):sha(p) for p in output.rglob("*") if p.is_file()}
    save(output/"build.json",report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument("--case",choices=("f16","q4_0","q8_0"),required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--first-query",type=int,default=16)
    p.add_argument("--queries",type=int,choices=(4,16,64),default=4)
    p.add_argument("--kv-head",type=int,default=0)
    a = p.parse_args()
    result = build(a.output,a.case,a.first_query,a.queries,a.kv_head)
    print({k:result[k] for k in ("state","error","elf","elf_sha256") if k in result})
    return result["state"] != "BUILT_NOT_EXECUTED"


if __name__ == "__main__":
    raise SystemExit(main())

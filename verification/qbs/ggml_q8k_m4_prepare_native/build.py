#!/usr/bin/env python3
"""Build a Q8_K native gate against the pinned production GGML archive."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--production-build", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--capture", type=Path, default=Path("/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m"))
    args = p.parse_args()
    previous = args.production_build.resolve(strict=True)
    pins = json.loads((previous / "manifest.json").read_text())
    prior = json.loads((previous / "build.json").read_text())
    if prior["state"] != "READY" or sha(previous / "manifest.json") != prior["manifest_sha256"]:
        raise ValueError("Production archive is not sealed")
    if any(sha(path) != value for path, value in pins.items()):
        raise ValueError("Production archive inputs changed")
    platform = Path("/home/wangwy/llama/platforms/cva6-qemu")
    tools = platform / "tools/bin"
    cxx, cc, objdump = [tools / ("riscv64-linux-" + name) for name in ("g++", "gcc", "objdump")]
    cpio = platform / "sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio"
    ggml = Path("/home/wangwy/llama/llama.cpp/ggml")
    sources = [*HERE.glob("*.py"), HERE / "native.cpp", HERE / "init.c",
               HERE.parent / "ggml_q8k_m4_prepare_candidate.h", cxx.resolve(), cc.resolve(), objdump.resolve(), cpio,
               previous / "build.json", previous / "manifest.json"]
    pins.update({str(path): sha(path) for path in sources})
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    rows, capture_records = [], []
    for role, k in (("attn", 1536), ("gate", 1536), ("down", 8960)):
        op = {"attn": "attn_q", "gate": "ffn_gate", "down": "ffn_down"}[role]
        base = args.capture / "prefill/operators" / ("blk_0_" + op + "_weight")
        meta_path, data_path = base / "activation_f32.json", base / "activation_f32.bin"
        meta, data = json.loads(meta_path.read_text()), data_path.read_bytes()
        if (meta["type"] != "f32" or meta["shape"][0] != k or meta["shape"][1] < 8 or
                meta["shape"][2:] != [1, 1] or meta["strides"][:2] != [4, k * 4] or
                len(data) != meta["nbytes"] or len(data) != k * meta["shape"][1] * 4):
            raise ValueError("Unexpected capture layout")
        pins.update({str(path): sha(path) for path in (meta_path, data_path)})
        for tag, row in (("first", 0), ("last", meta["shape"][1] - 4)):
            name = f"real_{role}_{tag}"
            target = out / (name + ".bin")
            target.write_bytes(data[row*k*4:(row+4)*k*4])
            rows.append(f"{len(rows)} {name} {k} /{target.name}")
            capture_records.append(dict(name=name, source=str(data_path), start_row=row,
                                        k=k, m=4, sha256=sha(target)))
    (out / "captures.txt").write_text("\n".join(rows) + "\n")
    dump(out / "captures.json", capture_records)
    dump(out / "sources-before.json", pins)
    commands = []

    def run(command, label):
        commands.append(list(map(str, command)))
        dump(out / "commands.json", commands)
        with (out / (label + ".log")).open("x") as stream:
            subprocess.run(commands[-1], stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=120)

    includes = [arg for directory in (ggml / "include", ggml / "src", ggml / "src/ggml-cpu")
                for arg in ("-isystem", str(directory))]
    obj = out / "native.o"
    run([cxx, "-std=c++17", "-march=rv64gcv", "-mabi=lp64d", "-O3", "-UNDEBUG",
         "-fno-fast-math", "-ffp-contract=off", "-fno-tree-vectorize", "-Wall", "-Wextra", "-Werror",
         *includes, "-c", HERE / "native.cpp", "-o", obj], "compile")
    libdir = previous / "build/tile-support/ggml/src"
    libs = [libdir / ("lib" + name + ".a") for name in ("ggml", "ggml-cpu", "ggml-base")]
    run([cxx, "-march=rv64gcv", "-mabi=lp64d", "-static", obj, *libs, "-lm", "-ldl", "-o", out / "native"], "link")
    run([cc, "-march=rv64gcv", "-mabi=lp64d", "-O2", "-static", HERE / "init.c", "-o", out / "init"], "init")
    disasm = subprocess.check_output([objdump, "-d", "--disassemble=ggml_quantize_mat_q8_K_4x1_ara_generic", out / "native"], text=True)
    (out / "oracle.disasm").write_text(disasm)
    if "fmadd.s" not in disasm:
        raise ValueError("Production rounding no longer uses the tested FMA contract")
    listing = ["dir /dev 755 0 0", "nod /dev/console 600 0 0 c 5 1",
               f"file /init {out / 'init'} 755 0 0", f"file /native {out / 'native'} 755 0 0",
               f"file /captures.txt {out / 'captures.txt'} 444 0 0"]
    listing += [f"file /{record['name']}.bin {out / (record['name'] + '.bin')} 444 0 0" for record in capture_records]
    (out / "initramfs.list").write_text("\n".join(listing) + "\n")
    with (out / "initramfs.cpio").open("wb") as stream:
        subprocess.run([cpio, out / "initramfs.list"], stdout=stream, check=True, timeout=60)
    if any(sha(path) != value for path, value in pins.items()):
        raise ValueError("Source drift during build")
    pins.update({str(path): sha(path) for path in out.iterdir() if path.is_file()})
    dump(out / "manifest.json", pins)
    dump(out / "build.json", dict(state="READY", manifest_sha256=sha(out / "manifest.json"),
         binary_sha256=sha(out / "native"), execution="NOT_RUN", source_capture=str(args.capture)))


if __name__ == "__main__":
    main()

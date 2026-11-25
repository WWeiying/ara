#!/usr/bin/env python3
"""Build a frozen Linux GGML pair; no board access and no simulated timings."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT.parent / "ara_dsa_signoff_integration/verification/out"
HERE = Path(__file__).resolve().parent
ARA_COMMIT = "4a7361f51ba5447a616217dad1c8e72e3ee2b45b"
LLAMA_COMMIT = "a2b7f30da9aadf88b0a068c447383ed2e26ee867"
LLAMA = Path("/home/wangwy/llama/llama.cpp")
TOOLCHAIN = Path("/home/wangwy/llama/platforms/cva6-qemu/toolchain-rvv.cmake")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open("x") as file:
        json.dump(value, file, indent=2)
        file.write("\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--call-cost", action="store_true", help="Freeze the reviewed software-only call-cost candidate")
    p.add_argument("--session-cost", action="store_true", help="Also package the opt-in persistent client session")
    p.add_argument("--view-cost", action="store_true", help="Build registered live KV and batched head-group candidate")
    args = p.parse_args()
    if args.view_cost:
        args.session_cost = True
    if args.session_cost:
        args.call_cost = True
    out = args.output.resolve()
    if out.parent != OUT or not out.name.startswith("resident_board_pair_"):
        p.error("use a fresh signoff verification/out/resident_board_pair_* directory")
    out.mkdir()
    inputs = out / "inputs"
    inputs.mkdir()
    commands = []

    def run(name, argv, cwd=None):
        with (out / (name + ".log")).open("x") as log:
            rc = subprocess.run(list(map(str, argv)), cwd=cwd, stdout=log,
                                stderr=subprocess.STDOUT, timeout=900).returncode
        commands.append(dict(name=name, command=list(map(str, argv)), returncode=rc))
        if rc:
            raise RuntimeError(name + " failed; see " + str(out / (name + ".log")))

    def archive(repo, commit, name, paths=()):
        dest = inputs / name
        dest.mkdir()
        tar = inputs / (name + ".tar")
        run("archive-" + name, ["git", "-C", repo, "archive", "--format=tar",
                                "--output=" + str(tar), commit, *paths])
        run("extract-" + name, ["tar", "-xf", tar, "-C", dest])
        return dest

    try:
        sdk = archive(ROOT, ARA_COMMIT, "sdk", ("software/akv", "software/qbs", "software/llama/platform"))
        llama = archive(LLAMA, LLAMA_COMMIT, "llama")
        linux = sdk / "software/llama/platform/linux"
        overlays = {}
        if args.call_cost:
            for repo, dest, files in (
                (ROOT, sdk, ("software/llama/platform/linux/ara_resident_broker.c",
                            "software/llama/platform/linux/ara_resident_uapi.h",
                            "software/llama/platform/linux/buffer_pool.h",
                            "software/llama/platform/linux/client.h",
                            "software/llama/platform/linux/client_v2.c",
                            "software/llama/platform/linux/client_rv64.S",
                            "software/llama/platform/linux/view_uapi.h",
                            "software/llama/platform/linux/view_layout.h",
                            "software/llama/platform/linux/kv_view.h",
                            "software/llama/platform/linux/sdk/finite_f16.h",
                            "software/llama/platform/linux/sdk/kernel_compute.h",
                            "software/llama/platform/linux/sdk/kernel_compute.c")),
                (LLAMA, llama, ("ggml/src/ggml-cpu/CMakeLists.txt", "ggml/src/ggml-cpu/arch/riscv/linux-resident.inc",
                               "tests/test-ara-linux-resident.cpp", "tests/test-ara-linux-resident-v2.cpp")),
            ):
                for relative in files:
                    shutil.copyfile(repo / relative, dest / relative)
                    overlays[str(repo / relative)] = sha(repo / relative)
            for name in ("test_pool.c", "test_finite_rvv.c", "prepare.py", "README.md"):
                source = HERE.parent / "call_cost" / name
                shutil.copyfile(source, inputs / ("CALL_COST.md" if name == "README.md" else name))
                overlays[str(source)] = sha(source)
            for name in ("client.ld", "client_start.S", "kernel_compute/test_prepare.c",
                         "linux_smoke/init_v2.c", "linux_smoke/device_numbers.h"):
                source = HERE.parent / name
                shutil.copyfile(source, inputs / source.name)
                overlays[str(source)] = sha(source)
            if args.session_cost:
                relative = "tests/test-ara-linux-resident-session.cpp"
                shutil.copyfile(LLAMA / relative, llama / relative)
                overlays[str(LLAMA / relative)] = sha(LLAMA / relative)
                for name in ("prepare.py", "README.md"):
                    source = HERE.parent / "session_cost" / name
                    shutil.copyfile(source, inputs / ("SESSION.md" if name == "README.md" else "session_prepare.py"))
                    overlays[str(source)] = sha(source)
            if args.view_cost:
                relative = "tests/test-ara-linux-resident-views.cpp"
                shutil.copyfile(LLAMA / relative, llama / relative)
                overlays[str(LLAMA / relative)] = sha(LLAMA / relative)
        oracle_path = ROOT / "verification/performance/resident_rvv/qk_shared/full_call_sdk/fixture.py"
        spec = importlib.util.spec_from_file_location("pair_oracle", oracle_path)
        oracle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(oracle)
        captured, pins = oracle.inputs()
        pins = {str(k): v for k, v in pins.items()}
        pins.update(overlays)
        pins[str(oracle_path)] = sha(oracle_path)
        assembly = ['.section .rodata', '.balign 64']
        header = ['#pragma once', '#include <stdint.h>', 'extern "C" {']
        for role, ctype, size in (("query", "float", 4), ("key", "uint16_t", 2),
                                  ("value", "uint16_t", 2), ("mask", "uint16_t", 2)):
            data = captured[0][role]
            path = inputs / (role + ".bin")
            path.write_bytes(data)
            assembly += ['.balign 64', '.global capture_' + role, 'capture_' + role + ':',
                         '.incbin ' + json.dumps(str(path))]
            header += [f'extern const {ctype} capture_{role}[{len(data) // size}];']
        header += ['}']
        goldens = {}
        for tokens in (65, 128, 137):
            case = dict(dimension=128, heads=2, kv_heads=1, tokens=tokens, capacity=256, initial_flags=0)
            ref = oracle.reference(case, captured[0])
            pins.update(ref["oracle_pins"])
            header += [f'static const uint32_t golden_{tokens}[256] = {{',
                       ','.join(f'0x{x:08x}u' for x in ref['bits']), '};',
                       f'static const unsigned flags_{tokens} = {ref["natural_flags"]};']
            goldens[str(tokens)] = ref
            if args.view_cost:
                import struct
                for kind in ("zero", "negative"):
                    changed = dict(captured[0])
                    raw = changed["value"]
                    changed["value"] = bytes(len(raw)) if kind == "zero" else b"".join(
                        struct.pack("<H", x[0] ^ 0x8000) for x in struct.iter_unpack("<H", raw))
                    # The historical two-head/T137 oracle also checks a fixed
                    # original-data hash. Preserve that check above. Evaluate
                    # each changed head independently with the same arithmetic.
                    parts = []
                    for head in range(2):
                        one = dict(changed, query=changed["query"][head * 512:(head + 1) * 512])
                        parts.append(oracle.reference(dict(case, heads=1), one))
                        pins.update(parts[-1]["oracle_pins"])
                    modified = dict(bits=parts[0]["bits"] + parts[1]["bits"],
                        natural_flags=parts[0]["natural_flags"] | parts[1]["natural_flags"],
                        oracle_pins={**parts[0]["oracle_pins"], **parts[1]["oracle_pins"]})
                    header += [f'static const uint32_t golden_{kind}_{tokens}[256] = {{',
                               ','.join(f'0x{x:08x}u' for x in modified['bits']), '};',
                               f'static const unsigned flags_{kind}_{tokens} = {modified["natural_flags"]};']
                    goldens[kind + "_" + str(tokens)] = modified
        assembly += ['.section .note.GNU-stack,"",@progbits']
        (inputs / "data.S").write_text('\n'.join(assembly) + '\n')
        (inputs / "fixture.h").write_text('\n'.join(header) + '\n')
        for name in ("bench.cpp", "run_board.sh", "analyze.py", "README.md"):
            shutil.copyfile(HERE / name, inputs / name)
        if args.view_cost:
            for name in ("bench.cpp", "run_board.sh", "analyze.py", "README.md"):
                source = HERE.parent / "view_cost" / name
                shutil.copyfile(source, inputs / name)
                pins[str(source)] = sha(source)
        save(inputs / "goldens.json", goldens)
        pins.update({str(path): sha(path) for path in inputs.rglob('*') if path.is_file()})
        pins[str(Path(__file__).resolve())] = sha(__file__)
        pins[str(TOOLCHAIN)] = sha(TOOLCHAIN)
        pins[str(HERE / 'test_analyze.py')] = sha(HERE / 'test_analyze.py')
        save(out / "source-pins.json", pins)
        run("checker-tests", ["python3", "-m", "unittest", "discover", "-s", HERE,
                              "-p", "test_*.py", "-v"])
        run("shell-check", ["sh", "-n", inputs / "run_board.sh"])
        build = out / "build"
        run("configure", ["cmake", "-G", "Ninja", "-S", llama, "-B", build,
            "-DCMAKE_TOOLCHAIN_FILE=" + str(TOOLCHAIN), "-DCMAKE_BUILD_TYPE=Release",
            "-DCMAKE_C_FLAGS=-fno-fast-math -ffp-contract=off",
            "-DCMAKE_CXX_FLAGS=-fno-fast-math -ffp-contract=off",
            "-DBUILD_SHARED_LIBS=OFF", "-DGGML_NATIVE=OFF", "-DGGML_RVV=ON",
            "-DGGML_RV_ZFH=ON", "-DGGML_RV_ZVFH=ON", "-DGGML_OPENMP=OFF",
            "-DGGML_RV_ZICBOP=OFF", "-DGGML_RV_ZIHINTPAUSE=OFF",
            "-DGGML_BACKEND_DL=OFF", "-DGGML_LLAMAFILE=OFF",
            "-DGGML_RISCV_AKV=ON", "-DGGML_RISCV_ACCEL_AUTO=ON",
            "-DGGML_RISCV_AKV_RUNTIME_DIR=" + str(sdk / "software/akv"),
            "-DGGML_RISCV_AKV_LINUX_PORTAL=ON", "-DGGML_RISCV_AKV_LINUX_PORTAL_DIR=" + str(linux),
            "-DGGML_RISCV_AKV_RESIDENT=OFF", "-DGGML_RISCV_QBS=OFF",
            "-DLLAMA_BUILD_COMMON=OFF", "-DLLAMA_BUILD_TESTS=OFF", "-DLLAMA_BUILD_EXAMPLES=OFF",
            "-DLLAMA_BUILD_TOOLS=OFF", "-DLLAMA_BUILD_SERVER=OFF", "-DLLAMA_BUILD_APP=OFF"])
        run("build", ["cmake", "--build", build, "--target", "ggml-cpu", "--parallel", "8"])
        cc = TOOLCHAIN.parent / "tools/bin/riscv64-linux-g++"
        prefix = TOOLCHAIN.parent / "tools/bin/riscv64-linux-"
        elf = out / "resident-ggml-pair"
        includes = ["-I" + str(llama / x) for x in ("ggml/include", "ggml/src", "ggml/src/ggml-cpu")]
        libs = [build / "ggml/src/libggml-base.a", build / "ggml/src/libggml-cpu.a"]
        run("link", [cc, "-O3", "-std=c++17", "-march=rv64gcv_zfh_zvfh", "-mabi=lp64d",
            "-static", "-fno-fast-math", "-ffp-contract=off", *includes, "-I" + str(linux),
            *(["-DRESIDENT_COST_STATS=1"] if args.call_cost else []),
            "-I" + str(inputs), inputs / "bench.cpp", inputs / "data.S",
            "-Wl,--wrap=ara_resident_linux_execute", "-Wl,--start-group", *libs,
            *(["-Wl,--wrap=ara_resident_linux_execute_batch", "-Wl,--wrap=ara_resident_linux_register_kv"] if args.view_cost else []),
            "-Wl,--end-group", "-lpthread", "-ldl", "-lm", "-o", elf])
        run("readelf", [str(prefix) + "readelf", "-h", "-l", elf])
        run("symbols", [str(prefix) + "nm", "-C", elf])
        symbols = (out / "symbols.log").read_text()
        for name in ("__wrap_ara_resident_linux_execute", "ara_resident_linux_execute",
                     "ggml_riscv_akv_flash_attn", "ara_resident_linux_open"):
            if name not in symbols:
                raise ValueError("missing linked symbol: " + name)
        if "INTERP" in (out / "readelf.log").read_text():
            raise ValueError("benchmark is not static")
        for path, digest in pins.items():
            if sha(path) != digest:
                raise ValueError("input changed: " + path)
        bundle = out / "board"
        bundle.mkdir()
        shutil.copyfile(elf, bundle / elf.name)
        (bundle / elf.name).chmod(0o755)
        for name in ("run_board.sh", "analyze.py", "README.md"):
            shutil.copyfile(inputs / name, bundle / name)
        save(bundle / "manifest.json", dict(ara_commit=ARA_COMMIT, llama_commit=LLAMA_COMMIT,
            elf_sha256=sha(elf), scope="GGML Attention entry, not whole model",
            dimension=128, query_heads=2, kv_heads=1, tokens=[65, 128, 137],
            expected_flags={key: ref["natural_flags"] for key, ref in goldens.items()},
            captured_source=str(oracle.DATA), numerical_check="independent tile64 oracle, exact bits and flags",
            client_session_available=args.session_cost, client_session_default=False,
            registered_live_views=args.view_cost, registered_views_default=False,
            linux_resident_required=True, board_executed=False))
        (bundle / "SHA256SUMS").write_text(''.join(
            f'{sha(path)}  {path.name}\n' for path in sorted(bundle.iterdir()) if path.is_file()))
        run("bundle-check", ["sha256sum", "-c", "SHA256SUMS"], cwd=bundle)
        run("package", ["tar", "-czf", out / "resident-board-pair.tar.gz", "-C", out, "board"])
        save(out / "result.json", dict(state="BUILT_NOT_BOARD_TESTED", elf=str(elf),
             elf_sha256=sha(elf), bundle=str(bundle), post_pins_match=True))
        print(json.dumps(dict(state="BUILT_NOT_BOARD_TESTED", bundle=str(bundle))), flush=True)
    except BaseException as error:
        save(out / "failure.json", dict(error=repr(error)))
        raise
    finally:
        save(out / "commands.json", commands)


if __name__ == "__main__":
    main()

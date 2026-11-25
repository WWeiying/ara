#!/usr/bin/env python3
"""Build the compact-coefficient candidate with the same paired workload."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent / "low_overhead_prepared"
OUT = ROOT.parent / "ara_dsa_signoff_integration/verification/out"
SDK_COMMIT = "4a7361f51ba5447a616217dad1c8e72e3ee2b45b"
FIXTURE = OUT / "resident_board_pair_views_20261113_04/inputs"
CC = Path("/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-gcc")
FIXTURE_HASHES = {
    "fixture.h": "34c9284abdc9adf5bb948ad2633b261b51b273a623314651952e14fd2e0ff55b",
    "goldens.json": "d5ff5c27c9bfe429df6333c8717c77cc724a88eb468016183469a7e4b31c68a7",
    "query.bin": "41b57646f533871b4451ac59551a4dee06612380bb7761142b66a189625b4d77",
    "key.bin": "5d14e468e7788e589bccd0b504f1d32d8b9401a020ac0089ef9debccb4d6695f",
    "value.bin": "64ae74fda7068fb06023c0c5333ac8227804067797cf6d2b9b0d623b0159b369",
    "mask.bin": "93a3f03c46a985eed8e4e7fed4db158d1cad01bafc33ea6220eff7efbb9aff10",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    with Path(path).open("x") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.parent != OUT or not out.name.startswith("resident_direct_build_"):
        parser.error("use a fresh signoff verification/out/resident_direct_build_* directory")
    for name in ("CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "LIBRARY_PATH", "LD_PRELOAD"):
        if os.environ.get(name):
            parser.error("compiler environment injection: " + name)
    out.mkdir()
    inputs = out / "inputs"
    inputs.mkdir()
    board = out / "board"
    board.mkdir()
    commands, pins = [], {}
    report = dict(state="FAIL", board_executed=False, linux_executed=False,
                  rtl_executed=False, performance_measured=False,
                  sdk_commit=SDK_COMMIT, scope="Complete SDK Attention call on captured Qwen3 data; not whole-model inference")

    def run(name, argv):
        argv = list(map(str, argv))
        with (out / (name + ".log")).open("x") as log:
            rc = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=900).returncode
        commands.append(dict(name=name, argv=argv, returncode=rc))
        if rc:
            raise RuntimeError(name + " failed; inspect its log")

    def copy(source, target):
        pins[str(source)] = sha(source)
        shutil.copyfile(source, target)
        pins[str(target)] = sha(target)

    try:
        pins[str(Path(__file__).resolve())] = sha(__file__)
        pins[str(CC.resolve())] = sha(CC.resolve())
        sdk = inputs / "sdk"
        sdk.mkdir()
        run("archive", ["git", "-C", ROOT, "archive", "--format=tar", "--output=" + str(inputs / "sdk.tar"),
                        SDK_COMMIT, "software/akv"])
        run("extract", ["tar", "-xf", inputs / "sdk.tar", "-C", sdk])
        runtime = sdk / "software/akv"
        # Apply only this reviewed SDK delta; never import dirty AKV assembly.
        overlay = [
            "src/akv_v2_native_riscv.c",
            "include/akv/akv.h",
            "experimental/resident_attention/pv_compact.h",
            "experimental/resident_attention/pv_compact.S",
            "experimental/resident_attention/pv.S",
            "experimental/resident_attention/pv.h",
            "experimental/resident_attention/pv_fast.inc",
            "experimental/resident_attention/qk.S",
            "experimental/resident_attention/qk.h",
            "experimental/resident_attention/admission.h",
            "experimental/resident_attention/dispatch.h",
        ]
        for relative in overlay:
            copy(ROOT / "software/akv" / relative, runtime / relative)
        report["sdk_overlay"] = overlay
        report["variant"] = "resident-compact-coefficients-v4"
        for path in sdk.rglob("*"):
            if path.is_file():
                pins[str(path)] = sha(path)
        fixture_receipt = FIXTURE.parent / "qualification.json"
        qualification = json.loads(fixture_receipt.read_text())
        if not str(qualification.get("state", "")).startswith("HOST_SANITIZER_RV64_CHECKED"):
            raise RuntimeError("fixture source did not qualify")
        copy(fixture_receipt, inputs / "fixture-qualification.json")
        for name in ("fixture.h", "goldens.json", "query.bin", "key.bin", "value.bin", "mask.bin"):
            if sha(FIXTURE / name) != FIXTURE_HASHES[name]:
                raise RuntimeError("checked fixture drift: " + name)
            copy(FIXTURE / name, inputs / name)
        assembly = [".section .rodata"]
        for role in ("query", "key", "value", "mask"):
            assembly += [".balign 64", ".global capture_" + role, "capture_" + role + ":",
                         ".incbin " + json.dumps(str(inputs / (role + ".bin")))]
        assembly += ['.section .note.GNU-stack,"",@progbits']
        (inputs / "data.S").write_text("\n".join(assembly) + "\n")
        pins[str(inputs / "data.S")] = sha(inputs / "data.S")
        direct = ROOT / "software/llama/platform/linux/direct"
        for name in ("direct_client.c", "direct_client.h", "direct_uapi.h"):
            copy(direct / name, inputs / name)
        for name in ("bench.cpp", "run_board.sh", "analyze.py", "README.md", "test_analyze.py"):
            copy(HERE / name, inputs / name)
        # Only the observed leaf name and its pointer type change. Workload,
        # timing boundary, scalar/vector checks and both controls are unchanged.
        bench = inputs / "bench.cpp"
        old_leaf = "LEAF(akv_experimental_resident_pv_prepared,\n     (const float *s,"
        new_leaf = "LEAF(akv_experimental_resident_pv_compact,\n     (const uint16_t *s,"
        text = bench.read_text()
        if text.count(old_leaf) != 1:
            raise RuntimeError("unexpected benchmark leaf declaration")
        bench.write_text(text.replace(old_leaf, new_leaf))
        pins[str(bench)] = sha(bench)
        report["benchmark_transform"] = "PV wrapper name/pointer type only"
        copy(HERE.parent / "test_client.py", inputs / "test_client.py")
        save(out / "source-pins.json", pins)
        run("checker-tests", [sys.executable, "-B", "-m", "unittest", "discover", "-s", inputs,
                              "-p", "test_analyze.py", "-v"])
        run("shell-check", ["sh", "-n", inputs / "run_board.sh"])
        flags = ["-O3", "-march=rv64gcv_zfh_zvfh", "-mabi=lp64d", "-fno-fast-math", "-ffp-contract=off",
                 "-fno-tree-vectorize", "-ffunction-sections", "-fdata-sections", "-Wall", "-Wextra",
                 "-Wno-unknown-pragmas", "-DAKV_REFILL_OVERLAP=0", "-DAKV_EXPERIMENTAL_RESIDENT_ATTENTION=1", "-DAKV_RESIDENT_COMPACT_COEFFICIENTS=1",
                 "-I" + str(runtime / "include"), "-I" + str(runtime / "experimental"), "-I" + str(inputs)]
        sources = [runtime / "src" / name for name in (
            "akv_runtime.c", "akv_decode.c", "akv_features.c", "akv_prefill_reference.c",
            "akv_native_riscv.c", "akv_v2_native_riscv.c", "akv_v2_attention_rvv.S", "akv_attention_rvv.S")]
        sources += [runtime / "experimental/resident_attention" / name for name in ("qk.S", "pv.S", "pv_compact.S")]
        sources += [inputs / "direct_client.c", inputs / "data.S", inputs / "bench.cpp"]
        objects = []
        cxx = CC.with_name("riscv64-linux-g++")
        for index, source in enumerate(sources):
            obj = out / (str(index) + "_" + source.stem + ".o")
            compiler = cxx if source.suffix == ".cpp" else CC
            extra = ["-std=c++17"] if source.suffix == ".cpp" else []
            if source.name == "direct_client.c":
                extra += ["-march=rv64gc", "-fno-stack-protector", "-fno-builtin", "-fno-tree-slp-vectorize"]
            run("compile-" + str(index), [compiler, *flags, *extra, "-c", source, "-o", obj])
            if source.name == "direct_client.c":
                spec = importlib.util.spec_from_file_location("direct_client_audit", inputs / "test_client.py")
                audit = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(audit)
                sections = audit.executable_sections(obj.read_bytes())
                save(out / "client-object-audit.json", {
                    "sha256": sha(obj), "sections": {
                        name: audit.audit_instructions(data) for name, data in sections.items()}})
                unresolved = subprocess.check_output([str(CC.with_name("riscv64-linux-nm")), "-u", str(obj)], text=True)
                if unresolved.strip():
                    raise RuntimeError("client has unaudited external calls: " + unresolved)
            objects.append(obj)
        elf = board / "resident-direct-pair"
        wrappers = ["akv_experimental_qk_f16_pair_panel4", "akv_experimental_pv_f16_pair",
                    "akv_experimental_resident_qk_prepared", "akv_experimental_resident_pv_compact", "akv_native_info",
                    "akv_experimental_attention_execute_v2_native", "ara_akv_direct_open",
                    "ara_akv_direct_acquire", "ara_akv_direct_release", "ara_akv_direct_close"]
        run("link", [cxx, *flags, "-static", "-Wl,--gc-sections", "-Wl,-Map=" + str(out / "link.map"),
                     *("-Wl,--wrap=" + name for name in wrappers), *objects, "-lm", "-o", elf])
        run("disassembly", [CC.with_name("riscv64-linux-objdump"), "-d", "-M", "no-aliases", elf])
        run("elf-headers", [CC.with_name("riscv64-linux-readelf"), "-hlW", elf])
        for path, digest in pins.items():
            if sha(path) != digest:
                raise RuntimeError("input drift: " + path)
        for name in ("run_board.sh", "analyze.py", "README.md"):
            shutil.copyfile(inputs / name, board / name)
        shutil.copyfile(inputs / "goldens.json", board / "goldens.json")
        shutil.copyfile(out / "source-pins.json", board / "source-pins.json")
        (board / "run_board.sh").chmod(0o755)
        (board / "SHA256SUMS").write_text("".join(
            sha(p) + "  " + p.name + "\n" for p in sorted(board.iterdir()) if p.is_file()))
        report.update(state="USERSPACE_BUILT_NOT_EXECUTED", elf=str(elf), elf_sha256=sha(elf),
                      gate_signature="0x414b5601", required_kernel_config="CONFIG_RISCV_AKV_DIRECT",
                      existing_bitstream_compatible=False, post_pins_match=True,
                      archive_native_assembly_sha256=sha(runtime / "src/akv_v2_attention_rvv.S"))
    except Exception as exc:
        report["error"] = str(exc)
    save(out / "commands.json", commands)
    save(out / "result.json", report)
    print(json.dumps(report, indent=2))
    return report["state"] != "USERSPACE_BUILT_NOT_EXECUTED"


if __name__ == "__main__":
    raise SystemExit(main())





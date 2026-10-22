"""AKV v2 successor: active-only writes, all guards/CSR/frame checks, no EDA."""
import argparse
import json
from pathlib import Path
import subprocess
import struct

import build_gap98_preflight as shared
import build_akv_column_boundary_preflight as original
from inventory_operand_debug import Design, points

ROOT, OUT, sha, save, require = shared.ROOT, shared.OUT, shared.sha, shared.save, shared.require
NAME = "vakv_column_boundary_v2"
APP = ROOT / "apps/riscv-tests/isa/rv64uv" / (NAME + ".c")
BASE = OUT / "cache-port1-offline-admitted-717-20261006-01"
BUILD = OUT / "repaired-aligned-build-20260930-01"
SCOPE = "ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_akv_engine"
REFERENCE = ROOT / "software/akv/src/akv_v2_reference.c"
SPIKE_SOURCE = Path("/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart")
SOFTWARE_CHECKS, DUT_CHECKS = 8422, 8420


native_elf_audit = original.native_elf_audit


def expected_snapshots():
    return [0x343f if r == 8 and i == 0 else
            0x2400+i if p == 3 and r == 10 else 0x3400+i if p == 3 and r == 12 else
            0x4400+i if p == 3 and r == 14 else 0x1000 + 64*r+i
            for p in range(4) for r in range(32) for i in range(64)]


target_evidence = original.target_evidence


memory = original.memory


def validate(commits, symbols):
    require(commits and not any(c.vector_writes or c.pc == symbols["trap_fail"] for c in commits),
            "Unexpected software vector write or trap")
    data = memory(commits)
    def read(name, index=0, size=8):
        address = symbols[name] + index*size
        require(all(address+i in data for i in range(size)), "Missing observed bytes: " + name)
        return sum(data[address+i] << (8*i) for i in range(size))
    require(read("tohost") == 1 and read("g75_result", 0, 4) == SOFTWARE_CHECKS and
            read("g75_result", 1, 4) == read("num_failed", 0, 4) == 0, "Software signature differs")
    require([read("boundary_status", i, 4) for i in range(8)] == [0, 0, 7, 0, 0, 0, 0, 0],
            "Wrong full/column/reject/recovery/release statuses")
    require([read("boundary_snapshots", i, 2) for i in range(8192)] == expected_snapshots(),
            "Full VRF oracle differs")
    require([read("boundary_csrs", i) for i in range(24)] == [21, 0, 64, 8, 2, 1]*4,
            "Actual Spike CSR snapshots differ")
    require([read("boundary_scan", i, 4) for i in range(8)] == [2048, 0]*4,
            "Missing/full-frame comparison counts or errors")
    require(all(read("g75_trap", i) == 0 for i in range(3)), "Unexpected real Spike trap")
    terminal = [v for c in commits for a, v in c.memory_accesses if a == symbols["tohost"] and v is not None]
    require(terminal == [1], "Nonunique terminal write")
    return dict(status="SPIKE_AKV_SOFTWARE_REFERENCE_PASS_NOT_NATIVE_CUSTOM", checks=SOFTWARE_CHECKS,
                full_vrf_snapshots=4, snapshot_bytes=16384, semantic_rejections=1, real_traps=0,
                custom_instructions_executed=False, measured_increment=None,
                native_expected_custom_write_bytes=388, actual_Spike_CSR_snapshot_bytes=192,
                complete_snapshot_comparisons=8192, inactive_tail_preserved=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    pins = {}
    target = target_evidence(pins)
    paths = [APP, REFERENCE, ROOT / "apps/common/string.c", Path(__file__).resolve(),
             Path(__file__).with_name("test_build_akv_column_boundary_v2_preflight.py"),
             ROOT / "verification/tests/gap75_start.S", ROOT / "verification/tests/gap75.ld",
             shared.LLVM / "clang", shared.LLVM / "ld.lld", shared.LLVM / "llvm-readelf",
             shared.LLVM / "llvm-objdump", shared.SPIKE, Path("/usr/bin/cc").resolve(),
             Path(original.__file__).resolve(),
             SPIKE_SOURCE / "riscv/processor.cc", SPIKE_SOURCE / "riscv/riscv.mk.in"]
    paths += list((ROOT / "software/akv/include").rglob("*.h")) + [ROOT / "apps/common/akv_abi.h"]
    paths += list((ROOT / "verification/ara_verify").glob("*.py"))
    paths += [Path(shared.__file__).resolve(), ROOT / "verification/coverage/build_gap95_preflight.py",
              ROOT / "verification/coverage/run_gap75_operand_batch.py"]
    for path in paths:
        pins[str(path)] = sha(path)
    shared.check(pins)
    out.mkdir()
    save(out / "target-before.json", target)
    def run(command, name, timeout=120):
        command = [str(x) for x in command]
        save(out / (name + "-command.json"), command)
        with (out / (name + ".stdout")).open("x") as stdout, (out / (name + ".stderr")).open("x") as stderr:
            subprocess.run(command, stdout=stdout, stderr=stderr, timeout=timeout, check=True)
    includes = ["-I" + str(ROOT / "apps/common"), "-I" + str(ROOT / "software/akv/include")]
    try:
        run(["/usr/bin/cc", "-O2", "-fno-tree-vectorize", "-DAKV_BOUNDARY_SOFTWARE", "-DAKV_BOUNDARY_HOST",
             *includes, APP, REFERENCE, "-o", out / "host"], "host-compile")
        run([out / "host"], "host", 30)
        require((out / "host.stdout").read_text() == "AKV_COLUMN_BOUNDARY_V2 checks=8422 errors=0\n",
                "Host software oracle failed")
        flags = ["--target=riscv64-unknown-elf", "-march=rv64gv_zfh_zvfh", "-mabi=lp64d", "-mcmodel=medany",
                 "-mno-relax", "-msmall-data-limit=0", "-O2", "-fno-vectorize", "-fno-slp-vectorize",
                 "-ffreestanding", "-fno-builtin", "-mno-implicit-float", "-fuse-ld=lld", "-nostdlib", *includes,
                 "-T" + str(ROOT / "verification/tests/gap75.ld"), ROOT / "verification/tests/gap75_start.S"]
        run([shared.LLVM / "clang", *flags, APP, ROOT / "apps/common/string.c", "-o", out / "input.elf"],
            "native-compile")
        run([shared.LLVM / "clang", *flags, "-march=rv64gv_zfh", "-DAKV_BOUNDARY_SOFTWARE", APP, REFERENCE,
             ROOT / "apps/common/string.c", "-o", out / "software.elf"], "software-compile")
        names = ("tohost", "g75_result", "num_failed", "g75_trap", "trap_fail", "boundary_status", "boundary_snapshots", "boundary_csrs", "boundary_scan")
        symbols = {n: shared._elf_symbol(out / "software.elf", shared.LLVM / "llvm-readelf", n) for n in names}
        native_symbols = {n: shared._elf_symbol(out / "input.elf", shared.LLVM / "llvm-readelf", n)
                          for n in (*names, "boundary_bad", "boundary_handler", "boundary_trap")}
        native_audit = native_elf_audit((out / "input.elf").read_bytes(), native_symbols)
        save(out / "native-elf-audit.json", native_audit)
        run([shared.LLVM / "llvm-objdump", "-d", out / "input.elf"], "native-disassembly")
        run([shared.SPIKE, "--isa=rv64gcv_zfh_zvfh_zvl1024b", "--priv=msu", "--pmpregions=0", "-l",
             "--log-commits", out / "software.elf"], "spike", 180)
        validation = validate(shared.parse_spike_commits(out / "spike.stderr"), symbols)
        save(out / "spike-validation.json", validation)
        shared.check(pins)
        for path in out.iterdir():
            pins[str(path)] = sha(path)
        shared.check(pins)
        manifest = dict(status="AKV_COLUMN_BOUNDARY_V2_HOST_SPIKE_SOFTWARE_PREFLIGHT_NOT_VCS", case=NAME,
            baseline_tests=717, input_elf=str(out / "input.elf"), software_elf=str(out / "software.elf"),
            symbols=native_symbols, software_symbols=symbols, pins=pins, validation=validation,
            dut_checks=DUT_CHECKS, dut_expected_commands=8, dut_expected_cause=2, dut_expected_tval=0,
            dut_expected_trap_pc=native_symbols["boundary_bad"], source_ISA="rv64gv_zfh_zvfh",
            software_compile_ISA="rv64gv_zfh", spike_ISA="rv64gcv_zfh_zvfh_zvl1024b",
            custom_model="existing akv_v2_reference SOFTWARE",
            spike_native_custom_model_available=False, full_scalar_differential_qualified=False,
            required_DUT_oracle="exact eight custom commands, one cause2/tval0 at boundary_bad; four full VRF snapshots; Q/K/V full row recovery; release",
            native_expected_custom_write_bytes=388, inactive_tail_preserved=True,
            actual_CSR_snapshots_required=True, old_image_timeout_s=900, target_before=str(out / "target-before.json"),
            coverage_admitted=False, vcs_launched=False, rtl_changed=False)
        save(out / "preflight-manifest.json", manifest)
        print(json.dumps(dict(output=str(out), seal=sha(out / "preflight-manifest.json"), validation=validation)))
    except Exception as error:
        save(out / "failure.json", dict(status="AKV_BOUNDARY_V2_PREFLIGHT_FAILED", reason=str(error)))
        raise


if __name__ == "__main__":
    main()

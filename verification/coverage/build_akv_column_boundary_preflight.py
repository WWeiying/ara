"""One AKV boundary: native ELF plus host/Spike SOFTWARE model, never EDA."""
import argparse
import json
from pathlib import Path
import subprocess
import struct

import build_gap98_preflight as shared
from inventory_operand_debug import Design, points

ROOT, OUT, sha, save, require = shared.ROOT, shared.OUT, shared.sha, shared.save, shared.require
NAME = "vakv_column_boundary"
APP = ROOT / "apps/riscv-tests/isa/rv64uv" / (NAME + ".c")
BASE = OUT / "cache-port1-offline-admitted-717-20261006-01"
BUILD = OUT / "repaired-aligned-build-20260930-01"
SCOPE = "ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_akv_engine"
REFERENCE = ROOT / "software/akv/src/akv_v2_reference.c"
SPIKE_SOURCE = Path("/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart")
SOFTWARE_CHECKS, DUT_CHECKS = 8398, 8396


def native_elf_audit(blob, symbols):
    require(blob[:6] == b"\x7fELF\x02\x01", "Expected little-endian ELF64")
    header = struct.unpack_from("<HHIQQQIHHHHHH", blob, 16)
    require(header[1] == 243 and header[8] == 56, "Wrong ELF machine/program-header size")
    sites = []
    for i in range(header[9]):
        kind, flags, offset, address, _, size, memory_size, _ = struct.unpack_from(
            "<IIQQQQQQ", blob, header[4] + 56*i)
        if kind != 1:
            continue
        require(offset + size <= len(blob) and 0x80000000 <= address and
                address + memory_size <= 0x80200000, "Truncated/out-of-L2 segment")
        if flags & 1:
            require(size % 4 == 0, "No-C executable layout differs")
            for off in range(0, size, 4):
                word = int.from_bytes(blob[offset+off:offset+off+4], "little")
                if word & 127 == 0x5b:
                    sites.append(dict(pc=address+off, word=word))
    require(sorted(s["word"] for s in sites) == sorted([0x00b5605b, 0x0005745b, 0x0005745b,
            0x0005355b, 0x0005365b, 0x0005375b, 0x0000505b]),
            "Missing/extra/wrong custom opcode")
    require(any(s == dict(pc=symbols["boundary_bad"], word=0x0005745b) for s in sites),
            "Wrong exact expected trap PC")
    return dict(status="NATIVE_ELF_STATIC_CUSTOM_ENCODING_ONLY", sites=sites,
                dynamic_commands=8, rejected_instruction_pc=symbols["boundary_bad"], custom_execution=False)


def expected_snapshots():
    return [0x343f if r == 8 and i == 0 else 0 if r == 8 else
            0x2400+i if p == 3 and r == 10 else 0x3400+i if p == 3 and r == 12 else
            0x4400+i if p == 3 and r == 14 else 0x1000 + 64*r+i
            for p in range(4) for r in range(32) for i in range(64)]


def target_evidence(pins):
    def pin(path, expected=None):
        actual = sha(path)
        require(expected is None or expected == actual, "Input drift: " + str(path))
        pins[str(path)] = actual
        return path
    bitmap = json.loads(pin(BASE / "combined-bits.json").read_bytes())
    state = json.loads(pin(BASE / "status.json").read_bytes())
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and state["aggregate_passed"] == 717 and
            len(bitmap["tests"]) == len(set(bitmap["tests"])) == 717, "Wrong717 population")
    design_path = BUILD / "sim/simv.vdb"
    require(pin(BASE / "combined-inputs.txt").read_text().splitlines() ==
            [str(design_path), *bitmap["tests"]], "717 input order differs")
    sources = json.loads(pin(BUILD / "build-source-pins.json").read_bytes())
    for rel in ("hardware/src/vlsu/akv/akv_engine.sv", "hardware/src/vlsu/akv/akv_v2_context.sv",
                "hardware/src/vlsu/vlsu.sv", "hardware/include/akv_pkg.sv"):
        path = ROOT / rel
        pin(path, sources[str(path)])
    old_dispatcher = OUT / "old-image-source-evidence-20261006-01/ara_dispatcher.sv"
    pin(old_dispatcher, sources[str(ROOT / "hardware/src/ara_dispatcher.sv")])
    design = Design(design_path)
    for relative, expected in bitmap["design"].items():
        pin(design.db / relative, expected)
    for relative in ("auxiliary/verilog.sourceinfo.xml", "shape/branch.verilog.info.xml"):
        pin(design.db / relative)
    record = bitmap["metrics"]["branch"][SCOPE]
    definition = design.definition(SCOPE, "branch")
    require(record["width"] == 166 and record["checksum"] == definition.get("chksum") == "131544421" and
            design.hierarchy[SCOPE].get("chksum") == "3509320291", "Compiled AKV identity differs")
    target = points("branch", definition, 166)[24]
    require(target["raw_index"] == 24 and target["native_id"] == "5" and target["vector"] == "4" and
            target["attributes"]["chksum"] == "3663631239" and
            target["native_vector"]["vector"] == "000110101010" and
            not int(record["bits"], 16) & (1 << 141), "Expected raw24 zero differs")
    require(design.source(SCOPE)["resolved_path"] == str(ROOT / "hardware/src/vlsu/akv/akv_engine.sv"),
            "Wrong compiled source owner")
    policy = json.loads(pin(OUT / "branch-combo-six-policy-717-20261006-01/config.json").read_bytes())
    require(not any(s == SCOPE or s.startswith(SCOPE + ".") for s in policy["scope_owners"]),
            "Candidate intersects six-policy scopes")
    return dict(baseline_tests=717, scope=SCOPE, metric="branch", width=166, checksum="131544421",
                module_checksum="3509320291", target=target, hit=False, source=design.source(SCOPE),
                native_GUI_ID_qualification=False, measured_increment=None, exclusions_generated=False)


def memory(commits):
    result = {}
    for c in commits:
        for address, value in c.memory_accesses:
            if value is None:
                continue
            require(c.instruction & 127 == 0x23, "Software model memory-write schema differs")
            size = 1 << ((c.instruction >> 12) & 7)
            require(size <= 8, "Invalid scalar store size")
            for i in range(size):
                result[address+i] = (value >> (8*i)) & 255
    return result


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
    require(all(read("g75_trap", i) == 0 for i in range(3)), "Unexpected real Spike trap")
    terminal = [v for c in commits for a, v in c.memory_accesses if a == symbols["tohost"] and v is not None]
    require(terminal == [1], "Nonunique terminal write")
    return dict(status="SPIKE_AKV_SOFTWARE_REFERENCE_PASS_NOT_NATIVE_CUSTOM", checks=SOFTWARE_CHECKS,
                full_vrf_snapshots=4, snapshot_bytes=16384, semantic_rejections=1, real_traps=0,
                custom_instructions_executed=False, measured_increment=None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    pins = {}
    target = target_evidence(pins)
    paths = [APP, REFERENCE, ROOT / "apps/common/string.c", Path(__file__).resolve(),
             Path(__file__).with_name("test_build_akv_column_boundary_preflight.py"),
             ROOT / "verification/tests/gap75_start.S", ROOT / "verification/tests/gap75.ld",
             shared.LLVM / "clang", shared.LLVM / "ld.lld", shared.LLVM / "llvm-readelf",
             shared.LLVM / "llvm-objdump", shared.SPIKE, Path("/usr/bin/cc").resolve(),
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
        require((out / "host.stdout").read_text() == "AKV_COLUMN_BOUNDARY checks=8398 errors=0\n",
                "Host software oracle failed")
        flags = ["--target=riscv64-unknown-elf", "-march=rv64gv_zfh_zvfh", "-mabi=lp64d", "-mcmodel=medany",
                 "-mno-relax", "-msmall-data-limit=0", "-O2", "-fno-vectorize", "-fno-slp-vectorize",
                 "-ffreestanding", "-fno-builtin", "-mno-implicit-float", "-fuse-ld=lld", "-nostdlib", *includes,
                 "-T" + str(ROOT / "verification/tests/gap75.ld"), ROOT / "verification/tests/gap75_start.S"]
        run([shared.LLVM / "clang", *flags, APP, ROOT / "apps/common/string.c", "-o", out / "input.elf"],
            "native-compile")
        run([shared.LLVM / "clang", *flags, "-march=rv64g_zfh", "-DAKV_BOUNDARY_SOFTWARE", APP, REFERENCE,
             ROOT / "apps/common/string.c", "-o", out / "software.elf"], "software-compile")
        names = ("tohost", "g75_result", "num_failed", "g75_trap", "trap_fail", "boundary_status", "boundary_snapshots")
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
        manifest = dict(status="AKV_COLUMN_BOUNDARY_HOST_SPIKE_SOFTWARE_PREFLIGHT_NOT_VCS", case=NAME,
            baseline_tests=717, input_elf=str(out / "input.elf"), software_elf=str(out / "software.elf"),
            symbols=native_symbols, software_symbols=symbols, pins=pins, validation=validation,
            dut_checks=DUT_CHECKS, dut_expected_commands=8, dut_expected_cause=2, dut_expected_tval=0,
            dut_expected_trap_pc=native_symbols["boundary_bad"], source_ISA="rv64gv_zfh_zvfh",
            software_compile_ISA="rv64g_zfh", spike_ISA="rv64gcv_zfh_zvfh_zvl1024b",
            custom_model="existing akv_v2_reference SOFTWARE",
            spike_native_custom_model_available=False, full_scalar_differential_qualified=False,
            required_DUT_oracle="exact eight custom commands, one cause2/tval0 at boundary_bad; four full VRF snapshots; Q/K/V full row recovery; release",
            old_image_timeout_s=300, target_before=str(out / "target-before.json"),
            coverage_admitted=False, vcs_launched=False, rtl_changed=False)
        save(out / "preflight-manifest.json", manifest)
        print(json.dumps(dict(output=str(out), seal=sha(out / "preflight-manifest.json"), validation=validation)))
    except Exception as error:
        save(out / "failure.json", dict(status="AKV_BOUNDARY_PREFLIGHT_FAILED", reason=str(error)))
        raise


if __name__ == "__main__":
    main()

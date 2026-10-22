"""Build/Spike only: normal-divisor six-bit scan, never VCS or admission."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from inventory_operand_debug import Design, ROOT
from closure_point_inventory import points
from run_gap75_operand_batch import SPIKE, parse_spike_commits
from ara_verify.random_rvv import _elf_symbol

OUT = ROOT / "verification/out"
APP = ROOT / "apps/riscv-tests/isa/rv64uv"
LLVM = Path("/home/wangwy/openproject/ara/install/riscv-llvm/bin")
CASES = {64: (32, 1616), 32: (64, 3152), 16: (128, 6224)}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def check(pins):
    for path, expected in pins.items():
        if sha(path) != expected:
            raise ValueError("Evidence drift: " + path)


def target_evidence(pins):
    build = OUT / "repaired-aligned-build-20260930-01"
    source_manifest = build / "build-source-pins.json"
    baseline = OUT / "gap94-offline-admitted-701-20261006-01/combined-bits.json"
    status = baseline.with_name("status.json")
    for path in (source_manifest, baseline, status):
        pins[str(path)] = sha(path)
    state = json.loads(status.read_bytes())
    if state["status"] != "PASS_RAW_UNION_HISTORICAL_ONLY" or state["aggregate_passed"] != 701:
        raise ValueError("Baseline not admitted701")
    source_pins = json.loads(source_manifest.read_bytes())
    names = {"ct_vfdsu_prepare.v", "ct_vfdsu_srt.v", "ct_vfdsu_srt_radix16_with_sqrt.v",
             "ct_vfdsu_srt_radix16_bound_table.v", "vmfpu.sv"}
    found = set()
    for path, expected in source_pins.items():
        if Path(path).name in names:
            if sha(path) != expected:
                raise ValueError("Old-image source differs: " + path)
            pins[path] = expected
            found.add(Path(path).name)
    if found != names:
        raise ValueError("Source chain incomplete")
    bitmap = json.loads(baseline.read_bytes())
    if len(bitmap["tests"]) != 701 or len(set(bitmap["tests"])) != 701:
        raise ValueError("Wrong baseline population")
    design = Design(build / "sim/simv.vdb")
    for relative, expected in bitmap["design"].items():
        path = design.db / relative
        if sha(path) != expected:
            raise ValueError("Design drift")
        pins[str(path)] = expected
    rows = []
    for scope, record in bitmap["metrics"]["branch"].items():
        if ".i_ara.gen_lanes[" not in scope or not scope.endswith("x_ct_vfdsu_srt_radix16_bound_table"):
            continue
        definition = design.definition(scope, "branch")
        if record["checksum"] != "974770724" or definition.get("chksum") != record["checksum"]:
            raise ValueError("Bound-table definition differs")
        group = [p for p in points("branch", definition, record["width"]) if p["line"] == "105"]
        if record["width"] != 123 or len(group) != 66 or any(p["native_id"] != "18" for p in group):
            raise ValueError("Bound-table shape differs")
        missing = [p for p in group if int(p["vector"]) < 64 and
                   not int(record["bits"], 16) & (1 << (record["width"] - p["raw_index"] - 1))]
        rows.append(dict(scope=scope, checksum=record["checksum"], width=record["width"],
                         missing_normal_table_points=missing,
                         excluded_from_stimulus_target=[p for p in group if int(p["vector"]) >= 64]))
    if len(rows) != 16 or sum(len(r["missing_normal_table_points"]) for r in rows) != 353:
        raise ValueError("Expected701 physical target population differs")
    return dict(status="STATIC_STIMULUS_TARGETS_NOT_MEASURED", baseline_tests=701,
                selector_values=list(range(64, 128)), missing_normal_table_points=353,
                default_is_not_a_target=True, rows=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    out = parser.parse_args().output.absolute()
    if out.parent != OUT or out.exists():
        raise ValueError("Fresh direct output required")
    pins = {}
    evidence = target_evidence(pins)
    startup, linker = ROOT / "verification/tests/gap75_start.S", ROOT / "verification/tests/gap75.ld"
    paths = [Path(__file__).resolve(), APP / "gap95_divisor_bound_common.h", startup, linker,
             LLVM / "clang", LLVM / "llvm-readelf", SPIKE,
             ROOT / "verification/coverage/test_build_gap95_preflight.py",
             ROOT / "verification/coverage/test_divisor_bound_scan_scope.py"]
    paths += [APP / ("vgap95_div%d_bound.c" % width) for width in CASES]
    paths += [p for p in (ROOT / "apps/riscv-tests/isa/macros").rglob("*") if p.is_file()]
    paths += [p for p in (ROOT / "verification/ara_verify").glob("*.py")]
    paths += [ROOT / "verification/coverage" / name for name in
              ("run_gap75_operand_batch.py", "inventory_operand_debug.py", "closure_point_inventory.py",
               "reviewed_20261004/audit_readonly.py")]
    for path in paths:
        pins[str(path.resolve())] = sha(path)
    check(pins)
    out.mkdir()
    save(out / "target-before.json", evidence)
    results = []
    try:
        for width, (vl, checks) in CASES.items():
            name = "vgap95_div%d_bound" % width
            directory = out / name
            directory.mkdir()
            elf = directory / "input.elf"
            command = [str(LLVM / "clang"), "--target=riscv64-unknown-elf", "-march=rv64gcv_zfh_zvfh",
                       "-mabi=lp64d", "-mcmodel=medany", "-mno-relax", "-msmall-data-limit=0", "-O2",
                       "-fno-vectorize", "-fno-slp-vectorize", "-ffreestanding", "-DG75_NO_PRINT",
                       "-D__SPIKE__", "-DVLEN=1024", "-DNR_LANES=4",
                       "-I" + str(ROOT / "apps/riscv-tests/isa/macros/vector"),
                       "-I" + str(ROOT / "apps/riscv-tests/env"), "-I" + str(ROOT / "apps/common"),
                       "-fuse-ld=lld", "-nostdlib", "-T" + str(linker), str(startup),
                       str(APP / (name + ".c")), "-o", str(elf)]
            save(directory / "compile-command.json", command)
            with (directory / "compile.log").open("x") as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
            data = elf.read_bytes()
            if struct.unpack_from("<Q", data, 24)[0] != 0x80000000:
                raise ValueError("Wrong ELF entry")
            phoff = struct.unpack_from("<Q", data, 32)[0]
            phsize, phnum = struct.unpack_from("<HH", data, 54)
            for i in range(phnum):
                segment = struct.unpack_from("<IIQQQQQQ", data, phoff + i * phsize)
                if segment[0] == 1 and segment[5] and segment[4] % 128:
                    raise ValueError("ELF preload alignment differs")
            symbols = {key: _elf_symbol(elf, LLVM / "llvm-readelf", key)
                       for key in ("tohost", "g75_result", "g75_trap", "num_failed")}
            command = [str(SPIKE), "--isa=rv64gcv_zfh_zvfh_zvl1024b", "--priv=msu",
                       "--pmpregions=0", "-l", "--log-commits", str(elf)]
            save(directory / "spike-command.json", command)
            with (directory / "spike.stdout").open("x") as stdout, (directory / "spike.trace").open("x") as stderr:
                subprocess.run(command, stdout=stdout, stderr=stderr, timeout=120, check=True)
            writes = {a: v for c in parse_spike_commits(directory / "spike.trace")
                      for a, v in c.memory_accesses if v is not None}
            required = {symbols["tohost"]: 1, symbols["g75_result"]: checks,
                        symbols["g75_result"] + 4: 0, symbols["num_failed"]: 0}
            if any(writes.get(a) != v for a, v in required.items()) or any(
                    writes.get(symbols["g75_trap"] + i, 0) for i in (0, 8, 16)):
                raise ValueError("Spike exact signature/trap failure: " + name)
            row = dict(case=name, eew=width, vl=vl, checks=checks, symbols=symbols,
                       expected_vector_instructions=48, expected_vector_bytes=12288,
                       status="SPIKE_SELF_CHECK_PASS_NOT_COVERAGE_ADMITTED")
            save(directory / "preflight.json", row)
            results.append(row)
        check(pins)
        for path in out.rglob("*"):
            if path.is_file():
                pins[str(path)] = sha(path)
        save(out / "preflight-manifest.json", dict(status="GAP95_THREE_SPIKE_PREFLIGHTS_PASS_NOT_VCS",
             pins=pins, cases=results, measured_raw_increment=None, rtl_changed=False, coverage_admitted=False))
        print(json.dumps(dict(output=str(out), seal=sha(out / "preflight-manifest.json"), cases=results)))
    except Exception as error:
        save(out / "failure.json", dict(status="PREFLIGHT_FAILED", reason=str(error), pins=pins))
        raise


if __name__ == "__main__":
    main()

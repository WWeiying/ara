"""FP32 pack exponent stimulus: compile and Spike only, no VCS/admission."""
import argparse
import importlib.util
import json
from pathlib import Path
import struct
import subprocess

from build_gap95_preflight import ROOT, OUT, APP, LLVM, SPIKE, sha, save, check
from run_gap75_operand_batch import parse_spike_commits
from ara_verify.random_rvv import _elf_symbol
from inventory_operand_debug import Design
from closure_point_inventory import points

NAME = "vgap96_div32_pack"
CORE = ROOT / "hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl"
SOURCE_NAMES = ("ct_vfdsu_prepare.v", "ct_vfdsu_srt.v", "ct_vfdsu_round.v",
                "ct_vfdsu_pack.v", "ct_vfdsu_double.v")


def target_evidence(pins):
    build = OUT / "repaired-aligned-build-20260930-01"
    source_manifest = build / "build-source-pins.json"
    baseline = OUT / "gap94-offline-admitted-701-20261006-01/combined-bits.json"
    statefile = baseline.with_name("status.json")
    for path in (source_manifest, baseline, statefile):
        pins[str(path)] = sha(path)
    sources = json.loads(source_manifest.read_bytes())
    for path in [*(CORE / name for name in SOURCE_NAMES),
                 ROOT / "hardware/deps/fpnew/src/fpnew_divsqrt_th_64_multi.sv",
                 ROOT / "hardware/src/lane/vmfpu.sv"]:
        expected = sources[str(path)]
        if sha(path) != expected:
            raise ValueError("Old-image source drift: " + str(path))
        pins[str(path)] = expected
    state = json.loads(statefile.read_bytes())
    bitmap = json.loads(baseline.read_bytes())
    if (state["status"] != "PASS_RAW_UNION_HISTORICAL_ONLY" or state["aggregate_passed"] != 701 or
            len(bitmap["tests"]) != 701 or len(set(bitmap["tests"])) != 701):
        raise ValueError("Baseline is not admitted701")
    design = Design(build / "sim/simv.vdb")
    for relative, expected in bitmap["design"].items():
        path = design.db / relative
        if sha(path) != expected:
            raise ValueError("Design drift")
        pins[str(path)] = expected
    review_path = OUT / "gap56-operand-independent-review-20261004-01/review.py"
    pins[str(review_path)] = sha(review_path)
    spec = importlib.util.spec_from_file_location("gap96_compiled_parameters", review_path)
    review = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(review)
    top = "ara_tb.dut.i_ara_soc.i_system.i_ara"
    variants = review.signature(design.definition(top, "tgl"))
    if len(variants) != 1 or any(variants[0].get(k) != v for k, v in
                              dict(NrLanes=4, VLEN=1024, FPUSupport=56).items()):
        raise ValueError("Compiled Ara configuration differs")
    rows = []
    for scope, record in bitmap["metrics"]["branch"].items():
        if (".i_ara.gen_lanes[" not in scope or ".gen_num_lanes[1]." not in scope or
                not scope.endswith("x_ct_vfdsu_pack")):
            continue
        wrapper = scope.split(".i_fpnew_divsqrt_th_64_c910.")[0] + ".i_fpnew_divsqrt_th_64_c910"
        parameters = review.signature(design.definition(wrapper, "tgl"))
        if len(parameters) != 1 or any(parameters[0].get(k) != v for k, v in dict(WIDTH=32, FpFmtConfig=40).items()):
            raise ValueError("Compiled FP32 physical wrapper differs")
        if design.source(scope)["resolved_path"] != str(CORE / "ct_vfdsu_pack.v"):
            raise ValueError("Compiled source owner differs")
        definition = design.definition(scope, "branch")
        if record["checksum"] != "839910393" or definition.get("chksum") != record["checksum"] or record["width"] != 143:
            raise ValueError("Pack metric shape differs")
        group = [p for p in points("branch", definition, record["width"]) if p["line"] == "178"]
        if len(group) != 55 or any(p["native_id"] != "7" for p in group):
            raise ValueError("Pack table shape differs")
        table = [p for p in group if int(p["vector"]) <= 52]
        if {p["raw_index"] for p in table} != set(range(30, 83)):
            raise ValueError("Explicit table position range differs")
        missing = [p for p in table if not int(record["bits"], 16) & (1 << (142 - p["raw_index"]))]
        rows.append(dict(scope=scope, wrapper=wrapper, compiled_parameters=parameters[0],
                         checksum=record["checksum"], width=143, missing_points=missing,
                         remaining_group_positions=[p for p in group if p not in table]))
    if len(rows) != 4 or [len(r["missing_points"]) for r in rows] != [24, 22, 25, 25]:
        raise ValueError("Expected raw701 FP32 missing population differs")
    return dict(status="GAP96_STATIC_TARGETS_NOT_MEASURED", baseline_tests=701,
                target_unhit_count=96, shift_values=list(range(53)),
                expected_pack_input_signed=[1 - n for n in range(53)],
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
    paths = [Path(__file__).resolve(), APP / (NAME + ".c"), startup, linker,
             LLVM / "clang", LLVM / "llvm-readelf", SPIKE,
             ROOT / "verification/coverage/test_gap96_pack_scope.py",
             ROOT / "apps/riscv-tests/isa/rv64uv/vgap91_div32_exp_lanes.c"]
    paths += [p for p in (ROOT / "apps/riscv-tests/isa/macros").rglob("*") if p.is_file()]
    paths += [p for p in (ROOT / "verification/ara_verify").glob("*.py")]
    paths += [ROOT / "verification/coverage" / name for name in
              ("build_gap95_preflight.py", "run_gap75_operand_batch.py", "inventory_operand_debug.py",
               "closure_point_inventory.py", "reviewed_20261004/audit_readonly.py")]
    for path in paths:
        pins[str(path.resolve())] = sha(path)
    check(pins)
    out.mkdir()
    save(out / "target-before.json", evidence)
    elf = out / "input.elf"
    try:
        command = [str(LLVM / "clang"), "--target=riscv64-unknown-elf", "-march=rv64gcv_zfh_zvfh",
                   "-mabi=lp64d", "-mcmodel=medany", "-mno-relax", "-msmall-data-limit=0", "-O2",
                   "-fno-vectorize", "-fno-slp-vectorize", "-ffreestanding", "-DG75_NO_PRINT",
                   "-D__SPIKE__", "-DVLEN=1024", "-DNR_LANES=4",
                   "-I" + str(ROOT / "apps/riscv-tests/isa/macros/vector"),
                   "-I" + str(ROOT / "apps/riscv-tests/env"), "-I" + str(ROOT / "apps/common"),
                   "-fuse-ld=lld", "-nostdlib", "-T" + str(linker), str(startup),
                   str(APP / (NAME + ".c")), "-o", str(elf)]
        save(out / "compile-command.json", command)
        with (out / "compile.log").open("x") as log:
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
        save(out / "spike-command.json", command)
        with (out / "spike.stdout").open("x") as stdout, (out / "spike.trace").open("x") as stderr:
            subprocess.run(command, stdout=stdout, stderr=stderr, timeout=120, check=True)
        writes = {a: v for c in parse_spike_commits(out / "spike.trace") for a, v in c.memory_accesses if v is not None}
        required = {symbols["tohost"]: 1, symbols["g75_result"]: 2758,
                    symbols["g75_result"] + 4: 0, symbols["num_failed"]: 0}
        if any(writes.get(a) != v for a, v in required.items()) or any(
                writes.get(symbols["g75_trap"] + i, 0) for i in (0, 8, 16)):
            raise ValueError("Spike exact signature/trap failure")
        check(pins)
        for path in out.rglob("*"):
            if path.is_file():
                pins[str(path)] = sha(path)
        save(out / "preflight-manifest.json", dict(status="GAP96_SPIKE_PREFLIGHT_PASS_NOT_VCS",
             case=NAME, eew=32, vl=64, checks=2758, symbols=symbols,
             expected_vector_instructions=42, expected_vector_bytes=10752,
             pins=pins, measured_raw_increment=None, coverage_admitted=False, rtl_changed=False))
        print(json.dumps(dict(output=str(out), seal=sha(out / "preflight-manifest.json"),
                             elf_sha=sha(elf), checks=2758, target_unhit_count=96)))
    except Exception as error:
        save(out / "failure.json", dict(status="PREFLIGHT_FAILED", reason=str(error), pins=pins))
        raise


if __name__ == "__main__":
    main()

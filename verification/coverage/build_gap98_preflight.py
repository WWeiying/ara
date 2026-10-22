"""Raw706-bound FP16 pack compile/Spike preflight; no VCS or admission."""
import argparse
from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import struct
import subprocess

from build_gap95_preflight import ROOT, OUT, LLVM, SPIKE, sha, save, check
from run_gap75_operand_batch import parse_spike_commits
from ara_verify.random_rvv import _elf_symbol
from inventory_operand_debug import Design
from closure_point_inventory import points
from run_gap95_simulation import merge_pins

NAME = "vgap98_div16_pack"
APP = ROOT / "apps/riscv-tests/isa/rv64uv" / (NAME + ".c")
INF = ROOT / "verification/tests/gap98_inf_flags.c"
BASE = OUT / "gap97-offline-admitted-706-20261006-01"
CORE = ROOT / "hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl"


def require(value, message):
    if not value:
        raise ValueError(message)


def exponent_at(batch, element):
    require(0 <= batch < 4 and 0 <= element < 128, "Invalid pattern position")
    return min(5 + batch * 8 + element // 16, 31)


def oracle(exponent, negative):
    require(5 <= exponent <= 31 and negative in (0, 1), "Invalid FP16 oracle input")
    if exponent == 31:
        return negative << 15, 0
    unit = Fraction(1, 1 << 24)
    exact = unit / (Fraction(2) ** (exponent - 15))
    scaled = exact / unit
    lower = scaled.numerator // scaled.denominator
    remainder = scaled - lower
    rounded = lower + int(remainder > Fraction(1, 2) or
                          (remainder == Fraction(1, 2) and lower & 1))
    return (negative << 15) | rounded, 3 if rounded * unit != exact else 0


def table_targets(record, mapped):
    require(record["width"] == 143 and record["checksum"] == "839910393", "FP16 pack shape differs")
    require(0 <= int(record["bits"], 16) < 1 << 143, "Bitmap overflow")
    group = [p for p in mapped if p["line"] == "178"]
    require(len(group) == 55 and all(p["native_id"] == "7" for p in group), "Pack table differs")
    candidate = [p for p in group if 56 <= p["raw_index"] <= 82]
    require(len(candidate) == 27 and {int(p["vector"]) for p in candidate} == set(range(27)),
            "Explicit signed exponent band differs")
    require(all(int(p["vector"]) == 82 - p["raw_index"] for p in candidate), "XML diagnostic ordering differs")
    hit = lambda p: bool(int(record["bits"], 16) & (1 << (142 - p["raw_index"])))
    return dict(intended_points=[dict(point=p, hit_before=hit(p)) for p in candidate],
                missing_points=[p for p in candidate if not hit(p)],
                outside_band_points=[dict(point=p, hit_before=hit(p), decision="NOT_A_GAP98_TARGET_NOT_WAIVED")
                                     for p in group if p not in candidate])


def target_evidence():
    pins = {}
    def pin(path, expected=None):
        path = Path(path).absolute()
        actual = sha(path)
        require(expected is None or expected == actual, "Expected input drift: " + str(path))
        nonlocal pins
        pins = merge_pins(pins, {str(path): actual})
        return path
    state_path, bitmap_path = pin(BASE / "status.json"), pin(BASE / "combined-bits.json")
    state, bitmap = json.loads(state_path.read_bytes()), json.loads(bitmap_path.read_bytes())
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and state["aggregate_passed"] == 706 and
            len(bitmap["tests"]) == len(set(bitmap["tests"])) == 706, "Not latest admitted706")
    require(pin(BASE / "combined-inputs.txt").read_text().splitlines() ==
            [str(OUT / "repaired-aligned-build-20260930-01/sim/simv.vdb"), *bitmap["tests"]],
            "Exact706 input membership/order differs")
    evidence_path = pin(BASE / "evidence-pins.json")
    pins = merge_pins(pins, json.loads(evidence_path.read_bytes()))
    check(pins)
    build = OUT / "repaired-aligned-build-20260930-01"
    sources = json.loads(pin(build / "build-source-pins.json").read_bytes())
    source_names = ("ct_vfdsu_prepare.v", "ct_vfdsu_srt.v", "ct_vfdsu_round.v", "ct_vfdsu_pack.v",
                    "ct_vfdsu_double.v", "ct_vfdsu_srt_radix16_with_sqrt.v", "ct_vfdsu_srt_radix16_bound_table.v")
    for path in [*(CORE / name for name in source_names),
                 ROOT / "hardware/deps/fpnew/src/fpnew_divsqrt_th_64_multi.sv",
                 ROOT / "hardware/deps/fpnew/src/fpnew_pkg.sv", ROOT / "hardware/src/lane/vmfpu.sv"]:
        pin(path, sources[str(path)])
    design = Design(build / "sim/simv.vdb")
    for relative, expected in bitmap["design"].items():
        pin(design.db / relative, expected)
    for relative in ("auxiliary/verilog.sourceinfo.xml", "shape/branch.verilog.info.xml",
                     "shape/tgl.verilog.info.xml", "shape/tgl.verilog.shape.xml"):
        pin(design.db / relative)
    review_path = pin(OUT / "gap56-operand-independent-review-20261004-01/review.py")
    spec = importlib.util.spec_from_file_location("gap98_compiled_parameters", review_path)
    review = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(review)
    top = "ara_tb.dut.i_ara_soc.i_system.i_ara"
    parameters = review.signature(design.definition(top, "tgl"))
    require(len(parameters) == 1 and all(parameters[0].get(k) == v for k, v in
                dict(NrLanes=4, VLEN=1024, FPUSupport=56).items()), "Old configuration differs")
    rows = []
    for lane in range(4):
        scopes = [s for s in bitmap["metrics"]["branch"] if
                  s.startswith(top + ".gen_lanes[%d]." % lane) and
                  ".gen_num_lanes[2]." in s and s.endswith("x_ct_vfdsu_pack")]
        require(len(scopes) == 1, "Ambiguous/missing physical FP16 pack scope")
        scope = scopes[0]
        wrapper = scope.split(".i_fpnew_divsqrt_th_64_c910.")[0] + ".i_fpnew_divsqrt_th_64_c910"
        params = review.signature(design.definition(wrapper, "tgl"))
        require(len(params) == 1 and params[0].get("WIDTH") == 16 and params[0].get("FpFmtConfig") == 8,
                "Not exact compiled FP16-only width16 wrapper")
        require(design.source(scope)["resolved_path"] == str(CORE / "ct_vfdsu_pack.v"), "Compiled source differs")
        record = bitmap["metrics"]["branch"][scope]
        definition = design.definition(scope, "branch")
        require(definition.get("chksum") == record["checksum"], "Compiled checksum differs")
        rows.append(dict(scope=scope, wrapper=wrapper, compiled_parameters=params[0], checksum=record["checksum"],
                         width=record["width"], **table_targets(record, points("branch", definition, record["width"]))))
    evidence = dict(status="GAP98_RAW706_STATIC_TARGETS_NOT_MEASURED", baseline_tests=706,
                    baseline=str(bitmap_path), baseline_sha256=pins[str(bitmap_path)], design=bitmap["design"],
                    targets_raw_band=[56, 82], target_unhit_count=sum(len(r["missing_points"]) for r in rows),
                    predicted_selector_signed_values=list(range(-25, 2)),
                    selector_prediction_not_measured=True,
                    infinity_operand_exponent31_special_path_not_finite_divisor=True,
                    exclusions_generated=False, default_is_not_a_target=True, rows=rows)
    return evidence, pins


def validate_spike(commits, symbols, pure_inf=False):
    divisions = [c for c in commits if c.instruction == 0x82821857]
    require(len(divisions) == (2 if pure_inf else 8), "Wrong division population")
    written = [c for c in commits if c.vector_writes]
    require(len(written) == (6 if pure_inf else 24), "Wrong vector destination population")
    require(all(set(c.vector_writes) in ({4, 5}, {8, 9}, {16, 17}) and c.vector_sew == 16 and
                c.vector_lmul == "m2" and c.vector_vl == 128 for c in written), "Wrong vector group/configuration")
    expected_flags, flags, index = [], 0, 0
    for commit in commits:
        if commit.instruction == 0x82821857:
            require(flags == 0, "fflags were not independently cleared")
            negative, batch = (index, 0) if pure_inf else divmod(index, 4)
            words, want_flags = [], 0
            for element in range(128):
                value, element_flags = oracle(31 if pure_inf else exponent_at(batch, element), negative)
                words.append(value)
                want_flags |= element_flags
            expected = {16 + register: sum(words[register * 64 + i] << (16 * i) for i in range(64))
                        for register in range(2)}
            require(commit.vector_writes == expected, "Independent exact FP16 division oracle failed")
            require(commit.csr_writes.get(1, flags) == want_flags, "Independent flags oracle failed")
            expected_flags.append(want_flags)
            index += 1
        if 1 in commit.csr_writes:
            flags = commit.csr_writes[1]
        if 3 in commit.csr_writes:
            flags = commit.csr_writes[3] & 31
        require(commit.pc != symbols["trap_fail"], "Spike entered trap handler")
    writes = {address: value for c in commits for address, value in c.memory_accesses if value is not None}
    count = 774 if pure_inf else 3112
    required = {symbols["tohost"]: 1, symbols["g75_result"]: count,
                symbols["g75_result"] + 4: 0, symbols["num_failed"]: 0,
                **{symbols["g75_trap"] + i: 0 for i in (0, 8, 16)}}
    require(all(writes.get(a) == v for a, v in required.items()), "Spike exact signature/trap failure")
    tohost = [v for c in commits for a, v in c.memory_accesses if a == symbols["tohost"] and v is not None]
    require(tohost == [1], "Wrong terminal tohost sequence")
    return dict(checks=count, exact_divisions=len(divisions), destination_instructions=len(written),
                destination_bytes=len(written) * 256, exact_division_flags=expected_flags,
                pure_infinity_probe=pure_inf, coverage_admitted=False)


def compile_spike(directory, source, pure_inf):
    directory.mkdir()
    startup, linker = ROOT / "verification/tests/gap75_start.S", ROOT / "verification/tests/gap75.ld"
    elf = directory / "input.elf"
    command = [str(LLVM / "clang"), "--target=riscv64-unknown-elf", "-march=rv64gcv_zfh_zvfh",
               "-mabi=lp64d", "-mcmodel=medany", "-mno-relax", "-msmall-data-limit=0", "-O2",
               "-fno-vectorize", "-fno-slp-vectorize", "-ffreestanding", "-DG75_NO_PRINT",
               "-D__SPIKE__", "-DVLEN=1024", "-DNR_LANES=4",
               "-I" + str(ROOT / "apps/riscv-tests/isa/macros/vector"),
               "-I" + str(ROOT / "apps/riscv-tests/env"), "-I" + str(ROOT / "apps/common"),
               "-fuse-ld=lld", "-nostdlib", "-T" + str(linker), str(startup), str(source), "-o", str(elf)]
    save(directory / "compile-command.json", command)
    with (directory / "compile.log").open("x") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
    data = elf.read_bytes()
    require(struct.unpack_from("<Q", data, 24)[0] == 0x80000000, "Wrong ELF entry")
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phsize, phnum = struct.unpack_from("<HH", data, 54)
    for i in range(phnum):
        segment = struct.unpack_from("<IIQQQQQQ", data, phoff + i * phsize)
        require(not (segment[0] == 1 and segment[5] and segment[4] % 128), "Bad preload alignment")
    symbols = {key: _elf_symbol(elf, LLVM / "llvm-readelf", key)
               for key in ("tohost", "g75_result", "g75_trap", "num_failed", "trap_fail")}
    with (directory / "input.objdump").open("x") as log:
        subprocess.run([str(LLVM / "llvm-objdump"), "-d", str(elf)], stdout=log,
                       stderr=subprocess.STDOUT, timeout=30, check=True)
    command = [str(SPIKE), "--isa=rv64gcv_zfh_zvfh_zvl1024b", "--priv=msu", "--pmpregions=0",
               "-l", "--log-commits", str(elf)]
    save(directory / "spike-command.json", command)
    with (directory / "spike.stdout").open("x") as stdout, (directory / "spike.trace").open("x") as trace:
        subprocess.run(command, stdout=stdout, stderr=trace, timeout=120, check=True)
    result = validate_spike(parse_spike_commits(directory / "spike.trace"), symbols, pure_inf)
    save(directory / "spike-validation.json", result)
    return dict(symbols=symbols, validation=result, input_elf=str(elf), input_spike_trace=str(directory / "spike.trace"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    out = parser.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    evidence, pins = target_evidence()
    paths = [Path(__file__).resolve(), Path(__file__).with_name("test_build_gap98_preflight.py"),
             Path(__file__).with_name("test_gap98_pack_scope.py"), APP, INF,
             ROOT / "verification/tests/gap75_start.S", ROOT / "verification/tests/gap75.ld",
             LLVM / "clang", LLVM / "llvm-readelf", LLVM / "llvm-objdump", SPIKE]
    paths += [p for p in (ROOT / "apps/riscv-tests/isa/macros").rglob("*") if p.is_file()]
    paths += [p for p in (ROOT / "verification/ara_verify").glob("*.py")]
    paths += [ROOT / "verification/coverage" / name for name in
              ("build_gap95_preflight.py", "run_gap75_operand_batch.py", "run_gap95_simulation.py",
               "inventory_operand_debug.py", "closure_point_inventory.py", "closure_scorecard.py",
               "reviewed_20261004/audit_readonly.py")]
    for path in paths:
        pins = merge_pins(pins, {str(path.resolve()): sha(path)})
    check(pins)
    out.mkdir()
    save(out / "target-before.json", evidence)
    try:
        main_case = compile_spike(out / NAME, APP, False)
        inf_case = compile_spike(out / "inf-flags-spike-only", INF, True)
        check(pins)
        for path in out.rglob("*"):
            if path.is_file():
                pins = merge_pins(pins, {str(path): sha(path)})
        save(out / "preflight-manifest.json", dict(status="GAP98_SPIKE_PREFLIGHT_PASS_NOT_VCS", case=NAME,
             baseline_tests=706, target_unhit_count=evidence["target_unhit_count"], eew=16, vl=128, checks=3112,
             expected_vector_instructions=24, expected_vector_bytes=6144, main_case=main_case,
             independent_inf_flags_probe=inf_case, pins=pins, measured_raw_increment=None,
             exclusions_generated=False, coverage_admitted=False, rtl_changed=False, new_RTL_signoff=False))
        print(json.dumps(dict(output=str(out), seal=sha(out / "preflight-manifest.json"),
                             baseline=706, target_unhit_count=evidence["target_unhit_count"], checks=3112)))
    except Exception as error:
        save(out / "failure.json", dict(status="GAP98_PREFLIGHT_FAILED", reason=str(error)))
        raise


if __name__ == "__main__":
    main()

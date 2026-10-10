"""Cached R1 successor; inherits the sealed byte-wise oracle, never launches VCS."""
import argparse
import json
from pathlib import Path
import subprocess

import build_narrow_reject_r1_preflight as original

life, require = original.life, original.require
ROOT, OUT, LLVM, SPIKE = original.ROOT, original.OUT, original.LLVM, original.SPIKE
NAME = "vnarrow_reject_r1_matrix_cached"
APP = ROOT / "apps/riscv-tests/isa/rv64uv" / (NAME + ".c")
OLD = OUT / "narrow-reject-r1-matrix-preflight-719-20261006-01"
OLD_SEAL = "28e6b5130b62e9ec720e08247475ac33496c30e184726112c72a375ec9b2b09b"
STATUS = "R1_CACHED_REJECT_MATRIX_PREFLIGHT_PASS_NOT_VCS"
validate, verify_elf = original.validate, original.verify_elf


def instruction_reduction(counts, predecessor):
    old = predecessor["reference_counts"]["matched_instructions"]
    new = counts["matched_instructions"]
    require(old == 1049731 and 0 < new < old, "No measured scalar instruction reduction")
    return dict(metric="SPIKE_COMPLETE_TOHOST_SCALAR_INSTRUCTIONS_NOT_VCS_CPU",
                old=old, new=new, fewer=old-new, reduction_percent=100*(old-new)/old,
                same_24_traps=True, same_26_full_snapshots=True, same_15489_checks=True,
                same_bytewise_independent_oracle=True, VCS_CPU_seconds_measured=None)


def verify(out, seal):
    pre = life.read_bound(out / "preflight-manifest.json", seal)
    require(pre["status"] == STATUS and pre["case"] == NAME and pre["baseline_tests"] == 719 and
            not pre["vcs_started"] and not pre["coverage_admitted"] and not pre["rtl_changed"], "Cached contract differs")
    life.check(pre["pins"])
    old = life.read_bound(OLD / "preflight-manifest.json", OLD_SEAL)
    require(pre["targets"] == old["targets"], "Frozen719 targets differ")
    symbols = {n: original.shared._elf_symbol(out / "input.elf", LLVM / "llvm-readelf", n) for n in original.SYMBOLS}
    require(symbols == pre["symbols"], "Cached ELF symbols differ")
    verify_elf((out / "input.elf").read_bytes(), symbols)
    commits = original.shared.parse_spike_commits(out / "spike.trace")
    require(validate(commits, symbols, (out / "spike.trace").read_text()) == pre["validation"], "Inherited full oracle differs")
    counts = original.strict.reference_counts(commits, symbols)
    require(counts == pre["reference_counts"] and instruction_reduction(counts, old) == pre["instruction_reduction"],
            "Actual instruction benchmark differs")
    return pre


def build(out):
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh cached output required")
    old = life.read_bound(OLD / "preflight-manifest.json", OLD_SEAL)
    life.check(old["pins"])
    paths = [APP, Path(__file__).resolve(), Path(__file__).with_name("test_narrow_reject_r1_cached_preflight.py"),
             Path(__file__).with_name("run_narrow_reject_r1_cached_simulation.py"),
             Path(__file__).with_name("test_run_narrow_reject_r1_cached_simulation.py"),
             Path('/usr/bin/cc'), Path('/usr/bin/cc').resolve()]
    pins = life.merge_pins(old["pins"], {str(OLD / "preflight-manifest.json"): OLD_SEAL})
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in paths})
    life.check(pins)
    command = life.read_bound(OLD / "compile-command.json", old["pins"][str(OLD / "compile-command.json")])
    require(command[0] == str(LLVM / "clang") and command.count(str(original.APP)) == 1 and
            command.count(str(OLD / "input.elf")) == 1, "Predecessor compile command differs")
    command = [str(APP) if x == str(original.APP) else str(out / "input.elf") if
               x == str(OLD / "input.elf") else x for x in command]
    require(not any('ZCC' in x or 'Terapines' in x for x in command), "Forbidden tool")
    out.mkdir(); life.save(out / "input-pins.json", pins)
    try:
        host = ["/usr/bin/cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                str(ROOT / "verification/tests/narrow_reject_r1_host.c"), "-o", str(out / "host-reference")]
        life.save(out / "host-command.json", host)
        with (out / "host.log").open('x') as log:
            subprocess.run(host, check=True, timeout=60, stdout=log, stderr=subprocess.STDOUT)
            subprocess.run([str(out / "host-reference")], check=True, timeout=10, stdout=log, stderr=subprocess.STDOUT)
        require((out / "host.log").read_bytes() == (OLD / "host.log").read_bytes(), "Byte-wise host oracle differs")
        life.save(out / "compile-command.json", command)
        with (out / "compile.log").open('x') as log:
            subprocess.run(command, check=True, timeout=120, stdout=log, stderr=subprocess.STDOUT)
        symbols = {n: original.shared._elf_symbol(out / "input.elf", LLVM / "llvm-readelf", n) for n in original.SYMBOLS}
        verify_elf((out / "input.elf").read_bytes(), symbols)
        h = life.digest(out / "input.elf")
        basepins = json.loads((original.review.BASE / "evidence-pins.json").read_text())
        require(h != old['pins'][str(OLD / 'input.elf')] and
                not any(p.endswith('.elf') and v == h for p, v in basepins.items()), "Duplicate predecessor/baseline ELF")
        life.save(out / 'elf-dedup.json', dict(baseline=719, baseline_elf_pins=736,
            input_elf_sha256=h, predecessor_elf_sha256=old['pins'][str(OLD / 'input.elf')], duplicate_elf=False))
        spike = [str(SPIKE), '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0', '-l', '--log-commits', str(out / 'input.elf')]
        life.save(out / 'spike-command.json', spike)
        with (out / 'spike.stdout').open('x') as stdout, (out / 'spike.trace').open('x') as trace:
            subprocess.run(spike, check=True, timeout=180, stdout=stdout, stderr=trace)
        commits = original.shared.parse_spike_commits(out / 'spike.trace')
        result = validate(commits, symbols, (out / 'spike.trace').read_text())
        counts = original.strict.reference_counts(commits, symbols)
        reduction = instruction_reduction(counts, old)
        life.save(out / 'spike-validation.json', result)
        life.save(out / 'instruction-reduction.json', reduction)
        life.save(out / 'target-before.json', old['targets'])
        life.check(pins)
        pins = life.merge_pins(pins, {str(p): life.digest(p) for p in out.iterdir() if p.is_file()})
        pre = dict(status=STATUS, case=NAME, baseline_tests=719, input_elf=str(out / 'input.elf'), pins=pins,
            symbols=symbols, validation=result, reference_counts=counts, targets=old['targets'],
            instruction_reduction=reduction, predecessor=str(OLD / 'preflight-manifest.json'), predecessor_seal=OLD_SEAL,
            coverage_admitted=False, vcs_started=False, rtl_changed=False, measured_raw_increment=None,
            ZCC_executed=False, old_image_files_checked=66, separate_from_descartes_positive_narrow_prefix=True,
            gold_source='Independent static r1_seed/r1_dump_word algorithm; never observed DUT/snapshot values',
            golden_original_words=512, full_scalar_vector_diff_entry='build_narrow_reject_r1_cached_preflight.py compare',
            dut_diff_executed=False)
        life.save(out / 'preflight-manifest.json', pre)
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'preflight-manifest.json'),
                              instruction_reduction=reduction, elf_sha256=h)))
    except Exception as error:
        life.save(out / 'failure.json', dict(status='CACHED_PREFLIGHT_FAILED_NOT_VCS', reason=str(error))); raise


def compare(out, seal, dut, result_path):
    # Keep the original complete scalar/vector gates, replacing only its preflight loader.
    old_verify = original.verify
    try:
        original.verify = verify
        original.compare(out, seal, dut, result_path)
    finally:
        original.verify = old_verify


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('build', 'verify', 'compare')); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal'); p.add_argument('--dut', type=Path); p.add_argument('--comparison', type=Path)
    a = p.parse_args(); require((a.mode != 'build') == bool(a.seal), 'Replay requires fixed seal')
    if a.mode == 'build': build(a.output.absolute())
    elif a.mode == 'verify': verify(a.output.absolute(), a.seal); print('VERIFY_PASS CACHED_R1 ordered24/full26/15489/byteoracle NO_VCS')
    else:
        require(a.dut is not None and a.comparison is not None, 'Existing traces/fresh comparison required')
        compare(a.output.absolute(), a.seal, a.dut.absolute(), a.comparison.absolute())


if __name__ == '__main__': main()

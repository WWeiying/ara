"""Prepare or explicitly run sealed GAP97; frozen lifecycle, no admission."""
import argparse
import json
from pathlib import Path

import run_gap95_simulation as lifecycle

ROOT, OUT = lifecycle.ROOT, lifecycle.OUT
PRE = OUT / "gap97-csr-large-avl-preflight-705-20261006-02"
PRE_SEAL = "e30c9ae331e7bc1c359c55c7edde8502e84018e91e9bb8149b9109ab86b200b3"
ELF_SEAL = "e0892776b7716cf14058bbbb6a582c1430fedcf27c684f068a25c2412392cf74"
TARGET_SEAL = "dfcf3f8a0a08a3dce31bdd3dd67ef5e9e959960596d0480ac4df31a3fab3a3e0"
SOURCE_SEAL = "9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43"
LIFECYCLE_SEAL = "1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8"
NAME = "vgap97_csr_large_avl"
SYMBOLS = dict(tohost=0x80001000, g75_result=0x80002824, g75_trap=0x80002800,
               num_failed=0x80002818, g97_observed=0x80002858, g97_avl=0x80002830,
               trap_fail=0x80000050, gap97_large_avl=0x80002688,
               gap97_probe0=0x8000203c, gap97_probe1=0x800020ce, gap97_probe2=0x80002160,
               gap97_probe3=0x800021ec, gap97_probe4=0x80002294, gap97_probe5=0x8000233e,
               gap97_probe6=0x800023f0, gap97_probe7=0x8000249e, gap97_probe8=0x8000254a,
               gap97_probe9=0x800025f8)


def validate_preflight(pre):
    expected = dict(status="GAP97_SPIKE_PREFLIGHT_PASS_NOT_VCS", case=NAME, baseline_tests=705,
                    target_unhit_count=6, checks=75, symbols=SYMBOLS,
                    expected_vector_data_requests=0, expected_vector_data_bytes=0,
                    expected_vsetvli=1, measured_raw_increment=None, coverage_admitted=False,
                    rtl_changed=False, new_RTL_signoff=False)
    if any(key not in pre or pre[key] != value for key, value in expected.items()):
        raise ValueError("Gap97 preflight contract differs")
    diagnostic = pre.get("spike_validation", {})
    diagnostic_expected = dict(checks=75, csr_phases=10, exact_observed_bytes=600,
                               probe_counts={**{str(i): 1 for i in range(10)}, "avl": 1})
    if any(diagnostic.get(key) != value for key, value in diagnostic_expected.items()):
        raise ValueError("Gap97 Spike validation differs")
    pins = pre.get("pins", {})
    for name, expected_hash in (("input.elf", ELF_SEAL), ("target-before.json", TARGET_SEAL),
                                ("frozen-ara_dispatcher.sv", SOURCE_SEAL)):
        if pins.get(str(PRE / name)) != expected_hash:
            raise ValueError("Unbound Gap97 input: " + name)
    for name in ("spike.trace", "spike-validation.json", "compile-command.json", "input.objdump",
                 "spike-command.json"):
        if str(PRE / name) not in pins:
            raise ValueError("Unpinned preflight artifact: " + name)


def command(output):
    return [str(lifecycle.IMAGE), "-l", "run.vcs.log", "+NO_FSDB", "+ntb_random_seed=1",
            "+PRELOAD=" + str(PRE / "input.elf"), "+TESTCASE=" + NAME,
            "+COMMIT_TOHOST=%x" % SYMBOLS["tohost"],
            "+COMMIT_TRACE=" + str(output / "commit_trace.csv"),
            "+VECTOR_TRACE=" + str(output / "vector_trace.csv"),
            "-cm", "line+cond+fsm+tgl+branch", "-cm_dir", str(output / "code.vdb"),
            "-cm_name", NAME]


def prepare(output):
    output = Path(output).absolute()
    if output.parent != OUT or output.resolve() != output or output.exists():
        raise ValueError("Fresh independent direct output required")
    helper = Path(lifecycle.__file__).resolve()
    if lifecycle.digest(helper) != LIFECYCLE_SEAL:
        raise ValueError("Frozen95 lifecycle changed")
    prefile = PRE / "preflight-manifest.json"
    pre = lifecycle.read_bound(prefile, PRE_SEAL)
    validate_preflight(pre)
    plan = lifecycle.read_bound(lifecycle.PLAN, lifecycle.PLAN_SEAL)
    if (plan.get("simv") != str(lifecycle.IMAGE) or
            plan.get("image", {}).get(str(lifecycle.IMAGE)) !=
            "2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3" or
            len(plan["image"]) != 66):
        raise ValueError("Old image identity differs")
    pins = lifecycle.merge_pins({}, pre["pins"])
    pins = lifecycle.merge_pins(pins, plan["image"])
    pins = lifecycle.merge_pins(pins, {str(prefile): PRE_SEAL, str(helper): LIFECYCLE_SEAL,
                                    str(lifecycle.PLAN): lifecycle.PLAN_SEAL})
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_run_gap97_simulation.py")):
        pins = lifecycle.merge_pins(pins, {str(path): lifecycle.digest(path)})
    lifecycle.check(pins)
    spec = {key: pre[key] for key in ("case", "checks", "symbols", "baseline_tests",
            "target_unhit_count", "expected_vector_data_requests", "expected_vector_data_bytes",
            "expected_vsetvli")}
    return output, dict(case=NAME, preflight=spec, pins=pins, command=command(output), timeout_s=600,
                        input_elf=str(PRE / "input.elf"), input_spike_trace=str(PRE / "spike.trace"),
                        target_before=str(PRE / "target-before.json"), old_image_files_checked=66,
                        coverage_admitted=False, rtl_changed=False, admission_performed=False,
                        new_RTL_signoff=False)


def prepared_path(output):
    return output.with_name(output.name + ".prepared.json")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepared-seal", help="Reviewed prepared JSON SHA256; mandatory for run")
    args = parser.parse_args(argv)
    if args.mode == "run" and args.prepared_seal is None:
        parser.error("run requires --prepared-seal")
    if args.mode == "prepare" and args.prepared_seal is not None:
        parser.error("prepare cannot take a prior seal")
    output, manifest = prepare(args.output)
    record = prepared_path(output)
    if args.mode == "prepare":
        lifecycle.save(record, manifest)
        print(json.dumps(dict(status="GAP97_RUN_PREPARED_NO_VCS", output=str(output),
                              prepared=str(record), seal=lifecycle.digest(record),
                              pins_checked=len(manifest["pins"]), old_image_files_checked=66)))
    else:
        reviewed = lifecycle.read_bound(record, args.prepared_seal)
        if reviewed != manifest:
            raise ValueError("Prepared run contract changed")
        lifecycle.run(output, manifest)


if __name__ == "__main__":
    main()

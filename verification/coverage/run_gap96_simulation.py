"""Run sealed raw704-bound GAP96 on the old image; no admission."""
import argparse
from pathlib import Path

import run_gap95_simulation as lifecycle

ROOT, OUT = lifecycle.ROOT, lifecycle.OUT
PRE = OUT / "gap96-div32-pack-preflight-704-20261006-01"
PRE_SEAL = "841ae88618b17e8dcd2cea52da9d6cc9781887d78fb2b58a4d8e17cf73212eb0"
ORIGINAL = OUT / "gap96-div32-pack-preflight-20261006-01"
ORIGINAL_SEAL = "f7f02db6bd6409f9fa7799903d2389f536415ea20a407afd260eda837df5c0b4"
LIFECYCLE_SEAL = "1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8"
ELF_SEAL = "73adea98bb42a6520bbc8aec11dad937dde76e0d4fdbe60366abe2e09b3ad500"
NAME = "vgap96_div32_pack"


def validate_preflight(pre):
    expected = dict(status="GAP96_SPIKE_PREFLIGHT_REBOUND_RAW704_NOT_VCS", case=NAME,
                    eew=32, vl=64, checks=2758, baseline_tests=704, target_unhit_count=96,
                    expected_vector_instructions=42, expected_vector_bytes=10752,
                    original_preflight=str(ORIGINAL / "preflight-manifest.json"),
                    original_preflight_seal=ORIGINAL_SEAL,
                    input_elf=str(ORIGINAL / "input.elf"), input_spike_trace=str(ORIGINAL / "spike.trace"),
                    measured_raw_increment=None, coverage_admitted=False, rtl_changed=False,
                    symbols=dict(tohost=0x80001000, g75_result=0x80002288,
                                 g75_trap=0x80002200, num_failed=0x80002280))
    if any(key not in pre or pre[key] != value for key, value in expected.items()):
        raise ValueError("Rebound preflight contract differs")
    pins = pre.get("pins", {})
    if (pins.get(str(ORIGINAL / "input.elf")) != ELF_SEAL or
            pins.get(str(ORIGINAL / "preflight-manifest.json")) != ORIGINAL_SEAL or
            str(ORIGINAL / "spike.trace") not in pins or str(PRE / "target-before.json") not in pins):
        raise ValueError("Rebound input artifacts are unpinned")


def command(output):
    return [str(lifecycle.IMAGE), "-l", "run.vcs.log", "+NO_FSDB", "+ntb_random_seed=1",
            "+PRELOAD=" + str(ORIGINAL / "input.elf"), "+TESTCASE=" + NAME, "+COMMIT_TOHOST=80001000",
            "+COMMIT_TRACE=" + str(output / "commit_trace.csv"),
            "+VECTOR_TRACE=" + str(output / "vector_trace.csv"),
            "-cm", "line+cond+fsm+tgl+branch", "-cm_dir", str(output / "code.vdb"), "-cm_name", NAME]


def prepare(output):
    output = Path(output).absolute()
    if output.parent != OUT or output.resolve() != output or output.exists():
        raise ValueError("Fresh independent direct output required")
    lifecycle_path = Path(lifecycle.__file__).resolve()
    if lifecycle.digest(lifecycle_path) != LIFECYCLE_SEAL:
        raise ValueError("Frozen95 lifecycle changed")
    prefile = PRE / "preflight-manifest.json"
    pre = lifecycle.read_bound(prefile, PRE_SEAL)
    validate_preflight(pre)
    plan = lifecycle.read_bound(lifecycle.PLAN, lifecycle.PLAN_SEAL)
    if plan.get("simv") != str(lifecycle.IMAGE) or str(lifecycle.IMAGE) not in plan.get("image", {}):
        raise ValueError("Old image identity differs")
    pins = lifecycle.merge_pins({}, pre["pins"])
    pins = lifecycle.merge_pins(pins, plan["image"])
    pins = lifecycle.merge_pins(pins, {str(prefile): PRE_SEAL, str(lifecycle_path): LIFECYCLE_SEAL,
                                    str(lifecycle.PLAN): lifecycle.PLAN_SEAL})
    for path in (Path(__file__).resolve(), ROOT / "verification/coverage/test_run_gap96_simulation.py"):
        pins = lifecycle.merge_pins(pins, {str(path): lifecycle.digest(path)})
    lifecycle.check(pins)
    spec = {key: pre[key] for key in ("case", "eew", "vl", "checks", "symbols",
            "expected_vector_instructions", "expected_vector_bytes", "baseline_tests", "target_unhit_count")}
    return output, dict(case=NAME, preflight=spec, pins=pins, command=command(output), timeout_s=600,
                        coverage_admitted=False, rtl_changed=False, admission_performed=False,
                        new_RTL_signoff=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output, manifest = prepare(parser.parse_args().output)
    lifecycle.run(output, manifest)


if __name__ == "__main__":
    main()

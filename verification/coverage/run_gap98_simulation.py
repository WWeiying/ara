"""Prepare a reviewed GAP98 old-image run; simulation requires explicit sealed run mode."""
import argparse
import json
from pathlib import Path

import run_gap95_simulation as life
import rebind_gap98_preflight_706_v2 as rebind

PRE = life.OUT / "gap98-div16-pack-preflight-706-20261006-02"
NAME = "vgap98_div16_pack"
LIFECYCLE_SEAL = "1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8"
ELF_SEAL = "8c43d7d5352ff0dfb632fae799d959630624c4baeeb320581a0a9211c24c1c09"


def validate(pre):
    expected = dict(status="GAP98_SPIKE_PREFLIGHT_PASS_NOT_VCS", case=NAME, baseline_tests=706,
                    physical_scope_count=8, target_unhit_count=125, checks=3112, eew=16, vl=128,
                    expected_vector_instructions=24, expected_vector_bytes=6144,
                    original_seal=rebind.PRE_SEAL, software_reexecuted=False,
                    coverage_admitted=False, rtl_changed=False, new_RTL_signoff=False,
                    measured_raw_increment=None, exclusions_generated=False)
    if any(k not in pre or pre[k] != v for k, v in expected.items()):
        raise ValueError("GAP98 successor contract differs")
    main = pre["main_case"]
    if (main["input_elf"] != str(rebind.PRE / NAME / "input.elf") or
            main["input_spike_trace"] != str(rebind.PRE / NAME / "spike.trace") or
            pre["pins"].get(main["input_elf"]) != ELF_SEAL or
            main["validation"] != dict(checks=3112, exact_divisions=8, destination_instructions=24,
                                      destination_bytes=6144, exact_division_flags=[0, 3, 3, 3] * 2,
                                      pure_infinity_probe=False, coverage_admitted=False)):
        raise ValueError("GAP98 software identity/oracle differs")
    if main["symbols"]["tohost"] != 0x80001000:
        raise ValueError("Unexpected terminal address")
    return main


def command(main, output):
    return [str(life.IMAGE), "-l", "run.vcs.log", "+NO_FSDB", "+ntb_random_seed=1",
            "+PRELOAD=" + main["input_elf"], "+TESTCASE=" + NAME,
            "+COMMIT_TOHOST=%x" % main["symbols"]["tohost"],
            "+COMMIT_TRACE=" + str(output / "commit_trace.csv"),
            "+VECTOR_TRACE=" + str(output / "vector_trace.csv"),
            "-cm", "line+cond+fsm+tgl+branch", "-cm_dir", str(output / "code.vdb"), "-cm_name", NAME]


def prepare(output, preflight_seal):
    output = Path(output).absolute()
    if output.parent != life.OUT or output.resolve() != output or output.exists():
        raise ValueError("Fresh direct output required")
    helper = Path(life.__file__).resolve()
    if life.digest(helper) != LIFECYCLE_SEAL:
        raise ValueError("Frozen lifecycle drift")
    prefile = PRE / "preflight-manifest.json"
    pre = life.read_bound(prefile, preflight_seal)
    main = validate(pre)
    original = life.read_bound(rebind.PRE / "preflight-manifest.json", rebind.PRE_SEAL)
    if any(pre[k] != original[k] for k in ("main_case", "independent_inf_flags_probe")):
        raise ValueError("Original software evidence changed")
    pins = life.merge_pins(pre["pins"], original["pins"])
    target = Path(pre["target_before"])
    if target != PRE / "target-before.json" or str(target) not in pins:
        raise ValueError("Unbound successor targets")
    evidence = life.read_bound(target, pins[str(target)])
    rebind.preserve_rows(json.loads((rebind.PRE / "target-before.json").read_bytes())["rows"], evidence["rows"])
    if (rebind.select_scopes([r["scope"] for r in evidence["rows"]]) != [r["scope"] for r in evidence["rows"]]
            or evidence["target_unhit_count"] != 125
            or sum(len(r["missing_points"]) for r in evidence["rows"]) != 125):
        raise ValueError("Eight-scope target inventory differs")
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    if (plan["simv"] != str(life.IMAGE) or len(plan["image"]) != 66 or
            plan["image"].get(str(life.IMAGE)) != "2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3"):
        raise ValueError("Old image differs")
    pins = life.merge_pins(pins, plan["image"])
    pins = life.merge_pins(pins, {str(prefile): preflight_seal, str(helper): LIFECYCLE_SEAL,
                                str(life.PLAN): life.PLAN_SEAL})
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_run_gap98_simulation.py")):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    return output, dict(case=NAME, preflight=pre, pins=pins, command=command(main, output), timeout_s=600,
                        input_elf=main["input_elf"], input_spike_trace=main["input_spike_trace"],
                        target_before=str(target), old_image_files_checked=66, baseline_tests=706,
                        coverage_admitted=False, rtl_changed=False, new_RTL_signoff=False,
                        admission_performed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preflight-seal", required=True)
    parser.add_argument("--prepared-seal")
    args = parser.parse_args()
    if (args.mode == "run") != bool(args.prepared_seal):
        parser.error("Only run requires --prepared-seal")
    output, manifest = prepare(args.output, args.preflight_seal)
    record = output.with_name(output.name + ".prepared.json")
    if args.mode == "prepare":
        life.save(record, manifest)
        print(json.dumps(dict(status="GAP98_RUN_PREPARED_NO_VCS", prepared=str(record),
                              seal=life.digest(record), pins_checked=len(manifest["pins"]))))
    else:
        if life.read_bound(record, args.prepared_seal) != manifest:
            raise ValueError("Reviewed run changed")
        life.run(output, manifest)


if __name__ == "__main__":
    main()

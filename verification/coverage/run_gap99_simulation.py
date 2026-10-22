"""Prepare or explicitly run scalar GAP99 using frozen old-image lifecycle."""
import argparse
import json
from pathlib import Path

import run_gap95_simulation as life

PRE = life.OUT / "gap99-csr-satp-mprv-preflight-707-20261006-01"
PRE_SEAL = "c0ae86b2cbe504036eb5db7b2fc272641e680ae9e52c213f2751e11e65819447"
ELF_SEAL = "9e87566b67583ba6fe05f6f25895afbc64ce7d2b371def68928952e4aa840594"
LIFE_SEAL = "1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8"
NAME = "vgap99_csr_satp_mprv"


def validate(pre):
    expected = dict(status="GAP99_SPIKE_PREFLIGHT_PASS_NOT_VCS", case=NAME, baseline_tests=707,
                    checks=14, exact_observed_bytes=96, target_unhit_count=2,
                    input_elf=str(PRE / "input.elf"), input_spike_trace=str(PRE / "spike.trace"),
                    target_before=str(PRE / "target-before.json"), measured_raw_increment=None,
                    coverage_admitted=False, rtl_changed=False, new_RTL_signoff=False, exclusions_generated=False)
    if any(k not in pre or pre[k] != v for k, v in expected.items()):
        raise ValueError("GAP99 preflight contract differs")
    if pre["spike_validation"] != dict(status="SPIKE_SCALAR_CSR_PREFLIGHT_PASS_NOT_DUT", checks=14,
            exact_observed_bytes=96, satp_writes=2, mprv_phases=2, vector_destination_instructions=0,
            vector_bytes=0, traps=0, measured_raw_increment=None, coverage_admitted=False):
        raise ValueError("GAP99 software oracle differs")
    if pre["pins"].get(str(PRE / "input.elf")) != ELF_SEAL or pre["symbols"]["tohost"] != 0x80001000:
        raise ValueError("ELF/terminal identity differs")
    for name in ("spike.trace", "spike-validation.json", "spike-command.json", "compile-command.json", "target-before.json"):
        if str(PRE / name) not in pre["pins"]:
            raise ValueError("Unpinned preflight evidence: " + name)


def command(output):
    return [str(life.IMAGE), "-l", "run.vcs.log", "+NO_FSDB", "+ntb_random_seed=1",
            "+PRELOAD=" + str(PRE / "input.elf"), "+TESTCASE=" + NAME, "+COMMIT_TOHOST=80001000",
            "+COMMIT_TRACE=" + str(output / "commit_trace.csv"),
            "+VECTOR_TRACE=" + str(output / "vector_trace.csv"),
            "-cm", "line+cond+fsm+tgl+branch", "-cm_dir", str(output / "code.vdb"), "-cm_name", NAME]


def prepare(output):
    output = Path(output).absolute()
    if output.parent != life.OUT or output.resolve() != output or output.exists():
        raise ValueError("Fresh direct independent output required")
    helper = Path(life.__file__).resolve()
    if life.digest(helper) != LIFE_SEAL:
        raise ValueError("Frozen lifecycle drift")
    prefile = PRE / "preflight-manifest.json"
    pre = life.read_bound(prefile, PRE_SEAL)
    validate(pre)
    targets = life.read_bound(PRE / "target-before.json", pre["pins"][str(PRE / "target-before.json")])
    if (targets["baseline_tests"] != 707 or len(targets["targets"]) != 2 or
            {r["point"]["raw_index"] for r in targets["targets"]} != {155, 334} or
            any(r["metric"] != "cond" or r["hit"] for r in targets["targets"])):
        raise ValueError("Exact two zero targets differ")
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    if (plan["simv"] != str(life.IMAGE) or len(plan["image"]) != 66 or
            plan["image"].get(str(life.IMAGE)) != "2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3"):
        raise ValueError("Frozen old image identity differs")
    pins = life.merge_pins(pre["pins"], plan["image"])
    pins = life.merge_pins(pins, {str(prefile): PRE_SEAL, str(helper): LIFE_SEAL,
                                str(life.PLAN): life.PLAN_SEAL})
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_run_gap99_simulation.py")):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    return output, dict(case=NAME, preflight=pre, pins=pins, command=command(output), timeout_s=600,
                        input_elf=str(PRE / "input.elf"), input_spike_trace=str(PRE / "spike.trace"),
                        target_before=str(PRE / "target-before.json"), old_image_files_checked=66,
                        baseline_tests=707, expected_vector_destination_requests=0, expected_vector_bytes=0,
                        expected_cvx_requests=0, coverage_admitted=False, admission_performed=False,
                        rtl_changed=False, new_RTL_signoff=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepared-seal")
    args = parser.parse_args(argv)
    if (args.mode == "run") != bool(args.prepared_seal):
        parser.error("Only run requires --prepared-seal")
    output, manifest = prepare(args.output)
    record = output.with_name(output.name + ".prepared.json")
    if args.mode == "prepare":
        life.save(record, manifest)
        print(json.dumps(dict(status="GAP99_RUN_PREPARED_NO_VCS", prepared=str(record),
                              seal=life.digest(record), pins_checked=len(manifest["pins"]))))
    else:
        if life.read_bound(record, args.prepared_seal) != manifest:
            raise ValueError("Reviewed prepared contract differs")
        life.run(output, manifest)


if __name__ == "__main__":
    main()

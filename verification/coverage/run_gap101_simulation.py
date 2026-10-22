"""Explicit one-shot GAP101 old-image lifecycle; no collector or admission."""
import argparse
import json
from pathlib import Path

import run_gap95_simulation as life

PRE = life.OUT / "gap101-illegal-segment-store-preflight-20261006-02"
PRE_SEAL = "fb201ab205a72b1790da0873237868bb7b389c9c0b9d08a589953851df652298"
ELF_SEAL = "0ee7feec51d7e25f8b17abc445a3b14eef99dace42a686e5d481335b825f3d59"
LIFE_SEAL = "1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8"
NAME = "vgap101_illegal_segment_store"
SCOPE = "ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher"


def validate(pre):
    expected = dict(status="GAP101_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS", case=NAME,
                    baseline_tests=715, checks=1075, target_unhit_count=4,
                    input_elf=str(PRE / "input.elf"), input_spike_trace=str(PRE / "spike.trace"),
                    target_before=str(PRE / "target-before.json"), measured_raw_increment=None,
                    coverage_admitted=False, rtl_changed=False, exclusions_generated=False)
    if any(pre.get(k) != v or k not in pre for k, v in expected.items()):
        raise ValueError("GAP101 preflight contract differs")
    oracle = dict(status="GAP101_SPIKE_EXACT_TWO_TRAPS_ORACLE_PASS_NOT_DUT", phases=2,
                  checks=1075, illegal_traps=2, rejected_store_writes=0, observed_vrf_bytes=8192,
                  target_guard_bytes=128, recovery_guard_bytes=128,
                  measured_raw_increment=None, coverage_admitted=False)
    if pre.get("validation") != oracle:
        raise ValueError("Exact software oracle differs")
    if pre["pins"].get(str(PRE / "input.elf")) != ELF_SEAL or pre["symbols"]["tohost"] != 0x80001000:
        raise ValueError("ELF/terminal identity differs")
    for name in ("spike.trace", "spike-validation.json", "spike-command.json", "compile-command.json",
                 "target-before.json", "host.log", "host-reference"):
        if str(PRE / name) not in pre["pins"]:
            raise ValueError("Unpinned preflight evidence: " + name)


def validate_targets(evidence):
    rows = evidence.get("targets", [])
    wanted = {("branch", 343), ("branch", 345), ("line", 1334), ("line", 1337)}
    actual = [(r["metric"], r["point"]["raw_index"]) for r in rows]
    if (evidence.get("status") != "GAP101_RAW715_TARGETS_ZERO_NOT_ADMISSION" or
            evidence.get("baseline_tests") != 715 or len(actual) != 4 or set(actual) != wanted or
            any(r["scope"] != SCOPE for r in rows)):
        raise ValueError("Exact715 targets differ")
    for row in rows:
        point = row["point"]
        if row["metric"] == "branch":
            if (row["checksum"] != "1558979345" or point["native_id"] != "25" or
                    point["vector"] != {343: "786", 345: "784"}[point["raw_index"]] or
                    point["attributes"]["chksum"] != "3771491581"):
                raise ValueError("Exact branch identity differs")
        elif (row["checksum"] != "1316526434" or
              point["line"] != {1334: "4542", 1337: "4545"}[point["raw_index"]]):
            raise ValueError("Exact line identity differs")


def command(output):
    return [str(life.IMAGE), "-l", "run.vcs.log", "+NO_FSDB", "+ntb_random_seed=1",
            "+PRELOAD=" + str(PRE / "input.elf"), "+TESTCASE=" + NAME, "+COMMIT_TOHOST=80001000",
            "+COMMIT_TRACE=" + str(output / "commit_trace.csv"),
            "+VECTOR_TRACE=" + str(output / "vector_trace.csv"),
            "-cm", "line+cond+fsm+tgl+branch", "-cm_dir", str(output / "code.vdb"), "-cm_name", NAME]


def prepare(output):
    output = Path(output).absolute()
    if output.parent != life.OUT or output.resolve() != output or output.exists():
        raise ValueError("Fresh independent output required")
    helper = Path(life.__file__).resolve()
    if life.digest(helper) != LIFE_SEAL:
        raise ValueError("Frozen lifecycle drift")
    prefile = PRE / "preflight-manifest.json"
    pre = life.read_bound(prefile, PRE_SEAL)
    validate(pre)
    evidence = life.read_bound(PRE / "target-before.json", pre["pins"][str(PRE / "target-before.json")])
    validate_targets(evidence)
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    if (plan["simv"] != str(life.IMAGE) or len(plan["image"]) != 66 or
            plan["image"].get(str(life.IMAGE)) != "2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3"):
        raise ValueError("Frozen old image differs")
    pins = life.merge_pins(pre["pins"], plan["image"])
    pins = life.merge_pins(pins, {str(prefile): PRE_SEAL, str(helper): LIFE_SEAL, str(life.PLAN): life.PLAN_SEAL})
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_run_gap101_simulation.py")):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    return output, dict(case=NAME, preflight=pre, pins=pins, command=command(output), timeout_s=600,
                        input_elf=str(PRE / "input.elf"), input_spike_trace=str(PRE / "spike.trace"),
                        target_before=str(PRE / "target-before.json"), old_image_files_checked=66,
                        baseline_tests=715, expected_checks=1075, expected_illegal_traps=2,
                        expected_initialization_vector_writes=64, expected_initialization_vector_bytes=8192,
                        expected_rejected_store_bytes=0, expected_legal_recovery_store_bytes=4,
                        dut_self_check_verified=False, coverage_admitted=False, admission_performed=False,
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
        print(json.dumps(dict(status="GAP101_RUN_PREPARED_NO_VCS", prepared=str(record),
                              seal=life.digest(record), pins_checked=len(manifest["pins"]))))
    else:
        if life.read_bound(record, args.prepared_seal) != manifest:
            raise ValueError("Reviewed prepared contract differs")
        life.run(output, manifest)


if __name__ == "__main__":
    main()

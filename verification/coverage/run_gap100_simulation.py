"""Prepare one GAP100 old-image run; software preflight is not DUT admission."""
import argparse
import json
from pathlib import Path

import run_gap95_simulation as life

PRE = life.OUT / "gap100-csr-hpm-vectored-preflight-708-20261006-04"
PRE_SEAL = "a7d725d519eec37dc6d1d42514a84f8121add0f9ed6bd147a9341697682e5cdc"
ELF_SEAL = "f98cb2b3b5a3fba31cb86ce0cfb04b48bd2173cafc426fd2195feed5a4304d56"
LIFE_SEAL = "1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8"
NAME = "vgap100_csr_hpm_vectored"
SCOPE = "ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i"
TARGETS = {"cond": {232, 443, 445, 447, 449, 451, 452, 453, 506, 515, 521, 524},
           "line": {890}, "branch": {587}}


def validate(pre):
    expected = dict(status="GAP100_SPIKE_PREFLIGHT_PASS_NOT_VCS", case=NAME, baseline_tests=708,
                    checks=225, target_unhit_count=14, scalar_comparison_qualified=False,
                    input_elf=str(PRE / "input.elf"), input_spike_trace=str(PRE / "spike.trace"),
                    target_before=str(PRE / "target-before.json"), measured_raw_increment=None,
                    coverage_admitted=False, rtl_changed=False, new_RTL_signoff=False, exclusions_generated=False)
    if any(k not in pre or pre[k] != v for k, v in expected.items()):
        raise ValueError("GAP100 preflight contract differs")
    oracle = dict(status="SPIKE_CSR_HPM_VECTORED_PREFLIGHT_PASS_NOT_DUT", phases=15, checks=225,
                  exact_observed_bytes=1800, raw_snapshot_bytes=1800, legal_hpm_reads=7,
                  denied_hpm_reads=5, expected_traps=23, irq_nop_prefix=0,
                  scalar_comparison_qualified=False, vector_destination_instructions=0,
                  measured_raw_increment=None, coverage_admitted=False,
                  trap_distribution=dict(trap_machine_ecall=5, trap_illegal_instruction=6,
                      trap_supervisor_ecall=5, trap_user_ecall=5, trap_breakpoint=1, **{"interrupt #1": 1}))
    if pre.get("spike_validation") != oracle:
        raise ValueError("GAP100 independent software oracle differs")
    if pre["pins"].get(str(PRE / "input.elf")) != ELF_SEAL or pre["symbols"]["tohost"] != 0x80001000:
        raise ValueError("ELF/terminal identity differs")
    for name in ("spike.trace", "spike-validation.json", "spike-command.json", "compile-command.json", "target-before.json"):
        if str(PRE / name) not in pre["pins"]:
            raise ValueError("Unpinned preflight evidence: " + name)


def validate_targets(evidence):
    rows = evidence.get("targets", [])
    expected = {(metric, raw) for metric, values in TARGETS.items() for raw in values}
    actual = [(r["metric"], r["point"]["raw_index"]) for r in rows]
    if (evidence.get("baseline_tests") != 708 or evidence.get("exclusions_generated") is not False or
            len(actual) != len(expected) or set(actual) != expected or
            any(r["scope"] != SCOPE or r["hit_before"] is not False for r in rows)):
        raise ValueError("Exact708 zero target inventory differs")


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
    evidence = life.read_bound(PRE / "target-before.json", pre["pins"][str(PRE / "target-before.json")])
    validate_targets(evidence)
    spike_command = life.read_bound(PRE / "spike-command.json", pre["pins"][str(PRE / "spike-command.json")])
    if (len(spike_command) != 7 or spike_command[1:] !=
            ["--isa=rv64gcv_zfh_zvfh_zvl1024b_zicntr_zihpm", "--priv=msu", "--pmpregions=0",
             "-l", "--log-commits", str(PRE / "input.elf")] or spike_command[0] not in pre["pins"]):
        raise ValueError("Counter-enabled Spike configuration differs")
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    if (plan["simv"] != str(life.IMAGE) or len(plan["image"]) != 66 or
            plan["image"].get(str(life.IMAGE)) != "2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3"):
        raise ValueError("Frozen old image identity differs")
    pins = life.merge_pins(pre["pins"], plan["image"])
    pins = life.merge_pins(pins, {str(prefile): PRE_SEAL, str(helper): LIFE_SEAL,
                                str(life.PLAN): life.PLAN_SEAL})
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_run_gap100_simulation.py")):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    return output, dict(case=NAME, preflight=pre, pins=pins, command=command(output), timeout_s=600,
                        input_elf=str(PRE / "input.elf"), input_spike_trace=str(PRE / "spike.trace"),
                        target_before=str(PRE / "target-before.json"), old_image_files_checked=66,
                        baseline_tests=708, expected_checks=225, expected_traps=23,
                        expected_vector_destination_requests=0, expected_vector_bytes=0,
                        expected_cvx_requests=0, expected_vset_instructions=0,
                        scalar_comparison_qualified=False, dut_self_check_verified=False,
                        coverage_admitted=False, admission_performed=False,
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
        print(json.dumps(dict(status="GAP100_RUN_PREPARED_NO_VCS", prepared=str(record),
                              seal=life.digest(record), pins_checked=len(manifest["pins"]))))
    else:
        if life.read_bound(record, args.prepared_seal) != manifest:
            raise ValueError("Reviewed prepared contract differs")
        life.run(output, manifest)


if __name__ == "__main__":
    main()

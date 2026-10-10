"""Explicit one-shot cross-PTE-line cache-boundary CACHE_PORT1 old-image lifecycle; no collector or admission."""
import argparse
import json
from pathlib import Path

import run_gap95_simulation as life

PRE = life.OUT / "cache-port1-sv39-preflight-715-20261006-04"
PRE_SEAL = "34bc28129d1074c53a9d3877a4798526578c7fbd536bea40494afd9d08eb8d72"
ELF_SEAL = "e045675b491894e04e290c046b4997113284430bcc8b82178de0352df278bac2"
LIFE_SEAL = "1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8"
NAME = "vcache_port1_sv39_boundary_crossline"

def validate(pre):
    expected = dict(status="CACHE_BOUNDARY_SPIKE_PREFLIGHT_PASS_NOT_DUT",
                    baseline_tests=715, expected_targets=5, coverage_admitted=False,
                    rtl_changed=False, scalar_comparison_qualified=False, replay_observed=False,
                    input_elf=str(PRE / "input.elf"), input_spike_trace=str(PRE / "spike.trace"),
                    VCS_timeout_proposal_seconds=600)
    if any(pre.get(k) != v or k not in pre for k, v in expected.items()):
        raise ValueError("Cache preflight contract differs")
    val = pre["spike_validation"]
    expected_val = dict(status="SPIKE_CACHE_BOUNDARY_ARCHITECTURE_PASS_NOT_REPLAY_WITNESS",
        checks=35, exact_output_bytes=160, trap_ledger_bytes=64, expected_S_ecalls=2,
        vector_destination_instructions=0, instruction_boundary_phases=2,
        replay_observed=False, measured_raw_increment=None, coverage_admitted=False)
    if any(val.get(k) != v or k not in val for k, v in expected_val.items()):
        raise ValueError("Exact software oracle differs")
    if pre["pins"].get(str(PRE / "input.elf")) != ELF_SEAL or pre["symbols"]["tohost"] != 0x80001000:
        raise ValueError("ELF/terminal identity differs")
    geometry = val["linked_geometry"]
    if (geometry["line_bytes"] != 32 or geometry["data_stride_bytes"] != 32 or
            geometry["distinct_data_lines"] != 8 or geometry["second_PTE_cold_at_runtime_proven"] is not False or
            len(geometry["pairs"]) != 2):
        raise ValueError("Cache geometry differs")
    for pair, slot in zip(geometry["pairs"], (3, 35)):
        addresses = [pre["symbols"]["gcb_leaf"] + i * 8 for i in (slot, slot + 1)]
        if (pair["slots"] != [slot, slot + 1] or pair["PTE_addresses"] != addresses or
                pair["Dcache_line_bases"] != [a // 32 * 32 for a in addresses] or
                addresses[0] // 32 == addresses[1] // 32 or
                pair["mapped_pages"] != [pre["symbols"][n] for n in ("gcb_page", "gcb_second")]):
            raise ValueError("Linked PTE geometry differs")
    for name in ("spike.trace", "spike-validation.json", "spike-command.json", "compile-command.json",
                 "target-before.json", "cache-configuration-proof.json"):
        if str(PRE / name) not in pre["pins"]:
            raise ValueError("Unpinned preflight evidence: " + name)


def validate_targets(evidence):
    scope = "ara_tb.dut.i_ara_soc.i_system.i_ariane.gen_cache_wt.i_cache_subsystem.i_wt_dcache.gen_rd_ports[1].genblk1.i_wt_dcache_ctrl"
    rows = evidence.get("targets", [])
    actual = [(r["metric"], r["raw_index"]) for r in rows]
    if (evidence.get("baseline_tests") != 715 or evidence.get("exclusions_generated") is not False or
            len(actual) != 5 or set(actual) != {("fsm", x) for x in (6, 7, 21, 27)} | {("branch", 36)}):
        raise ValueError("Exact715 targets differ")
    for row in rows:
        if (row["scope"] != scope or row["hit_before"] is not False or
                row["native_exclusion_identity_claimed"] is not False or
                row["width"] != (28 if row["metric"] == "fsm" else 43) or
                row["definition_checksum"] != ("3476102610" if row["metric"] == "fsm" else "3466602542")):
            raise ValueError("Target shape/zero identity differs")


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
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_run_cache_port1_sv39_simulation.py")):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    return output, dict(case=NAME, preflight=pre, pins=pins, command=command(output), timeout_s=600,
                        input_elf=str(PRE / "input.elf"), input_spike_trace=str(PRE / "spike.trace"),
                        target_before=str(PRE / "target-before.json"), old_image_files_checked=66,
                        baseline_tests=715, expected_checks=35, expected_S_ecalls=2,
                        expected_vector_destinations=0, expected_guarded_output_bytes=160,
                        expected_trap_ledger_bytes=64, replay_observed=False,
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
        print(json.dumps(dict(status="CACHE_PORT1_RUN_PREPARED_NO_VCS", prepared=str(record),
                              seal=life.digest(record), pins_checked=len(manifest["pins"]))))
    else:
        if life.read_bound(record, args.prepared_seal) != manifest:
            raise ValueError("Reviewed prepared contract differs")
        life.run(output, manifest)


if __name__ == "__main__":
    main()

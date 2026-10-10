"""Prepare a reviewed 300s old-image run; execution requires explicit run+seal."""
import argparse
import json
from pathlib import Path
import subprocess

import run_gap95_simulation as life

NAME = "vakv_column_boundary"
LIFE_SEAL = "1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8"


def validate(pre, directory):
    expected = dict(status="AKV_COLUMN_BOUNDARY_HOST_SPIKE_SOFTWARE_PREFLIGHT_NOT_VCS", case=NAME,
        baseline_tests=717, input_elf=str(directory / "input.elf"), dut_checks=8396,
        dut_expected_commands=8, dut_expected_cause=2, dut_expected_tval=0,
        source_ISA="rv64gv_zfh_zvfh", software_compile_ISA="rv64g_zfh",
        spike_ISA="rv64gcv_zfh_zvfh_zvl1024b", spike_native_custom_model_available=False,
        full_scalar_differential_qualified=False, old_image_timeout_s=300,
        coverage_admitted=False, vcs_launched=False, rtl_changed=False)
    if any(k not in pre or type(pre[k]) is not type(v) or pre[k] != v for k, v in expected.items()):
        raise ValueError("Exact AKV software/native preflight boundary differs")
    oracle = dict(status="SPIKE_AKV_SOFTWARE_REFERENCE_PASS_NOT_NATIVE_CUSTOM", checks=8398,
        full_vrf_snapshots=4, snapshot_bytes=16384, semantic_rejections=1, real_traps=0,
        custom_instructions_executed=False, measured_increment=None)
    if pre["validation"] != oracle or pre["symbols"]["tohost"] != 0x80001000 or \
            pre["dut_expected_trap_pc"] != pre["symbols"]["boundary_bad"]:
        raise ValueError("Wrong software oracle/terminal/expected exception PC")
    for name in ("input.elf", "software.elf", "host", "host.stdout", "target-before.json", "native-elf-audit.json",
                 "spike.stderr", "spike-validation.json", "native-compile-command.json", "spike-command.json"):
        if str(directory / name) not in pre["pins"]:
            raise ValueError("Missing independent preflight pin: " + name)


def command(pre, output):
    return [str(life.IMAGE), "-l", "run.vcs.log", "+NO_FSDB", "+ntb_random_seed=1", "+AKV_PERF",
        "+PRELOAD=" + pre["input_elf"], "+TESTCASE=" + NAME, "+COMMIT_TOHOST=80001000",
        "+COMMIT_TRACE=" + str(output / "commit_trace.csv"),
        "+VECTOR_TRACE=" + str(output / "vector_trace.csv"),
        "-cm", "line+cond+fsm+tgl+branch", "-cm_dir", str(output / "code.vdb"), "-cm_name", NAME]


def prepare(directory, seal, output):
    directory, output = Path(directory).absolute(), Path(output).absolute()
    if (directory.parent != life.OUT or directory.resolve() != directory or output.parent != life.OUT or
            output.resolve() != output or output.exists()):
        raise ValueError("Fresh independent direct output required")
    helper = Path(life.__file__).resolve()
    if life.digest(helper) != LIFE_SEAL:
        raise ValueError("Frozen lifecycle drift")
    prefile = directory / "preflight-manifest.json"
    pre = life.read_bound(prefile, seal)
    validate(pre, directory)
    target = life.read_bound(directory / "target-before.json", pre["pins"][str(directory / "target-before.json")])
    if (target["baseline_tests"] != 717 or target["scope"] !=
            "ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_akv_engine" or
            target["checksum"] != "131544421" or target["width"] != 166 or target["hit"] is not False or
            target["target"]["raw_index"] != 24 or target["target"]["native_vector"]["vector"] != "000110101010"):
        raise ValueError("Expected compiled raw24-zero binding differs")
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    if (plan["simv"] != str(life.IMAGE) or len(plan["image"]) != 66 or plan["image"][str(life.IMAGE)] !=
            "2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3"):
        raise ValueError("Exact old image66 identity differs")
    pins = life.merge_pins(pre["pins"], plan["image"])
    pins = life.merge_pins(pins, {str(prefile): seal, str(helper): LIFE_SEAL, str(life.PLAN): life.PLAN_SEAL})
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_run_akv_column_boundary_simulation.py")):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    return output, dict(case=NAME, preflight=pre, pins=pins, command=command(pre, output), timeout_s=300,
        input_elf=pre["input_elf"], baseline_tests=717, old_image_files_checked=66,
        expected_commands=8, expected_validation_exceptions=1, expected_custom_writes_bytes=640,
        scalar_differential_qualified=False, software_reference_not_native_Spike=True,
        admission_performed=False, coverage_admitted=False, rtl_changed=False, new_RTL_signoff=False)


def run(output, manifest):
    life.check(manifest["pins"])
    output.mkdir()
    life.save(output / "manifest.json", manifest)
    try:
        with (output / "console.log").open("x") as log:
            result = subprocess.run(manifest["command"], cwd=output, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=manifest["timeout_s"], check=True)
        life.check(manifest["pins"])
        life.save(output / "simulation-status.json", dict(status="SIMULATION_EXITED_NOT_ADMITTED",
            returncode=result.returncode, case=NAME, coverage_admitted=False))
    except Exception as error:
        drift = None
        try:
            life.check(manifest["pins"])
        except Exception as pin_error:
            drift = str(pin_error)
        life.save(output / "simulation-status.json", dict(status="SIMULATION_FAILED_NOT_ADMITTED",
            reason=str(error), post_failure_pin_error=drift, case=NAME, coverage_admitted=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run"))
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--preflight-seal", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepared-seal")
    args = parser.parse_args()
    if (args.mode == "run") != bool(args.prepared_seal):
        parser.error("Only run requires --prepared-seal")
    output, manifest = prepare(args.preflight, args.preflight_seal, args.output)
    record = output.with_name(output.name + ".prepared.json")
    if args.mode == "prepare":
        life.save(record, manifest)
        print(json.dumps(dict(status="AKV_COLUMN_RUN_PREPARED_NO_VCS", prepared=str(record),
                              seal=life.digest(record), pins_checked=len(manifest["pins"]))))
    else:
        if life.read_bound(record, args.prepared_seal) != manifest:
            raise ValueError("Reviewed prepared contract differs")
        run(output, manifest)


if __name__ == "__main__":
    main()

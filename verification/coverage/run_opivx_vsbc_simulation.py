"""Prepare/verify one sealed 600s old-image runner; run only after separate review."""
import argparse
import json
from pathlib import Path

import build_opivx_vsbc_preflight as preflight
import run_gap95_simulation as life

PRE = life.OUT / "opivx-vsbc-vd0-preflight-717-20261006-02"
SCOPE = "ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher"


def validate(pre):
    preflight.require(pre["status"] == "OPIVX_VSBC_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS" and
                      pre["case"] == preflight.NAME and pre["checks"] == 138 and
                      pre["baseline_tests"] == 717 and pre["vcs_started"] is False and
                      pre["coverage_admitted"] is False and pre["rtl_changed"] is False and
                      pre["measured_raw_increment"] is None, "Wrong preflight contract")
    expected = dict(status="OPIVX_VSBC_SPIKE_FULL_ORACLE_PASS_NOT_DUT", checks=138,
                    illegal_traps=1, trap_vstart=1, post_mret_vstart=1, illegal_vector_write_bytes=0,
                    handler_store_words=13, observed_vrf_bytes=768, guard_bytes=96,
                    recovery_vector_bytes=128, coverage_admitted=False)
    preflight.require(pre["validation"] == expected, "Wrong full oracle result")
    preflight.require(set(pre["targets"]) == {"branch", "line"}, "Unexpected targets")
    for metric, width, checksum, index in [("branch", 1215, "1558979345", 968),
                                            ("line", 1718, "1316526434", 502)]:
        t = pre["targets"][metric]
        preflight.require(t["scope"] == SCOPE and t["scope_width"] == width and
                          t["scope_checksum"] == checksum and t["baseline_hit"] is False and
                          t["point"]["raw_index"] == index, "Target identity differs")
        p = t["point"]
        if metric == "branch":
            preflight.require(p["native_id"] == "25" and p["vector"] == "161" and
                              p["attributes"]["chksum"] == "3771491581", "Branch identity differs")
        else:
            preflight.require(p["line"] == "2123" and p["attributes"]["id"] == "494" and
                              p["attributes"]["chksum"] == "2568828943", "Line identity differs")
    preflight.require(pre["input_elf"] == str(PRE / "input.elf") and
                      pre["symbols"]["tohost"] == 0x80001000, "Input/terminal identity differs")
    for name in ["input.elf", "spike.trace", "spike-validation.json", "host.log", "host-reference",
                 "compile-command.json", "spike-command.json", "target-before.json"]:
        preflight.require(str(PRE / name) in pre["pins"], "Missing preflight artifact pin")


def command(output):
    return [str(life.IMAGE), "-l", "run.vcs.log", "+NO_FSDB", "+ntb_random_seed=1",
            "+PRELOAD=" + str(PRE / "input.elf"), "+TESTCASE=" + preflight.NAME,
            "+COMMIT_TOHOST=80001000", "+COMMIT_TRACE=" + str(output / "commit_trace.csv"),
            "+VECTOR_TRACE=" + str(output / "vector_trace.csv"), "-cm", "line+cond+fsm+tgl+branch",
            "-cm_dir", str(output / "code.vdb"), "-cm_name", preflight.NAME]


def prepare(output, seal):
    output = Path(output).absolute()
    preflight.require(output.parent == life.OUT and output.resolve() == output and not output.exists(),
                      "Fresh direct simulation output required")
    pre = life.read_bound(PRE / "preflight-manifest.json", seal)
    validate(pre)
    life.check(pre["pins"])
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    preflight.require(plan["simv"] == str(life.IMAGE) and len(plan["image"]) == 66 and
                      plan["image"][str(life.IMAGE)] ==
                      "2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3",
                      "Frozen simv66 differs")
    pins = life.merge_pins(pre["pins"], plan["image"])
    pins = life.merge_pins(pins, {str(PRE / "preflight-manifest.json"): seal,
                               str(life.PLAN): life.PLAN_SEAL})
    life.check(pins)
    return output, dict(case=preflight.NAME, preflight=str(PRE / "preflight-manifest.json"),
                        preflight_seal=seal, command=command(output), output=str(output), pins=pins,
                        timeout_s=600, baseline_tests=717, targets=pre["targets"],
                        authorization_source="SEPARATE_PARENT_AGENT_REVIEW_REQUIRED_BEFORE_RUN",
                        old_image_files_checked=66, coverage_admitted=False, admission_performed=False,
                        rtl_changed=False, new_RTL_signoff=False, dut_self_check_verified=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("prepare", "verify", "run"))
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--preflight-seal", required=True)
    p.add_argument("--prepared-seal")
    a = p.parse_args()
    preflight.require((a.mode != "prepare") == bool(a.prepared_seal), "Verify/run require prepared seal")
    output, manifest = prepare(a.output, a.preflight_seal)
    record = output.with_name(output.name + ".prepared.json")
    if a.mode == "prepare":
        life.save(record, manifest)
        print(json.dumps(dict(status="RUN_PREPARED_NO_VCS", prepared=str(record),
                              seal=life.digest(record), pins_checked=len(manifest["pins"]))))
    else:
        preflight.require(life.read_bound(record, a.prepared_seal) == manifest, "Prepared runner drift")
        if a.mode == "verify":
            print("VERIFY_PASS simv66/pins/command/600s; VCS_NOT_STARTED admitted0")
        else:
            life.run(output, manifest)


if __name__ == "__main__":
    main()

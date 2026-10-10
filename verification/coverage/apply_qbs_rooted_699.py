#!/usr/bin/env python3
"""Fresh exact699 historical QBS report using the frozen qualified root hook."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import probe_qbs_root_refresh as pilot

base = pilot.base
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name("test_apply_qbs_rooted_699.py")
PILOT = base.OUT / "qbs-root-refresh-single-699-20261006-01"
PILOT_SEAL = "b016b8b7dbf83346bd3e041e0612305ee5c58b694b857afa9ff28ab6876ea954"
PILOT_RESULT_SEAL = "7f414c627b3f51a905dc926d52e9dcebd465ebd921db62b26003c4565fd0b338"


def scopes_for(config):
    scopes = ["ara_tb", "ara_tb.dut.i_ara_soc.i_system", "ara_tb.dut.i_ara_soc.i_system.i_ara"]
    scopes += sorted(config["plan"]["scopes"])
    base.require(len(scopes) == len(set(scopes)) == 5, "Wrong exact QBS root scopes")
    return scopes


def compare_saved(saved, actual):
    base.require(all(saved.get(k) == v for k, v in actual.items() if k != "files"), "Pilot independently differs")
    # The capture framework also seals config/selection outside this verifier's
    # artifact inventory. All required files match; gate_pilot hashes ALL saved files.
    base.require(all(saved.get("files", {}).get(path) == expected for path, expected in actual["files"].items()),
                 "Pilot independently differs")
    base.require(saved.get("config_sha256") == PILOT_SEAL and saved.get("tests") == 1
                 and saved.get("records") == 448 and saved.get("protected") == 3790
                 and saved.get("final_reset") is True and saved.get("aggregate_admission") is False
                 and saved.get("status") == "QBS_SINGLE_TEST_ROOT_REFRESH_DIAGNOSTIC_VERIFIED_NOT_REPORT",
                 "Unqualified root pilot")


def gate_pilot():
    base.require(base.sha(PILOT / "capture-result.json") == PILOT_RESULT_SEAL, "Pilot result seal differs")
    config = base.read_config(PILOT, PILOT_SEAL)
    base.require(config.get("root_refresh_scopes") == scopes_for(config), "Pilot root scope substitution")
    saved = json.loads((PILOT / "capture-result.json").read_bytes())
    actual = pilot.verify_artifacts(PILOT, config)
    compare_saved(saved, actual)
    pins = {**config["pins"], **saved["files"], str(PILOT / "config.json"): PILOT_SEAL,
            str(PILOT / "capture-result.json"): PILOT_RESULT_SEAL}
    for path, expected in pins.items():
        base.require(base.sha(Path(path)) == expected, "Pilot evidence drift: " + path)
    return pins


def population_gate(config):
    base.require(config["mode"] == "report" and config.get("latest_precheck_tests") == 699
                 and len(config["selected_tests"]) == len(set(config["selected_tests"])) == 699
                 and len(config["inputs"]) == len(set(config["inputs"])) == 700,
                 "Not exact frozen699 population")
    base.require(config["inputs"] == (base.BASE / "combined-inputs.txt").read_text().splitlines(),
                 "Frozen699 membership substitution")
    base.require(config["root_refresh_scopes"] == scopes_for(config), "Report root scope substitution")
    base.require(config.get("rooted_report_pilot") == dict(output=str(PILOT), config_sha256=PILOT_SEAL,
                                                         result_sha256=PILOT_RESULT_SEAL), "Pilot binding differs")


def verify_artifacts(output, config):
    # Original FAILED and frozen single-test evidence retain their own verifiers.
    if "rooted_report_pilot" not in config:
        return pilot.verify_artifacts(output, config)
    population_gate(config)
    result = pilot.original_verify(output, config)
    path = output / "rooted-metrics.csv"
    base.require(path.is_file() and not path.is_symlink(), "Missing/aliased rooted report")
    result["rooted_metrics"] = pilot.rooted_rows(path, config["root_refresh_scopes"])
    result["files"][str(path)] = base.sha(path)
    result["status"] = "QBS_ROOTED_REPORT_EXACT448_HISTORICAL699_ONLY"
    result["limitation"] = "Historical699 only; exact448 application evidence, no new RTL signoff, aggregate admission or official denominator validation"
    return result


def prepare(output, mode, qualification_result_seal, contract=None, contract_seal=None, contract_result_seal=None):
    base.require(mode == "report", "Full rooted report requires explicit report mode")
    base.require(contract is not None and Path(contract).absolute() == PILOT and contract_seal == PILOT_SEAL
                 and contract_result_seal == PILOT_RESULT_SEAL, "Explicit fixed pilot seals required")
    pins = gate_pilot()
    # Reuse all original report gates (native, zero bitmap, raw699 population,
    # actual membership and tool identity), with the corrected Depth parser.
    pilot.corrected.prepare(output, mode, qualification_result_seal, contract, contract_seal, contract_result_seal)
    config = json.loads((output / "config.json").read_bytes())
    config["root_refresh_scopes"] = scopes_for(config)
    config["rooted_report_pilot"] = dict(output=str(PILOT), config_sha256=PILOT_SEAL,
                                       result_sha256=PILOT_RESULT_SEAL)
    for path in (SCRIPT, TEST, pilot.SCRIPT, pilot.TEST, pilot.TCL):
        pins[str(path)] = base.sha(path)
    for path, expected in pins.items():
        base.require(path not in config["pins"] or config["pins"][path] == expected, "Report pin conflict")
        config["pins"][path] = expected
    # Reuse the pilot's exact scope-selection bytes, not native/XML ID inference.
    selection = output / "root-selection.tcl"
    selection.write_bytes((PILOT / "root-selection.tcl").read_bytes())
    config["pins"][str(selection)] = base.sha(selection)
    population_gate(config)
    base.write(output / "config.json", config)
    base.capture.check_inputs(config)
    seal = base.sha(output / "config.json")
    base.write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal,
                                           aggregate_admission=False, historical_tests=699))
    print("QBS_ROOTED699_FINAL_SEAL " + seal, flush=True)


base.TEST = TEST
base.TCL = pilot.TCL
base.prepare, base.verify_artifacts = prepare, verify_artifacts
if __name__ == "__main__":
    base.main()

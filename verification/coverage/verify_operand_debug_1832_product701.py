#!/usr/bin/env python3
"""Offline exact product-tree qualification; no DVE launch or native exclusion edits."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import apply_operand_debug_1832 as app

require, sha = app.require, app.sha
ROOT = "uvm_custom_install_verdi_recording"
SOURCE = Path("/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/etc/uvm-1.2/verdi/uvm_custom_install_verdi_recorder.sv")
SOURCE_SHA = "cc190ee7e762baa90030f7e71e47c90fe873b3c81f6f62c2100dab37c736286f"
ATTEMPT = app.OUT / "operand-debug-1832-application-full701-20261006-01"
SEAL = "98bf80a07a277739f80390fe8fcae8c24f755e7f70cfa7328a701562afe88c3e"


def validate_owner(source, definition, instances, hierarchy):
    require(source == dict(module=ROOT, definition_checksum="2787408814", file_id="152",
                           source_path=str(SOURCE), resolved_path=str(SOURCE), definition_lines=["42", "331"]),
            "Vendor source ownership differs")
    require(definition == dict(id="-203", name=ROOT, type="module", chksum="2787408814"),
            "Vendor module definition differs")
    require(instances == [dict(id="-2758", name=ROOT, pid="-1")], "Vendor is not the exact separate top instance")
    require(ROOT in hierarchy and not any(s.startswith(ROOT + ".") for s in hierarchy),
            "Vendor subtree exists")
    require("ara_tb" in hierarchy, "Missing product root")


def compare_product(actual, reference):
    require(set(reference) - set(actual) == {ROOT} and not (set(actual) - set(reference)),
            "Missing/extra roots or product rows")
    require(reference[ROOT]["Name"] == ROOT and reference[ROOT]["Depth"] == "0", "Vendor row is not a root")
    require(not any(s.startswith(ROOT + ".") for s in reference), "Reference vendor subtree exists")
    require(all(s == "ara_tb" or s.startswith("ara_tb.") for s in actual), "Nonproduct report member")
    require(len(actual) == 2988 and len(reference) == 2989, "Unexpected701 hierarchy size")
    require(all(row == reference[s] for s, row in actual.items()), "Product name/depth/metrics differ")


def verify():
    config = app.read_config(ATTEMPT, SEAL)
    require(config["mode"] == "full" and config["native_config"]["targets"] == {"branch": 1832} and
            config["native_config"]["protected"] == {"branch": 1176}, "Wrong exact population")
    original = json.loads((ATTEMPT / "status.json").read_bytes())
    require(original["status"] == "FAILED" and original["reason"] == "Independent raw701 report differs" and
            original["config_sha256"] == SEAL, "Original failure provenance differs")
    design_path = Path(config["native_config"]["plan"]["design_vdb"])
    design = app.debug.inventory.Design(design_path)
    definition = design.hierarchy[ROOT]
    source = design.source(ROOT)
    instances = [dict(n.attrib) for n in definition.findall("srcinst")]
    validate_owner(source, dict(definition.attrib), instances, design.hierarchy)
    require(not SOURCE.is_symlink() and SOURCE.resolve() == SOURCE and sha(SOURCE) == SOURCE_SHA,
            "Vendor installed source pin differs")
    lines = SOURCE.read_text().splitlines()
    require(lines[41].strip() == "module " + ROOT + ";" and lines[330].strip().startswith("endmodule"),
            "Vendor module source boundaries differ")
    require((ATTEMPT / "selected_tests.txt").read_text().splitlines() == config["selected_tests"] and
            len(config["selected_tests"]) == 701, "Selected population differs")
    expected = app.qualification.bind_native((app.NATIVE / "first.el").read_bytes(), config["native_config"])
    for name in ("applied.el", "after-refresh.el"):
        require(app.qualification.bind_native((ATTEMPT / name).read_bytes(), config["native_config"]) == expected,
                "Exact1832 native signatures differ")
    identities = None
    for stage, mode in (("raw", "before"), ("applied", "selected"), ("after", "selected"), ("reset", "reset"), ("final", "final")):
        identities = app.base.audit_states(ATTEMPT / ("states_" + stage + ".tsv"), config["native_config"], mode, identities)
    for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
        require((ATTEMPT / name).read_bytes() == b"", "Reset is not globally empty")
    reports = {s: app.merge_roots(ATTEMPT / ("table_" + s + ".csv"), ATTEMPT / ("roots_" + s + ".csv"), config)
               for s in ("raw", "applied", "reset")}
    require(reports["raw"] == reports["reset"], "Raw/reset hierarchy differs")
    reference = app.summaries(config["raw_reference"])
    compare_product(reports["raw"], reference)
    require(set(reports["applied"]) == set(reports["raw"]), "Applied hierarchy membership differs")
    changes = []
    for scope, row in reports["raw"].items():
        require(set(row) == set(reports["applied"][scope]), "Applied column schema differs")
        for metric, value in row.items():
            other = reports["applied"][scope][metric]
            if value != other:
                require(scope in config["report_roots"] and metric in ("Branch", "Score"), "Unexpected applied change")
                changes.append(dict(scope=scope, metric=metric, raw=value, applied=other))
    require(any(r["scope"] == "ara_tb.dut.i_ara_soc.i_system" and r["metric"] == "Branch" for r in changes),
            "No refreshed i_system Branch observation")
    log = (ATTEMPT / "DVEfiles/dve_gui.log").read_text()
    require(log.splitlines().count("OBD_DONE_RESET") == 1 and not re.search(
        r'OBD_FAILED|OBD_CLEANUP_ERROR|EK-CMD-|UCAPI-DLMA|DVCDT136|invalid command name|(?:^|\s)(Error|Fatal):', log),
        "GUI failure")
    for stage in ("raw", "applied", "after", "reset", "final"):
        require(log.splitlines().count("OBD_AUDIT %s 3008" % stage) == 1, "Incomplete native audit")
    execution = json.loads((ATTEMPT / "execution.json").read_bytes())
    live = json.loads((ATTEMPT / "live-identity.json").read_bytes())
    require(execution["returncode"] == 0 and execution["launch_count"] == 1 and live["executable_verified"] is True and
            live["launch_pid"] == execution["launch_pid"] and live["launch_starttime"] == execution["launch_starttime"] and
            live["executable"] == config["tool_identity"]["executable"], "Execution identity differs")
    paths = list(p for p in ATTEMPT.iterdir() if p.is_file()) + [ATTEMPT / "DVEfiles/dve_gui.log", SOURCE,
             Path(__file__), Path(__file__).with_name("test_verify_operand_debug_1832_product701.py")]
    paths += [design_path / "snps/coverage/db/design/verilog.design.xml",
              design_path / "snps/coverage/db/auxiliary/verilog.sourceinfo.xml"]
    pins = dict(config["pins"])
    for path in paths:
        require(not path.is_symlink(), "Aliased sidecar evidence")
        value = sha(path)
        require(str(path) not in pins or pins[str(path)] == value, "Conflicting artifact pin")
        pins[str(path)] = value
    app.check(config)
    return dict(status="FULL701_EXACT1832_ARA_TB_PRODUCT_REPORT_OFFLINE_QUALIFIED", tests=701, targets=1832,
                protected=1176, product_rows=2988, reference_rows=2989, original_failure_preserved=True,
                allowed_report_absence=dict(scope=ROOT, source=source, definition=dict(definition.attrib),
                                            instances=instances, descendants=[], native_exclusion_authorized=False),
                original_config_sha256=SEAL, final_reset=True, other_policy_imported=False, current_RTL_signoff=False,
                target_hit_counts_701=config["target_hit_counts_701"], summary_deltas=changes, pins=pins)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("qualify", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seal")
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent == app.OUT and output != ATTEMPT and not output.is_symlink(), "Unsafe sidecar output")
    if args.command == "qualify":
        require(not output.exists(), "Fresh sidecar output required")
        result = verify()
        output.mkdir()
        app.write(output / "qualification.json", result)
        print(result["status"] + " seal=" + sha(output / "qualification.json"))
    else:
        require(sha(output / "qualification.json") == args.seal, "External sidecar seal differs")
        saved = json.loads((output / "qualification.json").read_bytes())
        for path, expected in saved["pins"].items():
            require(sha(path) == expected, "Sidecar pin differs: " + path)
        require(saved == verify(), "Sidecar regeneration differs")
        print("FULL701_PRODUCT_OFFLINE_REVERIFIED")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Archive compact-completion/decoder evidence without inferring missing area."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

from summarize_sram_results import compare_cases, completed, sha, write_csv

ROOT = Path(__file__).resolve().parents[2]
REAL = ("q4_m4n32", "q4_m8n16", "q4_m7n16", "q6_m4n32", "q6_m8n16", "q6_m7n16")
MARKER = "QBS engine PASS: 33 functional cases plus four fault classes"


def area_pair(before, after):
    manifests = [json.loads((d / "manifest.json").read_text()) for d in (before, after)]
    for key in ("top", "period_ns", "setup_uncertainty_ns", "cores", "clock_gating",
                "element_width", "elaborate_only", "compact_read", "quick_reports"):
        if manifests[0][key] != manifests[1][key]:
            raise ValueError(f"local DC settings differ: {key}")
    for key in ("library_env.tcl",):
        if manifests[0]["flow_sha256"][key] != manifests[1]["flow_sha256"][key]:
            raise ValueError(f"local DC flow differs: {key}")
    # The only permitted script addition is the parameter-select define.
    # Clock, library, compile options and report commands must be identical.
    guard = ("if {[info exists env(DC_UNIQUE_INPUT_BYTES)] && $env(DC_UNIQUE_INPUT_BYTES) == 1} {\n"
             "  lappend defines QBS_UNIQUE_INPUT_BYTES\n}\n")
    scripts = [(d / "payload_dc.tcl").read_text().replace(guard, "") for d in (before, after)]
    if scripts[0] != scripts[1]:
        raise ValueError("local DC script differs beyond the unique-input parameter")
    states = [json.loads((d / "status.json").read_text()) for d in (before, after)]
    result = {"scope": "local_wrapper_not_chip", "before": str(before), "after": str(after),
              "states": states, "manifests": manifests}
    if not all(s["state"] == "PASS" for s in states):
        return result
    areas = []
    for directory in (before, after):
        completed(directory / "dc.log", "PAYLOAD_DC_COMPLETE")
        match = re.search(r"^Total cell area:\s+([\d.]+)",
                          (directory / "area.rpt").read_text(), re.MULTILINE)
        if not match:
            raise ValueError(f"missing mapped area: {directory}")
        areas.append(float(match[1]))
    result.update(before_um2=areas[0], after_um2=areas[1],
                  reduction_percent=100 * (areas[0] - areas[1]) / areas[0])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run, out = args.run.resolve(), args.output.resolve()
    old, new = run / "real_before", run / "real_after"
    logs = {}
    for name, directory in (("before", old), ("after", new)):
        status = json.loads((directory / "status.json").read_text())
        if status["state"] != "PASS" or sha(Path(status["simv"])) != status["simv_sha256"]:
            raise ValueError(f"incomplete or changed simulator: {directory}")
        logs[f"commands_{name}"] = directory / "commands.log"
    commands = compare_cases(completed(logs["commands_before"], MARKER),
                             completed(logs["commands_after"], MARKER))
    if len(commands) != 33 or any(row[-2] for row in commands):
        raise ValueError("command count/cycles differ")
    if sha(old / "commands.vectors") != sha(new / "commands.vectors"):
        raise ValueError("command inputs differ")
    inputs = {"commands": sha(new / "commands.vectors")}
    real = []
    for name in (*REAL, "q4_decode_m1n32"):
        if name == "q4_decode_m1n32":
            before, after = old / "decode.log", new / "decode.log"
            vector_paths = []
            for path in (before, after):
                match = re.search(r"\+QBS_COMMAND_VECTOR_FILE=(\S+)", path.read_text())
                if not match:
                    raise ValueError(f"missing vector provenance: {path}")
                vector_paths.append(Path(match[1]))
        else:
            before, after = old / "real" / f"{name}.log", new / "real" / f"{name}.log"
            vector_paths = [d / "real" / f"{name}.vectors" for d in (old, new)]
        if sha(vector_paths[0]) != sha(vector_paths[1]):
            raise ValueError(f"real inputs differ: {name}")
        inputs[name] = sha(vector_paths[1])
        bt = completed(before, "QBS engine PASS: 1 functional cases")
        at = completed(after, "QBS engine PASS: 1 functional cases")
        row, = compare_cases(bt, at)
        if row[-2]:
            raise ValueError(f"real cycle regression: {name}")
        for prefix in ("QBS traffic ", "QBS phase "):
            if [l for l in bt.splitlines() if l.startswith(prefix)] != [
                    l for l in at.splitlines() if l.startswith(prefix)]:
                raise ValueError(f"phase/traffic differ: {name}")
        real.append([name, *row])
        logs[f"{name}_before"], logs[f"{name}_after"] = before, after
    checks = {
        "decoder": ("after/decoder/run.log", "QBS decoder equivalence PASS cases=176768"),
        "unique": ("unique_adapter/sram/run.log", "QBS SRAM adapter PASS cases=81 strobe_masks=256"),
        "generic": ("generic_final/sram/run.log", "QBS SRAM adapter PASS cases=81 strobe_masks=256"),
        "macro": ("macro_unique/sram/run.log", "QBS SRAM adapter PASS cases=81 strobe_masks=256"),
        "synthesis_define": ("synthesis_final/engine/run.log", MARKER),
        "handoff": ("handoff/latest/console.log", "QBS/AKV handoff smoke: PASS traps=0"),
    }
    for name, (relative, marker) in checks.items():
        logs[name] = run / relative
        text = completed(logs[name], marker)
        if name in ("unique", "generic", "macro"):
            for extra in ("QBS SRAM streaming PASS cases=81 stalls=0", "QBS SRAM full-ingress clear PASS"):
                if extra not in text:
                    raise ValueError(f"missing coverage: {name}: {extra}")
    synth_compile = (run / "synthesis_final/engine/compile.log").read_text()
    if "+define+SYNTHESIS" not in synth_compile:
        raise ValueError("synthesis-mode simulation was not compiled with SYNTHESIS")
    soc = json.loads((run / "soc/status.json").read_text())
    if soc["state"] != "PASS":
        raise ValueError("ordinary RVV regression incomplete")
    for path, expected in soc["source_sha256"].items():
        if sha(ROOT / path) != expected:
            raise ValueError(f"RTL changed after regression build: {path}")
    handoff = (run / "handoff/latest/summary.txt").read_text().splitlines()
    if not all(s in handoff for s in ("status=PASS", "qbs_commands=4", "akv_commands=10")):
        raise ValueError("handoff command counts incomplete")
    area = {"adapter": area_pair(run / "dc_adapter_before", run / "dc_adapter_after"),
            "profile": area_pair(run / "dc_profile_before_snapshot", run / "dc_profile_after")}
    out.mkdir(parents=True, exist_ok=False)
    columns = ["case", "profile", "m", "n", "k_blocks", "weight_layout", "activation_layout",
               "before_cycles", "after_cycles", "delta_cycles", "delta_percent"]
    write_csv(out / "commands.csv", columns, commands)
    write_csv(out / "real.csv", ["name", *columns], real)
    evidence = {}
    for name, path in logs.items():
        dest = out / f"{name}.log"
        shutil.copy2(path, dest)
        evidence[name] = {"source": str(path), "sha256": sha(dest)}
    for name, pair in area.items():
        if "before_um2" in pair:
            for side in ("before", "after"):
                for filename in ("area.rpt", "qor.rpt", "manifest.json", "status.json"):
                    shutil.copy2(Path(pair[side]) / filename, out / f"{name}_{side}_{filename}")
    summary = {"functional_state": "PASS", "recorded": datetime.now(timezone.utc).isoformat(),
               "command_cases": 33, "fault_classes": 4, "real_slices": 7,
               "cycle_phase_traffic_parity": True, "formal_equivalence": False,
               "macro_timing_checks": False, "inputs_sha256": inputs, "evidence": evidence,
               "source_sha256": soc["source_sha256"], "local_area": area}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"verified and archived: {out}")


if __name__ == "__main__":
    main()

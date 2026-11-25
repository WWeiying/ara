"""Seal the short register-cut gate; run DC or the independent long Resident replays."""

import argparse
import json
from pathlib import Path
import re
import runpy
import shutil


def main(stage, out, component, branch):
    plan = json.loads((out / "plan.json").read_text())
    base = Path(plan["base"])
    base_plan = json.loads((base / "plan.json").read_text())
    parent = Path(base_plan["parent"])
    h = runpy.run_path(str(parent / "worker.py"))
    sha, check, save, verify = (h[k] for k in ("sha", "check", "save", "verify"))
    execute = h["_old"]["execute"]
    simv = out / "soc/simv"
    pins_file = out / "source-pins.json"
    dc_dir = out / "dc"
    flow = dc_dir / base_plan["flow"]
    proof_path = out / "dc-short-gate.json"
    gate_pins = out / "dc-short-pins.json"
    dc_status = out / "dc-status.json"

    if stage == "gate":
        verify(json.loads(pins_file.read_text()))
        check(component and branch, "component and branch evidence required")
        short_status = json.loads((out / "status.json").read_text())
        names = {n for n in plan["cases"] if not n.startswith("resident_")}
        check(names <= set(short_status["passed"]) and len(names) == 12, "short suite incomplete")
        # The original full-suite status is deliberately not changed or promoted.
        pins = {str(p): sha(p) for p in (pins_file, simv, base / "soc-pass.json")}
        for p in simv.with_suffix(".daidir").rglob("*.so"):
            pins[str(p)] = sha(p)
        logs = {}
        for name in sorted(names):
            case = plan["cases"][name]
            path = out / "runs" / name / "work/run.log"
            log = path.read_text(errors="replace")
            check(re.findall(r"(?m)^Loading ELF file (.+)$", log) == [case["elf"]], name)
            logs[name] = h["metrics"](log, case["marker"])
            pins[str(path)] = sha(path)
            check(sha(Path(case["elf"])) == case["elf_sha256"], name + " ELF drift")

        bench = "llama_qwen25_shape_decode_n32_qbs"
        baseline = json.loads((base / "soc-pass.json").read_text())["logs"]
        pairs = {}
        for name, key, budget in (("vsaxpy_asm", "task_cycles", 10), (bench, "projection_cycles", 5)):
            path = base / "runs" / name / "work/run.log"
            check(sha(path) == baseline[name], name + " baseline drift")
            log = path.read_text(errors="replace")
            a, b = h["metrics"](log)[key], logs[name][key]
            check(len(a) == len(b) == 1 and a[0] > 0 and b[0]*100 <= a[0]*(100+budget), name)
            pairs[name] = [a[0], b[0]]
            if name == bench:
                candidate = (out / "runs" / name / "work/run.log").read_text(errors="replace")
                pattern = r"(?m)^QBS_REAL_BENCH .*?\bchecksum=(0x[0-9a-f]+)"
                expect = re.findall(pattern, log)
                check(len(expect) == 1 and re.findall(pattern, candidate) == expect, "QBS checksum mismatch")

        component_result = (component / "run.log").read_text()
        check(bool(re.search(r"(?m)^QBS_BORROW_PRODUCT_REGISTER_PASS transfers=[1-9]\d*$",
                             component_result)) and "Fatal:" not in component_result, "component failed")
        branch_log = (branch / "run.log").read_text(errors="replace")
        branch_elf = branch / "guard.elf"
        check(re.findall(r"(?m)^Loading ELF file (.+)$", branch_log) == [str(branch_elf)], "branch ELF")
        h["metrics"](branch_log)
        for p in (component / "run.log", branch / "run.log", branch_elf):
            pins[str(p)] = sha(p)
        runner = out / "dc-short-worker.py"
        shutil.copy2(__file__, runner)
        pins[str(runner)] = sha(runner)
        save(proof_path, dict(state="SHORT_GATE_PASS", tests=logs, cycles=pairs,
                              scope="short tests plus branch guard and QBS cycle equivalence; no full Resident claim"))
        pins[str(proof_path)] = sha(proof_path)
        save(gate_pins, pins)
        return

    verify(json.loads(gate_pins.read_text()))
    verify(json.loads(pins_file.read_text()))
    if stage == "dc":
        check(not dc_status.exists() and not any((flow / "outputs").iterdir()), "DC already started")
        save(dc_status, dict(state="RUNNING_FULL_DC", gate=sha(proof_path)))
        try:
            log = execute(plan["dc"], dc_dir, dc_dir / "console.log", 86400)
            check("DC_FLOW_COMPLETE" in log.splitlines(), "DC did not complete")
            verify(json.loads(gate_pins.read_text()))
            verify(json.loads(pins_file.read_text()))
            save(dc_status, dict(state="SYNTHESIS_COMPLETE", gate=sha(proof_path),
                                 artifacts={ext: sha(flow / "outputs" / ("ara_soc_dc." + ext))
                                            for ext in ("ddc", "v", "sdc")}))
        except Exception as exc:
            save(dc_status, dict(state="FAILED", error=str(exc)))
            raise
    else:
        resident_out = out / "resident-long"
        resident_out.mkdir()
        ref = json.loads((parent / "plan.json").read_text())
        records = {}

        def run(name):
            case = plan["cases"][name]
            check(sha(Path(case["elf"])) == case["elf_sha256"], name)
            work = resident_out / name / "work"
            work.mkdir(parents=True)
            log = execute([str(simv), *case["argv"]], work, work / "run.log", 3600)
            check(re.findall(r"(?m)^Loading ELF file (.+)$", log) == [case["elf"]], name)
            h["oracle_proof"](ref, name, work, execute=True)
            actual = h["metrics"](log, case["marker"], True)
            baseline_log = (base / "runs" / name / "work/run.log").read_text(errors="replace")
            baseline = h["metrics"](baseline_log, case["marker"], True)
            check(actual["signatures"] == baseline["signatures"], name + " signature drift")
            return dict(candidate=actual["timers"], baseline=baseline["timers"], log=sha(work / "run.log"))

        def accept(name, row):
            records[name] = row
            save(resident_out / "status.json", dict(state="RUNNING", passed=records))

        save(resident_out / "status.json", dict(state="RUNNING", passed=records))
        try:
            h["batch"](("resident_qk", "resident_pv"), 2, run, accept)
        except Exception as exc:
            save(resident_out / "status.json", dict(state="FAIL", passed=records, error=str(exc)))
            raise
        save(resident_out / "status.json", dict(state="PASS", passed=records))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=("gate", "dc", "resident"))
    p.add_argument("out", type=Path)
    p.add_argument("--component", type=Path)
    p.add_argument("--branch", type=Path)
    a = p.parse_args()
    main(a.stage, a.out.resolve(), a.component and a.component.resolve(), a.branch and a.branch.resolve())

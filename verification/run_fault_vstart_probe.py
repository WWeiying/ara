#!/usr/bin/env python3
"""Capture trap-time vstart for two frozen failures; not a whole-case PASS."""
import argparse
import json
import re
from pathlib import Path
import subprocess

from ara_verify.artifacts import sha256, simulation_image
from run_coverage_checkpoint import check_service, save
from run_seed509_validation import compile_command, run

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "verification/out"
REFERENCE = OUT / "remaining15-image-20260927-01"
PROBE = ROOT / "verification/probes/ara_fault_vstart_probe.sv"
CASES = {1401: (0x2e238a07, 0, 0x80009c7f),
         1402: (0xeece8a07, 2, 0x800050d1)}


def read(path):
    return json.loads(path.read_text())


def execute(output):
    check_service()
    output = output.resolve()
    if output == OUT.resolve() or not output.is_relative_to(OUT.resolve()):
        raise ValueError("output must be a new verification/out subdirectory")
    output.mkdir(parents=True, exist_ok=False)
    state = {"status": "RUNNING", "phase": "compile", "scope": "diagnostic only"}
    save(output / "state.json", state)
    sources = {r["path"]: r["sha256"] for r in
               read(REFERENCE / "sim/vcs_source_manifest.json")["files"]}
    sources.update({str(PROBE): sha256(PROBE), str(Path(__file__).resolve()):
                    sha256(Path(__file__))})

    def check():
        for path, expected in sources.items():
            if sha256(Path(path)) != expected:
                raise RuntimeError("source/input drift: " + path)

    try:
        cases = {}
        for seed in CASES:
            source = (OUT / "batch-exploration-20260926-03/cases" /
                      f"load_store_slide-coverage300-seed{seed}-0166db9e7196/tests" /
                      "ara_dsa_rvv1_load_store_slide_coverage300_0")
            inputs = read(source / "inputs.json")
            elf = source / "input.elf"
            if sha256(elf) != inputs["binary"]["sha256"]:
                raise RuntimeError("archived ELF drift")
            sources[str(elf)] = inputs["binary"]["sha256"]
            sources[str(source / "rtl.command.json")] = sha256(source / "rtl.command.json")
            cases[seed] = source
        check()
        save(output / "sources.json", sources)
        command = [arg + " " + str(PROBE) if arg.startswith("verify_extra_sources=")
                   else arg for arg in compile_command(output)]
        run(command, output / "compile.log", 1800)
        check()
        sources.update(simulation_image(output / "sim/simv"))
        save(output / "frozen.json", sources)
        for seed, (insn, vstart, tval) in CASES.items():
            state.update(phase=f"seed{seed}")
            save(output / "state.json", state)
            target = output / f"seed{seed}"
            target.mkdir()
            command = read(cases[seed] / "rtl.command.json")["command"]
            command[0] = str(output / "sim/simv")
            for index, arg in enumerate(command):
                for prefix, name in (("+COMMIT_TRACE=", "commit_trace.csv"),
                                     ("+VECTOR_TRACE=", "vector_trace.csv")):
                    if arg.startswith(prefix):
                        command[index] = prefix + str(target / name)
            command.append("+ARA_FAULT_VSTART_PROBE")
            save(target / "command.json", {"command": command, "cwd": str(target)})
            check()
            with (target / "console.log").open("w") as stream:
                subprocess.run(command, cwd=target, check=True, timeout=180,
                               stdout=stream, stderr=subprocess.STDOUT)
            check()
            log = (target / "run.vcs.log").read_text(errors="replace")
            if "*** SUCCESS ***" not in log or re.search(r"(?m)^(Fatal:|Error:)", log):
                raise RuntimeError(f"seed{seed}: simulation did not complete cleanly")
            events = [dict(re.findall(r"(\w+)=([^\s]+)", line))
                      for line in log.splitlines() if line.startswith("[ARA_FAULT_VSTART]")]
            faults = [r for r in events if r.get("phase") == "RESP" and
                      int(r["current_insn"], 16) == insn and r["fire"] == "1"]
            if len(faults) != 1:
                raise RuntimeError(f"seed{seed}: expected one bound fault response")
            fault = faults[0]
            next_q = [r for r in events if r.get("phase") == "NEXT" and
                      r["event"] == fault["event"]]
            if (int(fault["cause"], 16) != 4 or int(fault["tval"], 16) != tval or
                fault["backend_valid"] != "1" or fault["backend_exception"] != "1" or
                int(fault["exception_vstart"], 16) != vstart or
                int(fault["csr_vstart_d"], 16) != vstart or len(next_q) != 1 or
                int(next_q[0]["actual_q"], 16) != vstart or next_q[0]["rst_n"] != "1"):
                raise RuntimeError(f"seed{seed}: fault vstart differs from expected evidence")
            save(target / "probe.json", {"status": "TRAP_VSTART_CONFIRMED",
                 "not_case_pass": True, "response": fault, "next": next_q[0],
                 "elf_sha256": sources[str(cases[seed] / "input.elf")]})
        state.update(status="PROBES_CAPTURED", phase="complete", not_case_pass=True)
        save(output / "state.json", state)
    except Exception as error:
        state.update(status="STOPPED", reason=f"{type(error).__name__}: {error}")
        save(output / "state.json", state)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    execute(parser.parse_args().output)

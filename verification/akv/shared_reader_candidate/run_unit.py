#!/usr/bin/env python3
"""Bounded VCS unit comparison; does not build or run an Ara SoC."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NEGATIVES = {
    "BAD_OWNER": "SHARED_READER_OWNER_CHANGED_LIVE",
    "BAD_FIRE": "SHARED_READER_BAD_COMMAND_FIRE",
    "BAD_READMIT": "SHARED_READER_OWNER_NOT_ADMITTED",
}


def hashes(paths):
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}


def write_json(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temp.replace(path)


def check_log(text, negative=None):
    if negative:
        marker = NEGATIVES[negative]
        if (text.count(marker) != 1 or "SHARED_READER_UNIT_PASS" in text or
                "UNIT_NEGATIVE_NOT_REJECTED" in text or "UNIT_TIMEOUT" in text or
                "Error:" in text or
                len(re.findall(r"^Fatal:", text, re.M)) != 1):
            raise ValueError("Expected only the targeted ownership assertion")
        return {"rejected": negative, "marker": marker}
    pattern = (r"^SHARED_READER_UNIT_PASS cases=10 faults=4 completions=7 bytes=4247 "
               r"clears=10 compared_cycles=(\d+)$")
    matches = re.findall(pattern, text, re.M)
    if (len(matches) != 1 or int(matches[0]) < 300 or
            re.search(r"Fatal:|Error:|UNIT_TIMEOUT", text) or
            text.count("SHARED_READER_UNIT_PASS") != 1):
        raise ValueError("Incomplete positive unit evidence")
    return {"cases": 10, "faults": 4, "completions": 7, "payload_bytes": 4247,
            "zero_owner_clears": 10, "compared_cycles": int(matches[0])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = {"state": "BUILDING", "pid": os.getpid(), "child_pid": None}

    def save():
        write_json(out / "status.json", state)

    def interrupted(signum, _frame):
        raise RuntimeError(f"Interrupted by signal {signum}")

    def run(command, logfile, timeout):
        with logfile.open("w") as stream:
            child = subprocess.Popen(command, cwd=out, stdout=stream,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            state["child_pid"] = child.pid
            save()
            try:
                return child.wait(timeout=timeout)
            finally:
                # Also kill surviving compiler/simulator descendants on failure.
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
                state["child_pid"] = None
                save()

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    save()
    pins = None
    try:
        vcs = shutil.which("vcs")
        if not vcs:
            raise RuntimeError("VCS not in PATH")
        # Expands the existing source graph only; never invokes a build target.
        sources = [Path(p) for p in subprocess.check_output([
            "make", "-s", "--no-print-directory", "-C", str(ROOT / "verification/qbs"),
            "--eval=print-shared-reader-sources:;@printf '%s\\n' $(RTL_SOURCES)",
            "print-shared-reader-sources"], text=True, timeout=30).splitlines()]
        includes = [ROOT / "hardware/deps/common_cells/include", ROOT / "hardware/deps/axi/include"]
        pins = hashes([*sources, ROOT / "verification/qbs/Makefile", Path(vcs), Path(vcs).resolve(),
                       *HERE.glob("*.sv"), *HERE.glob("*.svh"), *HERE.glob("*.py"),
                       HERE / "README.md", *[p for d in includes for p in d.rglob("*.svh")]])
        write_json(out / "source-pins.json", pins)
        command = [vcs, "-full64", "-sverilog", "-timescale=1ns/1ps", "+lint=TFIPC-L",
                   *["+incdir+" + str(d) for d in [*includes, HERE]], *map(str, sources),
                   str(HERE / "qbs_akv_shared_reader.sv"), str(HERE / "shared_reader_tb.sv"),
                   "-top", "shared_reader_tb", "-o", str(out / "simv")]
        write_json(out / "build-command.json", command)
        if run(command, out / "compile.log", 600):
            raise RuntimeError("VCS compilation failed; inspect compile.log")
        if hashes(map(Path, pins)) != pins:
            raise RuntimeError("Source drift after compile")
        state["state"] = "RUNNING"
        save()
        runs = {}
        for variant in [None, *NEGATIVES]:
            name = variant or "positive"
            log = out / f"{name}.log"
            code = run([str(out / "simv"), *(["+" + variant] if variant else [])], log, 120)
            # This VCS returns zero for $fatal; require its exact rejection log.
            if (variant is None and code != 0) or (variant is not None and code not in (0, 1)):
                raise RuntimeError(f"Unexpected simulator exit {code}: {name}")
            runs[name] = {"exit": code, **check_log(log.read_text(), variant)}
        if hashes(map(Path, pins)) != pins:
            raise RuntimeError("Source drift after simulation")
        write_json(out / "result.json", {
            "state": "PASS", "runs": runs,
            "scope": "Selected-client cycle comparison under finite unit stimulus; synthetic AXI/MMU, "
                     "not SoC/context residency, formal equivalence, synthesis or performance proof",
            "source_pins_sha256": hashes([out / "source-pins.json"])[str(out / "source-pins.json")],
            "artifacts": hashes([out / "simv", out / "build-command.json", out / "compile.log",
                                 *[out / f"{v}.log" for v in runs]])})
        state["state"] = "PASS"
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        if pins is not None:
            state["post_source_pins_match"] = hashes(map(Path, pins)) == pins
        raise
    finally:
        save()


if __name__ == "__main__":
    main()

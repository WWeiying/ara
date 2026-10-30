#!/usr/bin/env python3
"""Paired VCS command-level checks; no SoC speedup is inferred here."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def replay(args):
    """Recheck a coding-only refinement against every accepted on-mode log."""
    previous = json.loads((args.replay / "status.json").read_text())
    if previous["state"] != "passed" or not args.simv:
        raise ValueError("Replay requires a passed paired run and --simv")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = sorted((ROOT / "hardware/src/vlsu/qbs").glob("*.sv"))
    sources.append(ROOT / "verification/qbs/qbs_engine_tb.sv")
    hashes = {str(path.relative_to(ROOT)): digest(path) for path in sources}
    status = {"state": "running", "results": {}, "source_hashes": hashes,
              "simv_sha256": digest(args.simv)}
    try:
        for name, result in previous["results"]["on"].items():
            directory = output / name
            directory.mkdir()
            vectors = args.replay / "on" / name / "input.vectors"
            assert digest(vectors) == result["vectors_sha256"]
            (directory / "input.vectors").write_bytes(vectors.read_bytes())
            command = [str(args.simv.resolve()), "-l", "run.log",
                       "+QBS_COMMAND_VECTOR_FILE=" + str(directory / "input.vectors"),
                       "+QBS_RESPONSE_GAP=" + ("2" if name == "suite_gap2" else "0")]
            if not name.startswith("suite"):
                command.append("+QBS_FUNCTIONAL_ONLY")
            with (directory / "console.log").open("w") as stream:
                subprocess.run(command, cwd=directory, stdout=stream,
                               stderr=subprocess.STDOUT, timeout=240, check=True)
            log = (directory / "run.log").read_text()
            old = (args.replay / "on" / name / "run.log").read_text()
            assert "QBS engine PASS:" in log and not re.search(r"Fatal:|Error:", log), name
            assert [s for s in log.splitlines() if s.startswith("QBS ")] == [
                s for s in old.splitlines() if s.startswith("QBS ")], name
            status["results"][name] = "PASS: results and counters unchanged"
        for path in sources:
            assert digest(path) == hashes[str(path.relative_to(ROOT))], path
        status["state"] = "passed"
    except Exception as error:
        status["state"] = "failed"
        status["error"] = repr(error)
        raise
    finally:
        (output / "status.json").write_text(json.dumps(status, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--real-root", type=Path,
                        help="Archived timing_control_20260916/real vectors")
    parser.add_argument("--replay", type=Path, help="Recheck all on-mode cases of a passed paired run")
    parser.add_argument("--simv", type=Path, help="Rebuilt simulator for --replay")
    args = parser.parse_args()
    if args.replay:
        return replay(args)
    if not args.real_root:
        parser.error("--real-root is required without --replay")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources = sorted((ROOT / "hardware/src/vlsu/qbs").glob("*.sv"))
    sources += [ROOT / "hardware/include/qbs_pkg.sv",
                ROOT / "verification/qbs/qbs_engine_tb.sv",
                ROOT / "verification/qbs/qbs_command_vectors.c",
                ROOT / "verification/qbs/qbs_ref.c", Path(__file__).resolve()]
    hashes = {str(path.relative_to(ROOT)): digest(path) for path in sources}
    (out / "source_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")
    subprocess.run(["git", "diff", "--binary", "HEAD"], cwd=ROOT,
                   stdout=(out / "changes.patch").open("w"), check=True)
    status = {"started": time.time(), "state": "running", "results": {}}

    def save():
        tmp = out / "status.json.partial"
        tmp.write_text(json.dumps(status, indent=2) + "\n")
        tmp.replace(out / "status.json")

    def run(command, cwd, log, timeout):
        status["current"] = str(log.relative_to(out))
        save()
        with log.open("w") as stream:
            subprocess.run(command, cwd=cwd, stdout=stream,
                           stderr=subprocess.STDOUT, timeout=timeout, check=True)

    try:
        # One compile per setting, identical inputs and testbench in both.
        for mode in ("off", "on"):
            build = out / mode / "build"
            build.parent.mkdir()
            run(["make", "rtl-engine-compile", f"RTL_ENGINE_BUILD={build}",
                 "RTL_ENGINE_DEFINES=" + ("+define+QBS_NO_ACTIVATION_LOOKAHEAD"
                                          if mode == "off" else "")],
                ROOT / "verification/qbs", out / mode / "build.log", 600)
            status["results"][mode] = {}
            cases = [("suite", ROOT / "verification/qbs/qbs_command_vectors.txt", 0, False),
                     ("suite_gap2", ROOT / "verification/qbs/qbs_command_vectors.txt", 2, False)]
            for name in ("q4_m4n32", "q6_m4n32", "q4_K_decode_m1n32",
                         "q6_K_decode_m1n32", "q4_m8n16", "q6_m8n16"):
                vectors = args.real_root / name / "input.vectors"
                if not vectors.is_file():
                    raise FileNotFoundError(vectors)
                cases.append((name, vectors, 0, True))
            for name, vectors, gap, functional in cases:
                directory = out / mode / name
                directory.mkdir()
                (directory / "input.vectors").write_bytes(vectors.read_bytes())
                command = [str(build / "simv"), "-l", "run.log",
                           "+QBS_COMMAND_VECTOR_FILE=" + str(directory / "input.vectors"),
                           f"+QBS_RESPONSE_GAP={gap}"]
                if functional:
                    command.append("+QBS_FUNCTIONAL_ONLY")
                run(command, directory, directory / "console.log", 240)
                log = (directory / "run.log").read_text()
                if ("QBS engine PASS:" not in log or
                        re.search(r"Fatal:|Error:|Assertion.*fail", log)):
                    raise RuntimeError(f"Missing clean terminal PASS: {directory}")
                records = {}
                for match in re.finditer(r"QBS end-to-end case (\d+) PASS .* cycles=(\d+)", log):
                    records[match[1]] = {"cycles": int(match[2])}
                for match in re.finditer(r"QBS phase case=(\d+) (.*)", log):
                    records[match[1]]["phases"] = {k: int(v) for k, v in
                        re.findall(r"(\w+)=(\d+)", match[2])}
                for match in re.finditer(r"QBS traffic case=(\d+) (.*)", log):
                    records[match[1]]["traffic"] = {k: int(v) for k, v in
                        re.findall(r"(\w+)=(\d+)", match[2])}
                for match in re.finditer(r"QBS activation lookahead case=(\d+) (.*)", log):
                    records[match[1]]["activation"] = {k: int(v) for k, v in
                        re.findall(r"(\w+)=(\d+)", match[2])}
                status["results"][mode][name] = {
                    "pass": True, "vectors_sha256": digest(directory / "input.vectors"),
                    "records": records}
                save()
        comparisons = {}
        for name, before in status["results"]["off"].items():
            after = status["results"]["on"][name]
            assert before["vectors_sha256"] == after["vectors_sha256"]
            comparisons[name] = {}
            for index, old in before["records"].items():
                new = after["records"][index]
                comparisons[name][index] = {
                    "before": old["cycles"], "after": new["cycles"],
                    "speedup": old["cycles"] / new["cycles"]}
                if "traffic" in old:
                    for key in ("weight", "activation", "payload", "ranges", "dot"):
                        assert old["traffic"][key] == new["traffic"][key], (name, key)
        for path in sources:
            assert digest(path) == hashes[str(path.relative_to(ROOT))], path
        (out / "comparison.json").write_text(json.dumps(comparisons, indent=2) + "\n")
        status["state"] = "passed"
    except Exception as error:
        status["state"] = "failed"
        status["error"] = repr(error)
        raise
    finally:
        status["finished"] = time.time()
        save()


if __name__ == "__main__":
    main()

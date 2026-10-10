#!/usr/bin/env python3
"""Independent split/O1 candidate; never prepare, modify, or compile the old cache.

Run as a dedicated systemd user service with KillMode=control-group and a 4h
RuntimeMaxSec. Generation must pass the measured 100000-line function guard
before make -j12. This script never runs a simulation or changes a coverage gate.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time

from build_provenance import collect, sha256

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "verification/out/integrated-verilator-coverage-20260925-01/build/verilator"
MANIFEST = ROOT / "verification/out/batch-coverage-image-20260926-01/source_manifest.before.json"
LIMIT = 100000


def read(path):
    return json.loads(path.read_text())


def save(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def make_groups(text, name):
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(name + " ="))
    groups = []
    for line in lines[start + 1:]:
        value = line.strip()
        if not value.endswith("\\"):
            break
        value = value[:-1].strip()
        if value:
            groups.append(value)
    if not groups:
        raise ValueError(f"missing generated Makefile groups: {name}")
    return groups


def parse_command(record, makefile):
    records = [line[2:] for line in record.splitlines() if line.startswith("C ")]
    if len(records) != 1:
        raise ValueError("expected exactly one verFiles command record")
    tokens = shlex.split(json.loads(records[0]))
    # verFiles flattens argv quoting. Recover CFLAGS/LDFLAGS group boundaries
    # from the matching generated makefile, and require exact token agreement.
    groups = {"-CFLAGS": make_groups(makefile, "VM_USER_CFLAGS"),
              "-LDFLAGS": make_groups(makefile, "VM_USER_LDLIBS")}
    used = {key: 0 for key in groups}
    result = []
    index = 0
    while index < len(tokens):
        option = tokens[index]
        result.append(option)
        index += 1
        if option in groups:
            group = groups[option][used[option]]
            expected = shlex.split(group)
            if tokens[index:index + len(expected)] != expected:
                raise ValueError(f"verFiles and generated Makefile disagree: {option}")
            result.append(group)
            index += len(expected)
            used[option] += 1
    if any(used[key] != len(groups[key]) for key in groups):
        raise ValueError("unconsumed compiler/linker argument groups")
    return result


def candidate_args(original, old, destination, filelist):
    args = list(original)
    for option, expected, replacement in (("--Mdir", str(old), str(destination)),
                                           ("-f", str(old / "bender_script_default"), str(filelist))):
        if args.count(option) != 1 or args[args.index(option) + 1] != expected:
            raise ValueError(f"unexpected source command {option}")
        args[args.index(option) + 1] = replacement
    if any(flag in args for flag in ("--build", "--binary", "--output-split", "--output-split-cfuncs")):
        raise ValueError("unexpected build/split options in source command")
    if args.count("-O3") != 1 or args[args.index("--top-module") + 1] != "ara_tb_verilator":
        raise ValueError("unexpected Verilator optimization or top")
    replaced = 0
    for index, option in enumerate(args):
        if option == "-CFLAGS":
            flags = shlex.split(args[index + 1])
            replaced += flags.count("-O3")
            args[index + 1] = shlex.join(["-O1" if flag == "-O3" else flag for flag in flags])
    if replaced != 1:
        raise ValueError("expected exactly one C++ -O3 flag")
    args += ["--output-split", "10000", "--output-split-cfuncs", "2000"]
    return args


def check_sources(manifest):
    data = read(manifest)
    current = collect(Path(data["filelist"]), Path(data["repo_root"]), Path(data["build_dir"]))
    if current != data["files"]:
        raise RuntimeError("source hashes differ from original frozen build")
    return data


def measure(directory, output, label, execute):
    files = sorted(directory.glob("*.cpp"))
    if not files:
        raise RuntimeError("no generated C++ files")
    listing = output / f"{label}.cpp.list"
    listing.write_text("".join(str(path) + "\n" for path in files))
    tags = output / f"{label}.functions.jsonl"
    execute(["ctags", "--options=NONE", "--output-format=json", "--fields=+ne",
             "--kinds-C++=f", "--language-force=C++", "-f", str(tags), "-L", str(listing)],
            f"measure-{label}", timeout=900)
    functions = []
    spans = {str(path): [] for path in files}
    for line in tags.read_text().splitlines():
        row = json.loads(line)
        if row.get("_type") != "tag" or row.get("kind") != "function":
            continue
        if "line" not in row or "end" not in row or row["end"] < row["line"]:
            raise RuntimeError("ctags did not establish a complete function extent")
        item = {key: row[key] for key in ("name", "path", "line", "end")}
        item["lines"] = row["end"] - row["line"] + 1
        functions.append(item)
        spans[row["path"]].append((row["line"], row["end"]))
    if not functions:
        raise RuntimeError("no parsed C++ functions; refusing to infer a split success")
    file_records = []
    for path in files:
        with path.open("rb") as stream:
            lines = sum(1 for _ in stream)
        cursor, gap = 0, 0
        for start, end in sorted(spans[str(path)]):
            if end > lines:
                raise RuntimeError("function extent exceeds its source file")
            gap = max(gap, start - cursor - 1)
            cursor = max(cursor, end)
        gap = max(gap, lines - cursor)
        file_records.append({"path": str(path), "lines": lines, "bytes": path.stat().st_size,
                             "sha256": sha256(path), "max_unparsed_gap_lines": gap})
    ordered = sorted(functions, key=lambda item: item["lines"], reverse=True)
    report = {"function_count": len(functions), "cpp_count": len(files),
              "max_function_lines": ordered[0]["lines"], "largest_functions": ordered[:20],
              "over_limit_functions": [row for row in ordered if row["lines"] > LIMIT],
              "max_unparsed_gap_lines": max(row["max_unparsed_gap_lines"] for row in file_records),
              "files": file_records, "tags_sha256": sha256(tags), "limit_lines": LIMIT}
    save(output / f"{label}.size.json", report)
    return report


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    obj = output / "obj"
    obj.mkdir()
    log = (output / "build.log").open("w", buffering=1)
    started = time.monotonic()
    stamp = lambda: datetime.now(timezone.utc).isoformat()
    state = {"status": "BUILDING", "phase": "freeze", "started_at": stamp(), "commands": [],
             "service": os.environ.get("BUILD_SERVICE"), "original_cache": str(CACHE),
             "original_manifest": str(MANIFEST), "simulations_started": False, "make_started": False,
             "coverage": {"line": True, "expression": True, "toggle": False, "fsm": False, "assertion": False},
             "jobs": 12, "cxx_optimization": "-O1", "verilator_optimization": "-O3",
             "split": 10000, "split_cfuncs": 2000, "wall_limit_s": 14400}
    def publish():
        save(output / "status.json", state)
    def execute(command, phase, timeout):
        entry = {"argv": command, "cwd": str(ROOT / "hardware"), "phase": phase, "started_at": stamp()}
        state["phase"] = phase
        state["commands"].append(entry)
        publish()
        log.write(f"[{stamp()}] {phase}: {shlex.join(command)}\n")
        began = time.monotonic()
        try:
            remaining = int(14400 - (began - started))
            if remaining <= 0:
                raise RuntimeError("candidate exceeded its four-hour budget")
            process = subprocess.run(command, cwd=ROOT / "hardware", stdout=log,
                                     stderr=subprocess.STDOUT, timeout=min(timeout, remaining), check=False)
            entry["returncode"] = process.returncode
            if process.returncode:
                raise RuntimeError(f"{phase} exited {process.returncode}")
        finally:
            entry.update(finished_at=stamp(), elapsed_s=round(time.monotonic() - began, 3))
            publish()
    frozen = None
    try:
        publish()
        frozen = check_sources(MANIFEST)
        save(output / "source_manifest.before.json", frozen)
        originals = [CACHE / "Vara_tb_verilator__verFiles.dat", CACHE / "Vara_tb_verilator.mk",
                     CACHE / "bender_script_default", MANIFEST]
        pins = {str(path): sha256(path) for path in originals}
        for path in originals[:2]:
            shutil.copy2(path, output / ("original." + path.name))
        filelist = output / "bender_script_default"
        shutil.copy2(originals[2], filelist)
        shutil.copy2(Path(__file__), output / Path(__file__).name)
        original = parse_command(originals[0].read_text(), originals[1].read_text())
        args = candidate_args(original, CACHE, obj, filelist)
        tool = ROOT / "install/verilator/bin/verilator"
        state["verilator_sha256"] = sha256(tool.resolve())
        state["verilator_bin_sha256"] = sha256(tool.resolve().with_name("verilator_bin"))
        save(output / "commands.json", {"original_argv": original, "candidate_argv": [str(tool), *args],
                                       "input_hashes": pins, "copied_filelist_sha256": sha256(filelist)})
        execute([str(tool), "--version"], "version", 30)
        execute(["g++", "--version"], "compiler-version", 30)
        execute([str(tool), *args], "generation", 10800)
        check_sources(MANIFEST)
        for path, digest in pins.items():
            if sha256(Path(path)) != digest:
                raise RuntimeError("original generation inputs changed concurrently")
        new = measure(obj, output, "candidate", execute)
        old = measure(CACHE, output, "original", execute)
        comparison = {"original_max_function_lines": old["max_function_lines"],
                      "candidate_max_function_lines": new["max_function_lines"],
                      "original_function_count": old["function_count"],
                      "candidate_function_count": new["function_count"],
                      "candidate_over_100000": len(new["over_limit_functions"]),
                      "max_function_reduced": new["max_function_lines"] < old["max_function_lines"],
                      "note": "Function names may be renumbered; this is size evidence, not semantic equivalence."}
        save(output / "split_comparison.json", comparison)
        state["split_comparison"] = comparison
        if new["max_function_lines"] > LIMIT or new["max_unparsed_gap_lines"] > LIMIT:
            state.update(status="SPLIT_INSUFFICIENT", phase="generation-only-stop",
                         reason="function or unparsed region exceeds 100000 lines; make intentionally not started")
        else:
            check_sources(MANIFEST)
            flags = make_groups((obj / "Vara_tb_verilator.mk").read_text(), "VM_USER_CFLAGS")
            options = [arg for group in flags for arg in shlex.split(group)]
            if options.count("-O1") != 1 or "-O3" in options:
                raise RuntimeError("candidate generated C++ flags differ from requested O1")
            state["make_started"] = True
            execute(["make", "-C", str(obj), "-f", "Vara_tb_verilator.mk", "-j12"], "compile", 14400)
            image = output / "Vara_tb_verilator"
            shutil.copy2(obj / image.name, image)
            image.chmod(0o550)
            state.update(status="PASS", image=str(image), image_sha256=sha256(image))
    except Exception as error:
        state.update(status="FAIL", error=f"{type(error).__name__}: {error}")
        log.write(state["error"] + "\n")
    finally:
        if frozen is not None:
            try:
                after = check_sources(MANIFEST)
                save(output / "source_manifest.after.json", after)
                if after != frozen:
                    raise RuntimeError("source manifest changed")
                state["source_check"] = "PASS"
            except Exception as error:
                state.update(status="FAIL", source_check="FAIL", source_error=str(error))
        state.update(finished_at=stamp(), elapsed_s=round(time.monotonic() - started, 3))
        publish()
        log.write(f"[{stamp()}] {state['status']}; make_started={state['make_started']}\n")
        log.close()
    return 0 if state["status"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "verification/out") or output == CACHE or output.is_relative_to(CACHE):
        parser.error("candidate must use a new independent verification/out directory")
    return build(output)


if __name__ == "__main__":
    raise SystemExit(main())

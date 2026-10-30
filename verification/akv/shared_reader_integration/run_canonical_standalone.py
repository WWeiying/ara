#!/usr/bin/env python3
"""Prepare/review/run original engine suites against an explicit current source graph."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from ara_verify.vcs_source_manifest import collect
import ara_verify.vcs_source_manifest as inventory_helper
from compose_canonical_standalone import CONTRACTS, adapt_tb, compose, contract, digest

SCHEMA = "canonical_source_standalone_v1"
QBS_MARKER = "QBS engine PASS: 36 functional cases plus four fault classes"
AKV_MARKER = ("AKV engine PASS: v1 D64/D128 plus v2 D64/D96/D128 and segmented D256 "
              "row/column views, tails, counters, validation, and faults")
UART_REPEAT_PATH = "hardware/deps/cva6/corev_apu/tb/common/mock_uart.sv"
UART_REPEAT_SHA256 = "1bd632e6e7ec0f8395b30378e2c2a0a7b138a4bf4c89e95f6e4f092919c5c470"


def admitted_repeats(root, sources):
    repeats = {path: count for path, count in Counter(sources).items() if count > 1}
    admitted = {}
    for path, count in repeats.items():
        if (path != root / UART_REPEAT_PATH or count != 2 or
                digest(path) != UART_REPEAT_SHA256):
            raise ValueError("Duplicate source compilation unit: " + str(path))
        admitted[str(path)] = dict(count=count, sha256=UART_REPEAT_SHA256,
                                  reason="Exact inherited UART test model; original list retained")
    return admitted


def save(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def source_graph(root, filelist, kind, bench):
    """Accept a flat absolute Bender/manual filelist, never implicit -f/-y inputs."""
    sources, includes = [], []
    for raw in filelist.read_text().splitlines():
        token = raw.strip()
        if not token or token.startswith(("//", "#")):
            continue
        if token.startswith("+define+"):
            definitions = token[len("+define+"):].split("+")
            if any(not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*(?:=\S+)?", d) or
                   d.split("=", 1)[0] == "SYNTHESIS" for d in definitions):
                raise ValueError("Unsupported definition or disabled RTL assertions")
        elif token.startswith("+incdir+"):
            # collect() consumes one include directory per line.
            value = token[len("+incdir+"):]
            path = Path(value)
            if "+" in value or not path.is_absolute() or not path.is_dir():
                raise ValueError("Require one existing absolute include directory per line")
            includes.append(path.resolve())
        elif Path(token).is_absolute() and Path(token).suffix in (".sv", ".v"):
            path = Path(token).resolve(strict=True)
            if path == bench or any(path.is_relative_to(root / p) for p in ("hardware/tb", "verification/uvm")):
                raise ValueError("Use a production-only standalone filelist, not SoC/TB compilation units")
            sources.append(path)
        else:
            raise ValueError("Unsupported/unpinned filelist token: " + token)
    admitted_repeats(root, sources)
    engine = root / f"hardware/src/vlsu/{kind}/{kind}_engine.sv"
    required = [engine, root / "hardware/src/vlsu/qbs/qbs_read_engine.sv"]
    if any(p.resolve() not in sources for p in required):
        raise ValueError("Missing selected-root engine or original reader")
    text = engine.read_text()
    for pattern in (r"parameter\s+type\s+reader_req_t", r"parameter\s+type\s+reader_rsp_t",
                    r"output\s+reader_req_t\s+reader_req_o", r"input\s+reader_rsp_t\s+reader_rsp_i"):
        if not re.search(pattern, text):
            raise ValueError("Selected engine is not the external-reader interface")
    if re.search(r"\bqbs_read_engine\s*#", text):
        raise ValueError("Selected engine still contains a private reader")
    names = ["qbs_akv_shared_reader.sv"]
    if kind == "akv":
        names += ["akv_unified_context.sv", "akv_q_store.sv", "akv_legacy_repacker.sv", "akv_v2_context.sv"]
        if not re.search(r"\bakv_unified_context\s+i_unified_context\s*\(", text):
            raise ValueError("Selected AKV engine is not unified storage")
    for name in names:
        matches = [p for p in sources if p.name == name]
        if len(matches) != 1 or not matches[0].is_relative_to(root):
            raise ValueError("Missing/ambiguous/out-of-root production module: " + name)
    if not any((p / "shared_reader_types.svh").is_file() for p in includes):
        raise ValueError("Shared reader types not on the declared include path")
    return sources


def records(root, filelist, kind, bench, extras):
    sources = source_graph(root, filelist, kind, bench)
    # The frozen inventory helper does not understand // filelist comments.
    # Normalize comments only for its parser; pin and compile the ORIGINAL list.
    with tempfile.TemporaryDirectory(prefix="canonical-standalone-inventory-") as temporary:
        inventory_list = Path(temporary) / "sources.f"
        inventory_list.write_text("\n".join(line for line in filelist.read_text().splitlines()
                                           if not line.lstrip().startswith(("//", "#"))) + "\n")
        result = {row["path"]: row["sha256"] for row in collect(inventory_list, root, extras)}
        del result[str(inventory_list)]
    result[str(filelist)] = digest(filelist)
    # Also pin headers found through the compiler's source-local include lookup.
    for source in sources:
        for path in source.parent.iterdir():
            if path.is_file() and path.suffix.lower() in (".h", ".hpp", ".vh", ".svh"):
                result[str(path.resolve())] = digest(path)
    return result


def verify(pins):
    if not pins:
        raise ValueError("Empty source identity")
    for path, expected in pins.items():
        if digest(path) != expected:
            raise ValueError("Input identity changed: " + path)


def check_log(text, kind, code):
    if kind not in ("qbs", "akv"):
        raise ValueError("Unknown suite")
    marker = QBS_MARKER if kind == "qbs" else AKV_MARKER
    if code != 0 or text.splitlines().count(marker) != 1 or re.search(r"Fatal:|Error(?:-|:)|TIMEOUT", text):
        raise ValueError("Original suite did not complete cleanly")
    if kind == "qbs":
        cases = re.findall(r"^QBS end-to-end case (\d+) PASS\b", text, re.M)
        if list(map(int, cases)) != list(range(36)):
            raise ValueError("Missing/duplicated/out-of-order QBS functional case")
        for fault in ("validation", "MMU", "AXI", "PMA"):
            if text.splitlines().count(f"QBS {fault} atomic-fault PASS") != 1:
                raise ValueError("Missing/duplicate QBS fault evidence")
    return marker


def prepare(root, filelist, kind, bench, vectors, output):
    entry, _ = contract(kind)
    if digest(bench) != entry["tb_sha256"]:
        raise ValueError("Original TB identity mismatch")
    extras = [bench]
    if kind == "qbs":
        if vectors is None or digest(vectors) != entry["vectors_sha256"]:
            raise ValueError("Need the reviewed complete QBS vector collection")
        if vectors.read_text().splitlines()[0].split() != ["QBSCMD1", "36"]:
            raise ValueError("Wrong QBS vector count")
        extras.append(vectors)
    elif vectors is not None:
        raise ValueError("AKV suite has no external vectors")
    # Validate independently before creating anything in the output directory.
    initial = records(root, filelist, kind, bench, extras)
    vcs = shutil.which("vcs")
    if not vcs:
        raise RuntimeError("VCS unavailable; no tool invoked")
    tool = Path(vcs).resolve()
    compiler = tool.parents[1] / "linux64/bin/vcs1"
    own = [HERE / name for name in ("compose_canonical_standalone.py", "run_canonical_standalone.py",
           "test_canonical_standalone.py", "CANONICAL_STANDALONE_README.md", "compose_standalone.py")]
    own += [CONTRACTS / "manifest.json", CONTRACTS / "qbs_engine_legacy_header.svh",
            CONTRACTS / "akv_engine_legacy_header.svh", Path(inventory_helper.__file__).resolve(),
            Path(sys.executable).resolve(), Path(vcs), tool, compiler]
    own_pins = {str(p): digest(p) for p in own}
    output.mkdir(parents=True, exist_ok=False)
    wrapper, adapted = output / "composed_engine.sv", output / "original_suite.sv"
    wrapper.write_text(compose(kind))
    adapted.write_text(adapt_tb(bench.read_text(), kind))
    verify(initial)
    extras += [wrapper, adapted]
    graph = records(root, filelist, kind, bench, extras)
    inputs = {**graph, **own_pins}
    verify(inputs)
    manifest = {"schema": SCHEMA, "state": "PREPARED_NOT_EXECUTED", "kind": kind,
                "source_root": str(root), "filelist": str(filelist), "bench": str(bench),
                "vectors": str(vectors) if vectors else None, "output": str(output),
                "extra_sources": list(map(str, extras)), "graph_pins": graph, "input_pins": inputs,
                "duplicate_source_admissions": admitted_repeats(
                    root, source_graph(root, filelist, kind, bench)),
                "vcs": str(Path(vcs)), "compile_timeout_seconds": 600, "suite_timeout_seconds": 600,
                "production_promoted": False, "performance_measured": False}
    save(output / "manifest.json", manifest)
    save(output / "status.json", {"state": "PREPARED_NOT_EXECUTED"})
    return digest(output / "manifest.json")


def validate_inputs(manifest, output, reviewed):
    if digest(output / "manifest.json") != reviewed or manifest["schema"] != SCHEMA:
        raise ValueError("Reviewed manifest identity/type mismatch")
    if manifest["output"] != str(output):
        raise ValueError("Do not relocate prepared outputs")
    verify(manifest["input_pins"])
    current = records(Path(manifest["source_root"]), Path(manifest["filelist"]), manifest["kind"],
                      Path(manifest["bench"]), list(map(Path, manifest["extra_sources"])))
    if current != manifest["graph_pins"]:
        raise ValueError("Source/header inventory changed")


def run(command, output, name, state):
    save(output / (name + ".command.json"), command)
    with (output / (name + ".log")).open("w") as log:
        child = subprocess.Popen(command, cwd=output, stdout=log, stderr=log, start_new_session=True)
        state["child_pid"] = child.pid
        save(output / "status.json", state)
        try:
            code = child.wait(timeout=600)
            save(output / (name + ".exit.json"), {"exit_code": code})
            return code
        finally:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
            state["child_pid"] = None
            save(output / "status.json", state)


def execute(output, reviewed):
    manifest = json.loads((output / "manifest.json").read_text())
    if json.loads((output / "status.json").read_text())["state"] != "PREPARED_NOT_EXECUTED":
        raise ValueError("No automatic rerun of a partial or terminal attempt")
    validate_inputs(manifest, output, reviewed)
    state = {"state": "BUILDING", "pid": os.getpid(), "child_pid": None, "kind": manifest["kind"]}
    save(output / "status.json", state)
    try:
        command = [manifest["vcs"], "-full64", "-sverilog", "-timescale=1ns/1ps", "-debug_access+all",
                   "+lint=TFIPC-L", "-f", manifest["filelist"], str(output / "composed_engine.sv"),
                   str(output / "original_suite.sv"), "-top", manifest["kind"] + "_engine_tb",
                   "-o", str(output / "simv")]
        if run(command, output, "compile", state) or re.search(
                r"Error-\[|Error:|Fatal:", (output / "compile.log").read_text()):
            raise RuntimeError("VCS compilation failed")
        validate_inputs(manifest, output, reviewed)
        state["state"] = "RUNNING"
        command = [str(output / "simv"), "-no_save"]
        if manifest["kind"] == "qbs":
            command.append("+QBS_COMMAND_VECTOR_FILE=" + manifest["vectors"])
        code = run(command, output, "suite", state)
        marker = check_log((output / "suite.log").read_text(), manifest["kind"], code)
        validate_inputs(manifest, output, reviewed)
        names = ("manifest.json", "compile.command.json", "compile.exit.json", "compile.log",
                 "suite.command.json", "suite.exit.json", "suite.log", "simv",
                 "composed_engine.sv", "original_suite.sv")
        save(output / "result.json", {"state": "PASS", "schema": SCHEMA, "kind": manifest["kind"],
             "marker": marker, "manifest_sha256": reviewed, "post_pins_match": True,
             "original_assertions_and_expected_data_preserved": True,
             "production_promoted": False, "performance_measured": False,
             "evidence": {str(output / name): digest(output / name) for name in names}})
        state["state"] = "PASS"
    except BaseException as exc:
        state.update(state="TIMEOUT" if isinstance(exc, subprocess.TimeoutExpired) else "FAIL", error=repr(exc))
        save(output / "result.json", state)
        raise
    finally:
        save(output / "status.json", state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--filelist", type=Path)
    parser.add_argument("--kind", choices=("qbs", "akv"))
    parser.add_argument("--tb", type=Path)
    parser.add_argument("--vectors", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-reviewed", metavar="MANIFEST_SHA256")
    args = parser.parse_args()
    def interrupted(sig, _):
        raise InterruptedError(f"Signal {sig}")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    if args.execute_reviewed:
        if any((args.source_root, args.filelist, args.kind, args.tb, args.vectors)):
            parser.error("Execution consumes only the reviewed manifest; omit preparation arguments")
        execute(args.output.resolve(strict=True), args.execute_reviewed)
    else:
        if not all((args.source_root, args.filelist, args.kind, args.tb)):
            parser.error("Preparation requires --source-root --filelist --kind --tb")
        sha = prepare(args.source_root.resolve(strict=True), args.filelist.resolve(strict=True), args.kind,
                      args.tb.resolve(strict=True), args.vectors.resolve(strict=True) if args.vectors else None,
                      args.output.resolve())
        print("PREPARED_NOT_EXECUTED manifest_sha256=" + sha)


if __name__ == "__main__":
    main()

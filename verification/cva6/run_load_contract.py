#!/usr/bin/env python3
"""One bounded VCS load-unit contract run from selected sealed-package bytes.

This is a directed unit contract, not CPU/SoC/FPGA signoff. Only selected RTL,
headers, package metadata and the host harness are archived, never the package
tree. The separately maintained TB emits load_trace.jsonl and load_config.json.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))

DEFAULT_PACKAGE = ROOT / "verification/out/fpga-soc-candidate-20260922-04/package"
CORE = "rtl/cva6/core/"
COMMON = "rtl/common_cells/"
SOURCES = (
    COMMON + "src/cf_math_pkg.sv",
    CORE + "include/config_pkg.sv",
    CORE + "include/cv64a6_imafdcv_sv39_config_pkg.sv",
    CORE + "include/riscv_pkg.sv",
    CORE + "include/ariane_pkg.sv",
    CORE + "include/build_config_pkg.sv",
    CORE + "include/wt_cache_pkg.sv",
    COMMON + "src/lzc.sv",
    CORE + "lsu_bypass.sv",
    CORE + "load_unit.sv",
    CORE + "cache_subsystem/wt_dcache_ctrl.sv",
)
EXTRA = (CORE + "cva6.sv", COMMON + "include/common_cells/assertions.svh",
         COMMON + "include/common_cells/registers.svh")
TB = "verification/cva6/load_unit_contract_tb.sv"
CHECKER = "verification/cva6/load_checker.py"
RUNNER = "verification/cva6/run_load_contract.py"
EXECUTOR = "verification/cva6/run_contract.py"
HOST_MODULES = (
    ("ara_verify.dependency_patches", "verification/ara_verify/dependency_patches.py"),
    ("cva6.stimulus", "verification/cva6/stimulus.py"),
    ("cva6.checker", "verification/cva6/checker.py"),
    ("cva6.run_contract", EXECUTOR),
    ("cva6.load_checker", CHECKER),
)
HOST_FILES = (TB, RUNNER, "verification/patches/dependencies.json") + tuple(path for _, path in HOST_MODULES)
TYPE_NAMES = ("exception_t", "lsu_ctrl_t", "dcache_req_i_t", "dcache_req_o_t")
COMPILE_TIMEOUT = 180
RUN_TIMEOUT = 30
BUILD_ERROR = re.compile(r"(?:^|\n)\s*(?:Error\b|Fatal\b|UVM_ERROR\b|UVM_FATAL\b)|"
                         r"\bassert(?:ion)?\b[^\n]*(?:fail|error)", re.I)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(data)
    return digest(data)


def unlinked(path):
    path = Path(path).absolute()
    if ".." in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f"unsafe path (traversal or symlink): {path}")
    return path


def read_file(path):
    path = unlinked(path)
    if not path.is_file():
        raise ValueError(f"missing/non-regular file: {path}")
    return path.read_bytes()


def validate_output(path, package=DEFAULT_PACKAGE):
    path = unlinked(path)
    base = unlinked(ROOT / "verification/out")
    package = unlinked(package)
    if path == base or not path.is_relative_to(base):
        raise ValueError("output must be a new directory under verification/out in this worktree")
    if path.is_relative_to(package) or package.is_relative_to(path):
        raise ValueError("output must not overlap the input package")
    if path.exists():
        raise ValueError("output exists; refusing stale evidence or overwrite")
    if any(p.exists() and not p.is_dir() for p in path.parents):
        raise ValueError("output parent is not a directory")
    # VCS +incdir+ arguments use '+' as a separator, even within one argv item.
    if "+" in str(path) or any(c.isspace() for c in str(path)):
        raise ValueError("output path must not contain whitespace or '+'")
    return path


def extract_types(source):
    result = ["// Generated verbatim from frozen cva6.sv; Solderpad Hardware License 0.51."]
    for name in TYPE_NAMES:
        pattern = (r"(?:localparam|parameter)\s+type\s+" + name +
                   r"\s*=\s*(struct\s+packed\s*\{[^{}]*\})\s*,")
        matches = re.findall(pattern, source)
        if len(matches) != 1:
            raise ValueError(f"cannot unambiguously extract actual packed type {name}")
        result.append(f"typedef {matches[0]} {name};")
    return "\n".join(result) + "\n"


def parse_checksums(data):
    """Accept the package's SHA256SUMS format, rejecting aliases/duplicates."""
    records = {}
    for line in data.decode("utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
        if not match:
            raise ValueError("malformed package SHA256SUMS")
        sha, name = match.groups()
        path = PurePosixPath(name)
        if (path.is_absolute() or path.as_posix() != name or ".." in path.parts or
                name == "." or "\\" in name or any(c.isspace() for c in name)):
            raise ValueError(f"unsafe checksum path: {name}")
        if name in records:
            raise ValueError(f"duplicate checksum path: {name}")
        records[name] = sha
    if not records:
        raise ValueError("empty package SHA256SUMS")
    return records


def package_metadata(manifest_data, checksum_data):
    checksums = parse_checksums(checksum_data)
    if checksums.get("manifest.json") != digest(manifest_data):
        raise ValueError("package manifest checksum mismatch or missing entry")
    manifest = json.loads(manifest_data)
    if not isinstance(manifest, dict):
        raise ValueError("package manifest must be an object")
    for name in SOURCES + EXTRA:
        if name not in checksums:
            raise ValueError(f"selected package file missing from SHA256SUMS: {name}")
    return manifest, checksums


def freeze_bytes(target, data, source=None, expected=None):
    sha = digest(data)
    if expected is not None and sha != expected:
        raise ValueError(f"package source checksum mismatch: {source}")
    target = unlinked(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
    target.chmod(0o444)
    return dict(path=str(source) if source is not None else None,
                frozen=str(target), sha256=sha, size_bytes=len(data))


def freeze_inputs(package, output):
    package = unlinked(package)
    manifest_data = read_file(package / "manifest.json")
    checksum_data = read_file(package / "SHA256SUMS")
    baseline, checksums = package_metadata(manifest_data, checksum_data)
    inputs, records = output / "inputs", {}
    for name, data in (("manifest.json", manifest_data), ("SHA256SUMS", checksum_data)):
        records["package/" + name] = freeze_bytes(
            inputs / "package" / name, data, package / name)
    package_bytes = {}
    for name in SOURCES + EXTRA:
        data = read_file(package / name)
        records["package/" + name] = freeze_bytes(
            inputs / "package" / name, data, package / name, checksums[name])
        package_bytes[name] = data
    for name in HOST_FILES:
        records[name] = freeze_bytes(inputs / name, read_file(ROOT / name), ROOT / name)
    generated = "generated/load_contract_types.svh"
    records[generated] = freeze_bytes(
        inputs / generated, extract_types(package_bytes[CORE + "cva6.sv"].decode("utf-8")).encode("utf-8"))
    defines = []
    if ("ARIANE_ACCELERATOR_PORT" in baseline.get("defines", {}) or
            any(b"ARIANE_ACCELERATOR_PORT" in data for data in package_bytes.values())):
        defines.append("+define+ARIANE_ACCELERATOR_PORT=1")
    return dict(scope="actual packaged lsu_bypass/load_unit/wt_dcache_ctrl boundary contract; "
                      "modeled translation and cache storage, no real MMU/scoreboard/CPU or SoC signoff",
                package=str(package), sources=records, defines=defines,
                compile_sources=["package/" + name for name in SOURCES] + [TB],
                top="load_unit_contract_tb", compile_timeout_s=COMPILE_TIMEOUT,
                run_timeout_s=RUN_TIMEOUT,
                configuration=dict(source=CORE + "include/cv64a6_imafdcv_sv39_config_pkg.sv",
                                   expected=dict(mmu=1, ni=1, load_entries=2, xlen=64),
                                   unit_override="frozen TB enables NI with one low 256 MiB region "
                                                 "[0, 0x10000000); not the SoC NI map"),
                planned=dict(cases=15, logical_instructions=22, cache_attempts=15, completed=18, canceled=4),
                dependency_gate="selected sealed-package checksums; mutable-checkout gate/registry "
                                "archived for executor provenance only, not invoked",
                checksum_scope="selected inputs and baseline manifest only; not a whole-package audit")


def changed_inputs(records):
    errors = []
    for name, record in records.items():
        for key in ("path", "frozen"):
            if not record.get(key):
                continue
            try:
                data = read_file(record[key])
                if digest(data) != record["sha256"] or len(data) != record["size_bytes"]:
                    errors.append(f"modified input/evidence ({key}): {name}")
            except (OSError, ValueError) as error:
                errors.append(f"unavailable input/evidence ({key}): {name}: {error}")
    return errors


def load_frozen_module(name, record, dependencies):
    data = read_file(record["frozen"])
    if digest(data) != record["sha256"]:
        raise ValueError(f"modified frozen Python input: {name}")
    spec = importlib.util.spec_from_file_location(name, record["frozen"])
    module = importlib.util.module_from_spec(spec)
    replacements = {**dependencies, name: module}
    previous = {key: sys.modules.get(key) for key in replacements}
    sys.modules.update(replacements)
    try:
        # Compile these checked bytes directly, never a cached .pyc or live checker.
        exec(compile(data, record["frozen"], "exec"), module.__dict__)
    finally:
        for key, value in previous.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
    return module


def compile_command(output, vcs, manifest):
    inputs, build = output / "inputs", output / "build"
    command = [str(vcs), "-full64", "-sverilog", "-timescale=1ns/1ps", "-assert", "svaext",
               *manifest["defines"], "-top", manifest["top"], "-o", str(build / "simv"),
               "-Mdir=" + str(build / "csrc")]
    for name in ("package/" + COMMON + "include", "package/" + CORE + "include", "generated"):
        command.append("+incdir+" + str(inputs / name))
    return command + [str(inputs / name) for name in manifest["compile_sources"]]


def read_evidence(path, records, name):
    data = read_file(path)
    records[name] = dict(path=str(path), sha256=digest(data), size_bytes=len(data))
    return data


def run(output, package=DEFAULT_PACKAGE):
    package = unlinked(package)
    output = validate_output(output, package)
    output.mkdir(parents=True)
    report = dict(status="FAIL", errors=[], counts={}, package=str(package), output=str(output),
                  started_at=datetime.now(timezone.utc).isoformat(), build=None, run=None,
                  compile_count=0, run_count=0, sources={}, evidence={})
    records = {}
    try:
        manifest = freeze_inputs(package, output)
        report["sources"] = manifest["sources"]
        report["scope"] = manifest["scope"]
        records.update(manifest["sources"])
        records["manifest.json"] = freeze_bytes(
            output / "manifest.json", (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        report["manifest_sha256"] = records["manifest.json"]["sha256"]
        errors = changed_inputs(records)
        if errors:
            raise ValueError("; ".join(errors))
        # Reuse the unchanged executor from its frozen source. Its execute path
        # uses only its own stdlib imports, digest and save helpers.
        modules = {}
        for name, path in HOST_MODULES:
            modules[name] = load_frozen_module(name, records[path], modules)
        executor, checker = modules["cva6.run_contract"], modules["cva6.load_checker"]
        if not callable(getattr(checker, "analyze", None)):
            raise ValueError("frozen cva6.load_checker has no analyze function")
        vcs = shutil.which("vcs")
        if not vcs:
            raise ValueError("VCS not found")
        errors = changed_inputs(records)
        if errors:
            raise ValueError("; ".join(errors))
        report["compile_count"] = 1
        command = compile_command(output, vcs, manifest)
        report["build"] = dict(argv=command, cwd=str(output / "build"), timeout_s=COMPILE_TIMEOUT)
        compiled = executor.execute(command, output / "build", COMPILE_TIMEOUT)
        report["build"] = compiled
        console = read_evidence(output / "build/console.log", report["evidence"], "build/console.log")
        if compiled["log_sha256"] != digest(console):
            raise ValueError("modified build console before validation")
        if compiled["returncode"] != 0 or compiled.get("timeout") or BUILD_ERROR.search(console.decode("utf-8")):
            raise ValueError("VCS compilation failed; see build/console.log")
        errors = changed_inputs(records)
        if errors:
            raise ValueError("; ".join(errors))
        read_evidence(output / "build/simv", report["evidence"], "build/simv")
        for library in sorted((output / "build/simv.daidir").rglob("*.so")):
            read_evidence(library, report["evidence"], str(library.relative_to(output)))
        report["run_count"] = 1
        command = [str(output / "build/simv")]
        report["run"] = dict(argv=command, cwd=str(output / "run"), timeout_s=RUN_TIMEOUT)
        executed = executor.execute(command, output / "run", RUN_TIMEOUT)
        report["run"] = executed
        console = read_evidence(output / "run/console.log", report["evidence"], "run/console.log")
        if executed["log_sha256"] != digest(console):
            raise ValueError("modified simulation console before validation")
        trace = read_evidence(output / "run/load_trace.jsonl", report["evidence"], "run/load_trace.jsonl")
        config = read_evidence(output / "run/load_config.json", report["evidence"], "run/load_config.json")
        if not trace.strip():
            raise ValueError("empty load_trace.jsonl")
        # Hashes above describe the same bytes passed to the semantic checker.
        checked = checker.analyze(console.decode("utf-8"), trace.decode("utf-8"), config.decode("utf-8"),
                                  returncode=executed["returncode"])
        if (not isinstance(checked, dict) or checked.get("status") not in ("PASS", "FAIL") or
                not isinstance(checked.get("errors"), list) or not isinstance(checked.get("counts"), dict)):
            raise ValueError("invalid load checker report (expected status/errors/counts)")
        report["checker"] = checked
        report["counts"] = checked["counts"]
        report["errors"].extend(checked["errors"])
        if checked["status"] != "PASS" and not checked["errors"]:
            report["errors"].append("load checker did not pass")
        if executed["returncode"] != 0 or executed.get("timeout"):
            report["errors"].append("simulation failed or timed out")
    except Exception as error:
        report["errors"].append(f"{type(error).__name__}: {error}")
    report["errors"].extend(changed_inputs(records))
    report["errors"].extend(changed_inputs(report["evidence"]))
    if not report["errors"] and report.get("checker", {}).get("status") == "PASS":
        report["status"] = "PASS"
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    save(output / "summary.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    args = parser.parse_args()
    try:
        report = run(args.output, args.package)
    except (OSError, ValueError) as error:
        print(f"CVA6_LOAD_CONTRACT_FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps({key: report[key] for key in ("status", "errors", "counts", "output")}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

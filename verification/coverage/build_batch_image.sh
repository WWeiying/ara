#!/usr/bin/env bash
# Build only. Run under systemd KillMode=control-group for bounded child cleanup.
# Usage: bash build_batch_image.sh NEW_OUTPUT_DIR [TOGGLE=0|1]
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
exec /usr/bin/python3 - "$root" "${1:?new output directory required}" "${2:-0}" <<'PY'
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone

root = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).absolute()
toggle = int(sys.argv[3])
if toggle not in (0, 1):
    raise SystemExit("toggle must be 0 or 1")
cache = root / "verification/out/integrated-verilator-coverage-20260925-01"
build = cache / "build/verilator"
if not (build / "Vara_tb_verilator.mk").is_file():
    raise SystemExit("incremental cache is missing")
lock = (cache / ".batch-build.lock").open("a")
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit("another batch build owns the cache lock")

# Older build entry points do not use our lock; refuse an already active writer.
builders = {"make", "gmake", "verilator", "verilator_bin", "verilator_bin_dbg",
            "g++", "gcc", "c++", "cc1plus", "cc1", "ld", "ld.bfd", "collect2"}
for process in Path("/proc").iterdir():
    if not process.name.isdigit() or int(process.name) == os.getpid():
        continue
    try:
        argv = process.joinpath("cmdline").read_bytes().split(b"\0")
        if not argv[0] or Path(os.fsdecode(argv[0])).name not in builders:
            continue
        cwd = process.joinpath("cwd").resolve(strict=True)
        if str(cache).encode() in b"\0".join(argv) or cwd.is_relative_to(cache):
            raise SystemExit(f"cache already in use by pid {process.name}: {argv!r}")
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        continue

output.mkdir(parents=True, exist_ok=False)
log = (output / "build.log").open("w", buffering=1)
os.dup2(log.fileno(), 1)
os.dup2(log.fileno(), 2)

def stamp():
    return datetime.now(timezone.utc).isoformat()

def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

def write_json(name, payload):
    target = output / name
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temp, target)

make = ["make", "-C", str(root / "hardware"), "config=default",
        f"buildpath={cache / 'build'}", "qbs=1", "akv=1", "akv_v2=1",
        "sim_l2_mb=2", "veril_threads=4", "veril_coverage=1",
        f"veril_coverage_toggle={toggle}", "veril_cxx_opt=-O3", "veril_jobs=12",
        "veril_clean=0"]
provenance = [sys.executable, str(root / "verification/coverage/build_provenance.py")]
capture = provenance + ["--filelist", str(build / "bender_script_default"),
                        "--repo-root", str(root), "--build-dir", str(build)]
state = {"status": "BUILDING", "started_at": stamp(), "repo_root": str(root),
         "cache": str(cache), "jobs": 12, "service": os.environ.get("BUILD_SERVICE"),
         "invocation_id": os.environ.get("INVOCATION_ID"), "simulations_started": False,
         "coverage": {"line": True, "expression": True, "toggle": bool(toggle),
                      "fsm": False, "assertion": False},
         "commands": [], "source_check": "NOT_RUN"}
write_json("status.json", state)

def execute(command, phase, timeout=120):
    state["phase"] = phase
    state["commands"].append({"phase": phase, "argv": command, "cwd": str(root)})
    write_json("status.json", state)
    print(f"[{stamp()}] {phase}: {command!r}", flush=True)
    subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                   check=True, timeout=timeout)

before = output / "source_manifest.before.json"
try:
    previous = output / "previous"
    previous.mkdir()
    for source in sorted(cache.glob("source_manifest*.json")):
        shutil.copy2(source, previous / source.name)
    for name in (".build-signature", ".cxx-signature", "bender_script_default",
                 "bender_script_default.raw", "Vara_tb_verilator__verFiles.dat"):
        if (build / name).is_file():
            shutil.copy2(build / name, previous / name)
    binary = build / "Vara_tb_verilator"
    if binary.is_file():
        shutil.copy2(binary, previous / binary.name)
    write_json("previous.json", {p.name: digest(p) for p in sorted(previous.iterdir())})
    execute([str(root / "install/verilator/bin/verilator"), "--version"], "verilator-version")
    execute(["g++", "--version"], "compiler-version")
    execute(make + ["verilate_prepare"], "prepare")
    execute(capture + ["--output", str(before)], "freeze-sources")
    frozen = json.loads(before.read_text())
    with tarfile.open(output / "sources.before.tar.gz", "w:gz") as archive:
        for record in frozen["files"]:
            path = Path(record["path"])
            archive.add(path, arcname="absolute/" + str(path).lstrip("/"), recursive=False)
    shutil.copy2(root / "verification/coverage/build_batch_image.sh",
                 output / "build_batch_image.sh")
    execute(provenance + ["--output", str(before), "--check"], "check-before")
    execute(make + ["verilate"], "incremental-build", timeout=6 * 3600)
    execute(provenance + ["--output", str(before), "--check"], "check-after")
    state["source_check"] = "PASS"
    execute(capture + ["--output", str(output / "source_manifest.after.json")], "capture-after")
    if json.loads(before.read_text())["files"] != json.loads(
            (output / "source_manifest.after.json").read_text())["files"]:
        raise RuntimeError("source manifests differ")
    generated = (build / "Vara_tb_verilator__verFiles.dat").read_text()
    for flag in ("--coverage-line", "--coverage-expr", "-GL2SizeBytes=2097152"):
        if flag not in generated:
            raise RuntimeError(f"generated model lacks required option: {flag}")
    if ("--coverage-toggle" in generated) != bool(toggle):
        raise RuntimeError("generated toggle instrumentation differs from request")
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError("build did not produce an executable image")
    image = output / "Vara_tb_verilator"
    shutil.copy2(binary, image)
    if digest(image) != digest(binary):
        raise RuntimeError("image changed during freezing")
    image.chmod(0o550)
    shutil.copy2(before, output / "source_manifest.json")
    shutil.copy2(build / "Vara_tb_verilator__verFiles.dat", output / "verFiles.dat")
    state.update(status="PASS", image=str(image), image_sha256=digest(image))
except Exception as error:
    state.update(status="FAIL", error=f"{type(error).__name__}: {error}")
    print(state["error"], flush=True)
    if before.exists():
        try:
            execute(capture + ["--output", str(output / "source_manifest.after.json")],
                    "capture-after-failure")
            same = json.loads(before.read_text())["files"] == json.loads(
                (output / "source_manifest.after.json").read_text())["files"]
            state["source_check"] = "PASS" if same else "FAIL"
        except Exception as audit_error:
            state["source_check"] = "ERROR"
            state["source_check_error"] = str(audit_error)
finally:
    state["finished_at"] = stamp()
    write_json("status.json", state)
    artifacts = {str(path.relative_to(output)): digest(path)
                 for path in sorted(output.rglob("*"))
                 if path.is_file() and path.name not in ("build.log", "artifacts.json")}
    write_json("artifacts.json", artifacts)
print(f"[{stamp()}] {state['status']}; no simulations launched", flush=True)
raise SystemExit(0 if state["status"] == "PASS" else 1)
PY

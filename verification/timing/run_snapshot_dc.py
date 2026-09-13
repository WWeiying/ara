#!/usr/bin/env python3
"""Run the unchanged SoC DC flow on frozen inputs after a regression passes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
FLOW = ROOT / "backend/syn/ara_soc/v1-dc"


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(out):
    parser = runpy.run_path(str(ROOT / "hardware/scripts/akv/check-synthesis-preflight.py"))
    original = ROOT / "backend/flist/ara_soc_dc.f"
    text = original.read_text()
    defines, sources = parser["_filelist_entries"](text)
    required = {"ARA_QBS_ENABLE", "ARA_AKV_ENABLE", "ARA_AKV_V2_ENABLE", "TARGET_SRAM_MC"}
    names = {name.split("=")[0] for name in defines}
    if "IDEAL_DISPATCHER" in names or not required <= names:
        raise RuntimeError(f"filelist does not match the real QBS/AKV macro-SRAM baseline: {names}")
    snap = out / "sources"

    def target(path):
        return snap / str(path).lstrip("/")

    files = set(sources)
    include_dirs = set()
    for line in text.splitlines():
        if line.startswith("+incdir+"):
            include_dirs.update(Path(name) for name in line.split("+")[2:] if name)
    for directory in include_dirs:
        files.update(path for path in directory.rglob("*")
                     if path.is_file() and path.suffix in (".svh", ".vh", ".h", ".sv", ".v"))
        target(directory).mkdir(parents=True, exist_ok=True)
    records = []
    for path in sorted(files):
        dest = target(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        records.append({"path": str(path), "snapshot": str(dest), "sha256": digest(dest)})
    rewritten = []
    for line in text.splitlines():
        if line.startswith("+incdir+"):
            line = "+incdir+" + "+".join(str(target(Path(name))) for name in line.split("+")[2:] if name)
        elif line.strip() and not line.startswith("+"):
            path = Path(line.strip())
            if path not in files:
                raise RuntimeError(f"unsupported filelist line: {line}")
            line = str(target(path))
        rewritten.append(line)
    flist = out / "backend/flist/ara_soc_dc.f"
    flist.parent.mkdir(parents=True)
    flist.write_text("\n".join(rewritten) + "\n")
    flow = out / "backend/syn/ara_soc/v1-dc"
    for directory in ("global_scripts", "local_scripts"):
        shutil.copytree(FLOW / directory, flow / directory)
    for directory in ("run", "reports", "outputs", "inputs/inc"):
        (flow / directory).mkdir(parents=True)
    for name in (".synopsys_dc.setup", "run.cmd"):
        shutil.copy2(FLOW / "run" / name, flow / "run" / name)
    records += [{"path": str(path), "sha256": digest(path)}
                for path in sorted(flow.rglob("*")) if path.is_file()]
    manifest = {"created": now(), "files": records, "defines": sorted(defines),
                "source_count": len(sources), "period_ns": 1, "setup_uncertainty_ns": 0.15,
                "scope": "isolated full SoC; unmodified DC scripts/SDC; frozen RTL and headers"}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--regression", type=Path, required=True)
    parser.add_argument("--qbs-log", type=Path, required=True)
    parser.add_argument("--container", default="synopsys_workspace")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    out = args.output.resolve()
    if not args.worker:
        out.mkdir(parents=True, exist_ok=False)
        prepare(out)
        command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--output", str(out),
                   "--regression", str(args.regression.resolve()), "--qbs-log", str(args.qbs_log.resolve()),
                   "--container", args.container]
        with (out / "driver.log").open("w") as log:
            worker = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                      stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        print(f"scheduled pid={worker.pid} output={out}")
        return
    status = {"state": "WAITING_FOR_REGRESSION", "pid": os.getpid(), "started": now()}

    def save():
        (out / "status.json").write_text(json.dumps(status, indent=2) + "\n")

    save()
    try:
        deadline = time.monotonic() + 10800
        while time.monotonic() < deadline:
            reg = json.loads(args.regression.read_text())
            if reg["state"] != "RUNNING":
                break
            # A detached dependency waiter, not interactive simulation polling.
            time.sleep(30)
        else:
            raise RuntimeError("regression did not finish within the three-hour dependency window")
        if reg["state"] != "PASS":
            raise RuntimeError(f"regression is {reg['state']}; synthesis was not started")
        qbs = args.qbs_log.read_text()
        if "QBS engine PASS: 33 functional cases plus four fault classes" not in qbs or "Fatal:" in qbs:
            raise RuntimeError("QBS functional/fault gate did not pass")
        manifest = json.loads((out / "manifest.json").read_text())
        frozen = {record["path"]: record["sha256"] for record in manifest["files"]}
        for relative, expected in reg["source_sha256"].items():
            name = str(ROOT / relative)
            if name in frozen and frozen[name] != expected:
                raise RuntimeError(f"regression/source snapshot mismatch: {relative}")
        flow = out / "backend/syn/ara_soc/v1-dc"
        command = ["docker", "exec", "-u", f"{os.getuid()}:{os.getgid()}", "-e", f"HOME={Path.home()}",
                   "-e", "DC_ELAB_ONLY=0", "-w", str(flow / "run"), args.container,
                   "bash", "-lc", "exec ./run.cmd"]
        status.update(state="RUNNING", dc_started=now())
        save()
        with (out / "console.log").open("w") as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        text = (flow / "run/dc.log").read_text(errors="replace")
        status.update(state="PASS" if result.returncode == 0 and "DC_FLOW_COMPLETE" in text else "FAIL",
                      returncode=result.returncode)
    except Exception as error:
        status.update(state="FAIL", error=str(error))
    status["finished"] = now()
    save()


if __name__ == "__main__":
    main()

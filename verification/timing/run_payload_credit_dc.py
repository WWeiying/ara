"""Run one isolated synthesis, changing only the two VCS-checked timing sources."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess

from run_operand_ext import read, save, sha, verify
from run_payload_credit_soc import CHANGED

FLOW = Path("backend/syn/ara_soc/v1-dc")


def run(old, soc, out):
    verify(old)
    status = read(old / "status.json")
    tests = read(soc / "status.json")
    if status["state"] != "SYNTHESIS_COMPLETE" or tests["state"] != "PASS":
        raise ValueError("requires complete reference synthesis and passing paired VCS")
    previous = read(old / "source-pins.json")
    changes, pins = {}, {}
    for filename, digest in previous.items():
        source = Path(filename)
        if not source.is_relative_to(old):
            pins[filename] = digest
            continue
        relative = source.relative_to(old)
        if str(relative) == "manifest.json":
            continue
        dest = out / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        rtl = next((r for r in CHANGED if filename.endswith("/" + r)), None)
        if rtl:
            ref = Path(tests["reference"]) / "source" / rtl
            if sha(ref) != digest or sha(soc / rtl) != tests["changed_sha256"][rtl]:
                raise ValueError(f"VCS/DC input mismatch: {rtl}")
            shutil.copy2(soc / rtl, dest)
            changes[rtl] = {"old": digest, "new": sha(dest)}
        else:
            shutil.copy2(source, dest)
            if relative.parts[0] != "sources" and str(old).encode() in dest.read_bytes():
                dest.write_bytes(dest.read_bytes().replace(str(old).encode(), str(out).encode()))
        pins[str(dest)] = sha(dest)
    if set(changes) != set(CHANGED):
        raise ValueError("not all overlays were applied")
    for empty in ("reports", "outputs", "inputs/inc"):
        (out / FLOW / empty).mkdir(parents=True, exist_ok=True)
    # Some include directories in the pinned filelist are intentionally empty.
    for line in (out / "backend/flist/ara_soc_dc.f").read_text().splitlines():
        if line.startswith("+incdir+"):
            for name in line.split("+")[2:]:
                if name and Path(name).is_relative_to(out / "sources"):
                    Path(name).mkdir(parents=True, exist_ok=True)
    save(out / "manifest.json", {"parent": str(old), "main": status["main_rtl_commit"],
                                 "paired_soc": str(soc), "changes": changes,
                                 "constraints": "inherited unchanged from parent"})
    save(out / "source-pins.json", pins)
    verify(out)
    command = list(status["command"])
    i = command.index("-w") + 1
    if command[i] != str(old / FLOW / "run"):
        raise ValueError("unexpected reference launch command")
    command[i] = str(out / FLOW / "run")
    save(out / "status.json", {"state": "RUNNING_DC", "command": command, "worker": os.getpid()})
    with (out / "console.log").open("w") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    artifacts = [out / FLOW / "outputs" / ("ara_soc_dc." + x) for x in ("ddc", "v", "sdc")]
    if not all(f.is_file() and f.stat().st_size for f in artifacts):
        raise ValueError("DC returned without all mapped outputs")
    save(out / "status.json", {"state": "SYNTHESIS_COMPLETE", "output_sha256":
                               {str(f): sha(f) for f in artifacts}, "timing_signoff": False})


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("old", "soc", "out"):
        cli.add_argument(name, type=Path)
    a = cli.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    try:
        run(a.old.resolve(), a.soc.resolve(), out)
    except Exception as exc:
        save(out / "status.json", {"state": "FAIL", "error": str(exc)})
        raise

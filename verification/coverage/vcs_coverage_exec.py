#!/usr/bin/env python3
"""Immutable simulator adapter: add per-case coverage flags, then exec real VCS.

Copied beside coverage-wrapper.json by run_vcs_dve_checkpoint.py. The existing
replay/checker stays unchanged. The driver separately pins the REAL executable
and its libraries; the adapter also checks those pins on every invocation.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sys

METRICS = "line+cond+fsm+tgl+branch"


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def command(config, args, cwd):
    if not cwd.is_relative_to(Path(config["results"])):
        raise ValueError("coverage replay cwd is outside this queue")
    if any(arg == "-cm" or arg.startswith("-cm_") for arg in args):
        raise ValueError("caller must not override frozen coverage flags")
    names = [arg.split("=", 1)[1] for arg in args if arg.startswith("+TESTCASE=")]
    if len(names) != 1 or not re.fullmatch(r"[A-Za-z0-9_]+", names[0]):
        raise ValueError("one safe testcase name required")
    for path, expected in config["image"].items():
        if digest(path) != expected:
            raise RuntimeError(f"compiled VCS image changed: {path}")
    database = cwd / "code.vdb"
    if database.exists():
        raise ValueError("per-case VDB already exists")
    return [config["simv"], *args, "-cm", METRICS, "-cm_dir", str(database), "-cm_name", names[0]]


def main():
    config = json.loads(Path(__file__).with_name("coverage-wrapper.json").read_text())
    cwd = Path.cwd().resolve()
    argv = command(config, sys.argv[1:], cwd)
    with (cwd / "coverage.command.json").open("x") as stream:
        json.dump({"command": argv, "cwd": str(cwd)}, stream, indent=2)
    os.execv(argv[0], argv)


if __name__ == "__main__":
    main()

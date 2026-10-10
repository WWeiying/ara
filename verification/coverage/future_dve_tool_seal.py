#!/usr/bin/env python3
"""Prelaunch tool bytes and live Linux executable witnesses, never an approval.

This helper does not launch tools. A future supervisor must prepare before launch,
bind its fresh root PID, witness the real DVE descendant while alive, then finish
after exit. A post-hoc hash alone cannot complete that protocol. Shared libraries
and loader identity are outside this binary-only evidence scope.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

SCHEMA = "future-dve-binary-seal-v1"
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name("test_future_dve_tool_seal.py")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(stat):
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


def file_record(path):
    path = Path(path).absolute()
    resolved = path.resolve(strict=True)
    require(resolved.is_file(), "Not a regular tool")
    topology = [[str(p), p.lstat().st_dev, p.lstat().st_ino, p.lstat().st_mode,
                 os.readlink(p) if p.is_symlink() else None] for p in (path, *path.parents)]
    with path.open("rb") as stream:
        before = identity(os.fstat(stream.fileno()))
        h = hashlib.sha256()
        prefix = stream.read(64)
        h.update(prefix)
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
        require(identity(os.fstat(stream.fileno())) == before, "Tool changed during hash")
    require(identity(path.stat()) == before and path.resolve(strict=True) == resolved,
            "Tool changed during binding")
    after = [[str(p), p.lstat().st_dev, p.lstat().st_ino, p.lstat().st_mode,
              os.readlink(p) if p.is_symlink() else None] for p in (path, *path.parents)]
    require(topology == after, "Tool topology changed during binding")
    return dict(path=str(path), resolved=str(resolved), sha256=h.hexdigest(),
                identity=before, topology=topology), prefix


def boot_id(proc=Path("/proc")):
    return (proc / "sys/kernel/random/boot_id").read_text().strip()


def process(pid, proc=Path("/proc")):
    require(type(pid) is int and pid > 0, "Invalid PID")
    path = proc / str(pid)
    raw = (path / "stat").read_text()
    end = raw.rfind(")")
    require(end >= 0 and raw[:raw.find(" (")] == str(pid), "Malformed process identity")
    fields = raw[end + 2:].split()
    require(len(fields) >= 20 and fields[0] not in ("Z", "X"), "Process not alive")
    return dict(pid=pid, ppid=int(fields[1]), start_ticks=int(fields[19]), uid=path.stat().st_uid)


def prepare(wrapper, *, binary=None, launchers=(), environment=None):
    wrapper = Path(wrapper).absolute()
    if binary is None:
        binary = wrapper.parent.parent / "gui/dve/linux64/bin/dve.exe"
    roles = {"dve_wrapper": wrapper, "dve_executable": Path(binary)}
    for i, path in enumerate(launchers):
        roles["launcher%d" % i] = Path(path)
    tools = {}
    for role, path in roles.items():
        require(os.access(path, os.X_OK), "Tool is not executable")
        record, prefix = file_record(path)
        if role == "dve_executable":
            require(prefix[:6] == b"\x7fELF\x02\x01", "Real 64-bit ELF executable required")
        tools[role] = record
    require(tools["dve_executable"]["resolved"] != tools["dve_wrapper"]["resolved"],
            "Wrapper is not the real DVE executable")
    code = [file_record(p)[0] for p in (SCRIPT, TEST)]
    seal = dict(schema=SCHEMA, phase="PRELAUNCH", boot_id=boot_id(), uid=os.getuid(),
                created_boottime_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME),
                ticks_per_second=os.sysconf("SC_CLK_TCK"), tools=tools, helper_code=code,
                launch_environment_sha256=digest(encoded(dict(os.environ if environment is None else environment))),
                evidence_scope="wrapper + real executable + launchers; not loader/shared-library closure",
                application_approval=False)
    seal["seal_sha256"] = digest(encoded(seal))
    recheck(seal)
    return seal


def recheck(seal):
    body = {k: v for k, v in seal.items() if k != "seal_sha256"}
    require(seal.get("schema") == SCHEMA and seal.get("phase") == "PRELAUNCH"
            and seal.get("seal_sha256") == digest(encoded(body)), "Invalid prelaunch seal")
    require(seal["boot_id"] == boot_id() and seal["uid"] == os.getuid(), "Foreign boot/user")
    require({"dve_wrapper", "dve_executable"} <= set(seal["tools"]), "Missing real executable role")
    for record in [*seal["tools"].values(), *seal["helper_code"]]:
        require(file_record(record["path"])[0] == record, "Sealed tool bytes/identity/topology changed")


def bind_launch(seal, root_pid, *, proc=Path("/proc")):
    recheck(seal)
    require(boot_id(proc) == seal["boot_id"], "Foreign process namespace boot")
    root = process(root_pid, proc)
    require(root["uid"] == seal["uid"] and root["start_ticks"] * 1_000_000_000 >
            seal["created_boottime_ns"] * seal["ticks_per_second"],
            "Root process predates tool seal (same-tick ambiguity rejected)")
    return dict(seal_sha256=seal["seal_sha256"], root=root, witnessed=False)


def witness(seal, launch, pid, *, proc=Path("/proc")):
    recheck(seal)
    require(launch["seal_sha256"] == seal["seal_sha256"] and boot_id(proc) == seal["boot_id"],
            "Launch is not bound to seal")
    require(process(launch["root"]["pid"], proc) == launch["root"], "Root PID reused/changed")
    leaf = process(pid, proc)
    lineage = [leaf]
    while lineage[-1]["pid"] != launch["root"]["pid"]:
        require(len(lineage) < 128 and lineage[-1]["ppid"] > 0, "Not a bounded launch descendant")
        parent = process(lineage[-1]["ppid"], proc)
        require(parent["pid"] not in {p["pid"] for p in lineage}, "Cyclic process lineage")
        lineage.append(parent)
    require(all(p["uid"] == seal["uid"] for p in lineage), "Foreign process user")
    executable = proc / str(pid) / "exe"
    target = os.readlink(executable)
    expected = seal["tools"]["dve_executable"]
    require(target == expected["resolved"], "Runtime executable is not sealed real DVE")
    with executable.open("rb") as stream:
        before = identity(os.fstat(stream.fileno()))
        h = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
        require(before == identity(os.fstat(stream.fileno())) == expected["identity"]
                and h.hexdigest() == expected["sha256"], "Runtime executable bytes/identity differ")
    require(all(process(p["pid"], proc) == p for p in lineage)
            and os.readlink(executable) == target, "Process/exec changed during witness")
    recheck(seal)
    record = dict(seal_sha256=seal["seal_sha256"], lineage=lineage,
                  executable=dict(resolved=target, sha256=h.hexdigest(), identity=before),
                  observed_boottime_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME),
                  runtime_identity_verified=True)
    return record


def finish(seal, launch, witnesses, returncode, *, proc=Path("/proc")):
    recheck(seal)
    require(type(returncode) is int and returncode == 0, "Tool run did not succeed")
    require(launch["seal_sha256"] == seal["seal_sha256"] and witnesses, "No live executable witness")
    root_path = proc / str(launch["root"]["pid"])
    if root_path.exists():
        require(process(launch["root"]["pid"], proc) != launch["root"], "Launch root still running")
    expected = seal["tools"]["dve_executable"]
    for record in witnesses:
        require(record.get("runtime_identity_verified") is True and record["seal_sha256"] == seal["seal_sha256"]
                and record["lineage"][-1] == launch["root"]
                and record["executable"] == {k: expected[k] for k in ("resolved", "sha256", "identity")},
                "Invalid/unbound live witness")
    return dict(status="FUTURE_DVE_BINARY_WITNESSED_NOT_APPROVAL", seal_sha256=seal["seal_sha256"],
                witnesses_sha256=digest(encoded(witnesses)), runtime_witnesses=len(witnesses),
                application_approval=False, retrospective_capture_qualification=False,
                scope=seal["evidence_scope"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wrapper", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--launcher", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.wrapper, binary=args.binary, launchers=args.launcher)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()

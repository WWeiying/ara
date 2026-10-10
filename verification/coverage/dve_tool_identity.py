"""Seal DVE launcher and actual executable for a future host run.

This is not a shared-library inventory or retrospective qualification of a run.
"""
import hashlib
import os
from pathlib import Path


def identity(path):
    path = Path(path)
    st = path.stat()
    return dict(resolved=str(path.resolve(strict=True)), device=st.st_dev,
                inode=st.st_ino, size=st.st_size, mtime_ns=st.st_mtime_ns,
                ctime_ns=st.st_ctime_ns)


def seal_file(path):
    path = Path(path).absolute()
    before = identity(path)
    h = hashlib.sha256()
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before["device"], before["inode"]):
            raise ValueError("tool changed before opening")
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    if identity(path) != before:
        raise ValueError("tool changed while hashing")
    return dict(path=str(path), identity=before, sha256=h.hexdigest())


def prepare(wrapper, xvfb_run):
    wrapper, xvfb_run = Path(wrapper).absolute(), Path(xvfb_run).absolute()
    resolved = wrapper.resolve(strict=True)
    if wrapper.name != "dve" or resolved.parent.name != "bin":
        raise ValueError("only standard DVE launcher supported")
    home = resolved.parent.parent
    dve_home = home / "gui/dve"
    executable = dve_home / "linux64/bin/dve.exe"
    arch = dve_home / "bin/getarch_dve"
    for path in (wrapper, xvfb_run, executable):
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError("tool missing or not executable")
    with executable.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            raise ValueError("DVE executable is not ELF")
    files = [seal_file(p) for p in (wrapper, xvfb_run, executable, arch)]
    return dict(schema="dve-executable-identity-v1", files=files,
                roles=dict(launcher=str(wrapper), xvfb_run=str(xvfb_run),
                           executable=str(executable), architecture=str(arch)),
                executable=str(executable.resolve(strict=True)),
                environment=dict(VCS_HOME=str(home), DVE=str(dve_home),
                                 VCS_TARGET_ARCH="linux64"),
                scope="launcher, architecture selector and DVE ELF; shared libraries not inventoried",
                qualifies_previous_runs=False)


def revalidate(record):
    if record.get("schema") != "dve-executable-identity-v1":
        raise ValueError("unknown tool identity schema")
    roles = record.get("roles", {})
    if set(roles) != {"launcher", "xvfb_run", "executable", "architecture"}:
        raise ValueError("incomplete tool roles")
    if len(record.get("files", [])) != 4:
        raise ValueError("incomplete tool files")
    if len({str(Path(p).resolve(strict=True)) for p in roles.values()}) != 4:
        raise ValueError("aliased tool roles")
    expected = prepare(roles["launcher"], roles["xvfb_run"])
    if record != expected:
        raise ValueError("tool identity, roles or environment changed")


def controlled_environment(record, inherited):
    """Remove launcher redirection and injection before any process is started."""
    revalidate(record)
    forbidden = {"QADEBUG", "LD_PRELOAD", "LD_AUDIT", "BASH_ENV", "ENV",
                 "REPORT_FLAG", "NOGUI_FLAG", "REPORT_USE_THIS_EXE", "UCLI_USE_THIS_EXE"}
    env = {k: v for k, v in inherited.items()
           if k not in forbidden and not k.startswith(("DVE", "VERA"))}
    env.update(record["environment"])
    env["PATH"] = "/usr/bin:/bin"
    return env


def launch_command(record, script):
    revalidate(record)
    script = Path(script).resolve(strict=True)
    if not script.is_file():
        raise ValueError("coverage script missing")
    return [record["roles"]["xvfb_run"], "-a", record["roles"]["launcher"],
            "-full64", "-cov", "-script", str(script)]


def process_info(pid):
    text = Path(f"/proc/{int(pid)}/stat").read_text()
    fields = text.rsplit(")", 1)[1].split()
    return dict(parent=int(fields[1]), starttime=int(fields[19]))


def verify_launch_child(pid, launch_pid, launch_starttime):
    if min(int(pid), int(launch_pid)) <= 0 or pid == launch_pid:
        raise ValueError("DVE must be a child of this launch")
    if process_info(launch_pid)["starttime"] != launch_starttime:
        raise ValueError("launch process identity changed")
    info = process_info(pid)
    if info["starttime"] < launch_starttime:
        raise ValueError("executable predates this launch")
    cursor, seen = pid, set()
    for _ in range(64):
        if cursor == launch_pid:
            return info
        if cursor <= 1 or cursor in seen:
            break
        seen.add(cursor)
        cursor = process_info(cursor)["parent"]
    raise ValueError("executable is not descended from this launch")


def verify_live_executable(pid, record, launch_pid, launch_starttime):
    """Require a DVE child of the bound launch, not an arbitrary existing PID."""
    initial = verify_launch_child(pid, launch_pid, launch_starttime)
    expected = Path(record["executable"]).resolve(strict=True)
    actual = Path(f"/proc/{int(pid)}/exe").resolve(strict=True)
    if actual != expected:
        raise ValueError("observed process is not the sealed DVE executable")
    observed = identity(Path(f"/proc/{int(pid)}/exe"))
    saved = next(item for item in record["files"] if item["identity"]["resolved"] == str(expected))
    if observed != saved["identity"]:
        raise ValueError("running executable identity differs")
    revalidate(record)
    if process_info(pid) != initial:
        raise ValueError("DVE process identity changed during validation")
    return dict(pid=int(pid), executable=str(actual), executable_verified=True,
                starttime=initial["starttime"], launch_pid=int(launch_pid),
                launch_starttime=launch_starttime)

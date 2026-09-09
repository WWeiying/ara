#!/usr/bin/env python3
"""Preview or apply a conflict-checked source update to an exported FPGA package.

Repository: sync.py [DEST] [--apply] exports current sources into a temporary tree.
Windows:    sync.py DEST --from-package NEW_PACKAGE [--apply] uses a prepared tree.
Neither mode runs Vivado nor modifies its build, reports or output directories.
"""
import argparse
from contextlib import contextmanager
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
DEFAULT_TARGET = HERE.parent / "ara_dsa_vcu118"
SUMS = "SHA256SUMS"
OWNED_DIRS = {"rtl", "scripts", "constraints", "board_files", "software", "licenses", "provenance"}
RESERVED = {"con", "prn", "aux", "nul"} | {f"{p}{i}" for p in ("com", "lpt") for i in range(1, 10)}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def validate_name(name):
    path = PurePosixPath(name)
    if (not name or not path.parts or path.is_absolute() or path.as_posix() != name or
            any(p in (".", "..") or p.rstrip(" .") != p or
                p.split(".")[0].casefold() in RESERVED or
                any(c in p for c in '<>:"\\|?*\n\r\t') for p in path.parts)):
        raise RuntimeError(f"Unsafe/non-portable package path: {name!r}")


def managed(name):
    path = PurePosixPath(name)
    return (name in {"README_WINDOWS.md", "manifest.json", ".gitignore", ".gitattributes"} or
            path.parts[0] in OWNED_DIRS or
            (path.parts[0] == "docs" and path.suffix == ".md"))


def safe_path(root, name):
    validate_name(name)
    path = root
    parts = PurePosixPath(name).parts
    for index, part in enumerate(parts):
        path = path / part
        if path.is_symlink():
            raise RuntimeError(f"Refusing symlink in managed path: {path}")
        if index < len(parts) - 1 and path.exists() and not path.is_dir():
            raise RuntimeError(f"Non-directory parent in managed path: {path}")
    if path.exists() and not path.is_file():
        raise RuntimeError(f"Expected a file, found a directory: {path}")
    return path


def read_hashes(root):
    rows = safe_path(root, SUMS).read_text(encoding="utf-8").splitlines()
    hashes = {}
    for row in rows:
        try:
            value, name = row.split("  ", 1)
        except ValueError:
            raise RuntimeError(f"Invalid {SUMS} row: {row!r}") from None
        validate_name(name)
        if not re.fullmatch(r"[0-9a-f]{64}", value) or name in hashes or name == SUMS:
            raise RuntimeError(f"Invalid/duplicate checksum: {name}")
        hashes[name] = value
    if not {"manifest.json", "scripts/sources.tcl"} <= hashes.keys():
        raise RuntimeError(f"Not a complete exported FPGA package: {root}")
    return hashes


def check_case_collisions(root, names):
    seen = {}
    paths = set(names)
    # Do not traverse Vivado build products or user backups.
    for directory in OWNED_DIRS | {"docs"}:
        folder = root / directory
        if folder.is_symlink():
            raise RuntimeError(f"Refusing linked package directory: {folder}")
        if folder.is_dir():
            paths.update(p.relative_to(root).as_posix() for p in folder.rglob("*"))
    for name in sorted(paths):
        validate_name(name)
        parts = PurePosixPath(name).parts
        for i in range(1, len(parts) + 1):
            prefix = "/".join(parts[:i])
            folded = prefix.casefold()
            if folded in seen and seen[folded] != prefix:
                raise RuntimeError(f"Windows case collision: {seen[folded]} / {prefix}")
            seen[folded] = prefix


def make_plan(target, source):
    old = read_hashes(target)
    incoming = read_hashes(source)
    names = sorted(n for n in old.keys() | incoming.keys() if managed(n))
    check_case_collisions(target, names)
    check_case_collisions(source, names)
    old_manifest = json.loads(safe_path(target, "manifest.json").read_text(encoding="utf-8"))
    new_manifest = json.loads(safe_path(source, "manifest.json").read_text(encoding="utf-8"))
    if old_manifest.get("top") != "ara_dsa_vcu118" or new_manifest.get("top") != old_manifest["top"]:
        raise RuntimeError("Target/source must use the ara_dsa_vcu118 top")
    actions, conflicts, local, observed, adopt = [], [], [], {}, []
    for name in names:
        before, after = old.get(name), incoming.get(name)
        src = safe_path(source, name)
        if after is not None and digest(src) != after:
            raise RuntimeError(f"Incoming file missing or checksum mismatch: {name}")
        current = digest(safe_path(target, name))
        observed[name] = current
        if current == after:
            if before != after:
                adopt.append(name)
        elif current == before:
            action = "DELETE" if after is None else ("ADD" if before is None else "UPDATE")
            actions.append((action, name))
        elif after == before:
            local.append(name)
        else:
            conflicts.append(name)
    # Keep historical log checksums; never seal Vivado outputs into the baseline.
    baseline = {n: h for n, h in old.items() if not managed(n)}
    baseline.update((n, h) for n, h in incoming.items() if managed(n))
    sums = "".join(f"{baseline[n]}  {n}\n" for n in sorted(baseline)).encode()
    config_keys = ("files", "include_dirs", "defines", "part", "board_part", "top", "soc_clock_mhz")
    config_changed = any(old_manifest.get(k) != new_manifest.get(k) for k in config_keys)
    config_changed |= any(n.startswith("scripts/") and n != "scripts/sync.py" or
                          n.startswith("board_files/") for _, n in actions)
    return dict(actions=actions, conflicts=conflicts, local=local, adopt=adopt,
                observed=observed, sums=sums, old_sums=(target / SUMS).read_bytes(),
                incoming=incoming, config_changed=config_changed)


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    fd, temp = tempfile.mkstemp(prefix=".fpga-sync-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def update_lock(target):
    path = target / ".fpga_sync.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise RuntimeError(f"Sync lock exists: {path}; check for a running/interrupted sync") from None
    try:
        with os.fdopen(fd, "w") as output:
            output.write(f"pid={os.getpid()}\n")
        yield
    finally:
        path.unlink()


def apply_plan(target, source, plan):
    if plan["conflicts"]:
        raise RuntimeError("Conflicts found; no target files were changed")
    if not plan["actions"] and plan["sums"] == plan["old_sums"]:
        return None
    with update_lock(target):
        if (target / SUMS).read_bytes() != plan["old_sums"]:
            raise RuntimeError("Checksum baseline changed after preview; retry")
        for name, expected in plan["observed"].items():
            if digest(safe_path(target, name)) != expected:
                raise RuntimeError(f"Target changed after preview: {name}; retry")
        incoming = read_hashes(source)
        if incoming != plan["incoming"]:
            raise RuntimeError("Incoming checksum baseline changed after preview; retry")
        payloads = {}
        for action, name in plan["actions"]:
            if action != "DELETE":
                payloads[name] = safe_path(source, name).read_bytes()
                if hashlib.sha256(payloads[name]).hexdigest() != incoming[name]:
                    raise RuntimeError(f"Incoming source changed after preview: {name}; retry")
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        parent = target / ".fpga_sync_backups"
        if parent.is_symlink():
            raise RuntimeError(f"Refusing linked backup directory: {parent}")
        backup = parent / (stamp + "_" + uuid.uuid4().hex[:8])
        backup.mkdir(parents=True)
        changed = [n for _, n in plan["actions"]] + [SUMS]
        existed = []
        for name in changed:
            path = safe_path(target, name)
            if path.exists():
                saved = backup / "files" / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, saved)
                existed.append(name)
        record = dict(status="prepared", target=str(target), actions=plan["actions"],
                      previously_existing=existed, local_preserved=plan["local"],
                      adopted=plan["adopt"], project_refresh_required=plan["config_changed"],
                      validation="Not rerun; previous synthesis, bitstreams and logs are stale")
        journal = backup / "record.json"
        journal.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        written = []
        try:
            for action, name in plan["actions"]:
                path = safe_path(target, name)
                written.append(name)
                if action == "DELETE":
                    path.unlink()
                else:
                    atomic_write(path, payloads[name])
            written.append(SUMS)
            atomic_write(target / SUMS, plan["sums"])
            record["status"] = "complete"
            journal.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        except BaseException:
            for name in reversed(written):
                path = safe_path(target, name)
                if name in existed:
                    shutil.copy2(backup / "files" / name, path)
                elif path.exists():
                    path.unlink()
            record["status"] = "rolled_back"
            journal.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            raise
        return backup


def print_plan(plan):
    for action, name in plan["actions"]:
        print(f"{action:8} {name}")
    for label, key in (("ADOPT", "adopt"), ("LOCAL", "local"), ("CONFLICT", "conflicts")):
        for name in plan[key]:
            print(f"{label:8} {name}")
    print(f"Changes={len(plan['actions'])}, local preserved={len(plan['local'])}, "
          f"conflicts={len(plan['conflicts'])}")
    if plan["config_changed"]:
        print("PROJECT CONFIG/SOURCE LIST CHANGED: re-create or manually refresh the Vivado project.")


def default_tool(name):
    local = Path.home() / "llama/platforms/cva6-qemu/tools/bin" / ("riscv64-linux-" + name)
    if local.is_file():
        return str(local)
    return shutil.which("riscv64-unknown-elf-" + name) or "riscv64-unknown-elf-" + name


@contextmanager
def incoming_package(args, target):
    if args.from_package is not None:
        source = args.from_package.resolve()
        if source == target or source in target.parents or target in source.parents:
            raise RuntimeError("Incoming and target packages must be separate, non-nested directories")
        yield source
        return
    if not (HERE / "prepare.py").is_file():
        raise RuntimeError("In an exported package use --from-package NEW_PACKAGE (no RTL repo required)")
    # Lazy imports keep the Windows package-to-package mode standard-library only.
    from prepare import prepare, CACHE
    from export import export, seal
    prepare(download_board=not (CACHE / "board_files/vcu118/2.4/board.xml").is_file())
    with tempfile.TemporaryDirectory(prefix="sync-", dir=CACHE) as temporary:
        source = Path(temporary) / "package"
        export(source, args.gcc, args.objdump, smoke_from=target)
        manifest = json.loads((source / "manifest.json").read_text())
        previous = json.loads((target / "manifest.json").read_text())
        # Preserve creation time so an unchanged source tree is a true no-op.
        manifest["created_utc"] = previous.get("created_utc", manifest["created_utc"])
        (source / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        seal(source)
        yield source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", type=Path,
                        help="Existing package; default: hardware/fpga/ara_dsa_vcu118")
    parser.add_argument("--apply", action="store_true", help="Apply after conflict check; otherwise preview only")
    parser.add_argument("--from-package", type=Path, help="Use an already-exported package, also works on Windows")
    parser.add_argument("--gcc", default=default_tool("gcc"))
    parser.add_argument("--objdump", default=default_tool("objdump"))
    args = parser.parse_args()
    if args.target is None:
        if not (HERE / "prepare.py").is_file():
            parser.error("Specify the existing target package directory")
        args.target = DEFAULT_TARGET
    target = args.target.resolve()
    try:
        read_hashes(target)
        with incoming_package(args, target) as source:
            plan = make_plan(target, source)
            print_plan(plan)
            if plan["conflicts"]:
                print("STOP: resolve conflicts first; nothing applied.")
                return 2
            if not args.apply:
                print("DRY RUN: no target files changed. Add --apply to synchronize.")
                return 0
            backup = apply_plan(target, source, plan)
            if backup:
                print(f"Synchronized. Backup and journal: {backup}")
                print("Vivado runs were NOT launched. Re-synthesize/re-implement before using a new bitstream.")
                print("Validation logs were NOT regenerated. Commit the updated package before pushing.")
            else:
                print("No upstream changes to apply.")
            if plan["local"]:
                print("Local-only changes remain visible to verify_package.py; they were not blessed as upstream.")
            return 0
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

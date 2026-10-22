#!/usr/bin/env python3
"""Read-only VCU118 export audit; JSON on stdout, exit 0 only when accepted.

Run from any directory: python3 verification/fpga/check_sources.py
Optional: --source-root PATH --export-root PATH --package-root NAME=RELATIVE_PATH
--output PATH also saves JSON with exclusive creation (never overwrites a result).
Output is forbidden inside the export or mapped source trees. Stdout is unchanged.
Package overrides are explicit checkout locations within source-root, not searches.

--exceptions accepts a JSON object with schema_version=1 and an exceptions list.
Each entry requires export_path, source_path (relative to source-root),
source_sha256, export_sha256, reviewed_by and reason. Both hashes must match
the actual files. No built-in adaptation is automatically approved. Missing
sources, ambiguous mappings, and unused/stale exceptions cannot be waived.

Integrity checks SHA256SUMS entries and coverage of manifest/packaged RTL.
Correspondence checks all packaged RTL/headers, required VMFPU/fence compilation
units, and unexported first-party RTL. It is not a Bender/Vivado elaboration,
proof of functional equivalence, signature authentication, or bitstream audit.
The manifest's pre-integration hashes are claims, never substitutes for source.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from typing import Sequence


DEFAULT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXPORT = "hardware/fpga/ara_dsa_vcu118"
HASH = re.compile(r"[0-9a-fA-F]{64}")
RTL_SUFFIXES = {".sv", ".svh", ".v", ".vh"}
CRITICAL_FILES = {
    "rtl/ara/hardware/src/lane/vmfpu.sv": "VMFPU reduction/narrowing fixes",
    "rtl/cva6/core/acc_dispatcher.sv": "accelerator fence memory barrier",
    "rtl/cva6/core/issue_read_operands.sv": "CVXIF upstream stall preservation",
}
# Exact paths from vcu118/export.py; these are annotations, NOT exemptions.
ADAPTATIONS = {
    "rtl/cheshire/hw/cheshire_pkg.sv": "patch_soc_pkg",
    "rtl/cheshire/hw/cheshire_soc.sv": "patch_soc",
    "rtl/cva6/common/local/util/sram_cache.sv": "patch_sram_cache",
    "rtl/riscv-dbg/src/dmi_jtag.sv": "patch_jtag",
    "rtl/riscv-dbg/src/dmi_jtag_tap.sv": "patch_tap",
    "rtl/common_cells/src/rstgen_bypass.sv": "patch_reset_sync, patch_reset_muxes",
    "rtl/common_cells/src/cdc_fifo_gray.sv": "patch_fifo_selectors",
    "rtl/ara/hardware/src/ara_dispatcher.sv":
        "patch_dispatcher_vlen_casts, patch_dispatcher_layout, patch_dispatcher_control",
    "rtl/ara/hardware/src/segment_sequencer.sv": "patch_segment_geometry",
    "rtl/ara/hardware/src/vlsu/qbs/qbs_engine.sv": "patch_qbs_fault_decode",
    "rtl/ara/hardware/src/vlsu/akv/akv_engine.sv": "patch_akv_byte_counts",
    "rtl/board/dram_wrapper_xilinx.sv": "patch_dram, patch_ready",
}
BOARD_FILES = {"ara_dsa_vcu118.sv", "dram_wrapper_xilinx.sv", "phy_definitions.svh"}
SOURCE_EXCLUSIONS = {
    "hardware/src/ara_soc.sv": "export.py replaces the simulation SoC with the board top",
    "hardware/src/ara_system.sv": "export.py replaces the simulation system with Cheshire",
    "hardware/src/accel_dispatcher_ideal.sv": "Bender.yml: ara_test target only",
}


def sha256(path: Path) -> str:
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"not a regular file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_name(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("path must be a nonempty string")
    path = PurePosixPath(value)
    if (not path.parts or path.is_absolute() or path.as_posix() != value or
            any(p in {".", ".."} for p in path.parts) or
            any(c in value for c in "\\:*?[]\x00\r\n\t")):
        raise ValueError(f"unsafe/noncanonical relative path: {value!r}")
    return value


def safe_path(root: Path, name: str) -> Path:
    path = root
    for part in PurePosixPath(relative_name(name)).parts:
        path /= part
        if path.is_symlink():
            raise ValueError(f"symlink is not auditable: {path}")
    return path


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def scan_tree(root: Path, directory: str, errors: list[str]) -> set[str]:
    result = set()
    try:
        folder = safe_path(root, directory)
        if not folder.is_dir():
            raise ValueError(f"missing directory: {directory}")
        def onerror(error):
            errors.append(str(error))
        for parent, dirs, files in os.walk(folder, followlinks=False, onerror=onerror):
            for name in dirs[:]:
                path = Path(parent) / name
                if path.is_symlink():
                    errors.append(f"symlink directory: {path.relative_to(root)}")
                    dirs.remove(name)
            for name in files:
                result.add((Path(parent) / name).relative_to(root).as_posix())
    except (OSError, ValueError) as error:
        errors.append(str(error))
    return result


def names(values: object, field: str, errors: list[str]) -> set[str]:
    result = set()
    if not isinstance(values, list):
        errors.append(f"{field} must be a list")
        return result
    for value in values:
        try:
            name = relative_name(value)
            if name in result:
                raise ValueError(f"duplicate {field} path: {name}")
            result.add(name)
        except ValueError as error:
            errors.append(str(error))
    return result


def export_inventory(root: Path):
    errors = []
    sums, actual = {}, {}
    metadata = {}
    for name in ("manifest.json", "SHA256SUMS"):
        try:
            metadata[name] = sha256(safe_path(root, name))
        except (OSError, ValueError) as error:
            errors.append(f"{name}: {error}")
    try:
        for line in safe_path(root, "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
            if not match:
                errors.append(f"malformed SHA256SUMS row: {line!r}")
                continue
            digest, name = match.groups()
            try:
                relative_name(name)
                if name == "SHA256SUMS" or name in sums:
                    raise ValueError(f"duplicate/self checksum: {name}")
                sums[name] = digest.lower()
            except ValueError as error:
                errors.append(str(error))
        if not sums:
            errors.append("SHA256SUMS is empty")
    except (OSError, ValueError) as error:
        errors.append(f"SHA256SUMS: {error}")
    try:
        manifest = read_json(safe_path(root, "manifest.json"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be an object")
    except (OSError, ValueError) as error:
        errors.append(f"manifest.json: {error}")
        manifest = {}
    compiled = names(manifest.get("files"), "manifest.files", errors)
    includes = names(manifest.get("include_dirs"), "manifest.include_dirs", errors)
    if not compiled:
        errors.append("manifest.files is empty")
    before, ambiguous = {}, set()
    records = manifest.get("source_hashes_before_integration")
    if not isinstance(records, list) or not records:
        errors.append("source_hashes_before_integration must be a nonempty list")
        records = []
    for entry in records:
        try:
            if not isinstance(entry, dict):
                raise ValueError("malformed source hash record")
            name = relative_name(entry.get("file"))
            value = entry.get("source_sha256")
            if name in before:
                ambiguous.add(name)
                raise ValueError(f"duplicate source hash record: {name}")
            if not isinstance(value, str) or not HASH.fullmatch(value):
                raise ValueError(f"invalid source hash: {name}")
            before[name] = value.lower()
        except ValueError as error:
            errors.append(str(error))
    rtl = scan_tree(root, "rtl", errors)
    inventory = rtl | compiled | set(before) | {n for n in sums if n.startswith("rtl/")}
    for directory in includes:
        try:
            if not directory.startswith("rtl/") or not safe_path(root, directory).is_dir():
                raise ValueError(f"invalid/missing include directory: {directory}")
        except ValueError as error:
            errors.append(str(error))
    folded = {}
    for name in sorted(inventory | set(sums)):
        parts = PurePosixPath(name).parts
        for end in range(1, len(parts) + 1):
            prefix = "/".join(parts[:end])
            key = prefix.casefold()
            if key in folded and folded[key] != prefix:
                errors.append(f"case-ambiguous export paths: {folded[key]} / {prefix}")
                ambiguous.add(name)
            folded[key] = prefix
    for name in sorted(inventory | set(sums) | {"manifest.json", "scripts/sources.tcl"}):
        try:
            actual[name] = sha256(safe_path(root, name))
        except (OSError, ValueError) as error:
            actual[name] = None
            errors.append(f"{name}: {error}")
        if name not in sums:
            errors.append(f"not covered by SHA256SUMS: {name}")
        elif actual[name] is not None and actual[name] != sums[name]:
            errors.append(f"checksum mismatch: {name}")
    for name in inventory:
        if not name.startswith("rtl/"):
            errors.append(f"non-RTL manifest source path: {name}")
        if name not in before and name not in {f"rtl/board/{n}" for n in BOARD_FILES}:
            errors.append(f"missing pre-integration source record: {name}")
    integrity = {
        "status": "invalid" if errors else "valid",
        "scope": "listed checksums plus manifest and complete packaged rtl tree",
        "metadata_sha256": metadata,
        "checksum_count": len(sums),
        "files": [{"path": n, "expected_sha256": sums.get(n), "sha256": actual[n]}
                  for n in sorted(actual)],
        "errors": sorted(set(errors)),
    }
    return integrity, manifest, compiled, before, inventory, actual, ambiguous


class GitInventory:
    """Query each owning repository, including nested dependencies, without locks."""

    def __init__(self, root: Path):
        self.root = root
        self.repositories = {}
        self.cache = {}

    def file(self, path: Path) -> dict:
        owner = next((p for p in path.parents if (p / ".git").exists() and
                      (p == self.root or self.root in p.parents)), None)
        if owner is None:
            return {"status": "unavailable", "error": "no owning Git repository"}
        key = owner.relative_to(self.root).as_posix()
        if key not in self.cache:
            def git(*args):
                return subprocess.check_output(
                    ["git", "--no-optional-locks", "-C", str(owner), *args],
                    stderr=subprocess.PIPE, timeout=30,
                ).decode("utf-8", errors="surrogateescape")
            try:
                head = git("rev-parse", "HEAD").strip()
                tracked = set(git("ls-files", "-z").split("\0"))
                entries = git("status", "--porcelain=v1", "-z", "--untracked-files=all",
                              "--ignored=matching", "--ignore-submodules=none").split("\0")
                states = {}
                index = 0
                while index < len(entries):
                    entry = entries[index]
                    index += 1
                    if not entry:
                        continue
                    code, name = entry[:2], entry[3:]
                    states[name] = code
                    if "R" in code or "C" in code:
                        index += 1  # porcelain -z puts rename/copy's old path next
                self.cache[key] = (tracked, states, None)
                self.repositories[key] = {
                    "head": head,
                    "state_scope": "whole owning repository; audited_files identifies compared source",
                    "dirty": any(code != "!!" for code in states.values()),
                    "tracked_changes": [{"path": n, "porcelain": c}
                                        for n, c in sorted(states.items()) if c not in {"??", "!!"}],
                    "untracked_files": sorted(n for n, c in states.items() if c == "??"),
                    "ignored_paths": sorted(n for n, c in states.items() if c == "!!"),
                    "audited_files": [],
                }
            except (OSError, subprocess.SubprocessError) as error:
                self.cache[key] = (set(), {}, str(error))
                self.repositories[key] = {"head": None, "error": str(error), "audited_files": []}
        tracked, states, error = self.cache[key]
        if error:
            return {"repository": key, "status": "unavailable", "error": error}
        name = path.relative_to(owner).as_posix()
        code = states.get(name, next((v for n, v in states.items()
                                     if n.endswith("/") and name.startswith(n)), "  "))
        is_tracked = name in tracked
        state = "ignored" if code == "!!" else "untracked" if not is_tracked else (
            "dirty" if code != "  " else "clean")
        result = {"repository": key, "path": name, "status": state,
                  "tracked": is_tracked, "porcelain": code}
        if result not in self.repositories[key]["audited_files"]:
            self.repositories[key]["audited_files"].append(result)
        return result


def reviewed_exceptions(path: Path | None, errors: list[str]) -> dict:
    if path is None:
        return {}
    result = {}
    try:
        data = read_json(path)
        if (not isinstance(data, dict) or data.get("schema_version") != 1 or
                not isinstance(data.get("exceptions"), list)):
            raise ValueError("exceptions require schema_version=1 and an exceptions list")
        for item in data["exceptions"]:
            if not isinstance(item, dict):
                raise ValueError("exception must be an object")
            name = relative_name(item.get("export_path"))
            relative_name(item.get("source_path"))
            for field in ("source_sha256", "export_sha256"):
                if not isinstance(item.get(field), str) or not HASH.fullmatch(item[field]):
                    raise ValueError(f"exception {name}: exact {field} required")
            for field in ("reviewed_by", "reason"):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    raise ValueError(f"exception {name}: {field} required")
            if name in result:
                raise ValueError(f"duplicate exception: {name}")
            result[name] = item
    except (OSError, ValueError) as error:
        errors.append(f"invalid exceptions: {error}")
        return {}
    return result


def package_roots(root: Path, manifest: dict, overrides: Sequence[str], errors: list[str]):
    revisions = manifest.get("revisions")
    if not isinstance(revisions, dict):
        errors.append("manifest.revisions must be an object")
        revisions = {}
    roots = {"ara": ".", "cheshire": "hardware/fpga/vcu118/.cache/cheshire_ara",
             "board": "hardware/fpga/vcu118/.cache/cheshire_board/target/xilinx/src"}
    for name in revisions:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            errors.append(f"invalid package namespace: {name}")
        elif name not in roots:
            roots[name] = f"hardware/deps/{name}"
    seen, ambiguous = set(), set()
    for entry in overrides:
        name, sep, location = entry.partition("=")
        if not sep or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            errors.append(f"invalid package-root: {entry!r}")
            continue
        if name in seen or name == "ara":
            ambiguous.add(name)
            errors.append(f"duplicate/prohibited package-root: {name}")
            continue
        seen.add(name)
        try:
            relative_name(location)
            safe_path(root, location)
            roots[name] = location
        except ValueError as error:
            ambiguous.add(name)
            errors.append(str(error))
    return roots, ambiguous


def source_mapping(name: str, roots: dict) -> tuple[str | None, str]:
    parts = PurePosixPath(name).parts
    if len(parts) < 3 or parts[0] != "rtl":
        return None, "unmatched export namespace"
    package, tail = parts[1], "/".join(parts[2:])
    if package == "board":
        if tail not in BOARD_FILES:
            return None, "unmatched board file (no basename search)"
        if tail == "ara_dsa_vcu118.sv":
            return "hardware/fpga/vcu118/rtl/ara_dsa_vcu118.sv", "export.py board top copy"
    if package not in roots:
        return None, "unmatched package; provide an explicit package-root"
    if package == "ara" and not tail.startswith(("hardware/src/", "hardware/include/")):
        return None, "unmatched Ara source tree"
    prefix = roots[package]
    return (tail if prefix == "." else f"{prefix}/{tail}"), "export.py namespace-relative copy"


def check_sources(source_root: Path, export_root: Path, *,
                  root_overrides: Sequence[str] = (), exceptions_path: Path | None = None) -> dict:
    source_root, export_root = source_root.resolve(), export_root.resolve()
    integrity, manifest, compiled, before, inventory, actual, ambiguous = export_inventory(export_root)
    errors = []
    roots, ambiguous_packages = package_roots(source_root, manifest, root_overrides, errors)
    exceptions = reviewed_exceptions(exceptions_path, errors)
    used_exceptions = set()
    git = GitInventory(source_root)
    files, mapped = [], set()
    # These files cannot disappear from a resealed manifest without detection.
    for name in CRITICAL_FILES:
        if name not in compiled:
            errors.append(f"required fix-bearing compilation unit missing: {name}")
    for name in sorted(inventory | set(CRITICAL_FILES)):
        source, rule = source_mapping(name, roots)
        record = {"export_path": name, "source_path": source, "mapping": rule,
                  "export_sha256": actual.get(name), "source_sha256": None,
                  "manifest_source_sha256": before.get(name),
                  "compiled": name in compiled, "known_adaptation": ADAPTATIONS.get(name),
                  "critical": CRITICAL_FILES.get(name), "review": None}
        parts = PurePosixPath(name).parts
        if name in ambiguous or (len(parts) > 1 and parts[1] in ambiguous_packages):
            record["status"] = "ambiguous_mapping"
        elif source is None:
            record["status"] = "unmatched"
        else:
            mapped.add(source)
            try:
                path = safe_path(source_root, source)
                if export_root == path or export_root in path.parents:
                    raise ValueError("source mapping points into the export itself")
                record["source_sha256"] = sha256(path)
                record["source_git"] = git.file(path)
                if record["source_git"]["status"] == "unavailable":
                    errors.append(f"Git source state unavailable: {source}")
                if record["export_sha256"] is None:
                    record["status"] = "missing_export"
                elif record["source_sha256"] == record["export_sha256"]:
                    record["status"] = "matched"
                else:
                    record["status"] = (
                        "adapted_unreviewed" if name in ADAPTATIONS and
                        record["source_sha256"] == before.get(name) else "differing")
                    review = exceptions.get(name)
                    if review is not None and all(
                        review[key].lower() == record[key] if key.endswith("sha256")
                        else review[key] == record[key]
                        for key in ("source_path", "source_sha256", "export_sha256")
                    ):
                        record["status"] = "adapted_reviewed"
                        record["review"] = review
                        used_exceptions.add(name)
            except (OSError, ValueError) as error:
                record["status"] = "missing_source" if isinstance(error, FileNotFoundError) else "unreadable_source"
                record["error"] = str(error)
        record["source_matches_manifest"] = (
            record["source_sha256"] == before[name]
            if name in before and record["source_sha256"] is not None else None)
        record["byte_equal"] = (record["source_sha256"] == record["export_sha256"]
                                if record["source_sha256"] and record["export_sha256"] else None)
        if record["status"] not in {"matched", "adapted_reviewed"}:
            errors.append(f"{record['status']}: {name}")
        files.append(record)
    for name in sorted(set(exceptions) - used_exceptions):
        errors.append(f"unused or stale exact-hash exception: {name}")

    unexported = []
    for directory in ("hardware/src", "hardware/include"):
        for source in sorted(scan_tree(source_root, directory, errors) - mapped):
            if PurePosixPath(source).suffix not in RTL_SUFFIXES:
                continue
            record = {"source_path": source, "source_sha256": None,
                      "status": "excluded" if source in SOURCE_EXCLUSIONS else "unexported",
                      "reason": SOURCE_EXCLUSIONS.get(source)}
            try:
                path = safe_path(source_root, source)
                record["source_sha256"] = sha256(path)
                record["source_git"] = git.file(path)
                if record["source_git"]["status"] == "unavailable":
                    errors.append(f"Git source state unavailable: {source}")
            except (OSError, ValueError) as error:
                record["error"] = str(error)
                errors.append(f"unreadable source: {source}: {error}")
            if source not in SOURCE_EXCLUSIONS:
                errors.append(f"unexported first-party RTL: {source}")
            unexported.append(record)
    counts = dict(sorted(Counter(r["status"] for r in files).items()))
    critical = [r for r in files if r["export_path"] in CRITICAL_FILES]
    status = "incomplete_or_different" if errors else (
        "reviewed_adaptations" if used_exceptions else "exact")
    return {
        "schema_version": 1,
        "accepted": integrity["status"] == "valid" and not errors,
        "source_root": str(source_root), "export_root": str(export_root),
        "export_integrity": integrity,
        "critical_fixes": {
            "all_byte_equal": all(r["byte_equal"] is True and r["compiled"] for r in critical),
            "differing_or_unresolved": [r["export_path"] for r in critical
                                        if r["byte_equal"] is not True or not r["compiled"]],
            "files": critical,
            "scope": "whole-file comparison, not a semantic assertion that individual fixes are correct",
        },
        "source_correspondence": {
            "status": status, "counts": counts, "files": files,
            "unexported_current_sources": unexported,
            "errors": sorted(set(errors)),
            "scope": "all packaged RTL/headers and first-party RTL; not full dependency elaboration",
        },
        "source_repositories": git.repositories,
        "package_roots": roots,
        "export_recorded_revisions": manifest.get("revisions"),
        "exceptions": {"path": str(exceptions_path) if exceptions_path else None,
                       "used": sorted(used_exceptions)},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--export-root", type=Path,
                        help=f"default: SOURCE_ROOT/{DEFAULT_EXPORT}")
    parser.add_argument("--package-root", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--exceptions", type=Path)
    parser.add_argument("--output", type=Path, help="also save JSON; destination must not exist")
    args = parser.parse_args(argv)
    if args.output is not None and (args.output.exists() or args.output.is_symlink()):
        print(f"refusing to overwrite existing result: {args.output}", file=sys.stderr)
        return 2
    result = check_sources(args.source_root, args.export_root or args.source_root / DEFAULT_EXPORT,
                           root_overrides=args.package_root, exceptions_path=args.exceptions)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        try:
            output = args.output.absolute()
            resolved_output = output.resolve()
            source = Path(result["source_root"])
            protected = [Path(result["export_root"]), source / "hardware/src",
                         source / "hardware/include", source / "hardware/includes",
                         source / "hardware/deps", source / "hardware/fpga/vcu118/rtl"]
            protected.extend((source / p).resolve() for p in result["package_roots"].values()
                             if p != ".")
            if any(resolved_output == p or p in resolved_output.parents for p in protected):
                raise ValueError("report output must not be inside export or source trees")
            output.parent.mkdir(parents=True, exist_ok=True)
            # 'x' also refuses a file created after the preflight existence check.
            with output.open("x", encoding="utf-8") as stream:
                stream.write(payload)
        except (OSError, ValueError) as error:
            print(f"cannot save audit result: {error}", file=sys.stderr)
            return 2
    print(payload, end="")
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

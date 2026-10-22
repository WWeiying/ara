#!/usr/bin/env python3
"""Read-only, local VCU118 inventory, NOT FPGA/Linux signoff.

Never launches a subprocess, imports a UART driver, opens a device, contacts a
server, or extracts an image. Only --output writes, exclusively under the selected
worktree's verification/fpga directory. Missing means absent in the stated scope;
unknown means unobserved, unreadable, unsafe, or beyond a bound. Available means
bytes were identified, not that an image boots or a board works.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
EXPORT = Path("hardware/fpga/ara_dsa_vcu118")
SDK = Path("/home/wangwy/openproject/cva6/cva6-sdk")
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 50000
TOOLS = ("vivado", "hw_server", "openocd", "dtc", "cpio", "readelf",
         "riscv64-linux-gnu-gcc", "riscv64-unknown-elf-gcc", "qemu-system-riscv64")
QUESTION = (
    "Which host owns the VCU118, what is its CP2105 Enhanced UART path/COM port "
    "and JTAG cable or hw_server endpoint, and where are the matching .bit/.ltx "
    "and export/build manifest (including boot baud)?"
)


def local_path(root: Path, path: Path) -> Path:
    path = Path(os.path.abspath(path if path.is_absolute() else root / path))
    path.relative_to(root)
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"symlink not followed: {current}")
    return path


def regular_open(root: Path, path: Path):
    path = local_path(root, path)
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("not a regular file; not opened")
    # NONBLOCK prevents a substituted FIFO from hanging before fstat rejects it.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("not a regular file")
        if info.st_size > MAX_FILE_BYTES:
            raise ValueError(f"file exceeds {MAX_FILE_BYTES}-byte inspection bound")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def artifact(root: Path, path: Path) -> dict:
    record = {"path": str(path if path.is_absolute() else root / path)}
    try:
        # Reject special files before open, as well as checking the opened fd.
        path = local_path(root, path)
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("not a regular file; not opened")
        with regular_open(root, path) as stream:
            before = os.fstat(stream.fileno())
            digest = hashlib.sha256()
            head = stream.read(64)
            digest.update(head)
            total = len(head)
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                total += len(chunk)
                if total > MAX_FILE_BYTES:
                    raise ValueError("file grew beyond inspection bound")
                digest.update(chunk)
            after = os.fstat(stream.fileno())
        current = local_path(root, path).stat()
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size,
                                 info.st_mtime_ns, info.st_ctime_ns)
        if identity(before) != identity(after) or identity(after) != identity(current):
            raise ValueError("file changed during inspection")
        if not total:
            raise ValueError("empty file is not an available payload")
        record.update(status="available", size_bytes=total, sha256=digest.hexdigest())
        if head.startswith(b"\x7fELF") and len(head) >= 24:
            record["format_hint"] = {
                "elf_class": head[4], "elf_data_encoding": head[5],
                "machine": int.from_bytes(head[18:20], "little" if head[5] == 1 else "big"),
                "scope": "header hint only; not ELF loadability or runtime ABI validation",
            }
    except FileNotFoundError:
        record.update(status="missing", reason="absent at inspected path")
    except (OSError, ValueError) as error:
        record.update(status="unknown", reason=str(error))
    return record


def json_record(root: Path, path: Path) -> dict:
    record = artifact(root, path)
    if record["status"] == "available":
        try:
            with regular_open(root, path) as stream:
                raw = stream.read()
            if hashlib.sha256(raw).hexdigest() != record["sha256"]:
                raise ValueError("JSON changed after hashing")
            record["content"] = json.loads(raw.decode("utf-8-sig"))
        except (OSError, ValueError) as error:
            record.update(status="unknown", reason=str(error))
    return record


def scan(root: Path, directories: list[Path]) -> dict:
    records, errors, skipped, count = [], [], [], 0
    for directory in directories:
        try:
            directory = local_path(root, directory)
            if not directory.exists():
                continue
            def onerror(error):
                errors.append(str(error))
            for parent, dirs, files in os.walk(directory, followlinks=False, onerror=onerror):
                for name in dirs[:]:
                    child = Path(parent) / name
                    if name in {".git", "__pycache__"} or child.is_symlink():
                        skipped.append(str(child))
                        dirs.remove(name)
                for name in files:
                    count += 1
                    if count > MAX_ENTRIES:
                        raise ValueError(f"scan reached {MAX_ENTRIES}-entry bound")
                    path = Path(parent) / name
                    if path.suffix.lower() in {".bit", ".ltx", ".dcp", ".gguf"}:
                        records.append(artifact(root, path))
        except (OSError, ValueError) as error:
            errors.append(str(error))
    return {"roots": [str(p) for p in directories], "artifacts": records,
            "errors": errors, "skipped_directories": skipped, "files_examined": count,
            "scope": "local non-symlink trees only; remote/shared locations not searched"}


def directory_entries(path: Path) -> tuple[list[Path], dict]:
    try:
        return sorted(path.iterdir()), {"status": "available", "path": str(path)}
    except FileNotFoundError:
        return [], {"status": "missing", "path": str(path)}
    except OSError as error:
        return [], {"status": "unknown", "path": str(path), "reason": str(error)}


def metadata(path: Path) -> dict:
    """stat/readlink only, including for device nodes and external SDK tools."""
    result = {"path": str(path)}
    try:
        info = path.lstat()
        result.update(status="available", mode=stat.filemode(info.st_mode))
        if stat.S_ISLNK(info.st_mode):
            result["target"] = os.readlink(path)
            result["target_status"] = "unknown"
            try:
                result["target_mode"] = stat.filemode(path.stat().st_mode)
                result["target_status"] = "available"
            except FileNotFoundError:
                result["target_status"] = "missing"
        result["executable"] = os.access(path, os.X_OK) if not stat.S_ISCHR(info.st_mode) else None
    except FileNotFoundError:
        result["status"] = "missing"
    except OSError as error:
        result.update(status="unknown", reason=str(error))
    return result


def board_hints(dev: Path, sysfs: Path) -> dict:
    listings, uart = [], []
    for directory in (dev, dev / "serial/by-id", dev / "serial/by-path"):
        entries, record = directory_entries(directory)
        listings.append(record)
        for path in entries:
            if directory != dev or path.name.startswith(("ttyUSB", "ttyACM")):
                uart.append(metadata(path))
    tty, tty_listing = directory_entries(sysfs / "class/tty")
    tty_hints = [metadata(p / "device") for p in tty
                 if p.name.startswith(("ttyUSB", "ttyACM"))]
    usb, usb_listing = directory_entries(sysfs / "bus/usb/devices")
    devices = []
    for path in usb:
        if ":" in path.name:
            continue  # USB interfaces do not carry device-level VID/PID.
        fields = {}
        for field in ("idVendor", "idProduct", "manufacturer", "product", "serial"):
            candidate = path / field
            try:
                resolved = candidate.resolve()
                resolved.relative_to(sysfs.resolve())
                with regular_open(sysfs.resolve(), resolved) as stream:
                    fields[field] = {"status": "available",
                                     "value": stream.read(4096).decode("utf-8", "replace").strip()}
            except FileNotFoundError:
                fields[field] = {"status": "missing"}
            except (OSError, ValueError) as error:
                fields[field] = {"status": "unknown", "reason": str(error)}
        vid = fields["idVendor"].get("value")
        devices.append({"path": str(path), "attributes": fields,
                        "hint": {"10c4": "Silicon Labs UART candidate",
                                 "0403": "FTDI candidate; function unconfirmed",
                                 "1443": "Digilent JTAG candidate",
                                 "03fd": "Xilinx JTAG candidate"}.get(vid),
                        "board_identity": "unknown"})
    return {"uart_listings": listings, "uart_nodes": uart,
            "tty_listing": tty_listing, "tty_devices": tty_hints,
            "usb_listing": usb_listing, "usb_devices": devices,
            "board_identity": "unknown", "jtag_connectivity": "unknown",
            "programmed_bitstream": "unknown", "ddr_calibration": "unknown",
            "linux_boot": "unknown", "question": QUESTION,
            "scope": "directory/stat/readlink and whitelisted sysfs text only; no device opened"}


def tool_inventory(search_path: str, sdk: Path) -> dict:
    tools = {}
    for name in TOOLS:
        candidates = [metadata(Path(folder or ".") / name) for folder in search_path.split(os.pathsep)]
        found = [p for p in candidates if p["status"] == "available" and p.get("executable")
                 and p.get("target_mode", p["mode"])[0] == "-"
                 and p.get("target_status", "available") == "available"]
        tools[name] = {"status": "available" if found else (
            "unknown" if any(p["status"] == "unknown" for p in candidates) else "missing"),
            "candidates": found, "scope": "PATH only, never executed", "version": "unknown"}
    paths = {
        "linux_cc": "buildroot/output/host/bin/riscv64-buildroot-linux-gnu-gcc",
        "linux_readelf": "buildroot/output/host/bin/riscv64-buildroot-linux-gnu-readelf",
        "linux_strip": "buildroot/output/host/bin/riscv64-buildroot-linux-gnu-strip",
        "kernel": "install64_qemu/Image", "opensbi_makefile": "buildroot/output/build/opensbi-1.7/Makefile",
        "busybox": "buildroot/output/target/bin/busybox",
        "loader": "buildroot/output/target/lib/ld-linux-riscv64-lp64d.so.1",
        "libc": "buildroot/output/target/lib/libc.so.6",
        "libresolv": "buildroot/output/target/lib/libresolv.so.2",
    }
    return {"path_tools": tools, "sdk_root": str(sdk),
            "sdk_hints": {k: metadata(sdk / v) for k, v in paths.items()},
            "sdk_scope": "metadata only; no compiler execution or SDK content reads"}


def audit(root: Path, *, dev: Path, sysfs: Path, search_path: str, sdk: Path,
          linux_dir: Path | None = None, replay_elf: Path | None = None,
          bitstream: Path | None = None, llama_elf: Path | None = None,
          model: Path | None = None) -> dict:
    root = root.resolve()
    export = root / EXPORT
    linux_dir = linux_dir or export / "linux/artifacts"
    manifest = json_record(root, export / "manifest.json")
    inventory = scan(root, [root / "hardware/fpga", root / "hardware/build",
                            root / "verification/out", root / "apps/bin"])
    if bitstream:
        inventory["artifacts"].append(artifact(root, bitstream))
    images = {name: artifact(root, linux_dir / name)
              for name in ("fw_jump.elf", "Image", "ara_vcu118.dtb", "initramfs.cpio", "SHA256SUMS")}
    replay = artifact(root, replay_elf or root / "apps/bin/rv64uv-ara-vfredmax_boundary")
    combined = export / "software/qwen_small_combined"
    optional = lambda path: artifact(root, path) if path else {
        "status": "unknown", "reason": "no explicit path selected; not inferred from a marker"}
    board = board_hints(dev, sysfs)
    blockers = []
    for name, record in (("export_manifest", manifest),
                         ("export_checksums", artifact(root, export / "SHA256SUMS"))):
        if record["status"] != "available":
            blockers.append({"id": name, "status": record["status"], "reason": record["path"]})
    runtime = {"status": "unknown", "reason": "requires ELF/runtime inspection; see REPLAY.md"}
    if replay.get("sha256") == "98a007e64cb2187bc077b6798a0cc583b6340acf309fb90f451fcd9c400648a5":
        runtime = {"status": "blocked", "reason": "exact audited simulation ELF uses simulation SP/EOC/UART MMIO, not the board runtime"}
        blockers.append({"id": "verification_elf_runtime", **runtime})
    bits = [p for p in inventory["artifacts"] if Path(p["path"]).suffix.lower() == ".bit"]
    if not any(p["status"] == "available" for p in bits):
        blockers.append({"id": "local_bitstream", "status": "unknown" if bits or inventory["errors"] else "missing",
                         "reason": "no hashed bitstream in inspected trees; remote board host unknown"})
    for name, record in images.items():
        if record["status"] != "available":
            blockers.append({"id": f"linux:{name}", "status": record["status"], "reason": record["path"]})
    if images["initramfs.cpio"].get("sha256") == "e98ae673a251ee2ddf362fb3f18fd2ac12b7625c7087d2af2842857230b6106a":
        blockers.append({"id": "historical_initramfs", "status": "blocked",
                         "reason": "exact audited image lacks lib64 -> lib; see READINESS.md; rebuild DTB and embedded firmware together"})
    unknowns = ["bitstream/export/current-source correspondence", "bitstream timing/CDC signoff",
                "board identity and programmed image", "DDR/reset and Linux boot",
                "DTB/initramfs/embedded firmware consistency", "FPGA signature replay transport",
                "Linux QBS/AKV compute and hidden-state isolation", "llama.cpp/model ABI and memory budget"]
    return {"schema_version": 1, "kind": "read_only_readiness_inventory",
            "observed_utc": datetime.now(timezone.utc).isoformat(), "root": str(root),
            "status": "BLOCKED" if blockers else "UNVERIFIED", "ready_for_signoff": False,
            "export": {"manifest": manifest, "checksums": artifact(root, export / "SHA256SUMS"),
                       "integrity": "unknown: run check_sources.py separately; manifest revisions are claims",
                       "source_correspondence": "unknown: requires fresh check_sources.py evidence"},
            "build_inventory": inventory, "linux_images": images,
            "replay": {"verification_elf": replay, "runtime_compatibility": runtime,
                       "board_operator_elf": artifact(root, combined / "qbs_akv.elf"),
                       "case": json_record(root, combined / "case.json"),
                       "provenance_claims": json_record(root, combined / "provenance.json")},
            "llama_cpp": {"executable": optional(llama_elf), "model": optional(model)},
            "board": board, "tools": tool_inventory(search_path, sdk),
            "verification_gates": {
                "linux_rvv_userspace": {
                    "status": "unknown", "target": "VCU118",
                    "requires": "board arithmetic/load-store, preemption, signal and fault-return evidence",
                    "excludes": "custom query, QBS/AKV compute, and hidden persistent contexts",
                },
                "custom_query": {
                    "status": "unknown", "target": "VCU118",
                    "requires": "actual query results; SIGILL means unavailable, never compute success",
                },
                "qbs_akv_compute": {
                    "status": "unknown", "target": "Linux userspace on VCU118",
                    "requires": "real llama.cpp input/golden comparison and native dispatch evidence",
                    "excludes": "CUSTOM_COMPUTE=NOT_VALIDATED and query-only tests",
                },
                "shared_ddr_mmu_cache": {
                    "status": "unknown",
                    "requires": "translation/permissions, page faults, ordering, cache visibility and shared DDR correctness",
                },
                "hidden_context_isolation": {
                    "status": "unknown",
                    "requires": "OS task/address-space ownership and save/restore or drain/invalidate/rebuild policy; stale-token rejection",
                    "excludes": "ordinary RVV register save/restore and VLSU transaction arbitration",
                },
            },
            "blockers": blockers, "unknowns": unknowns,
            "limitations": ["No marker, historical report or filename proves execution success.",
                            "SHA-256 identifies bytes, not provenance, validity or bootability.",
                            "No subprocess, device I/O, network, synthesis or programming performed."]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dev-root", type=Path, default=Path("/dev"))
    parser.add_argument("--sys-root", type=Path, default=Path("/sys"))
    parser.add_argument("--sdk", type=Path, default=SDK)
    for name in ("linux-dir", "replay-elf", "bitstream", "llama-elf", "model"):
        parser.add_argument(f"--{name}", type=Path)
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        output = local_path(root, args.output)
        output.relative_to(root / "verification/fpga")
        if output.exists():
            raise ValueError(f"refusing to overwrite: {output}")
        result = audit(root, dev=args.dev_root, sysfs=args.sys_root,
                       search_path=os.environ.get("PATH", ""), sdk=args.sdk,
                       linux_dir=args.linux_dir, replay_elf=args.replay_elf,
                       bitstream=args.bitstream, llama_elf=args.llama_elf, model=args.model)
        output.parent.mkdir(parents=True, exist_ok=True)
        local_path(root, output)
        with output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "ready_for_signoff": False,
                      "output": str(output), "blockers": result["blockers"]}, sort_keys=True))
    return 1  # An offline inventory can never establish board signoff.


if __name__ == "__main__":
    raise SystemExit(main())

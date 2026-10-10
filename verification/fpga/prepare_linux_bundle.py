#!/usr/bin/env python3
"""Build an isolated VCU118 Linux handoff from the existing checked initramfs.

Software compilation only. No FPGA, serial, JTAG or emulator access. Success
means matched files and load geometry, not board boot or custom compute.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
SDK = Path("/home/wangwy/openproject/cva6/cva6-sdk")
EXPORT = Path("hardware/fpga/ara_dsa_vcu118")
CHECKED_INITRAMFS = Path("verification/out/linux-userspace-20260922/payload-checked/initramfs.cpio")
CHECKED_SHA256 = "6ef0ee1a3f279b59d628c5e1ba435125d0b0b0eaeb12b265db387948ccf26ef3"
FW_ADDR, DTB_ADDR, KERNEL_ADDR, INITRD_ADDR = 0x80000000, 0x80100000, 0x80200000, 0x88000000
DDR_END = 0x100000000
SOURCE_EXCLUDES = {"build", ".git"}
HOST_PATH = "/usr/bin:/bin"


def plain_path(path: Path) -> Path:
    """Reject symlinks in every existing component, before any write/open."""
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        if part.is_symlink():
            raise ValueError(f"symlink path is not allowed: {part}")
    return path


def make_path(path: Path | str) -> str:
    value = str(path)
    # OpenSBI expands these values in shell recipes without quoting them.
    if not re.fullmatch(r"/[A-Za-z0-9_./+\-]+", value):
        raise ValueError(f"path unsafe for OpenSBI make recipes: {value!r}")
    return value


def file_record(path: Path) -> dict:
    path = plain_path(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"not a regular file: {path}")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"not a regular file: {path}")
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    key = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if key(info) != key(before) or key(before) != key(after) or key(after) != key(path.stat()):
        raise ValueError(f"input changed while reading: {path}")
    return {"path": str(path), "size_bytes": after.st_size, "sha256": digest.hexdigest()}


def unchanged(record: dict) -> None:
    if file_record(Path(record["path"])) != record:
        raise ValueError(f"input changed: {record['path']}")


def copy_checked(record: dict, destination: Path) -> None:
    unchanged(record)
    plain_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Path(record["path"]).open("rb") as incoming, destination.open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing)
    copied = file_record(destination)
    if (copied["sha256"], copied["size_bytes"]) != (record["sha256"], record["size_bytes"]):
        raise ValueError(f"copy mismatch: {destination}")
    unchanged(record)


def tree_records(source: Path, *, exclude_build: bool = True) -> dict:
    source = plain_path(source)
    if not source.is_dir():
        raise ValueError(f"missing OpenSBI source directory: {source}")
    records = {}
    def onerror(error):
        raise error
    for directory, dirs, files in os.walk(source, followlinks=False, onerror=onerror):
        if Path(directory) == source and exclude_build:
            dirs[:] = [name for name in dirs if name not in SOURCE_EXCLUDES]
        for name in dirs + files:
            path = plain_path(Path(directory) / name)
            if name in files:
                relative = path.relative_to(source).as_posix()
                records[relative] = {**file_record(path), "mode": stat.S_IMODE(path.stat().st_mode)}
    if not records:
        raise ValueError("empty OpenSBI source tree")
    return records


def tree_digest(records: dict) -> str:
    content = {name: {k: row[k] for k in ("sha256", "size_bytes", "mode")}
               for name, row in records.items()}
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def freeze_source(source: Path, destination: Path, records: dict) -> None:
    destination.mkdir()
    for name, row in records.items():
        copy_checked({k: row[k] for k in ("path", "size_bytes", "sha256")}, destination / name)
        (destination / name).chmod(row["mode"])
    if tree_digest(tree_records(destination)) != tree_digest(records):
        raise ValueError("OpenSBI snapshot mismatch")
    if tree_records(source) != records:
        raise ValueError("OpenSBI source changed while snapshotting")


def native_tool(name: str) -> dict:
    found = shutil.which(name, path=HOST_PATH)
    if not found:
        raise ValueError(f"missing executable: {name}")
    # Keep argv[0]: Buildroot's gcc symlink selects the actual compiler by name.
    invoked = Path(os.path.abspath(found))
    resolved = invoked.resolve(strict=True)
    record = file_record(resolved)
    return {"argv0": str(invoked), "resolved": record,
            "symlink_target": os.readlink(invoked) if invoked.is_symlink() else None}


class NativeRunner:
    def __init__(self, output: Path, environment: dict, commands: list):
        self.output, self.environment, self.commands = output, environment, commands
        (output / "logs").mkdir()

    def run(self, argv: list[str], cwd: Path, label: str, timeout: int = 300) -> str:
        if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or not x for x in argv):
            raise ValueError("native argv must be a nonempty list of nonempty strings")
        stem = f"{len(self.commands):03d}-{label}"
        stdout, stderr = self.output / "logs" / (stem + ".stdout"), self.output / "logs" / (stem + ".stderr")
        command = {"argv": argv, "cwd": str(cwd), "stdout": str(stdout), "stderr": str(stderr)}
        self.commands.append(command)
        start = time.monotonic()
        with stdout.open("xb") as out, stderr.open("xb") as err:
            with subprocess.Popen(argv, cwd=cwd, env=self.environment,
                                  stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                  start_new_session=True, umask=0o022) as process:
                try:
                    process.wait(timeout=timeout)
                except BaseException:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    raise
                finally:
                    command.update(returncode=process.returncode, elapsed_s=time.monotonic() - start)
        if process.returncode:
            raise ValueError(f"native helper failed ({process.returncode}): {label}; see {stderr}")
        return stdout.read_text(encoding="utf-8")


def make_argv(make: str, source: Path, build: Path, prefix: str, dtb: Path, dtc: str,
              jobs: int, quiet_opensbi: bool = False) -> list[str]:
    if not 1 <= jobs <= 32:
        raise ValueError("jobs must be between 1 and 32")
    argv = [make, "-C", make_path(source), f"-j{jobs}", f"O={make_path(build)}",
            "PLATFORM=generic", "PLATFORM_RISCV_XLEN=64", f"CROSS_COMPILE={make_path(prefix)}",
            f"DTC={make_path(dtc)}", f"FW_TEXT_START={FW_ADDR:#x}", f"FW_FDT_PATH={make_path(dtb)}",
            "FW_JUMP=y", "FW_DYNAMIC=n", "FW_PAYLOAD=n",
            f"FW_JUMP_ADDR={KERNEL_ADDR:#x}", f"FW_JUMP_FDT_ADDR={DTB_ADDR:#x}"]
    if quiet_opensbi:
        argv.append("FW_OPTIONS=0x1")
    return [*argv, "all"]


def render_dts(template: str, initrd_size: int, ram_end: int = DDR_END) -> str:
    if initrd_size <= 0 or INITRD_ADDR + initrd_size > ram_end:
        raise ValueError("initramfs size is empty or outside DDR")
    if any(template.count(token) != 1 for token in ("__INITRD_START__", "__INITRD_END__")):
        raise ValueError("template must contain exactly one of each initrd placeholder")
    return template.replace("__INITRD_START__", hex(INITRD_ADDR)).replace(
        "__INITRD_END__", hex(INITRD_ADDR + initrd_size))


def cells(text: str, count: int) -> list[int]:
    words = text.split()
    if len(words) != count or any(not re.fullmatch(r"[0-9a-fA-F]{1,8}", w) for w in words):
        raise ValueError(f"invalid fdtget cells: {text!r}")
    return [int(word, 16) for word in words]


def validate_dtb(run: NativeRunner, fdtget: str, dtb: Path, initrd_size: int,
                 ram_end: int = DDR_END) -> dict:
    expected = {("/chosen", "linux,initrd-start"): [0, INITRD_ADDR],
                ("/chosen", "linux,initrd-end"): [0, INITRD_ADDR + initrd_size],
                ("/memory@80000000", "reg"): [0, FW_ADDR, 0, ram_end - FW_ADDR]}
    observed = {}
    for (node, prop), values in expected.items():
        result = cells(run.run([fdtget, "-t", "x", str(dtb), node, prop], dtb.parent, "fdtget"), len(values))
        if result != values:
            raise ValueError(f"DTB {node}/{prop} mismatch: {result} != {values}")
        observed[f"{node}/{prop}"] = result
    return observed


def parse_readelf(text: str, file_size: int) -> dict:
    required = (r"Class:\s+ELF64\s*$", r"Data:.*little endian\s*$",
                r"Type:\s+EXEC\b", r"Machine:\s+RISC-V\s*$")
    if not all(re.search(pattern, text, re.M) for pattern in required):
        raise ValueError("firmware must be an ELF64 little-endian RISC-V executable")
    entry_match = re.search(r"Entry point address:\s+(0x[0-9a-fA-F]+)\s*$", text, re.M)
    if not entry_match or int(entry_match[1], 16) != FW_ADDR:
        raise ValueError("firmware entry is not 0x80000000")
    segments = []
    for line in text.splitlines():
        if not line.strip().startswith("LOAD"):
            continue
        words = line.split()
        if len(words) < 8 or words[0] != "LOAD" or not all(
                re.fullmatch(r"0x[0-9a-fA-F]+", w) for w in [*words[1:6], words[-1]]):
            raise ValueError(f"malformed readelf LOAD: {line}")
        offset, virtual, physical, filesz, memsz, align = [int(w, 16) for w in [*words[1:6], words[-1]]]
        flags = "".join(words[6:-1])
        if not flags or any(c not in "RWE" for c in flags) or virtual != physical:
            raise ValueError("unsupported LOAD flags or virtual/physical address mismatch")
        if not memsz or filesz > memsz or offset + filesz > file_size:
            raise ValueError("invalid or truncated LOAD size")
        if align < 1 or align & (align - 1) or physical % align != offset % align:
            raise ValueError("misaligned LOAD")
        if not FW_ADDR <= physical < physical + memsz <= DTB_ADDR:
            raise ValueError("firmware LOAD is outside its reserved DDR region")
        if memsz > 64 * 1024 * 1024:
            raise ValueError("LOAD exceeds UART loader bound")
        segments.append({"address": physical, "offset": offset, "file_bytes": filesz,
                         "memory_bytes": memsz, "flags": flags, "alignment": align})
    if not segments or not any(s["address"] <= FW_ADDR < s["address"] + s["file_bytes"] and
                               "E" in s["flags"] for s in segments):
        raise ValueError("missing executable LOAD containing entry")
    nonoverlap([{**s, "size_bytes": s["memory_bytes"]} for s in segments])
    symbols = {}
    for line in text.splitlines():
        words = line.split()
        if len(words) == 8 and words[-1] in {"fw_fdt_bin", "_jump_addr"}:
            if words[-1] in symbols or words[-2] in {"UND", "ABS"} or not re.fullmatch(r"[0-9a-fA-F]+", words[1]):
                raise ValueError("missing/ambiguous firmware symbol")
            symbols[words[-1]] = int(words[1], 16)
    if set(symbols) != {"fw_fdt_bin", "_jump_addr"}:
        raise ValueError("firmware must retain fw_fdt_bin and _jump_addr symbols")
    return {"entry": FW_ADDR, "segments": segments, "symbols": symbols}


def nonoverlap(regions: list[dict]) -> None:
    regions = sorted(regions, key=lambda r: r["address"])
    for row in regions:
        if not row["size_bytes"] or not FW_ADDR <= row["address"] < row["address"] + row["size_bytes"] <= DDR_END:
            raise ValueError("empty or out-of-DDR load region")
    for left, right in zip(regions, regions[1:]):
        if left["address"] + left["size_bytes"] > right["address"]:
            raise ValueError("overlapping load regions")


def validate_embedded(elf: Path, dtb: Path, parsed: dict) -> dict:
    data, blob = plain_path(elf).read_bytes(), plain_path(dtb).read_bytes()
    def at_symbol(name, size):
        address = parsed["symbols"][name]
        for row in parsed["segments"]:
            if row["address"] <= address and address + size <= row["address"] + row["file_bytes"]:
                offset = row["offset"] + address - row["address"]
                return data[offset:offset + size], offset
        raise ValueError(f"symbol {name} is outside file-backed LOAD bytes")
    embedded, offset = at_symbol("fw_fdt_bin", len(blob))
    if not blob or embedded != blob:
        raise ValueError("embedded DTB does not match external DTB")
    jump, _ = at_symbol("_jump_addr", 8)
    if int.from_bytes(jump, "little") != KERNEL_ADDR:
        raise ValueError("embedded firmware kernel jump target mismatch")
    return {"dtb_sha256": hashlib.sha256(embedded).hexdigest(), "file_offset": offset,
            "address": parsed["symbols"]["fw_fdt_bin"], "size_bytes": len(embedded),
            "kernel_jump_address": KERNEL_ADDR}


def save_json(path: Path, value: dict) -> None:
    with plain_path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def prepare_bundle(output: Path, *, root: Path = ROOT, sdk: Path = SDK,
                   initramfs: Path | None = None, kernel: Path | None = None,
                   template: Path | None = None, opensbi: Path | None = None,
                   jobs: int = 4, sim_ram_mib: int = 2048,
                   quiet_opensbi: bool = False) -> dict:
    root, sdk, output = plain_path(root), plain_path(sdk), plain_path(output)
    output.relative_to(root / "verification/out")
    if output == root / "verification/out":
        raise ValueError("select a new bundle directory, not verification/out itself")
    make_path(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"output must be new or empty: {output}")
    if not 1 <= jobs <= 32:
        raise ValueError("jobs must be between 1 and 32")
    if sim_ram_mib not in (256, 512, 1024, 2048):
        raise ValueError("simulation RAM must be 256, 512, 1024 or 2048 MiB")
    ram_end = FW_ADDR + sim_ram_mib * 1024 * 1024
    source = plain_path(opensbi or sdk / "buildroot/output/build/opensbi-1.7")
    paths = {"initramfs": initramfs or root / CHECKED_INITRAMFS,
             "kernel": kernel or sdk / "install64_qemu/Image",
             "template": template or root / EXPORT / "linux/ara_vcu118.dts.in",
             "original_builder": root / EXPORT / "linux/build_linux_bringup.sh",
             "preparer": Path(__file__).absolute()}
    for path in [source, sdk, *paths.values()]:
        path = plain_path(path)
        if path == output or path in output.parents or output in path.parents:
            raise ValueError(f"output and input must be independent: {path}")
    inputs = {name: file_record(path) for name, path in paths.items()}
    if any(not row["size_bytes"] for row in inputs.values()):
        raise ValueError("empty bundle input")
    if inputs["initramfs"]["sha256"] != CHECKED_SHA256:
        raise ValueError("checked initramfs SHA-256 mismatch; refusing a different rootfs")
    sources = tree_records(source)
    for required in ("Makefile", "platform/generic/configs/defconfig", "firmware/fw_base.S", "include/sbi/sbi_version.h"):
        if required not in sources:
            raise ValueError(f"OpenSBI source missing {required}")
    version = (source / "include/sbi/sbi_version.h").read_text()
    if not all(re.search(rf"^#define OPENSBI_VERSION_{field}\s+{value}\s*$", version, re.M)
               for field, value in (("MAJOR", 1), ("MINOR", 7))):
        raise ValueError("OpenSBI 1.7 sources required")
    prefix = make_path(sdk / "buildroot/output/host/bin/riscv64-buildroot-linux-gnu-")
    native_names = ["make", "dtc", "fdtget", "python3"]
    if sim_ram_mib != 2048:
        native_names.append("fdtput")
    tools = {name: native_tool(name) for name in native_names}
    tools.update({name: native_tool(prefix + name) for name in ("gcc", "gcc.br_real", "as", "ld", "ar", "objcopy", "readelf", "strip")})
    tool = lambda name: tools[name]["argv0"]
    # Only this output is written. No make target runs in the SDK source tree.
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".prepare.lock").open("x"):
        pass
    manifest = {"schema_version": 1, "status": "PREPARING", "board_boot": "NOT_RUN",
                "custom_compute": "NOT_VALIDATED", "inputs": inputs, "tools": tools,
                "sim_ram_mib": sim_ram_mib, "quiet_opensbi": quiet_opensbi,
                "source": {"path": str(source), "tree_sha256": tree_digest(sources),
                           "excluded_top_level": sorted(SOURCE_EXCLUDES), "files": sources},
                "commands": []}
    try:
        (output / "inputs").mkdir()
        (output / "tmp").mkdir()
        frozen = output / "inputs/opensbi-1.7"
        freeze_source(source, frozen, sources)
        for key, name in (("initramfs", "initramfs.cpio"), ("kernel", "Image"),
                          ("template", "inputs/ara_vcu118.dts.in"),
                          ("original_builder", "inputs/build_linux_bringup.sh"),
                          ("preparer", "inputs/prepare_linux_bundle.py")):
            copy_checked(inputs[key], output / name)
        environment = {"PATH": HOST_PATH,
                       "LC_ALL": "C", "TZ": "UTC", "SOURCE_DATE_EPOCH": "0",
                       "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(output / "tmp"),
                       "TMPDIR": str(output / "tmp"), "GIT_CONFIG_NOSYSTEM": "1",
                       "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CEILING_DIRECTORIES": str(output)}
        manifest["environment"] = environment
        runner = NativeRunner(output, environment, manifest["commands"])
        size = inputs["initramfs"]["size_bytes"]
        dts, dtb = output / "ara_vcu118.dts", output / "ara_vcu118.dtb"
        with dts.open("x", encoding="ascii") as stream:
            stream.write(render_dts((output / "inputs/ara_vcu118.dts.in").read_text(), size,
                                    ram_end))
        runner.run([tool("dtc"), "-I", "dts", "-O", "dtb", "-o", str(dtb), str(dts)], output, "dtc")
        if sim_ram_mib != 2048:
            runner.run([tool("fdtput"), "-t", "x", str(dtb), "/memory@80000000", "reg",
                        "0", f"{FW_ADDR:x}", "0", f"{ram_end - FW_ADDR:x}"], output, "fdtput")
        dtb_identity = file_record(dtb)
        manifest["dtb_properties"] = validate_dtb(runner, tool("fdtget"), dtb, size,
                                                   ram_end)
        # Discover the compiler backend actually selected by the wrapper.
        cc1 = runner.run([tool("gcc"), "-print-prog-name=cc1"], output, "compiler-backend").strip()
        tools["cc1"] = native_tool(cc1)
        build = output / "opensbi-build"
        build.mkdir()
        runner.run(make_argv(tool("make"), frozen, build, prefix, dtb, tool("dtc"), jobs,
                             quiet_opensbi), output, "opensbi")
        unchanged(dtb_identity)
        built = build / "platform/generic/firmware/fw_jump.elf"
        elf = output / "fw_jump.elf"
        copy_checked(file_record(built), elf)
        runner.run([tool("strip"), "--strip-debug", str(elf)], output, "strip")
        elf_identity = file_record(elf)
        text = runner.run([tool("readelf"), "-h", "-lW", "-sW", str(elf)], output, "readelf")
        parsed = parse_readelf(text, elf_identity["size_bytes"])
        manifest["embedded_dtb"] = validate_embedded(elf, dtb, parsed)
        regions = [{"name": f"firmware_LOAD_{i}", "address": s["address"], "size_bytes": s["memory_bytes"]}
                   for i, s in enumerate(parsed["segments"])]
        regions += [{"name": name, "address": address, "size_bytes": file_record(output / name)["size_bytes"]}
                    for name, address in (("ara_vcu118.dtb", DTB_ADDR), ("Image", KERNEL_ADDR), ("initramfs.cpio", INITRD_ADDR))]
        nonoverlap(regions)
        if any(region["address"] + region["size_bytes"] > ram_end for region in regions):
            raise ValueError("boot artifact extends beyond simulation RAM")
        manifest["elf"] = parsed
        manifest["load_regions"] = regions
        unchanged(elf_identity)
        unchanged(dtb_identity)
        for record in inputs.values():
            unchanged(record)
        for key, name in (("initramfs", "initramfs.cpio"), ("kernel", "Image")):
            if file_record(output / name)["sha256"] != inputs[key]["sha256"]:
                raise ValueError(f"copied {name} changed during build")
        if tree_records(source) != sources or tree_digest(tree_records(frozen)) != tree_digest(sources):
            raise ValueError("OpenSBI source/snapshot changed during build")
        for record in tools.values():
            if native_tool(record["argv0"]) != record:
                raise ValueError(f"native tool changed: {record['argv0']}")
        manifest["inputs_unchanged"] = True
        manifest["source"]["snapshot"] = str(frozen)
        # Identify all generated build products/configuration/logs, not just the
        # final ELF; this excludes only the manifest and its own checksum list.
        manifest["files"] = tree_records(output, exclude_build=False)
        with (output / "SHA256SUMS").open("x", encoding="ascii") as stream:
            for name, row in sorted(manifest["files"].items()):
                stream.write(f"{row['sha256']}  {name}\n")
        manifest["checksum_list"] = file_record(output / "SHA256SUMS")
        manifest["status"] = "PREPARED_NOT_BOOTED"
        save_json(output / "manifest.json", manifest)
        return manifest
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        manifest.update(status="FAILED", error=str(error))
        save_json(output / "failure.json", manifest)
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sdk", type=Path, default=SDK)
    parser.add_argument("--initramfs", type=Path)
    parser.add_argument("--kernel", type=Path)
    parser.add_argument("--template", type=Path)
    parser.add_argument("--opensbi", type=Path)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--sim-ram-mib", type=int, default=2048)
    parser.add_argument("--quiet-opensbi", action="store_true",
                        help="verification-only OpenSBI without the UART boot banner")
    args = parser.parse_args(argv)
    try:
        result = prepare_bundle(args.output, sdk=args.sdk, initramfs=args.initramfs,
                                kernel=args.kernel, template=args.template, opensbi=args.opensbi,
                                jobs=args.jobs, sim_ram_mib=args.sim_ram_mib,
                                quiet_opensbi=args.quiet_opensbi)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "FAILED", "error": str(error)}))
        return 1
    print(json.dumps({"status": result["status"], "output": str(args.output.absolute()),
                      "initramfs_sha256": result["inputs"]["initramfs"]["sha256"],
                      "initrd_end": hex(INITRD_ADDR + result["inputs"]["initramfs"]["size_bytes"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

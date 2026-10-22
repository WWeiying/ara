#!/usr/bin/env python3
"""Freeze a sealed FPGA candidate, then run its real Cheshire SoC under VCS.

Only external DDR and explicit technology cells are modeled. No board timing,
Linux boot, or whole-model acceptance is implied by the bare-metal smoke.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import textwrap
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACKAGE = ROOT / "verification/out/fpga-soc-candidate-20260922-04/package"
OMITTED = {
    "rtl/tech_cells_generic/src/fpga/pad_functional_xilinx.sv": "no pads in SoC top",
    "rtl/tech_cells_generic/src/fpga/tc_clk_xilinx.sv": "reviewed functional tc_clk_gating",
    "rtl/tech_cells_generic/src/fpga/tc_sram_xilinx.sv": "reviewed functional tc_sram",
    "rtl/board/dram_wrapper_xilinx.sv": "external sparse AXI memory; no DDR/CDC claim",
    "rtl/board/ara_dsa_vcu118.sv": "thin bench; exact board_cfg copied without changes",
}
TRACER = "rtl/cva6/common/local/util/instr_tracer.sv"
TRACER_PKG = "rtl/cva6/core/include/instr_tracer_pkg.sv"
CHESHIRE_SOC = "rtl/cheshire/hw/cheshire_soc.sv"
CHESHIRE_SOC_VCS = "generated/cheshire_soc_vcs.sv"
CHESHIRE_PKG = "rtl/cheshire/hw/cheshire_pkg.sv"
CHESHIRE_PKG_VCS = "generated/cheshire_pkg_vcs.sv"
TB = "verification/fpga/sim/candidate_soc_tb.sv"
MODELS = "verification/fpga/sim/tech_models.sv"
MODELS_TB = "verification/fpga/sim/tech_models_tb.sv"
SELF = "verification/fpga/run_soc_smoke.py"
PAYLOAD = "software/smoke.elf"
LINUX_FILES = (
    "linux/artifacts/fw_jump.elf", "linux/artifacts/ara_vcu118.dtb",
    "linux/artifacts/Image", "linux/artifacts/initramfs.cpio",
    "linux/artifacts/SHA256SUMS",
)
LINUX_ADDRESSES = {"linux/artifacts/ara_vcu118.dtb": 0x80100000,
                   "linux/artifacts/Image": 0x80200000,
                   "linux/artifacts/initramfs.cpio": 0x88000000}
FDT_PRELOAD_PAGE_BYTES = 4096
DRAM_BASE, DRAM_END = 0x80000000, 0x100000000
ERROR = re.compile(r"^\s*(?:Error(?:-|:|\[)|Fatal(?:-|:|\[)|UVM_FATAL|UVM_ERROR)", re.M)
PASS = {
    "smoke": re.compile(r"^SOC_SMOKE_PASS mode=SMOKE_UART reason=UART_PASS_AND_PAYLOAD_RETIREMENT$", re.M),
    "linux": re.compile(r"^SOC_LINUX_PASS mode=LINUX reason=UART_USERSPACE_MARKERS_AND_RTL_ACTIVITY$", re.M),
}
PROGRESS = re.compile(rb"^\[SOC_PROGRESS\] cycle=(\d+) [^\n]*\n", re.M)
LINUX_FAILURE_MARKERS = (b"SOC_LINUX_FAIL", b"[LINUX_RVV] FAIL",
                         b"ARA_LINUX_USERSPACE FAIL", b"Kernel panic", b"Oops:",
                         b"Fatal:", b"a_invalid_write_data", b"[CACHE_SELECTED_X]",
                         b"[CACHE_UNMATCHED_RESPONSE]")
LINUX_READ_WARNING = b"a_invalid_read_data"
CACHE_PROBE_ACTIVE = "[CACHE_PROBE_ACTIVE] selected-byte and response-ID checks enabled"
LINUX_UART_MILESTONES = ("Linux version", "Ara verification Linux init reached")


def linux_failure_markers(cache_probe=False):
    return LINUX_FAILURE_MARKERS if cache_probe else LINUX_FAILURE_MARKERS + (LINUX_READ_WARNING,)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def safe_name(name):
    if not isinstance(name, str):
        raise ValueError("filename must be a string")
    p = PurePosixPath(name)
    if (p.is_absolute() or p.as_posix() != name or
            ".." in p.parts or name == "." or "\\" in name or "+" in name or
            any(c.isspace() for c in name)):
        raise ValueError(f"unsafe relative filename: {name!r}")
    return p


def unlinked(path):
    path = Path(path).absolute()
    if ".." in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f"symlink/traversal not accepted: {path}")
    return path


def seal(data):
    records = {}
    for line in data.decode().splitlines():
        m = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
        if not m:
            raise ValueError("malformed SHA256SUMS")
        digest, name = m.groups()
        safe_name(name)
        if name in records:
            raise ValueError(f"duplicate checksum: {name}")
        records[name] = digest
    if not records:
        raise ValueError("empty SHA256SUMS")
    return records


def board_config(source):
    # Copy the complete board-owned function, not a separately maintained config.
    matches = re.findall(r"  function automatic cheshire_cfg_t board_cfg\(\);.*?endfunction",
                         source, re.S)
    if len(matches) != 1:
        raise ValueError("candidate board_cfg function is missing or ambiguous")
    return "// Copied verbatim from the sealed board top, SHL-0.51.\n" + matches[0] + "\n"


def vcs_compat_cheshire_soc(source):
    """Move only Ara AXI typedefs out of generate scope for VCS elaboration."""
    insertion = "  `CHESHIRE_TYPEDEF_ALL(, Cfg)\n"
    start = "      // Configure Ara with the right AXI id width\n"
    after = "      axi_ara_wide_req_t  axi_ara_wide_req_inval, axi_ara_wide_req;"
    if any(source.count(marker) != 1 for marker in (insertion, start, after)):
        raise ValueError("Cheshire Ara AXI typedef scope does not match reviewed VCS adapter")
    begin = source.index(start)
    end = source.index(after)
    if not (source.index(insertion) < begin < end):
        raise ValueError("unexpected Cheshire Ara AXI typedef ordering")
    block = source[begin:end]
    if block.count("`AXI_TYPEDEF_ALL(") != 1 or "assign " in block:
        raise ValueError("unexpected logic in Cheshire Ara AXI typedef block")
    without_block = source[:begin] + source[end:]
    return without_block.replace(insertion, insertion + "\n" + textwrap.dedent(block), 1)


def vcs_compat_cheshire_pkg(source):
    """Replace a zero-valued function-local parameter with its exact value."""
    declaration = "    localparam int unsigned DefaultMapEntry[2] = '{0, 0};\n"
    result = "      default: return '{default: DefaultMapEntry};"
    if source.count(declaration) != 1 or source.count(result) != 1:
        raise ValueError("Cheshire CVA6 ID map does not match reviewed VCS adapter")
    zero_map = "'{" + ", ".join(["'{0, 0}"] * 7) + "}"
    return source.replace(declaration, "", 1).replace(
        result, f"      default: return {zero_map};", 1)


def elf_segments(data):
    from elftools.elf.elffile import ELFFile

    elf = ELFFile(io.BytesIO(data))
    if elf.elfclass != 64 or not elf.little_endian or elf["e_machine"] != "EM_RISCV":
        raise ValueError("payload must be little-endian ELF64 RISC-V")
    if elf["e_type"] != "ET_EXEC":
        raise ValueError("payload must be an executable, not PIE/shared object")
    result = []
    executable_entry = False
    for s in elf.iter_segments():
        if s["p_type"] != "PT_LOAD" or not s["p_memsz"]:
            continue
        addr, memsz, filesz = s["p_paddr"], s["p_memsz"], s["p_filesz"]
        if memsz > 16 * 1024 * 1024:
            raise ValueError("oversized segment for this bare-metal smoke runner")
        if filesz > memsz or not (DRAM_BASE <= addr < addr + memsz <= DRAM_END):
            raise ValueError("invalid or out-of-DDR ELF load segment")
        if s["p_vaddr"] != addr:
            raise ValueError("smoke requires identity-addressed ELF segments")
        if any(addr < old[0] + len(old[1]) and old[0] < addr + memsz for old in result):
            raise ValueError("overlapping ELF load segments")
        payload = s.data()
        if len(payload) != filesz:
            raise ValueError("truncated ELF segment")
        result.append((addr, payload + bytes(memsz - filesz)))
        executable_entry |= bool(s["p_flags"] & 1 and addr <= elf["e_entry"] < addr + filesz)
    if not result or not executable_entry:
        raise ValueError("ELF entry is not in initialized executable DDR")
    return elf["e_entry"], sorted(result)


def memory_hex(segments):
    lines = []
    for addr, data in segments:
        lines.append(f"@{addr:016x}")
        lines.extend(data[i:i+32].hex(" ") for i in range(0, len(data), 32))
    return ("\n".join(lines) + "\n").encode()


def initialized_fdt_page(dtb):
    if (len(dtb) < 8 or dtb[:4] != bytes.fromhex("d00dfeed") or
            int.from_bytes(dtb[4:8], "big") != len(dtb) or
            len(dtb) > FDT_PRELOAD_PAGE_BYTES):
        raise ValueError("Linux DTB must be a complete blob within one preload page")
    return dtb + bytes(FDT_PRELOAD_PAGE_BYTES - len(dtb))


def linux_segments(package_bytes, package):
    from elftools.elf.elffile import ELFFile

    firmware = package_bytes[LINUX_FILES[0]]
    dtb = package_bytes[LINUX_FILES[1]]
    entry, segments = elf_segments(firmware)
    if entry != DRAM_BASE:
        raise ValueError("Linux firmware entry differs from the reviewed boot address")
    elf = ELFFile(io.BytesIO(firmware))
    symbols = elf.get_section_by_name(".symtab")
    if symbols is None:
        raise ValueError("Linux firmware lacks symbols needed to verify embedded DTB")
    matches = {name: [s["st_value"] for s in symbols.iter_symbols() if s.name == name]
               for name in ("fw_fdt_bin", "_jump_addr")}
    if any(len(values) != 1 for values in matches.values()):
        raise ValueError("Linux firmware DTB/jump symbols are missing or ambiguous")

    def file_backed(address, size):
        for segment in elf.iter_segments():
            if (segment["p_type"] == "PT_LOAD" and
                    segment["p_paddr"] <= address and
                    address + size <= segment["p_paddr"] + segment["p_filesz"]):
                offset = segment["p_offset"] + address - segment["p_paddr"]
                return firmware[offset:offset + size]
        raise ValueError("Linux firmware symbol lies outside initialized LOAD data")

    if not dtb or file_backed(matches["fw_fdt_bin"][0], len(dtb)) != dtb:
        raise ValueError("Linux firmware embedded DTB differs from external DTB")
    if int.from_bytes(file_backed(matches["_jump_addr"][0], 8), "little") != 0x80200000:
        raise ValueError("Linux firmware jump target differs from Image load address")
    for name, address in LINUX_ADDRESSES.items():
        data = package_bytes[name]
        if not data or len(data) > 64 * 1024 * 1024:
            raise ValueError(f"Linux payload size outside reviewed bound: {name}")
        if name == LINUX_FILES[1]:
            data = initialized_fdt_page(data)
        segments.append((address, data))
    segments.sort()
    for (address, data), (next_address, _) in zip(segments, segments[1:]):
        if address + len(data) > next_address:
            raise ValueError("Linux firmware, DTB, Image or initramfs regions overlap")
    if any(not (DRAM_BASE <= address < address + len(data) <= DRAM_END)
           for address, data in segments):
        raise ValueError("Linux payload lies outside external DDR region")
    fdtget = shutil.which("fdtget")
    if not fdtget:
        raise ValueError("fdtget is required to validate Linux DTB initrd bounds")

    def dtb_cells(property_name):
        command = [fdtget, "-t", "x", str(package / LINUX_FILES[1]),
                   "/chosen", property_name]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode:
            raise ValueError(f"fdtget failed for {property_name}: {result.stderr.strip()}")
        cells = result.stdout.split()
        if len(cells) != 2:
            raise ValueError(f"unexpected DTB cells for {property_name}")
        return (int(cells[0], 16) << 32) | int(cells[1], 16)

    if (dtb_cells("linux,initrd-start") != LINUX_ADDRESSES[LINUX_FILES[3]] or
            dtb_cells("linux,initrd-end") != LINUX_ADDRESSES[LINUX_FILES[3]] +
            len(package_bytes[LINUX_FILES[3]])):
        raise ValueError("Linux DTB initrd range differs from frozen initramfs")
    return entry, segments


def prepare(package, output, mode="smoke"):
    if mode not in PASS:
        raise ValueError(f"unsupported SoC simulation mode: {mode}")
    package, output = unlinked(package), unlinked(output)
    base = unlinked(ROOT / "verification/out")
    if (output == base or not output.is_relative_to(base) or output.exists() or
            output.is_relative_to(package) or package.is_relative_to(output) or
            any(c.isspace() for c in str(output)) or "+" in str(output)):
        raise ValueError("output must be a new nonoverlapping directory under verification/out")
    manifest_data = (package / "manifest.json").read_bytes()
    seal_data = (package / "SHA256SUMS").read_bytes()
    checksums = seal(seal_data)
    if checksums.get("manifest.json") != sha(manifest_data):
        raise ValueError("manifest differs from package seal")
    manifest = json.loads(manifest_data)
    files, includes, defines = manifest["files"], manifest["include_dirs"], manifest["defines"]
    if len(files) != len(set(files)) or not set(OMITTED).issubset(files):
        raise ValueError("duplicate files or unrecognized candidate technology/board mapping")
    for path in files + includes:
        safe_name(path)
    expected = {"ARA": None, "NR_LANES": 4, "VLEN": 1024, "ARA_QBS_ENABLE": 1,
                "ARA_AKV_ENABLE": 1, "ARA_AKV_V2_ENABLE": 1,
                "TARGET_CV64A6_IMAFDCV_SV39": None}
    if any(key not in defines or defines[key] != value for key, value in expected.items()):
        raise ValueError("unexpected candidate core/accelerator configuration")
    if "SYNTHESIS" in defines or "VERILATOR" in defines:
        raise ValueError("do not hide VCS verification code with SYNTHESIS/VERILATOR")
    override = manifest.get("simulation_only_linux_override", {})
    quiet_opensbi = override.get("quiet_opensbi", False)
    if type(quiet_opensbi) is not bool or (quiet_opensbi and mode != "linux"):
        raise ValueError("invalid verification-only OpenSBI boot setting")
    for key, value in defines.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", key) or not (value is None or type(value) is int):
            raise ValueError("unrecognized macro in candidate")

    selected = set(files) | {TRACER, TRACER_PKG}
    selected.update((PAYLOAD, "software/smoke.dump") if mode == "smoke" else LINUX_FILES)
    selected.update(name for name in checksums
                    if any(PurePosixPath(name).is_relative_to(inc) for inc in includes))
    # Check every selected byte before creating a partial preparation result.
    package_bytes = {}
    for name in sorted(selected):
        data = unlinked(package / name).read_bytes()
        if checksums.get(name) != sha(data):
            raise ValueError(f"unsealed/changed candidate input: {name}")
        package_bytes[name] = data
    if mode == "linux":
        entry, segments = linux_segments(package_bytes, package)
    else:
        entry, segments = elf_segments(package_bytes[PAYLOAD])
        if entry != DRAM_BASE:
            raise ValueError("smoke entry differs from reviewed UART/PC probe plan")
    output.mkdir(parents=True)
    records = {}

    def capture(name, data, source=None):
        safe_name(name)
        target = output / "inputs" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as f:
            f.write(data)
        target.chmod(0o444)
        records[name] = dict(sha256=sha(data), size_bytes=len(data),
                             source=str(source) if source else None)

    capture("package/manifest.json", manifest_data, package / "manifest.json")
    capture("package/SHA256SUMS", seal_data, package / "SHA256SUMS")
    for name, data in package_bytes.items():
        capture("package/" + name, data, package / name)
    host = [SELF, TB, MODELS, MODELS_TB, "verification/fpga/sim/TECH_MODELS.md",
            "verification/fpga/sim/BOOT_PROBE_PLAN.md", "verification/fpga/sim/requirements.txt"]
    for name in host:
        capture(name, (ROOT / name).read_bytes(), ROOT / name)
    # This simulation-only module belongs to the pinned local AXI dependency;
    # record the resolved source explicitly because deps may be symlinked.
    axi = (ROOT / "hardware/deps/axi/src/axi_sim_mem.sv").resolve(strict=True)
    capture("models/axi_sim_mem.sv", axi.read_bytes(), axi)
    capture("generated/board_cfg.svh", board_config(package_bytes[
        "rtl/board/ara_dsa_vcu118.sv"].decode()).encode())
    capture(CHESHIRE_SOC_VCS, vcs_compat_cheshire_soc(
        package_bytes[CHESHIRE_SOC].decode()).encode(), package / CHESHIRE_SOC)
    capture(CHESHIRE_PKG_VCS, vcs_compat_cheshire_pkg(
        package_bytes[CHESHIRE_PKG].decode()).encode(), package / CHESHIRE_PKG)
    capture("generated/memory.hex", memory_hex(segments))
    ordered = [MODELS] + [
        CHESHIRE_SOC_VCS if f == CHESHIRE_SOC else
        CHESHIRE_PKG_VCS if f == CHESHIRE_PKG else "package/" + f
        for f in files if f not in OMITTED
    ]
    # Tracer is simulation-only and missing from the board's synthesis list.
    ordered += ["package/" + TRACER_PKG, "package/" + TRACER, "models/axi_sim_mem.sv", TB]
    compiled_includes = ["package/" + d for d in includes] + ["generated"]
    for inc in compiled_includes:
        (output / "inputs" / inc).mkdir(parents=True, exist_ok=True)
    result = dict(schema=1, status="PREPARED_NOT_BUILT", package=str(package), mode=mode,
                  quiet_opensbi=quiet_opensbi,
                  scope=("Cheshire VCS Linux boot and RVV userspace; not custom compute or board signoff"
                         if mode == "linux" else
                         "Cheshire bare-metal smoke; not Linux/DDR/FPGA/model signoff"),
                  created_at=datetime.now(timezone.utc).isoformat(), inputs=records,
                  compile_sources=ordered, include_dirs=compiled_includes, defines=defines,
                  omitted_sources=OMITTED, entry=entry,
                  vcs_source_adaptations={CHESHIRE_SOC: CHESHIRE_SOC_VCS,
                                          CHESHIRE_PKG: CHESHIRE_PKG_VCS},
                  load_segments=[dict(address=a, bytes=len(d)) for a, d in segments])
    save(output / "inputs.json", result)
    return result


def check_inputs(output, manifest):
    errors = []
    for name, record in manifest["inputs"].items():
        data = (output / "inputs" / name).read_bytes()
        if sha(data) != record["sha256"] or len(data) != record["size_bytes"]:
            errors.append(name)
    if errors:
        raise ValueError("frozen inputs changed: " + ", ".join(errors))


def simulation_image(simv):
    libraries = Path(str(simv) + ".daidir")
    files = [simv, *sorted(libraries.rglob("*.so"))]
    if not simv.is_file() or len(files) == 1:
        raise ValueError("compiled VCS image or generated libraries are missing")
    return {str(path.relative_to(simv.parent)): sha(path.read_bytes()) for path in files}


def compiled_inputs(manifest):
    """Only these frozen bytes can affect the SoC VCS image."""
    names = set(manifest["compile_sources"]) | {MODELS_TB}
    for name in manifest["inputs"]:
        if name == "generated/memory.hex":
            continue
        if any(PurePosixPath(name).is_relative_to(directory)
               for directory in manifest["include_dirs"]):
            names.add(name)
    return {name: manifest["inputs"][name]["sha256"] for name in names}


def reuse_compiled(output, source, expected_mode=None):
    output, source = unlinked(output), unlinked(source)
    if output == source or (output / "compile").exists() or (output / "summary.json").exists():
        raise ValueError("reuse requires a new prepare-only output")
    target_manifest = json.loads((output / "inputs.json").read_text())
    source_manifest = json.loads((source / "inputs.json").read_text())
    if expected_mode != "linux" or any(m.get("mode") != "linux" for m in
                                      (target_manifest, source_manifest)):
        raise ValueError("compile reuse currently requires two Linux packages")
    for field in ("compile_sources", "include_dirs", "defines", "entry"):
        if target_manifest[field] != source_manifest[field]:
            raise ValueError(f"compiled configuration differs: {field}")
    if compiled_inputs(target_manifest) != compiled_inputs(source_manifest):
        raise ValueError("compiled RTL/include inputs differ")
    check_inputs(output, target_manifest)
    check_inputs(source, source_manifest)
    source_result = json.loads((source / "summary.json").read_text())
    if (source_result.get("inputs_manifest_sha256") !=
            sha((source / "inputs.json").read_bytes()) or
            source_result.get("compile", {}).get("returncode") != 0 or
            source_result.get("technology", {}).get("passed") is not True or
            source_result.get("simv_sha256") != sha((source / "compile/simv").read_bytes())):
        raise ValueError("source is not a verified compiled SoC run")
    image_before = simulation_image(source / "compile/simv")
    if ("simv_image_sha256" in source_result and
            source_result["simv_image_sha256"] != image_before):
        raise ValueError("source VCS image changed after its run")
    shutil.copytree(source / "compile", output / "compile")
    if simulation_image(output / "compile/simv") != image_before:
        raise ValueError("copied VCS image differs from source")
    result = {
        "scope": target_manifest["scope"],
        "status": "COMPILED_NOT_RUN",
        "inputs_manifest_sha256": sha((output / "inputs.json").read_bytes()),
        "technology": source_result["technology"],
        "compile": source_result["compile"],
        "compile_reuse": {"source": str(source),
                          "source_manifest_sha256": sha((source / "inputs.json").read_bytes()),
                          "image_sha256": image_before},
        "simv_sha256": sha((output / "compile/simv").read_bytes()),
    }
    save(output / "summary.json", result)
    return result


def latest_progress_cycle(log_path):
    if not log_path.is_file():
        return None
    with log_path.open("rb") as log:
        log.seek(0, os.SEEK_END)
        size = log.tell()
        log.seek(max(0, size - 65536))
        tail = log.read()
    matches = PROGRESS.findall(tail)
    return int(matches[-1]) if matches else None


def linux_failure_marker(log_path, cache_probe=False):
    if not log_path.is_file():
        return None
    with log_path.open("rb") as log:
        for line in log:
            for marker in linux_failure_markers(cache_probe):
                if marker in line:
                    return marker.decode()
    return None


class LinuxLogMonitor:
    """Read only appended log bytes while retaining split marker/progress lines."""

    def __init__(self, path, markers=None):
        self.path = path
        self.markers = markers if markers is not None else linux_failure_markers()
        self.offset = 0
        self.partial = b""
        self.failure_marker = None
        self.progress_cycle = None
        self.uart_markers_seen = set()
        self._suffix = b""

    def update(self):
        if not self.path.is_file():
            return
        with self.path.open("rb") as log:
            log.seek(self.offset)
            while chunk := log.read(65536):
                self.offset += len(chunk)
                search = self._suffix + chunk
                if self.failure_marker is None:
                    for marker in self.markers:
                        if marker in search:
                            self.failure_marker = marker.decode()
                            break
                self._suffix = search[-max(len(m) for m in self.markers):]
                lines = (self.partial + chunk).split(b"\n")
                self.partial = lines.pop()
                for line in lines:
                    match = PROGRESS.match(line + b"\n")
                    if match:
                        self.progress_cycle = int(match.group(1))
                    if line.startswith(b"[CANDIDATE_UART] "):
                        for marker in LINUX_UART_MILESTONES:
                            if marker.encode() in line:
                                self.uart_markers_seen.add(marker)


def budget_infeasible(cycles, elapsed, timeout, target, margin=1.5):
    if cycles is None or elapsed <= 0 or elapsed >= timeout or cycles >= target:
        return False
    observed_rate = cycles / elapsed
    return cycles + (timeout - elapsed) * observed_rate * margin < target


def execute(argv, directory, timeout, min_cycle_target=None, budget_check_after=900,
            budget_poll_interval=5, linux_fail_fast=False, no_progress_timeout=None,
            cycle_milestone=None, first_progress_timeout=None, uart_milestone=None):
    directory.mkdir()
    record = dict(argv=list(map(str, argv)), cwd=str(directory), timeout_s=timeout,
                  started_at=datetime.now(timezone.utc).isoformat())
    save(directory / "command.json", record)
    start = time.monotonic()
    last_cycle = None
    last_progress_at = None
    monitor = LinuxLogMonitor(directory / "console.log",
                              linux_failure_markers("+CACHE_TAG_PROBE" in record["argv"]))
    with (directory / "console.log").open("wb") as log:
        proc = subprocess.Popen(record["argv"], cwd=directory, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        record["pid"] = proc.pid
        save(directory / "command.json", record)
        try:
            if (min_cycle_target is None and not linux_fail_fast and
                    no_progress_timeout is None and cycle_milestone is None and
                    first_progress_timeout is None and uart_milestone is None):
                record["returncode"] = proc.wait(timeout=timeout)
            else:
                while True:
                    elapsed = time.monotonic() - start
                    try:
                        record["returncode"] = proc.wait(
                            timeout=min(budget_poll_interval, max(0.01, timeout - elapsed)))
                        break
                    except subprocess.TimeoutExpired:
                        elapsed = time.monotonic() - start
                        monitor.update()
                        if linux_fail_fast:
                            marker = monitor.failure_marker
                            if marker is not None:
                                record.update(early_failure_marker=marker, returncode=-1)
                                break
                        if uart_milestone in monitor.uart_markers_seen:
                            record.update(uart_milestone_reached=uart_milestone,
                                          last_progress_cycle=monitor.progress_cycle,
                                          returncode=-1)
                            break
                        if cycle_milestone is not None:
                            cycles = monitor.progress_cycle
                            if cycles is not None and cycles >= cycle_milestone:
                                record.update(milestone_reached=True,
                                              last_progress_cycle=cycles,
                                              cycle_milestone=cycle_milestone, returncode=-1)
                                break
                        if no_progress_timeout is not None:
                            cycles = monitor.progress_cycle
                            if cycles is not None and (last_cycle is None or cycles > last_cycle):
                                last_cycle = cycles
                                last_progress_at = elapsed
                            elif (last_progress_at is not None and
                                  elapsed - last_progress_at >= no_progress_timeout):
                                record.update(no_progress_timeout=True,
                                              last_progress_cycle=last_cycle, returncode=-1)
                                break
                        if (first_progress_timeout is not None and
                                monitor.progress_cycle is None and
                                elapsed >= first_progress_timeout):
                            record.update(first_progress_timeout=True, returncode=-1)
                            break
                        if min_cycle_target is not None and elapsed >= budget_check_after:
                            cycles = monitor.progress_cycle
                            if budget_infeasible(cycles, elapsed, timeout, min_cycle_target):
                                record.update(budget_infeasible=True, last_progress_cycle=cycles,
                                              min_cycle_target=min_cycle_target, returncode=-1)
                                break
                        if elapsed >= timeout:
                            record.update(timeout=True, returncode=-1)
                            break
        except subprocess.TimeoutExpired:
            record.update(timeout=True, returncode=-1)
        finally:
            # Only this invocation's private process group may be cleaned up.
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(proc.pid, sig)
                except ProcessLookupError:
                    break
                time.sleep(0.2)
            proc.wait()
        record.update(wall_seconds=round(time.monotonic()-start, 3),
                  ended_at=datetime.now(timezone.utc).isoformat())
    save(directory / "command.json", record)
    return record


def run(output, manifest, args):
    check_inputs(output, manifest)
    inputs = output / "inputs"
    vcs = shutil.which(args.vcs)
    if not vcs:
        raise ValueError("VCS is not available")
    result = dict(scope=manifest["scope"], status="CHECKING_TECH_MODELS",
                  inputs_manifest_sha256=sha((output / "inputs.json").read_bytes()))
    save(output / "summary.json", result)
    macro_args = ["+define+" + key + ("" if val is None else f"={val}")
                  for key, val in manifest["defines"].items() if key != "TARGET_VIVADO"]
    result["omitted_vcs_define"] = {
        "TARGET_VIVADO": "only used by unread.sv to drive an input port; Vivado-only behavior"
    }
    result["technology"] = check_technology(vcs, output, inputs, macro_args,
                                             args.license_wait)
    if not result["technology"]["passed"]:
        result["status"] = "TECH_MODEL_CHECK_FAILED"
        save(output / "summary.json", result)
        return 1
    argv = vcs_prefix(vcs, args.license_wait) + ["-full64", "-sverilog", "-timescale=1ns/1ps", "-top", "candidate_soc_tb",
            "-o", str(output / "compile/simv"), "-j", str(args.jobs)]
    argv += ["+incdir+" + str(inputs / d) for d in manifest["include_dirs"]]
    argv += macro_args
    argv += [str(inputs / name) for name in manifest["compile_sources"]]
    result["status"] = "COMPILING"
    save(output / "summary.json", result)
    result["compile"] = execute(argv, output / "compile", args.compile_timeout)
    check_inputs(output, manifest)
    if result["compile"]["returncode"] or ERROR.search((output / "compile/console.log").read_text(errors="replace")):
        result["status"] = "COMPILE_FAILED"
    elif args.compile_only:
        result["status"] = "COMPILED_NOT_RUN"
    else:
        simulate(output, manifest, result, args.run_timeout, args.cache_tag_probe,
                 args.linux_min_cycle_target, args.budget_check_after,
                 args.linux_fail_fast, args.linux_no_progress_timeout,
                 args.linux_cycle_milestone, args.linux_first_progress_timeout,
                 args.linux_uart_milestone)
    result["ended_at"] = datetime.now(timezone.utc).isoformat()
    if (output / "compile/simv").is_file():
        result["simv_sha256"] = sha((output / "compile/simv").read_bytes())
    save(output / "summary.json", result)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result["status"] in ("SMOKE_PASS", "LINUX_BOOT_PASS", "COMPILED_NOT_RUN") else 1


def simulate(output, manifest, result, timeout, cache_tag_probe=False,
             min_cycle_target=None, budget_check_after=900,
             linux_fail_fast=False, no_progress_timeout=None,
             cycle_milestone=None, first_progress_timeout=None, uart_milestone=None):
    check_inputs(output, manifest)
    simv = output / "compile/simv"
    image_before = simulation_image(simv)
    if (output / "sim").exists():
        raise ValueError("simulation output already exists")
    result["simv_image_sha256"] = image_before
    result["status"] = "RUNNING"
    save(output / "summary.json", result)
    argv = [str(simv), "+NO_INSTR_TRACE",
            "+MEM_HEX=" + str(output / "inputs/generated/memory.hex"),
            f"+BOOT_ENTRY={manifest['entry']:x}"]
    mode = manifest.get("mode", "smoke")
    if mode == "linux":
        argv.append("+LINUX_MODE")
        if manifest.get("quiet_opensbi", False):
            argv.append("+QUIET_OPENSBI")
    if cache_tag_probe:
        argv.append("+CACHE_TAG_PROBE")
        argv.append("+DTB_TAIL_PROBE")
    result["simulation"] = execute(argv, output / "sim", timeout,
                                   min_cycle_target, budget_check_after,
                                   linux_fail_fast=linux_fail_fast,
                                   no_progress_timeout=no_progress_timeout,
                                   cycle_milestone=cycle_milestone,
                                   first_progress_timeout=first_progress_timeout,
                                   uart_milestone=uart_milestone)
    check_inputs(output, manifest)
    log = (output / "sim/console.log").read_text(errors="replace")
    probed = "+CACHE_TAG_PROBE" in argv
    passed = (result["simulation"]["returncode"] == 0 and
              PASS[mode].search(log) and not ERROR.search(log) and
              (not probed or log.count(CACHE_PROBE_ACTIVE) == 1) and
              (mode != "linux" or not any(marker.decode() in log
                                          for marker in linux_failure_markers(probed))))
    result["status"] = ("LINUX_BOOT_PASS" if mode == "linux" else "SMOKE_PASS") if passed else (
        "LINUX_EARLY_FAILURE" if result["simulation"].get("early_failure_marker") else
        "LINUX_UART_MILESTONE_REACHED" if result["simulation"].get("uart_milestone_reached") else
        "LINUX_MILESTONE_REACHED" if result["simulation"].get("milestone_reached") else
        "LINUX_NO_INITIAL_PROGRESS" if result["simulation"].get("first_progress_timeout") else
        "LINUX_STALLED" if result["simulation"].get("no_progress_timeout") else
        "LINUX_BUDGET_INCOMPLETE" if result["simulation"].get("budget_infeasible") else
        "LINUX_BOOT_FAILED" if mode == "linux" else "SMOKE_FAILED")
    if simulation_image(simv) != image_before:
        result["status"] = "HARNESS_ERROR"
        result["image_changed_during_run"] = True


def run_precompiled(output, timeout, expected_mode=None, cache_tag_probe=False,
                    min_cycle_target=None, budget_check_after=900,
                    linux_fail_fast=False, no_progress_timeout=None,
                    cycle_milestone=None, first_progress_timeout=None, uart_milestone=None):
    output = unlinked(output)
    manifest = json.loads((output / "inputs.json").read_text())
    result = json.loads((output / "summary.json").read_text())
    if expected_mode is not None and manifest.get("mode", "smoke") != expected_mode:
        raise ValueError("requested mode differs from compiled SoC mode")
    if (result.get("status") != "COMPILED_NOT_RUN" or
            result.get("inputs_manifest_sha256") != sha((output / "inputs.json").read_bytes()) or
            result.get("compile", {}).get("returncode") != 0 or
            result.get("technology", {}).get("passed") is not True):
        raise ValueError("output is not a verified compile-only SoC run")
    simv = output / "compile/simv"
    if sha(simv.read_bytes()) != result.get("simv_sha256"):
        raise ValueError("compiled VCS executable changed")
    if (output / "sim").exists() or (output / "run_driver.py").exists():
        raise ValueError("simulation output already exists")
    driver = Path(__file__).read_bytes()
    with (output / "run_driver.py").open("xb") as file:
        file.write(driver)
    (output / "run_driver.py").chmod(0o444)
    result["run_driver_sha256"] = sha(driver)
    simulate(output, manifest, result, timeout, cache_tag_probe,
             min_cycle_target, budget_check_after,
             linux_fail_fast, no_progress_timeout, cycle_milestone,
             first_progress_timeout, uart_milestone)
    result["ended_at"] = datetime.now(timezone.utc).isoformat()
    save(output / "summary.json", result)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result["status"] in ("SMOKE_PASS", "LINUX_BOOT_PASS") else 1


def expected_fatal_pass(record, log, case, diagnostic):
    """VCS may return zero for $fatal; require the actual expected diagnostic."""
    lines = log.splitlines()
    markers = [i for i, line in enumerate(lines)
               if line.strip() == f"TECH_MODELS_EXPECT_FATAL: {case}"]
    fatals = [i for i, line in enumerate(lines) if line.startswith("Fatal:")]
    return (not record.get("timeout") and record.get("returncode", -1) >= 0 and
            len(markers) == 1 and len(fatals) == 1 and markers[0] < fatals[0] and
            diagnostic in "\n".join(lines[fatals[0]:fatals[0] + 3]) and
            not any(token in log for token in
                    ("TECH_MODELS_MISSING_FATAL", "TECH_MODELS_BAD_TEST", "TECH_MODELS_PASS:")) and
            not re.search(r"^Error(?:-|:)", log, re.M))


def vcs_prefix(vcs, license_wait):
    return [vcs, "+vcs+lic+wait"] if license_wait else [vcs]


def check_technology(vcs, output, inputs, macro_args, license_wait=False):
    """Small model contract, not vendor equivalence or device timing signoff."""
    results = dict(passed=False, checks={})
    for top in ("tech_models_tb", "tech_models_error_tb"):
        directory = output / (top + "_compile")
        cmd = vcs_prefix(vcs, license_wait) + ["-full64", "-sverilog", "-timescale=1ns/1ps", "-top", top,
               "-o", str(directory / "simv"), *macro_args, str(inputs / MODELS), str(inputs / MODELS_TB)]
        record = execute(cmd, directory, 180)
        results["checks"][top + "_compile"] = record
        if record["returncode"] or ERROR.search((directory / "console.log").read_text(errors="replace")):
            return results
    directory = output / "tech_models_positive"
    record = execute([output / "tech_models_tb_compile/simv"], directory, 30)
    log = (directory / "console.log").read_text(errors="replace")
    record["passed"] = record["returncode"] == 0 and "TECH_MODELS_PASS:" in log and not ERROR.search(log)
    results["checks"]["positive"] = record
    if not record["passed"]:
        return results
    diagnostics = {
        "collision_rw": "unsupported SRAM collision",
        "collision_ww": "unsupported SRAM collision",
        "reset_collision_ww": "unsupported SRAM collision",
        "req_x": "unknown SRAM request", "addr_x": "invalid SRAM address",
        "addr_oob": "invalid SRAM address", "we_x": "unknown effective write mask",
        "mask_x": "unknown effective write mask", "rst_x": "unknown SRAM reset",
        "reset_req_x_write": "unknown SRAM request",
        "reset_addr_x_write": "invalid SRAM address",
        "reset_mask_x_write": "unknown effective write mask",
    }
    for case, diagnostic in diagnostics.items():
        directory = output / ("tech_models_" + case)
        record = execute([output / "tech_models_error_tb_compile/simv", "+CASE=" + case], directory, 30)
        log = (directory / "console.log").read_text(errors="replace")
        record["passed"] = expected_fatal_pass(record, log, case, diagnostic)
        results["checks"][case] = record
        if not record["passed"]:
            return results
    results["passed"] = True
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("smoke", "linux"))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--compile-only", action="store_true")
    parser.add_argument("--run-only", action="store_true")
    parser.add_argument("--reuse-compiled-from", type=Path,
                        help="prepare a new Linux payload but reuse an identical verified RTL image")
    parser.add_argument("--vcs", default="vcs")
    parser.add_argument("--license-wait", action="store_true",
                        help="queue for a VCS license within each compile timeout")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--compile-timeout", type=int, default=1800)
    parser.add_argument("--run-timeout", type=int, default=10800)
    parser.add_argument("--linux-min-cycle-target", type=int,
                        help="optional lower-bound Linux cycle milestone for conservative wall-budget early stop")
    parser.add_argument("--budget-check-after", type=int, default=900,
                        help="seconds of measured simulation before testing the optional cycle budget")
    parser.add_argument("--linux-fail-fast", action="store_true",
                        help="stop Linux simulation after an explicit failure marker")
    parser.add_argument("--linux-no-progress-timeout", type=int,
                        help="stop Linux simulation if cycle progress stalls for this many seconds")
    parser.add_argument("--linux-first-progress-timeout", type=int,
                        help="stop Linux simulation if no SoC progress appears within this many seconds")
    parser.add_argument("--linux-cycle-milestone", type=int,
                        help="diagnostic only: stop after this observed SoC cycle; never counts as Linux boot PASS")
    parser.add_argument("--linux-uart-milestone", choices=LINUX_UART_MILESTONES,
                        help="diagnostic only: stop at the selected Linux UART marker; never counts as boot PASS")
    parser.add_argument("--cache-tag-probe", action="store_true",
                        help="capture focused D-cache X and DTB-tail DDR diagnostics")
    args = parser.parse_args()
    if min(args.jobs, args.compile_timeout, args.run_timeout, args.budget_check_after) < 1:
        parser.error("jobs, timeouts and budget-check-after must be positive")
    if args.linux_min_cycle_target is not None:
        if args.linux_min_cycle_target < 1 or args.mode != "linux":
            parser.error("--linux-min-cycle-target requires --mode linux and a positive cycle count")
    if args.linux_no_progress_timeout is not None and args.linux_no_progress_timeout < 1:
        parser.error("--linux-no-progress-timeout must be positive")
    if args.linux_first_progress_timeout is not None and args.linux_first_progress_timeout < 1:
        parser.error("--linux-first-progress-timeout must be positive")
    if args.linux_cycle_milestone is not None and args.linux_cycle_milestone < 1:
        parser.error("--linux-cycle-milestone must be positive")
    if (args.linux_fail_fast or args.linux_no_progress_timeout is not None or
            args.linux_first_progress_timeout is not None or
            args.linux_cycle_milestone is not None or
            args.linux_uart_milestone is not None) and args.mode != "linux":
        parser.error("Linux early-stop options require --mode linux")
    if sum((args.prepare_only, args.compile_only, args.run_only,
            args.reuse_compiled_from is not None)) > 1:
        parser.error("prepare-only, compile-only, run-only and reuse-compiled-from are mutually exclusive")
    output = args.output.absolute()
    prepared = False
    try:
        if args.run_only:
            return run_precompiled(output, args.run_timeout, args.mode, args.cache_tag_probe,
                                   args.linux_min_cycle_target, args.budget_check_after,
                                   args.linux_fail_fast, args.linux_no_progress_timeout,
                                   args.linux_cycle_milestone,
                                   args.linux_first_progress_timeout,
                                   args.linux_uart_milestone)
        manifest = prepare(args.package, output, args.mode or "smoke")
        prepared = True
        if args.reuse_compiled_from is not None:
            reuse_compiled(output, args.reuse_compiled_from, args.mode)
            print(f"COMPILED_NOT_RUN (reused) {output}")
            return 0
        if args.prepare_only:
            print(f"PREPARED_NOT_BUILT {output}")
            return 0
        return run(output, manifest, args)
    except (ValueError, OSError, KeyError, ImportError) as exc:
        print(f"soc-smoke: {exc}", file=sys.stderr)
        if prepared:
            save(output / "failure.json", dict(error=str(exc), status="HARNESS_ERROR"))
        return 1


if __name__ == "__main__":
    sys.exit(main())

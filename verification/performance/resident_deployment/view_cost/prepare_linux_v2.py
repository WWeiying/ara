#!/usr/bin/env python3
"""Targeted v2 successor: descriptor-output aliases and prefaulted private KV.

Without --run this compiles the init only. Execution requires an explicitly
identified frozen module, SHA256, and its complete source-pins inventory.
No module/RTL builds, board access, numerical-success claims, or retries.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT.parent / "ara_dsa_signoff_integration/verification/out"
GNU = Path("/home/wangwy/llama/platforms/cva6-qemu/tools/bin")
IMAGES = Path("/home/wangwy/llama/platforms/cva6-qemu/images")
QEMU = OUT / "stage5_qemu_build_20261110_07/qemu-system-riscv64"
CPU = "rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true,xaraakv=true,xaraakv-resident=true"
PLATFORM_PINS = {
    QEMU: "1f4619e1573ed6626b259912d6780ac9d40e8cca8ed38ec32694a0b1d399388a",
    IMAGES / "Image": "716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285",
    IMAGES / "fw_dynamic.bin": "30e855897b24423232a6859ca8f29441f37a5a445d84735e943cb4ae2c752182",
}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cpio(entries):
    data = bytearray()
    for ino, (name, mode, payload, major, minor) in enumerate(
            entries + [("TRAILER!!!", 0, b"", 0, 0)], 1):
        name = name.encode() + b"\0"
        fields = [ino, mode, 0, 0, 1, 0, len(payload), 0, 0, major, minor, len(name), 0]
        data += b"070701" + "".join(f"{v:08x}" for v in fields).encode() + name
        data += b"\0" * (-len(data) % 4)
        data += payload
        data += b"\0" * (-len(data) % 4)
    data += b"\0" * (-len(data) % 512)
    return data


# Exact counts distinguish a complete lifecycle run from an early PASS marker.
REQUIRED = {
    "finit_module": (1, 0), "view_caps": (1, 0),
    "register_zero_descriptor": (1, -22), "batch_zero_descriptor": (1, -22),
    "release_zero_descriptor": (1, -22), "register_live_view": (1, 0),
    "finite_capability_decline": (1, -95), "live_finite_update_decline": (1, -95),
    "live_key_nan_before_info": (1, -95), "live_key_restored_info": (1, -95),
    "live_value_inf_before_info": (1, -95), "live_value_restored_info": (1, -95),
    "live_query_nan_before_info": (1, -95), "live_mask_nan_before_info": (1, -95),
    "live_inputs_restored_info": (1, -95), "sixteen_groups_decline_first": (1, -95),
    "seventeen_groups_rejected": (1, -22), "output_alias_rejected": (6, -22),
    "handle_is_fd_local": (1, -116), "other_fd_cannot_release": (1, -2),
    "fork_inherited_fd_wrong_mm": (1, -116), "child_exit_status": (1, 0),
    "parent_handle_survives_shared_fork": (1, -95),
    "released_live_view_stale": (1, -116), "release_twice_missing": (1, -2),
    "key_mapping_stale": (2, -116), "value_mapping_stale": (2, -116),
    "mprotect_registered_none": (2, 0), "unmap_registered_storage": (2, 0),
    "restored_address_still_stale": (4, -116), "fresh_mapping_cap_decline": (4, -95),
    "fill_handle_table": (64, 0), "handle_limit_33": (2, -28),
    "reuse_free_table_slot": (2, 0), "released_handle_stale": (2, -116),
    "close_releases_live_views": (1, 0), "closed_fd_handle_stale": (1, -116),
    "delete_module": (1, 0),
    "metadata_disjoint_control_before": (1, -95), "metadata_disjoint_control_after": (1, -95),
    "metadata_alias_key": (1, -22), "metadata_alias_value": (1, -22),
    "metadata_alias_query": (1, -22), "metadata_alias_mask": (1, -22),
    "metadata_alias_groups": (1, -22), "metadata_group_independently_valid": (1, 1),
    "metadata_group_overlap_one_byte": (1, 1),
    "metadata_alias_descriptor_unpublished": (5, 0), "metadata_alias_input_unchanged": (5, 0),
    "metadata_alias_output_unpublished": (5, 0), "private_mmap_writable": (2, 1),
    "private_prefaulted_register": (1, 0), "private_finite_capability_decline": (1, -95),
    "private_live_update_decline": (1, -95), "private_live_nan_before_info": (1, -95),
    "private_live_restored_info": (1, -95), "private_mprotect_none": (1, 0),
    "private_protection_stale": (1, -116), "private_mprotect_restore": (1, 0),
    "private_protection_sticky_stale": (1, -116), "private_release_invalidated": (1, 0),
    "private_released_stale": (1, -116), "private_release_twice_missing": (1, -2),
    "private_reregister_restored": (1, 0), "private_new_handle_identity": (1, 1),
    "private_reregister_capability_decline": (1, -95), "private_unmap_value": (1, 0),
    "private_unmapped_stale": (1, -116), "private_release_unmapped": (1, 0),
    "private_cleanup_key": (1, 0),
}


def audit(log, trace, cpus):
    require(cpus in (1, 2), "Unsupported CPU count")
    require(not re.search(r"\bFAIL\b|Kernel panic|Oops:|BUG:|WARNING:|Unknown symbol|"
                          r"unexpected relocation|disagrees about version", log), "Kernel/check failure")
    final = re.findall(r"^RESIDENT_VIEWS_V2_LINUX_PASS cpus=(\d+) checks=(\d+) errors=0\r?$", log, re.M)
    require(len(final) == 1 and int(final[0][0]) == cpus, "Missing/ambiguous guest completion")
    rows = re.findall(r"^CHECK name=(\w+) rc=(-?\d+) expected=(-?\d+) (PASS|FAIL)\r?$", log, re.M)
    require(all(a == b and state == "PASS" for _, a, b, state in rows), "Check value/status mismatch")
    require(len(rows) == int(final[0][1]) + 4, "Parent/child check count mismatch")
    counts = Counter(name for name, _, _, _ in rows)
    for name, (count, expected) in REQUIRED.items():
        require(counts[name] == count, "Missing/duplicate lifecycle check: " + name)
        require(all(int(a) == expected for n, a, _, _ in rows if n == name), "Wrong errno: " + name)
    rounds = 17 if cpus == 1 else 0
    require(re.findall(r"^INFO_EXPECT cpus=(\d+) rounds=(\d+)\r?$", log, re.M) ==
            [(str(cpus), str(rounds))], "Wrong independent INFO-round expectation")
    events = re.findall(r"\bakv_arch_\w+", trace)
    require(all(event == "akv_arch_info" for event in events), "Unexpected accelerator command")
    queries = [(int(i), int(v, 16)) for i, v in re.findall(
        r"akv_arch_info index=(\d+) result=0x([0-9a-fA-F]+)", trace)]
    require(len(queries) == len(events), "Malformed INFO trace")
    require([i for i, _ in queries] == list(range(5)) * rounds, "Wrong discovery sequence/live-input gate")
    require(all(v == 0 for i, v in queries if i == 4), "INFO4 unexpectedly admits arithmetic")
    return dict(cpus=cpus, state="PASS", checks=len(rows), info4_zero_reads=rounds,
                live_update_gate_checked=cpus == 1, arithmetic_executed=False)


def self_test():
    """Parser mutation checks only; these are not guest evidence."""
    for cpus in (1, 2):
        rows = [f"CHECK name={name} rc={expected} expected={expected} PASS"
                for name, (count, expected) in REQUIRED.items() for _ in range(count)]
        rounds = 17 if cpus == 1 else 0
        log = "\n".join(rows) + f"\nINFO_EXPECT cpus={cpus} rounds={rounds}\n" + (
            f"RESIDENT_VIEWS_V2_LINUX_PASS cpus={cpus} checks={len(rows) - 4} errors=0\n")
        trace = "".join(f"akv_arch_info index={i} result=0x0\n" for _ in range(rounds) for i in range(5))
        audit(log, trace, cpus)
        mutations = [(log.replace("name=key_mapping_stale", "name=missing", 1), trace),
                     (log.replace("errors=0", "errors=1"), trace),
                     (log + "Kernel panic\n", trace), (log, trace + "akv_arch_begin\n"),
                     (log.replace("rc=-116", "rc=0", 1), trace),
                     (log, trace + "akv_arch_info index=4 result=0x1\n")]
        if cpus == 1:
            mutations += [(log, trace.replace("index=4 result=0x0", "index=4 result=0x1", 1)),
                          (log, trace.split("\n", 1)[1])]
        for target in ("key", "value", "query", "mask", "groups"):
            name = "metadata_alias_" + target
            mutations.append((log.replace(
                f"CHECK name={name} rc=-22 expected=-22 PASS",
                f"CHECK name={name} rc=-95 expected=-95 PASS", 1), trace))
        mutations += [
            (log.replace("name=private_prefaulted_register", "name=missing_private", 1), trace),
            (log.replace("name=metadata_group_independently_valid rc=1 expected=1",
                         "name=metadata_group_independently_valid rc=0 expected=0", 1), trace)]
        for bad_log, bad_trace in mutations:
            try:
                audit(bad_log, bad_trace, cpus)
            except RuntimeError:
                continue
            raise RuntimeError("Checker accepted a deliberately broken report")
    archive = cpio([("init", 0o100755, b"abc", 0, 0)])
    require(len(archive) % 512 == 0 and archive[:6] == b"070701" and
            b"TRAILER!!!\0" in archive, "CPIO framing")
    print("PASS lifecycle audit self-test: 2 parser fixtures, 28 rejected mutations; not guest execution")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--module", type=Path)
    parser.add_argument("--module-sha256")
    parser.add_argument("--module-pins", type=Path)
    parser.add_argument("--run", action="store_true", help="Boot exactly one 1-CPU and one 2-CPU guest")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required")
    if args.run and not args.module:
        parser.error("--run requires the frozen --module path and --module-sha256")
    if args.module and not re.fullmatch(r"[0-9a-f]{64}", args.module_sha256 or ""):
        parser.error("--module requires an explicit SHA256")
    out = args.output.resolve()
    require(out.parent == OUT and out.name.startswith("resident_view_linux_v2_") and not out.exists(),
            "Use a fresh direct signoff verification/out/resident_view_linux_v2_* directory")
    out.mkdir()
    inputs = out / "inputs"
    inputs.mkdir()
    pins, commands = {}, []
    report = dict(state="FAIL", module_loaded=False, linux_executed=False,
                  arithmetic_executed=False, board_executed=False, guests=[])

    def save(name, obj):
        (out / name).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")

    def pin(path, expected=None):
        path = Path(path)
        actual = sha(path)
        require(expected is None or actual == expected, "Identity mismatch: " + str(path))
        require(str(path) not in pins or pins[str(path)] == actual, "Pin changed: " + str(path))
        pins[str(path)] = actual
        return actual

    def freeze(path, name, expected=None):
        digest = pin(path, expected)
        target = inputs / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        pin(target, digest)
        return target

    def verify_pins():
        for path, digest in pins.items():
            require(sha(path) == digest, "Source/artifact drift: " + path)

    def run(name, argv, timeout=30):
        argv = list(map(str, argv))
        started = time.monotonic()
        record = dict(name=name, argv=argv, timeout_seconds=timeout)
        try:
            with (out / (name + ".log")).open("xb") as log:
                proc = subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            record["returncode"] = proc.returncode
            require(proc.returncode == 0, name + " failed; retain " + str(out / (name + ".log")))
        except subprocess.TimeoutExpired:
            record["timed_out"] = True
            raise
        finally:
            record["elapsed_seconds"] = round(time.monotonic() - started, 3)
            commands.append(record)
            save("commands.json", commands)
        return (out / (name + ".log")).read_text(errors="replace")

    try:
        self_test()
        freeze(__file__, "view_cost/prepare_linux_v2.py")
        # Pin only the sealed predecessor tests, not obsolete live broker sources.
        freeze(HERE / "init_views.c", "predecessor/init_views.c",
               "3f3651a26cbda12feb3b0005ab8e57712aa71215b66056293ead138103645798")
        freeze(HERE / "prepare_linux.py", "predecessor/prepare_linux.py",
               "b948cb42d45cadaa7ba36862bf43f1aed605e39731d8b99cf33dd7bb4e70e267")
        init = freeze(HERE / "init_views_v2.c", "view_cost/init_views_v2.c")
        for name in ("init_v2.c", "device_numbers.h"):
            freeze(HERE.parent / "linux_smoke" / name, "linux_smoke/" + name)
        # Compile against the delivered module's UAPI, never a moving live header.
        header_dir = args.module.resolve().parent if args.module else ROOT / "software/llama/platform/linux"
        for name in ("client.h", "ara_resident_uapi.h", "view_uapi.h"):
            freeze(header_dir / name, "headers/" + name)
        for name in ("gcc", "readelf", "nm"):
            pin(GNU / ("riscv64-linux-" + name))
        flags = ["-O2", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-march=rv64gc", "-mabi=lp64d",
                 "-mcmodel=medany", "-mno-relax", "-msmall-data-limit=0", "-ffreestanding", "-fno-builtin",
                 "-fno-stack-protector", "-fno-tree-vectorize", "-fno-tree-slp-vectorize",
                 "-ffunction-sections", "-fdata-sections", "-nostdlib", "-static", "-I" + str(inputs / "headers"),
                 "-Wl,-e,_start", "-Wl,--build-id=none", "-Wl,--gc-sections"]
        elf = out / "init_views_v2.elf"
        run("init-build", [GNU / "riscv64-linux-gcc", *flags, init, "-o", elf])
        elf_info = run("init-elf", [GNU / "riscv64-linux-readelf", "-h", "-l", elf])
        require("RISC-V" in elf_info and "INTERP" not in elf_info, "Init must be static RISC-V")
        require(not run("init-undefined", [GNU / "riscv64-linux-nm", "-u", elf]).strip(), "Unresolved init symbols")
        symbols = run("init-symbols", [GNU / "riscv64-linux-nm", elf])
        require("inherited_smoke_main" not in symbols and "smoke_checked_execute" not in symbols,
                "Inherited main/wrappers must be discarded")
        pin(elf)
        report["init_sha256"] = sha(elf)
        if args.module:
            module = args.module.resolve()
            manifest = args.module_pins or module.parent.parent / "source-pins.json"
            freeze(manifest, "module-source-pins.json")
            inherited = json.loads(Path(manifest).read_text())
            require(isinstance(inherited, dict) and inherited and
                    str(module.parent / "ara_resident_broker.c") in inherited,
                    "Missing frozen module source inventory")
            for path, digest in inherited.items():
                pin(path, digest)
            build_report_path = module.parent.parent / "result.json"
            freeze(build_report_path, "module-result.json")
            build_report = json.loads(build_report_path.read_text())
            require(build_report.get("state") == "MODULE_BUILT_NOT_EXECUTED" and
                    build_report.get("module_sha256") == args.module_sha256 and build_report.get("pins_match"),
                    "Unqualified module build result")
            require(build_report["core_sha256"] ==
                    "2570ece271ba12ae9384d6d4c9acc8eef6c2f3c613d776675c2400f66f89d195",
                    "Targeted broker-only successor must retain the reviewed compute core")
            pin(module.parent / "sdk/ara_resident_compute_core.o", build_report["core_sha256"])
            replacement = freeze(module, "ara_resident.ko", args.module_sha256)
            metadata = run("module-info", [GNU / "riscv64-linux-readelf", "-p", ".modinfo", replacement])
            require("vermagic=6.19.6 SMP mod_unload riscv" in metadata, "Wrong module vermagic")
            relocs = run("module-relocations", [GNU / "riscv64-linux-readelf", "-rW", replacement])
            require("R_RISCV_ALIGN" not in relocs and "R_RISCV_RELAX" not in relocs, "Unsafe module relocations")
            report["module_sha256"] = args.module_sha256
            archive = out / "initramfs.cpio"
            archive.write_bytes(cpio([("dev", 0o040755, b"", 0, 0), ("proc", 0o040755, b"", 0, 0),
                ("sys", 0o040755, b"", 0, 0), ("dev/console", 0o020600, b"", 5, 1),
                ("init", 0o100755, elf.read_bytes(), 0, 0),
                ("ara_resident.ko", 0o100644, replacement.read_bytes(), 0, 0)]))
            pin(archive)
        verify_pins()
        save("source-pins.json", pins)
        if args.run:
            for path, digest in PLATFORM_PINS.items():
                pin(path, digest)
            image = freeze(IMAGES / "Image", "Image")
            bios = freeze(IMAGES / "fw_dynamic.bin", "fw_dynamic.bin")
            pin(GNU / "fdtput")
            pin(GNU / "dtc")
            for cpus in (1, 2):
                verify_pins()
                dtb = out / f"virt-{cpus}.dtb"
                base = [QEMU, "-M", "virt", "-cpu", CPU, "-smp", cpus, "-m", "256M",
                        "-display", "none", "-monitor", "none", "-serial", "stdio", "-nic", "none",
                        "-bios", bios, "-kernel", image]
                dump = base.copy()
                dump[2] = "virt,dumpdtb=" + str(dtb)
                run(f"dump-dtb-{cpus}", dump, timeout=15)
                run(f"dtb-node-{cpus}", [GNU / "fdtput", "-c", dtb, "/ara-resident"])
                for name, kind, values in (
                    ("compatible", "s", ["pulp,ara-resident-attention-v1"]), ("status", "s", ["okay"]),
                    ("pulp,nr-lanes", "x", ["4"]), ("pulp,vlen-bits", "x", ["400"]),
                    ("pulp,hart-id", "x", ["0", "0"]), ("pulp,ram-base", "x", ["0", "80000000"]),
                    ("pulp,ram-size", "x", ["0", "10000000"])):
                    run(f"dtb-{cpus}-{name.replace(',', '-')}",
                        [GNU / "fdtput", "-t", kind, dtb, "/ara-resident", name, *values])
                for name in ("dma-coherent", "pulp,firmware-preserves-accelerator"):
                    run(f"dtb-{cpus}-{name.replace(',', '-')}", [GNU / "fdtput", dtb, "/ara-resident", name])
                run(f"dtb-{cpus}-decode", [GNU / "dtc", "-I", "dtb", "-O", "dts", dtb])
                pin(dtb)
                verify_pins()
                save("source-pins.json", pins)
                trace = out / f"guest-{cpus}.trace"
                command = base + ["-dtb", dtb, "-initrd", archive, "-append",
                    f"console=ttyS0 rdinit=/init panic=0 loglevel=6 resident_views_cpus={cpus}",
                    "-trace", "enable=akv_arch_*,file=" + str(trace)]
                report["linux_executed"] = True
                log = run(f"guest-{cpus}", command, timeout=180)
                report["module_loaded"] |= "CHECK name=finit_module rc=0 expected=0 PASS" in log
                verify_pins()
                guest = audit(log, trace.read_text(), cpus)
                guest.update(log_sha256=sha(out / f"guest-{cpus}.log"), trace_sha256=sha(trace))
                report["guests"].append(guest)
                save("result.json", report)
            report["state"] = "QEMU_LINUX_VIEW_V2_SAFETY_PASS"
        else:
            report["state"] = "PREPARED_NOT_EXECUTED" if args.module else "INIT_BUILT_MODULE_REQUIRED"
        verify_pins()
        report["source_pins_match"] = True
    except Exception as error:
        report["error"] = repr(error)
    finally:
        save("source-pins.json", pins)
        save("commands.json", commands)
        save("result.json", report)
    print(json.dumps(report, sort_keys=True), flush=True)
    return int(report["state"] == "FAIL")


if __name__ == "__main__":
    raise SystemExit(main())

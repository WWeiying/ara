#!/usr/bin/env python3
"""Run the Linux payload contract on QEMU, not as RTL or board evidence."""

import argparse
import json
from pathlib import Path

from check_boot import USERSPACE_MARKERS, check_stage_result
from run_stage import run_stage, sha256


SDK = Path("/home/wangwy/openproject/cva6/cva6-sdk")
REPO = Path(__file__).resolve().parents[2]
MARKERS = [*USERSPACE_MARKERS,
           "[LINUX_RVV] PASS arithmetic_load_store",
           "[LINUX_RVV] PASS vfredmax_boundary",
           "[LINUX_RVV] PASS preempt_parent", "[LINUX_RVV] PASS preempt_child",
           "[LINUX_RVV] PASS signal_return", "[LINUX_RVV] PASS scalar_fault_return",
           "[LINUX_RVV] PASS illegal_instruction_return",
           "RVV fallback userspace PASS", "RVV context switch and fault return PASS",
           "CUSTOM_COMPUTE=NOT_VALIDATED"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--qemu", type=Path,
                        default=SDK / "buildroot/output/host/bin/qemu-system-riscv64")
    parser.add_argument("--kernel", type=Path,
                        default=REPO / "hardware/fpga/ara_dsa_vcu118/linux/artifacts/Image")
    parser.add_argument("--firmware", type=Path, default=SDK / "install64_qemu/fw_dynamic.bin")
    parser.add_argument("--vlen", type=int, choices=(128, 256, 512, 1024), default=1024)
    parser.add_argument("--memory-mib", type=int, choices=(256, 512, 1024), default=512,
                        help="QEMU RAM size; choose the SoC candidate's declared size for comparison")
    parser.add_argument("--kernel-loglevel", type=int, choices=range(8),
                        help="optional Linux console log level for boot-speed preflight")
    args = parser.parse_args()
    try:
        output = args.output.resolve()
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise ValueError(f"output must be empty: {output}")
        payload = args.payload.resolve()
        manifest_path = payload / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("status") != "BUILT":
            raise ValueError("payload build did not finish")
        artifacts = {"kernel": args.kernel.resolve(), "firmware": args.firmware.resolve(),
                     "emulator": args.qemu.resolve(), "payload_manifest": manifest_path,
                     "initramfs": payload / "initramfs.cpio", "elf": payload / "rvv_linux_smoke"}
        for path in artifacts.values():
            if not path.is_file():
                raise ValueError(f"missing artifact: {path}")
        for name in ("initramfs.cpio", "rvv_linux_smoke"):
            if manifest["outputs"][name]["sha256"] != sha256(payload / name):
                raise ValueError(f"payload changed after build: {name}")
        bootargs = "console=ttyS0 earlycon=sbi rdinit=/init panic=1"
        if args.kernel_loglevel is not None:
            bootargs += f" loglevel={args.kernel_loglevel}"
        command = [str(artifacts["emulator"]), "-machine", "virt", "-cpu",
                   f"rv64,v=true,vlen={args.vlen},elen=64,zfh=true,zvfh=true",
                   "-smp", "1", "-m", f"{args.memory_mib}M", "-no-reboot", "-display", "none", "-monitor", "none",
                   "-serial", "stdio", "-bios", str(artifacts["firmware"]),
                   "-kernel", str(artifacts["kernel"]), "-initrd", str(artifacts["initramfs"]),
                   "-append", bootargs]
        run_stage("qemu", output, command, MARKERS, artifacts, 180)
        checked = check_stage_result(output / "stage_result.json", expected_stage="qemu",
                                     required_markers=MARKERS)
        checked["scope"] = "Linux userspace payload on QEMU; custom compute not validated"
        (output / "userspace_check.json").write_text(json.dumps(checked, indent=2) + "\n")
        print(json.dumps({"status": checked["status"], "output": str(output)}))
        return 0 if checked["status"] == "PASS" else 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

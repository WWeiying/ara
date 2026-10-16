"""Bounded shell/DDR/tmpfs smoke test; not vector or peripheral signoff."""
import argparse
import json
from pathlib import Path
import re
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=90)
    parser.add_argument("--tx-gap", type=float, default=0,
                        help="Seconds between command bytes for small UART receive FIFOs")
    parser.add_argument("--clear-line", action="store_true",
                        help="Send Ctrl-C before the initial newline to discard our incomplete command")
    parser.add_argument("--serial-wheel", type=Path,
                        help="Existing pyserial wheel, as used by host_load.py")
    args = parser.parse_args()
    if not 0 <= args.tx_gap <= 1:
        parser.error("--tx-gap must be between zero and one second")
    if args.serial_wheel:
        if not args.serial_wheel.is_file():
            parser.error("--serial-wheel does not exist")
        sys.path.insert(0, str(args.serial_wheel))
    import serial
    args.out.mkdir(parents=True, exist_ok=False)
    data = bytearray()
    report = {"passed": False, "scope": "shell_tmpfs_scalar_only",
              "tx_gap_seconds": args.tx_gap, "clear_line": args.clear_line}
    command = (
        "uname -a && cat /proc/cpuinfo && "
        "dd if=/dev/zero of=/tmp/ara_console_check.bin bs=4096 count=256 && "
        "sha256sum /tmp/ara_console_check.bin && "
        "cp /tmp/ara_console_check.bin /tmp/ara_console_check.copy && "
        "cmp /tmp/ara_console_check.bin /tmp/ara_console_check.copy && "
        "printf '\\nARA_SHELL_MEMORY_%s\\n' OK\n"
    )
    try:
        with serial.Serial(args.port, 115200, timeout=0.2,
                           rtscts=False, dsrdtr=False) as console:
            if args.clear_line:
                console.write(b"\x03")
                time.sleep(0.2)
            console.write(b"\n")
            deadline = time.monotonic() + args.seconds
            sent = False
            while time.monotonic() < deadline:
                data.extend(console.read(4096))
                if not sent and re.search(rb"(?:^|[\r\n])[^\r\n]*[#$] $", data):
                    if args.tx_gap:
                        for byte in command.encode("ascii"):
                            console.write(bytes([byte]))
                            time.sleep(args.tx_gap)
                    else:
                        console.write(command.encode("ascii"))
                    sent = True
                if re.search(rb"(?:^|[\r\n])ARA_SHELL_MEMORY_OK[\r\n]", data):
                    report["passed"] = True
                    break
            report["command_sent"] = sent
            if not report["passed"]:
                report["error"] = "Shell smoke marker not received before deadline"
    except (OSError, serial.SerialException) as exc:
        report["error"] = str(exc)
    finally:
        (args.out / "uart.bin").write_bytes(data)
        (args.out / "uart.txt").write_text(data.decode("utf-8", errors="replace"))
        (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

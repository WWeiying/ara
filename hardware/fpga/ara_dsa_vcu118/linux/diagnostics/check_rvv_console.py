"""Upload a small RVV context test to Linux tmpfs and require checked completion."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--serial-wheel", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=120)
    args = parser.parse_args()
    payload = args.elf.read_bytes()
    if not payload.startswith(b"\x7fELF") or not 0 < len(payload) <= 32768:
        parser.error("Expected a small ELF, at most 32 KiB")
    sys.path.insert(0, str(args.serial_wheel))
    import serial
    args.out.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256(payload).hexdigest()
    report = {"passed": False, "elf_sha256": digest, "elf_bytes": len(payload),
              "scope": "128_syscalls_with_vector_reinitialization_and_131072_checked_bytes"}
    data = bytearray()

    def receive(console, pattern, seconds):
        deadline = time.monotonic() + seconds
        start = len(data)
        while time.monotonic() < deadline:
            data.extend(console.read(4096))
            match = re.search(pattern, data[start:])
            if match:
                return match
        raise TimeoutError("Console marker deadline exceeded")

    try:
        with serial.Serial(args.port, 115200, timeout=0.2,
                           write_timeout=5, rtscts=False, dsrdtr=False) as console:
            console.write(b"\nprintf '\\nARA_HOST_%s\\n' READY\n")
            receive(console, rb"(?:^|[\r\n])ARA_HOST_READY[\r\n]", 15)
            console.write(b"base64 -d > /tmp/ara_rvv_context_check <<'ARA_ELF_END'\n")
            encoded = base64.b64encode(payload)
            for offset in range(0, len(encoded), 64):
                console.write(encoded[offset:offset + 64] + b"\n")
                time.sleep(0.02)
            console.write(b"ARA_ELF_END\n")
            command = (
                "actual=$(sha256sum /tmp/ara_rvv_context_check); "
                f"[ \"${{actual%% *}}\" = {digest} ] && "
                "chmod +x /tmp/ara_rvv_context_check && /tmp/ara_rvv_context_check; "
                "r=$?; printf '\\nARA_RVV_EXIT_%s\\n' \"$r\"\n"
            )
            console.write(command.encode("ascii"))
            result = receive(console, rb"(?:^|[\r\n])ARA_RVV_EXIT_([0-9]+)[\r\n]", args.seconds)
            report["exit_code"] = int(result.group(1))
            marker = rb"(?:^|[\r\n])ARA_RVV_CONTEXT_OK iterations=128 bytes_checked=131072[\r\n]"
            report["passed"] = report["exit_code"] == 0 and re.search(marker, data) is not None
            if not report["passed"]:
                report["error"] = "RVV checked marker or successful exit missing"
    except (OSError, TimeoutError, serial.SerialException) as exc:
        report["error"] = str(exc)
    finally:
        (args.out / "uart.bin").write_bytes(data)
        (args.out / "uart.txt").write_text(data.decode("utf-8", errors="replace"))
        (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

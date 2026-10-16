#!/usr/bin/env python3
"""Cold integrated-board Linux diagnostic using guarded JTAG or Ethernet loading."""
import argparse
import contextlib
from pathlib import Path
import secrets
import socket
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--rootfs", type=Path)
    parser.add_argument("--probes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--vivado", required=True)
    parser.add_argument("--port", default="COM6")
    parser.add_argument("--seconds", type=float, default=120)
    parser.add_argument("--marker", default="Linux console, DDR and RVV handoff are alive")
    parser.add_argument("--ethernet-host", help="Use the existing guarded integrated Ethernet loader instead")
    parser.add_argument("--source", default="192.168.1.11")
    args = parser.parse_args()
    sys.path.insert(0, str(args.tools / "ethernet"))
    import ara_load as integrated
    host = integrated.host
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"state": "starting", "passed": False,
              "transport": "Ethernet" if args.ethernet_host else "JTAG",
              "diagnostic_only": True, "ethernet_packets_used": bool(args.ethernet_host)}
    try:
        image = integrated.prepare_image(args.base / "fw_jump.elf", [
            (0x80100000, args.base / "ara_vcu118.dtb"),
            (0x80200000, args.image),
            (0x88000000, args.rootfs or args.base / "initramfs.cpio")],
            caps=integrated.CAP_HOST, allow_dynamic=True)
        integrated.validate_image(image)
        report["image"] = image.manifest()
        with integrated.VivadoTransport(args.out / "transport", vivado=args.vivado,
                                        probes=args.probes) as transport:
            report["identity"] = host.identity(transport)
            report["cold_before"] = integrated.cold_guard(transport)
            report["ethernet_before"] = integrated.loader_status(transport.ethernet_status())
            with contextlib.ExitStack() as stack:
                if args.ethernet_host:
                    sock = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
                    sock.bind((args.source, 0))
                    sock.connect((args.ethernet_host, 49204))
                    def launch():
                        return integrated.load_and_run(
                            transport, sock, image, args.out, report,
                            full_reset_confirmed=True,
                            run_id=secrets.randbelow(0xffffffff) + 1,
                            seconds=args.seconds, launch_only=True)
                else:
                    report["ethernet_locked"] = integrated.lock_and_drain(transport)
                    def launch():
                        return host.load_and_run(
                            transport, image, args.out, report, full_reset_confirmed=True,
                            run_id=secrets.randbelow(0xffffffff) + 1, seconds=args.seconds,
                            batch_chunks=128, launch_only=True)
                print("COLD_GUARD_PASS transport=" + report["transport"], flush=True)
                console = stack.enter_context(host.serial_module().Serial(
                    args.port, 115200, timeout=0.2, rtscts=False, dsrdtr=False))
                report["uart"] = host.wait_linux_console(
                    console, args.out, launch, args.seconds,
                    marker=args.marker.encode("ascii"))
            report.update(state="passed_requested_console_marker", passed=True,
                          requested_marker=args.marker)
    except (OSError, ValueError, RuntimeError, StopIteration) as exc:
        report.update(state="failed", passed=False, error=str(exc))
    finally:
        host.write_json(args.out / "report.json", report)
    print(report["state"], args.out, report.get("error", ""), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

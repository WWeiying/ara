#!/usr/bin/env python3
"""UART register snapshot after Linux starts; RBR read may consume one byte."""
import argparse
import json
from pathlib import Path

from host_transport import Operation, VivadoTransport


REGISTERS = {
    "uart_rbr_ier": 0x03002000,
    "uart_iir_lcr": 0x03002008,
    "uart_mcr_lsr": 0x03002010,
    "uart_msr_scr": 0x03002018,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probes", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--vivado", default="vivado")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"memory_writes": False, "rbr_read_may_consume_rx": True,
              "registers": {}}
    try:
        with VivadoTransport(args.out / "transport", vivado=args.vivado,
                             probes=args.probes) as transport:
            for name, address in REGISTERS.items():
                word = transport.exchange([Operation("M", "READ", address)])[0]
                report["registers"][name] = {
                    "address": hex(address),
                    "low": hex(int.from_bytes(word[:4], "little")),
                    "high": hex(int.from_bytes(word[4:], "little")),
                }
    finally:
        (args.out / "uart_state.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

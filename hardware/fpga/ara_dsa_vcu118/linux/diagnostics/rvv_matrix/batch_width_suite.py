"""Legacy recovery-wrapper entry point for the opt-in batch observer."""
import argparse
from pathlib import Path
from batch_serial import main, verify


def arguments(argv=None, root=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--reuse-directory', required=True)
    parser.add_argument('--verify-only', action='store_true')
    selected = parser.parse_args(argv)
    selected.root = root or Path(__file__).resolve().parent
    selected.guest_directory = selected.reuse_directory
    selected.host_tools = Path(r'D:\fpga_runs\ara_dual_linux_memory_20261006_01\tools\software')
    selected.probes = Path(r'D:\fpga_runs\ara_dual_bitgen_20261006_01\bitstream\ara_dsa_vcu118.ltx')
    selected.vivado = Path(r'D:\Xilinx\Vivado\2020.1\bin\vivado.bat')
    selected.port = 'COM6'
    return selected


if __name__ == '__main__':
    args = arguments()
    if args.verify_only:
        from batch_serial import command
        _, protocol = verify(args.root)
        command(args.guest_directory, protocol['script_sha256'])
        print('BATCH_OBSERVER_PREFLIGHT_PASS')
    else:
        raise SystemExit(main(args))

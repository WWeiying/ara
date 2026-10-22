"""Run the native printf successor using the unchanged eight-case acceptance."""
import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import run_masklogical_restart8 as sealed

PRE = sealed.ROOT / 'verification/out/masklogical-restart8-nativefix-preflight-20261008-01'
ELF_SHA = 'a306e117bab7c28967da01ff38b7a23bc21ac1690ac222d84f2e4b674524485b'


def execute(build, output):
    from build_masklogical_restart8_nativefix import check_native
    check_native((PRE / 'native-no-syscalls-disassembly.log').read_text(),
                 (PRE / 'native-link.log').read_text())
    sealed.PRE = PRE
    sealed.ELF_SHA = ELF_SHA
    return sealed.execute(build, output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(execute(args.build.resolve(), args.output.resolve()))

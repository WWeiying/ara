#!/usr/bin/env python3
"""Route the immutable scheduling gates through profile-bound tail aggregation."""
import argparse
from pathlib import Path
import signal
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from verification.akv.quantized_kv.tail_split import coordinate as original
from verification.akv.quantized_kv.tail_split import coordinate_v2, combine_v2

HERE = Path(__file__).resolve().parent
BaseExecution = original.Execution


class Execution(BaseExecution):
    def execute(self, argv, log, timeout, phase):
        command = list(map(str, argv))
        if phase == 'COMBINING':
            original.s.require(command[:4] == ['/usr/bin/python3', '-B',
                               str(HERE/'combine.py'), '--runs'] and
                               len(command) == 10 and command[-2] == '--output',
                               'Unexpected aggregate command policy')
            command[2] = str(HERE/'combine_v2.py')
        return super().execute(command, log, timeout, phase)


def downstream_args(target, combined, output):
    command = original_downstream_args(target, combined, output)
    original.s.require(command[:3] == ['/usr/bin/python3', '-B', str(HERE/'threeway.py')],
                       'Unexpected downstream worker policy')
    return command[:2] + [str(HERE/'threeway_v2.py')] + command[3:]


original_downstream_args = original.downstream_args


def configure():
    original.Execution = Execution
    original.wait_all = coordinate_v2.wait_all
    original.checked_combined = combine_v2.checked_combined
    original.downstream_args = downstream_args


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--launch', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--unit-prefix', required=True)
    for kind in ('q4', 'q8'):
        parser.add_argument('--'+kind+'-build', type=Path, required=True)
        parser.add_argument('--'+kind+'-prerequisite', type=Path, default=original.ROOT /
                            f'verification/out/akv-quantkv-strided-attention-{kind}-20261024-01')
    parser.add_argument('--wait-timeout', type=int, default=10800)
    parser.add_argument('--inspect-only', action='store_true')
    args = parser.parse_args()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, coordinate_v2.interrupted)
    configure()
    original.run(args)


if __name__ == '__main__':
    main()

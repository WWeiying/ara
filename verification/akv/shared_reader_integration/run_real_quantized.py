#!/usr/bin/env python3
"""Successor launch policy: QBS counters, no F16-AKV summary, unchanged checkers."""
import argparse
from pathlib import Path
import signal
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_real_runtime as worker


def counter_flags(argv, phase):
    result = list(argv)
    if phase != 'RUNNING':
        return result
    text = list(map(str, result))
    cases = [a for a in text if a.startswith('+TESTCASE=')]
    worker.s.require(len(cases) == 1 and cases[0] in (
        '+TESTCASE=shared_real_quant_q4_0', '+TESTCASE=shared_real_quant_q8_0') and
        Path(text[0]).name == 'simv' and text.count('+AKV_PERF') == text.count('+AKV_SUMMARY') == 1 and
        '+QBS_PERF' not in text, 'Unexpected predecessor simulator command')
    return [a for a in result if str(a) not in ('+AKV_PERF', '+AKV_SUMMARY')] + ['+QBS_PERF']


class QuantizedExecution(worker.Execution):
    def execute(self, argv, log, timeout, phase):
        selected = counter_flags(argv, phase)
        if phase == 'RUNNING':
            self.state['counter_policy'] = 'QBS_PERF_ONLY_NO_AKV_SUMMARY'
            self.save()
        return super().execute(selected, log, timeout, phase)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=('quant_q4_0','quant_q8_0'), required=True)
    for name in ('soc-build','build','prior','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    worker.Execution = QuantizedExecution
    worker.run(args)

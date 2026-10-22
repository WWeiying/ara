"""Offline encoding-only closure of frozen CSR02 native qualification."""
import argparse
import json
import re
from decimal import Decimal
from pathlib import Path
from types import FunctionType

import capture_csr_reserved1193_v2 as frozen

ORIGINAL_SHA = '1bd92817145456021c00c3873bbb469d0d4511657518c0a274192dd1985ceb9c'
CONFIG_SHA = '564012de8606df39dc91981ab857092cd6e49ff5f2463b8cebd40c5629c3786d'
SOURCE = frozen.life.OUT/'csr-reserved1193-native-agent-20261007-02'


def percent(value):
    frozen.require(isinstance(value, str) and
                   re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?%', value) is not None,
                   'Exact native percent encoding')
    # One suffix only; whitespace, repeated signs and nonfinite values are rejected.
    number = Decimal(value.removesuffix('%'))
    frozen.require(0 <= number <= 100, 'Native percent range')
    return float(number)


metrics = FunctionType(frozen.metrics.__code__, dict(vars(frozen), float=percent))
compare_metrics = FunctionType(frozen.compare_metrics.__code__, dict(vars(frozen), float=percent))


def audit(output):
    life = frozen.life
    frozen.require(output.parent == life.OUT and not output.exists(), 'Fresh offline qualification directory')
    frozen.require(life.digest(Path(frozen.__file__)) == ORIGINAL_SHA, 'Frozen02 verifier source seal')
    frozen.require(not (SOURCE/'capture-result.json').exists(), 'Original02 not already qualified')
    hold = json.loads((SOURCE/'qualification-hold.json').read_bytes())
    frozen.require(hold['status'] == 'HOLD_NOT_APPLIED' and hold['reason'] == 'Native metric encoding',
                   'Preserved original encoding-only rejection required')
    before = {str(p): life.digest(p) for p in SOURCE.rglob('*') if p.is_file()}

    class Evidence:
        def __getattr__(self, name):
            return getattr(life, name)

        def save(self, path, result):
            frozen.require(path == SOURCE/'capture-result.json', 'Only qualification output redirected')
            life.check(before)
            extra = {str(Path(__file__).resolve()): life.digest(Path(__file__).resolve()),
                     str(Path(__file__).with_name('test_audit_csr_reserved1193_percent.py')):
                         life.digest(Path(__file__).with_name('test_audit_csr_reserved1193_percent.py'))}
            result = dict(result, status='CSR1193_LOCAL_NATIVE_OFFLINE_PERCENT_ENCODING_QUALIFIED',
                          original_attempt=str(SOURCE), original_verifier_sha=ORIGINAL_SHA,
                          correction='Strict single percent suffix parsing only; original CSV strings retained',
                          original_attempt_success_claim=False,
                          pins=life.merge_pins(result['pins'], before, extra))
            output.mkdir()
            life.save(output/'qualification.json', result)

        def digest(self, path):
            return life.digest(output/'qualification.json' if path == SOURCE/'capture-result.json' else path)

    # All original terminal/tool, DONE, source/config, typed complements, native EL,
    # reset/roundtrip and metric identity gates run unchanged.
    verify = FunctionType(frozen.verify.__code__, dict(vars(frozen), life=Evidence(),
                          metrics=metrics, compare_metrics=compare_metrics,
                          print=lambda *args, **kwargs: None))
    verify(SOURCE, CONFIG_SHA)
    life.check(before)
    frozen.require(not (SOURCE/'capture-result.json').exists(), 'Original attempt remains untouched')
    print(json.dumps(dict(status='CSR1193_LOCAL_NATIVE_OFFLINE_PERCENT_ENCODING_QUALIFIED',
                          output=str(output), seal=life.digest(output/'qualification.json'))), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    audit(parser.parse_args().output.absolute())

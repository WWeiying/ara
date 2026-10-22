#!/usr/bin/env python3
"""Independently check closed local evidence; never start or change a simulation."""
import csv
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parent
    data = root / 'measurement01'
    result = data / 'result.json'
    assert digest(result) == 'e2af226c3b560e06782bd1bd1c482bd5e841970d123488be99a876a42b6eb5e6'
    for filename, expected in (
        ('cycles.csv', 'accb9536879cc1d30dce3a5e0ac261f951416d29604ea062d75144059f5ace8e'),
        ('context.csv', '21d9503179da770350d7c6da26159fdd25f1f78861bc92c9339edbd042d93985'),
    ):
        assert digest(data / 'candidate' / filename) == expected
    pins = json.loads((data / 'input_pins.json').read_text())
    for filename, expected in pins.items():
        assert digest(Path(filename)) == expected, filename
    for version in ('candidate', 'm8_normals'):
        folder = data / version
        for stage in ('compile', 'run'):
            receipt = json.loads((folder / (stage + '_exit.json')).read_text())
            assert receipt['returncode'] == 0 and not receipt['timeout']
        log = (folder / 'run.log').read_text()
        assert not any(s in log for s in ('Fatal:', 'Error:', '[ASSERT FAILED]'))
        assert log.count('M9_LOCAL_ACCEPTANCE_COMPLETE') == 1
        frozen = json.loads((folder / 'pins.json').read_text())
        for filename, expected in frozen.items():
            assert digest(folder / 'frozen' / filename) == expected
    with (data / 'candidate' / 'cycles.csv').open() as stream:
        cycles = list(csv.DictReader(stream))
    with (data / 'candidate' / 'context.csv').open() as stream:
        context = list(csv.DictReader(stream))
    assert len(cycles) == len(context) == 1757
    for case, addresses in enumerate((
        [0x80010000, 0x80010008], [0x80010000], [0x80010000], [],
        [0x80010000], [0x80010000, 0x80010000], [0x80010008, 0x80010000],
    )):
        rows = [r for r in cycles if int(r['case']) == case]
        meta = [r for r in context if int(r['case']) == case]
        assert [int(r['cycle']) for r in rows] == list(range(5, 256))
        assert [int(r['cycle']) for r in meta] == list(range(5, 256))
        actual = [int(r['ar_addr'], 16) for r in rows
                  if r['ar_valid'] == r['ar_ready'] == '1']
        assert actual == addresses, (case, actual)
        ack = [r for r in meta if r['ack'] == '1']
        reply = [m for r, m in zip(rows, meta) if r['response'] == '1']
        assert len(ack) == len(reply) == 1
        fault = case in (1, 3)
        assert int(ack[0]['exception']) == int(reply[0]['resp_exception']) == int(fault)
        if fault:
            assert ack[0]['cause'] == reply[0]['resp_cause'] == '4'
            assert int(ack[0]['tval'], 16) == int(reply[0]['resp_tval'], 16) == 0x80010004
            assert ack[0]['exception_start'] == reply[0]['resp_start'] == '1'
        assert sum(int(r['load_complete']) for r in rows) == 1
        assert sum(int(r['done'], 2) != 0 for r in rows) == 1
        assert rows[-1]['global_idle'] == rows[-1]['ld_idle'] == rows[-1]['ag_idle'] == '1'
        if case == 1:
            grants = [int(r['cycle']) for r in rows if int(r['final_gnt'], 2)]
            assert grants == [15] and int(reply[0]['cycle']) == 17
        print('case={} closed_rows={} AR={} fault={}'.format(case, len(rows), len(actual), fault))
    for filename in ('cycles.csv', 'context.csv'):
        original = (data / 'candidate' / filename).read_bytes().splitlines(keepends=True)
        selected = original[:1] + [r for r in original[1:] if r.split(b',')[0] in (b'4', b'5', b'6')]
        assert b''.join(selected) == (data / 'm8_normals' / filename).read_bytes()
    print('PASS: closed local LOAD evidence and normal-cycle identity; STORE/MMU/SoC not covered')


if __name__ == '__main__':
    main()

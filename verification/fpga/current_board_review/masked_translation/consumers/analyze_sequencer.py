#!/usr/bin/env python3
"""Check fixed-stimulus sequencer fault-barrier A/B evidence."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEQ = 'hardware/src/ara_sequencer.sv'
TB = 'verification/fpga/current_board_review/masked_translation/consumers/sequencer_fault_tb.sv'
EXPECTED = {
    'normal_delayed_done': 9,
    'fof_fault_delayed_done': 21,
    'fault_delayed_done': 21,
    'other_vid_done': 25,
    'done_before_ack': 15,
    'done_with_ack': 9,
    'fof_no_fault': 9,
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_run(directory):
    status = json.loads((directory / 'status.json').read_text())
    pins = json.loads((directory / 'pins.json').read_text())['files']
    assert status['state'] == 'PROBES_COMPLETE' and status['frozen_verified']
    cases = {}
    for entry in status['cases']:
        name = entry['name']
        assert entry['returncode'] == 0 and entry['probe_completed']
        assert 'Fatal:' not in (directory / name / 'run.log').read_text()
        with (directory / name / 'cycles.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        responses = [r for r in rows if r['slot'] == '1' and r['resp_valid'] == '1']
        assert len(responses) == 1
        observation = entry['observation']
        response = responses[0]
        assert int(response['cycle']) == observation['response']
        assert int(response['resp_exception']) == observation['fault']
        assert int(response['resp_fof']) == (observation['fault'] and observation['fof'])
        if observation['fault']:
            assert int(response['resp_vstart']) == 3
        cases[name] = observation
    assert cases.keys() == EXPECTED.keys()
    return pins, cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    before = HERE / 'sequencer_before10'
    after, out = args.after.resolve(), args.out.resolve()
    assert after.is_relative_to(HERE) and out.is_relative_to(HERE) and not out.exists()
    bp, bc = read_run(before)
    ap, ac = read_run(after)
    assert bp[TB] == ap[TB] == '2e6e022a52d436a8e6cf0ba2ece08f481d2c11bc41dcc347903ad5d5c145e182'
    changes = {name: [bp.get(name), ap.get(name)] for name in bp.keys() | ap.keys()
               if bp.get(name) != ap.get(name)}
    assert set(changes) == {SEQ}, changes
    assert sha(before / 'frozen/sequencer_types.svh') == sha(after / 'frozen/sequencer_types.svh')
    for name, cycle in EXPECTED.items():
        b, a = bc[name], ac[name]
        assert a['response'] == cycle and a['early_fault_response'] == 0 and a['idle'] == 1
        for field in ('case', 'owner', 'other_owner', 'pe', 'ack', 'done', 'other_done', 'fault', 'fof'):
            assert b[field] == a[field], (name, field)
        if name in ('normal_delayed_done', 'fof_no_fault', 'done_before_ack', 'done_with_ack'):
            assert b == a
        else:
            assert b['early_fault_response'] == 1 and b['response'] < b['done']
    result = dict(status='PASS_7_SEQUENCER_FAULT_BARRIER',
                  scope='Real sequencer public-port unit; AddrGen/VLDU completion peers modeled; not SoC',
                  before=str(before), after=str(after), source_changes=changes,
                  tb_sha256=ap[TB], metadata_oracle_preserved=True,
                  observations_before=bc, observations_after=ac,
                  status_sha256={str(p): sha(p / 'status.json') for p in (before, after)})
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], 'RTL', ap[SEQ])


if __name__ == '__main__':
    main()

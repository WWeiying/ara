#!/usr/bin/env python3
"""Compare preserved VLDU experiments without changing their evidence."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RTL = 'hardware/src/vlsu/vldu.sv'
TB_ROOT = 'verification/fpga/current_board_review/masked_translation/consumers/'


def read_run(name):
    directory = HERE / name
    status = json.loads((directory / 'status.json').read_text())
    pins = json.loads((directory / 'pins.json').read_text())['files']
    if status['state'] != 'PROBES_COMPLETE':
        raise ValueError('Incomplete probe run: ' + name)
    cases = {}
    for case in status['cases']:
        if not case['probe_completed'] or case['returncode']:
            raise ValueError('Probe execution failed: ' + name + '/' + case['name'])
        if 'Fatal:' in (directory / case['name'] / 'run.log').read_text():
            raise ValueError('Simulation assertion failed: ' + name + '/' + case['name'])
        cases[case['name']] = case['observation']
    return pins, cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(HERE) or out.exists():
        raise ValueError('New owned output file required')
    names = ('baseline02', 'candidate03', 'arrival_candidate04', 'arrival_baseline05',
             'successor06', 'arrival_successor07')
    runs = {name: read_run(name) for name in names}
    tb = TB_ROOT + 'vldu_exception_tb.sv'
    assert len({runs[n][0][tb] for n in ('baseline02', 'candidate03', 'successor06')}) == 1
    atb = TB_ROOT + 'vldu_arrival_tb.sv'
    assert len({runs[n][0][atb] for n in ('arrival_candidate04', 'arrival_baseline05',
                                        'arrival_successor07')}) == 1
    assert runs['successor06'][0][RTL] == runs['arrival_successor07'][0][RTL]
    before, after = runs['baseline02'][1], runs['successor06'][1]
    assert len(before) == len(after) == 6
    assert before['partial_exception']['early_data_done'] == 1
    assert before['fof_exception_successor']['early_data_done'] == 1
    assert before['first_exception']['idle_after_flush'] == 0
    assert before['normal_delayed_final'] == after['normal_delayed_final']
    for case in after.values():
        assert case['early_data_done'] == 0 and case['idle_after_flush'] == 1
        assert case['successor_done'] == 1 and case['successor_idle'] == 1
    # The admission-only successor must preserve every PE-first observation.
    assert runs['candidate03'][1] == after
    bad_arrival = runs['arrival_candidate04'][1]
    old_arrival = runs['arrival_baseline05'][1]
    fixed_arrival = runs['arrival_successor07'][1]
    assert len(bad_arrival) == len(old_arrival) == len(fixed_arrival) == 4
    for name, case in fixed_arrival.items():
        assert bad_arrival[name]['accepts'] == bad_arrival[name]['dones'] == 0
        assert old_arrival[name]['accepts'] == old_arrival[name]['dones'] == 1
        assert case['accepts'] == case['dones'] == 1 and case['idle'] == 1
        assert case['pops'] == int(name.startswith('descriptor_'))
    result = dict(scope='Public-port VLDU unit only; not SoC or Sv39 signoff',
                  status='PASS_6_EXCEPTION_4_ARRIVAL',
                  same_tb_verified=True, pe_first_cycles_preserved=True,
                  rtl_sha256={name: runs[name][0][RTL] for name in names},
                  tb_sha256=runs['successor06'][0][tb],
                  arrival_tb_sha256=runs['arrival_successor07'][0][atb],
                  observations={name: runs[name][1] for name in names},
                  status_sha256={name: hashlib.sha256((HERE / name / 'status.json').read_bytes()).hexdigest()
                                 for name in names})
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], 'RTL', result['rtl_sha256']['successor06'])


if __name__ == '__main__':
    main()

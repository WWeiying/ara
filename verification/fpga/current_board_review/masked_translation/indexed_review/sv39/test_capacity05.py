#!/usr/bin/env python3
"""Bounded host admission tests; no process control or simulation."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import successor_capacity05 as s


def main():
    refused = []
    def reject(name, fn):
        try:
            fn()
        except ValueError:
            refused.append(name)
        else:
            raise AssertionError('Unexpected acceptance: ' + name)
    state = dict(LoadState='not-found', ActiveState='inactive', MainPID='0', ControlGroup='')
    external = [dict(pid=100+i, exe='/other/simv', cwd='/other/work', argv=['/other/simv'],
                     cgroups=['/session-17.scope'], starttime=str(i)) for i in range(7)]
    for count in range(7):
        result = s.decide(state, state, external[:count], 2)
        assert result['total_at_admission'] == count + 2 and result['external_simvs'] == external[:count]
    reject('seven_external', lambda: s.decide(state, state, external, 2))
    for jobs in (0, 1, 3, 4):
        reject('wrong_jobs_' + str(jobs), lambda: s.decide(state, state, [], jobs))
    for own in ('nf2', 'arithmetic'):
        active = {**state, 'LoadState': 'loaded', 'ActiveState': 'active', 'MainPID': '42'}
        reject(own + '_live', lambda: s.decide(active if own == 'nf2' else state,
                                             active if own == 'arithmetic' else state, [], 2))
        root = s.gate.NF2.parent if own == 'nf2' else s.gate.ARITH
        unit = s.gate.NF2_UNIT if own == 'nf2' else s.gate.ARITH_UNIT
        for source, value in [('cgroups', ['/slice/' + unit]), ('argv', ['--out=' + str(root)]),
                              ('cwd', str(root / 'run'))]:
            record = {**external[0], 'exe': '/usr/bin/python3', source: value}
            reject(own + '_residual_' + source, lambda: s.decide(state, state, [record], 2))
    reject('unknown_active_cgroup', lambda: s.decide({**state, 'ControlGroup': '/owned'}, state, [], 2))
    plan = s.gate.read(s.snapshot.PREVIOUS / 'plan.json')
    plan.update(max_jobs=2, suggested_service_runtime_s=33600)
    s.validate(plan)
    for key, value in [('max_jobs', 4), ('suggested_service_runtime_s', 16800), ('group_timeout_s', 2401),
                       ('group_outer_s', 2701), ('groups', [0]), ('trials', list(range(95)))]:
        reject('plan_' + key, lambda: s.validate({**plan, key: value}))
    s.gate.save(s.HERE / 'capacity05_host_tests.json', dict(status='HOST_CAPACITY05_PASS_NOT_DUT',
        accepted_external_counts=list(range(7)), negatives=refused, VCS_started=False,
        pins=s.gate.pins([Path(__file__), Path(s.__file__), Path(s.snapshot.__file__), Path(s.gate.__file__)])))
    print('HOST_CAPACITY05_PASS_NOT_DUT', len(refused))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Focused host tests for the explicitly authorized scheduling delta."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import successor_resources06 as s


def main():
    state = dict(LoadState='not-found', ActiveState='inactive', MainPID='0', ControlGroup='')
    proc = dict(pid=1, exe='/other/simv', cwd='/other/work', argv=['simv'], cgroups=['/other'], starttime='1')
    external = [{**proc, 'pid': i+1} for i in range(22)]
    alias = {**proc, 'pid': 90, 'cgroups': ['/slice/' + s.ALIAS_UNIT]}
    memory = 32*1024**3
    assert s.ALIAS_OUT == Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/mask_alias_original/vcs_candidate02_01')
    assert s.decide(state, state, external[:21], 2, memory)['total_live_reserved'] == 24
    result = s.decide(state, state, external[:21]+[alias], 2, memory)
    assert result['total_live_reserved'] == 24 and result['alias_actual'] == 1
    alias_path = {**alias, 'cgroups': ['/other'], 'cwd': str(s.ALIAS_OUT / 'run/tests/alias/work')}
    assert s.decide(state, state, [alias_path], 2, memory)['alias_actual'] == 1
    refused = []
    for name, processes, jobs, free in [('cap_without_alias', external, 2, memory),
            ('cap_with_alias', external+[alias], 2, memory), ('memory', [], 2, memory-1),
            ('jobs', [], 4, memory), ('own_residual', [{**proc, 'cgroups': ['/slice/'+s.gate.ARITH_UNIT]}], 2, memory),
            ('alias_substring_not_membership', external[:21]+[{**alias, 'cgroups': ['/slice/'+s.ALIAS_UNIT+'-fake']}], 2, memory)]:
        try:
            s.decide(state, state, processes, jobs, free)
        except ValueError:
            refused.append(name)
        else:
            raise AssertionError(name)
    s.gate.save(s.HERE / 'resources06_host_tests.json', dict(status='HOST_RESOURCES06_PASS_NOT_DUT',
        negatives=refused, pending_alias_reserved=True, live_alias_not_double_counted=True,
        exact_alias_path_match=True, VCS_started=False,
        pins=s.gate.pins([Path(__file__), Path(s.__file__), Path(s.previous.__file__), Path(s.snapshot.__file__)])))
    print('HOST_RESOURCES06_PASS_NOT_DUT', len(refused))


if __name__ == '__main__':
    main()

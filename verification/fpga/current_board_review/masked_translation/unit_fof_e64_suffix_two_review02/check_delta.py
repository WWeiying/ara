"""Independent owner-delta review only; no reference, CSV, or DUT execution."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
WORK = HERE.parent / 'unit_fof_e64_suffix_two_vcs_m9_plan01'
PREP = WORK / 'prepared01'
PRIOR = HERE.parent / 'unit_fof_e64_suffix_two_review01'
PLAN = '3bc80c42d8e6bf7f722d81184ef8fc4bcac099e2518547292f5172665324e949'
sys.path.insert(0, str(WORK))
import test_worker as host
import source_owners as owners


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    assert not (HERE / 'result.json').exists(), 'Exclusive independent output'
    plan = read(PREP / 'plan.json')
    assert sha(PREP / 'plan.json') == PLAN
    assert read(PRIOR / 'result.json')['source_reference_accepted'] is True
    assert sha(PRIOR / 'result.json') == '335b1d57d5435030db4e92d0ad92a4823333d0a174b290518b32150914924083'
    files = [Path(__file__), PRIOR / 'result.json', PRIOR / 'REVIEW.md',
             PREP / 'plan.json', PREP / 'ready.json', PREP / 'dryrun_gate.json',
             PREP / 'service_launch.json']
    files += [WORK / n for n in ('source_owners.py', 'checker.py', 'replay.py',
              'test_worker.py', 'host02/status.json', 'host02/execution.json',
              'service_launch.py', 'pinned_service_exit.py')]
    before = {str(p): sha(p) for p in files}
    # Verify the changed runtime code against the actual plan, not all old732 pins.
    for name in ('source_owners.py', 'checker.py', 'replay.py', 'test_worker.py'):
        p = WORK / name
        assert plan['pins'][str(p)] == before[str(p)]
    assert read(WORK / 'host02/execution.json')['actual_wait_returncode'] == 0
    assert read(WORK / 'host02/status.json')['tests'] == 44
    assert read(PREP / 'dryrun_gate.json')['plan_sha256'] == PLAN
    results = []
    for scenario in (1, 2):
        spec = plan['specs'][str(scenario)]
        rows = host.owner_rows(spec)
        good = host.check_owners(spec, rows)
        assert good['memory_owner_count'] == 4
        results.append(dict(scenario=scenario, test='all_four_owners', accepted=True))
        for seq, site in enumerate(owners.recipe(spec)):
            bad = [r for r in rows if not (int(r['order']) == seq and
                   r['event'] in ('uop_alloc', 'uop_done'))]
            try:
                host.check_owners(spec, bad)
            except ValueError as error:
                assert str(error) == 'Missing nonempty backend lifecycle for ' + site['site']
                results.append(dict(scenario=scenario, test='delete_complete_pair_' + site['site'],
                                    rejected=True, reason=str(error)))
            else:
                raise AssertionError('Deleted complete owner accepted')
    assert {str(p): sha(p) for p in files} == before, 'Review input drift'
    result = dict(decision='NO_BLOCKER', blockers=[], plan_sha256=PLAN,
        worker_sha256=sha(WORK / 'replay.py'), checker_sha256=sha(WORK / 'checker.py'),
        source_owners_sha256=sha(WORK / 'source_owners.py'),
        reference_ready_sha256=plan['reference_ready_sha256'],
        image_sha256=plan['image_sha256'], source_reference_review=str(PRIOR / 'result.json'),
        source_reference_reused_not_reaudited=True, source_reference_accepted=True,
        worker_entry_accepted=True, tests=results, independent_delta_host_tests=len(results),
        inputs_unchanged=True, evidence_pins=before, jobs=2, case_timeout_s=1800,
        worker_timeout_s=3900, service_timeout_s=4200,
        scope='M9 two original e64 suffix singles; launch-entry review only, no DUT acceptance',
        no_new_reference=True, no_CSV_parse=True, no_live_queries=True, DUT_started_by_review=False,
        zero_physical_MMU_activity_proved=False)
    with (HERE / 'result.json').open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print('NO_BLOCKER: 2 owner positives + 8 full-pair deletion negatives; plan=' + PLAN)


if __name__ == '__main__':
    main()

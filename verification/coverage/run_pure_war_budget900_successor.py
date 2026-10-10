"""Same frozen ELF/command, one 900s successor; no retry or automatic launch."""
import argparse
import json
from pathlib import Path
from types import FunctionType

import run_pure_war_simulation as original

life, require = original.life, original.require
PRE, PRE_SEAL = original.PRE, original.PRE_SEAL
BUDGET = 900
OLD_RUN = life.OUT / 'pure-war-old-image-parent-20261006-01'
OLD_PREPARED = OLD_RUN.with_name(OLD_RUN.name + '.prepared.json')
OLD_SEAL = '451934511f1c7014169a180f53868e530f227849193c19d8c7252592c60d5493'
# Only the local budget binding changes; the frozen foreground implementation is untouched.
run = FunctionType(original.run.__code__, dict(original.run.__globals__, BUDGET=BUDGET))
command = original.command


def prepare(out):
    out = out.absolute()
    require(out.parent == life.OUT and out.resolve() == out and not out.exists() and out != OLD_RUN,
            'Fresh independent direct run directory required')
    pre = life.read_bound(PRE / 'preflight-manifest.json', PRE_SEAL); original.validate(pre)
    old = life.read_bound(OLD_PREPARED, OLD_SEAL)
    require(old['output'] == str(OLD_RUN) and old['command'] == command(OLD_RUN) and old['timeout_s'] == 600 and
            old['preflight_seal'] == PRE_SEAL and old['image_sha256'] == original.IMAGE_SEAL and
            old['elf_sha256'] == original.ELF_SEAL and old['targets'] == pre['targets'] and
            old['scalar_reference_counts'] == pre['reference_counts'], 'Frozen predecessor differs')
    state = json.loads((OLD_RUN / 'simulation-status.json').read_bytes())
    require(state['status'] == 'SIMULATION_FAILED_OR_TIMEOUT_NOT_ADMITTED' and state['timeout'] is True and
            state['returncode'] == -9 and state['process_group_cleanup'] is True and state['post_failure_pin_error'] is None and
            state['coverage_admitted'] is False and state['admission_performed'] is False, 'Not protected600 TIMEOUT')
    require(json.loads((OLD_RUN / 'manifest.json').read_bytes()) ==
            dict(old, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'), 'Original runtime identity differs')
    pins = life.merge_pins(pre['pins'], old['pins'])
    paths = [OLD_PREPARED, OLD_RUN / 'simulation-status.json', OLD_RUN / 'manifest.json', OLD_RUN / 'started.json',
             OLD_RUN / 'commit_trace.csv', OLD_RUN / 'vector_trace.csv', OLD_RUN / 'trace_hart_0.log',
             OLD_RUN / 'trace_hart_0_commit.log', OLD_RUN / 'console.log', OLD_RUN / 'run.vcs.log',
             Path(__file__).resolve(), Path(__file__).with_name('test_run_pure_war_budget900_successor.py')]
    pins = life.merge_pins(pins, {str(path): life.digest(path) for path in paths}); life.check(pins)
    manifest = dict(old, output=str(out), command=command(out), timeout_s=BUDGET, pins=pins,
        systemd_policy=dict(RuntimeMaxSec=930, TimeoutStopSec=10, KillMode='control-group'),
        authorization_source='SEPARATE_PARENT_AGENT_REVIEW_REQUIRED_BEFORE_RUN',
        predecessor=str(OLD_RUN), predecessor_prepared_seal=OLD_SEAL,
        predecessor_status='TIMEOUT_NOT_QUALIFIED_NOT_ADMITTED',
        same_ELF=True, software_or_RTL_modified=False, old_VDB_reused=False,
        raw_gain_requires_latest_formal_baseline_at_least=729)
    require(manifest['command'][0] == str(life.IMAGE) and manifest['elf_sha256'] == original.ELF_SEAL,
            'Successor changed stimulus/image')
    return out, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'run'))
    parser.add_argument('--output', required=True, type=Path); parser.add_argument('--prepared-seal')
    parser.add_argument('--parent-authorized', action='store_true'); a = parser.parse_args()
    require((a.mode != 'prepare') == bool(a.prepared_seal), 'Only verify/run require prepared seal')
    require((a.mode == 'run') == a.parent_authorized, 'Run requires separate parent authorization')
    out, manifest = prepare(a.output); record = out.with_name(out.name + '.prepared.json')
    if a.mode == 'prepare':
        life.save(record, manifest)
        print(json.dumps(dict(prepared=str(record), seal=life.digest(record), budget_s=900, pins=len(manifest['pins']), VCS_started=False)))
    else:
        require(life.read_bound(record, a.prepared_seal) == manifest, 'Prepared successor drift')
        if a.mode == 'verify': print('VERIFY_PASS sameELF/simv66/900wall/fullcommit/vector/noFSDB NO_VCS')
        else: run(out, dict(manifest, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))


if __name__ == '__main__': main()

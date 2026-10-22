"""Parameter-bound900 successor; reuse every frozen pure-WAR oracle algorithm."""
import argparse
import json
from pathlib import Path
from types import FunctionType

import qualify_pure_war_parent_terminal as frozen
import run_pure_war_budget900_successor as runner

life, require, p = frozen.life, frozen.require, frozen.p


def binding(pre, prepared, run):
    runner.original.validate(pre)
    require(run.parent == life.OUT and run.resolve() == run and run != runner.OLD_RUN, 'Independent900 run path required')
    require(prepared['case'] == p.NAME and prepared['preflight_seal'] == runner.PRE_SEAL and
            prepared['preflight'] == str(runner.PRE / 'preflight-manifest.json') and
            prepared['output'] == str(run) and prepared['command'] == runner.command(run) and
            prepared['timeout_s'] == 900 and prepared['baseline_tests'] == 727 and
            prepared['targets'] == pre['targets'] and prepared['scalar_reference_counts'] == pre['reference_counts'] and
            prepared['image_sha256'] == runner.original.IMAGE_SEAL and prepared['elf_sha256'] == runner.original.ELF_SEAL and
            prepared['test_supplement_seal'] == runner.original.SUPPLEMENT_SEAL and
            prepared['same_ELF'] is True and prepared['software_or_RTL_modified'] is False and
            prepared['old_VDB_reused'] is False and prepared['no_FSDB'] is True and prepared['automatic_retry'] is False and
            prepared['predecessor'] == str(runner.OLD_RUN) and prepared['predecessor_prepared_seal'] == runner.OLD_SEAL and
            prepared['predecessor_status'] == 'TIMEOUT_NOT_QUALIFIED_NOT_ADMITTED' and
            prepared['coverage_admitted'] is False and prepared['admission_performed'] is False, 'Successor scope/ELF/command differs')


def terminal(state, actual, started, prepared):
    require(state.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and type(state.get('returncode')) is int and
            state['returncode'] == 0 and state.get('case') == p.NAME and state.get('timeout') is False and
            state.get('coverage_admitted') is False and state.get('admission_performed') is False and
            state.get('terminal_oracle_verified') is False, 'Failed/nonterminal900 simulation')
    require(actual == dict(prepared, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'),
            'Actual successor command/ELF/authorization differs')
    require(type(started.get('pid')) is int and started['pid'] > 0 and
            started['pid'] == started['process_group'] == state['pid'] and started['budget_s'] == 900 and
            started['input_elf'] == str(runner.PRE / 'input.elf') and started['elf_sha256'] == runner.original.ELF_SEAL and
            started['image'] == str(life.IMAGE) and started['image_sha256'] == runner.original.IMAGE_SEAL and
            started['command'] == prepared['command'] and started['foreground_lifetime'] is True and
            started['coverage_admitted'] is False, 'Successor startup identity/budget differs')


def prepare(out, run, prepared_seal):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct qualification plan directory')
    record = run.with_name(run.name + '.prepared.json')
    pre = life.read_bound(runner.PRE / 'preflight-manifest.json', runner.PRE_SEAL)
    prepared = life.read_bound(record, prepared_seal); binding(pre, prepared, run)
    pins = life.merge_pins(pre['pins'], prepared['pins'])
    paths = [Path(__file__).resolve(), Path(__file__).with_name('test_qualify_pure_war_budget900_terminal.py'),
             Path(frozen.__file__).resolve(), Path(frozen.__file__).with_name('test_qualify_pure_war_parent_terminal.py'),
             Path(frozen.common.__file__).resolve(), *sorted((life.ROOT / 'verification/ara_verify').glob('*.py'))]
    sourcepath = life.OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    sourcepins = json.loads(sourcepath.read_bytes())
    for name in ('hardware/tb/ara_commit_monitor.sv', 'hardware/include/ara_pkg.sv'):
        path = life.ROOT / name; pins = life.merge_pins(pins, {str(path): sourcepins[str(path)]})
    pins = life.merge_pins(pins, {str(path): life.digest(path) for path in paths})
    pins = life.merge_pins(pins, {str(runner.PRE / 'preflight-manifest.json'): runner.PRE_SEAL,
                                str(record): prepared_seal, str(sourcepath): life.digest(sourcepath)})
    life.check(pins)
    out.mkdir(); life.save(out / 'plan.json', dict(status=frozen.PLAN_STATUS, run=str(run), pins=pins,
        preflight_seal=runner.PRE_SEAL, parent_prepared_seal=prepared_seal, successor_budget_s=900,
        provenance='SUCCESSOR_PLAN_FOR_PARENT_REVIEW_NOT_EXECUTION_PROOF',
        preflight_baseline=727, raw_gain_requires_latest_formal_baseline_at_least=729,
        source_lifetime_probes_observed=False, coverage_admitted=False, actualDUT_read=False, simulations_started=False,
        frozen_oracle=str(Path(frozen.__file__).resolve()), predecessor_not_qualified=True))
    print(json.dumps(dict(plan=str(out / 'plan.json'), seal=life.digest(out / 'plan.json'), pins=len(pins))))


def verify_plan(plan):
    require(plan['status'] == frozen.PLAN_STATUS and plan['successor_budget_s'] == 900 and
            plan['preflight_seal'] == runner.PRE_SEAL and plan['predecessor_not_qualified'] is True, 'Successor plan contract differs')
    run = Path(plan['run']); record = run.with_name(run.name + '.prepared.json')
    require(plan['pins'][str(record)] == plan['parent_prepared_seal'], 'Prepared seal not pinned')
    life.check(plan['pins'])
    prepared = life.read_bound(record, plan['parent_prepared_seal'])
    binding(life.read_bound(runner.PRE / 'preflight-manifest.json', runner.PRE_SEAL), prepared, run)
    return run, record


def collect(plan_path, seal, out):
    plan = life.read_bound(plan_path, seal); run, record = verify_plan(plan)
    # Constants are local to the new function; frozen source and module globals stay unchanged.
    context = dict(frozen.collect.__globals__, RUN=run, PREPARED=record,
                   RUN_SEAL=plan['parent_prepared_seal'], runner=runner, terminal=terminal)
    FunctionType(frozen.collect.__code__, context)(plan_path, seal, out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'collect'))
    parser.add_argument('--run', type=Path); parser.add_argument('--prepared-seal'); parser.add_argument('--output', type=Path)
    parser.add_argument('--plan', type=Path); parser.add_argument('--seal'); a = parser.parse_args()
    if a.mode == 'prepare':
        require(a.run is not None and a.prepared_seal and a.output is not None and a.plan is None and a.seal is None,
                'Prepare needs explicit successor run/prepared seal/fresh output')
        prepare(a.output.absolute(), a.run.absolute(), a.prepared_seal)
    else:
        require(a.plan is not None and a.seal and a.run is None and a.prepared_seal is None, 'Fixed plan binding required')
        if a.mode == 'verify':
            verify_plan(life.read_bound(a.plan, a.seal)); print('VERIFY_PASS900 SAME_FULL_ORACLES NO_ACTUAL_DUT_READ NO_VCS')
        else:
            require(a.output is not None, 'Fresh actual qualification output required'); collect(a.plan.absolute(), a.seal, a.output.absolute())


if __name__ == '__main__': main()

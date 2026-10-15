#!/usr/bin/env python3
"""Explicit pinned extended8 successor gate; preserve the reviewed 38-case runner."""
import argparse
import copy
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import replay_memory_regression as base

ORIGINAL_GATE = base.gate
EXPECTED = base.REVIEW / 'masked_translation/sv39_extended/candidate02_extended8_02'


def validate_config(config, data):
    root = Path(config['extended8_dir'])
    base.require(root == EXPECTED and root == root.resolve(), 'Explicit extended8_02 path required')
    base.require(data['gates']['extended8'] == str(root / 'complete.json'), 'Gate path mismatch')
    base.require(config['image_sha256'] == data['image_sha256'], 'Gate image mismatch')
    base.require((config['inner_timeout_s'], config['outer_timeout_s']) == (1800, 2100), 'Budget gate mismatch')
    base.require(config['expected_status'] == 'CANDIDATE02_EXTENDED8_PASS', 'Terminal gate weakened')
    return root


def configured_gate(data):
    config_path = Path(data['gate_config'])
    base.require(base.sha(config_path) == data['pins'][str(config_path)], 'Gate config drift')
    config = base.read(config_path)
    root = validate_config(config, data)
    contract_path = root / 'budget_preflight.json'
    base.require(base.sha(contract_path) == config['budget_preflight_sha256'], 'Budget preflight drift')
    base.require(base.sha(root / 'preflight.json') == config['preflight_sha256'], 'Extended8 preflight drift')
    contract = base.read(contract_path)
    base.require(contract['image_sha256'] == config['image_sha256'] and
                 contract['elf_sha256'] == config['elf_sha256'], 'Budget input identity mismatch')
    base.require(contract['output'] == str(root) and contract['inner_timeout_s'] == 1800 and
                 contract['outer_timeout_s'] == 2100 and contract['jobs'] == 1, 'Budget contract mismatch')
    # The old reviewed gate is unchanged; its evidence directory is explicitly
    # selected only after the new, parent-approved configuration is verified.
    base.EXTENDED8 = root
    pins = ORIGINAL_GATE(data)
    complete = base.read(root / 'complete.json')
    base.require(complete.get('post_hashes') == 'ALL_PRE_RUN_PINS_AND_IMAGE_UNCHANGED',
                 'Extended8 post-run pin verification not PASS')
    base.require(complete.get('elf_sha256') == config['elf_sha256'], 'Extended8 terminal ELF mismatch')
    worker = base.read(root / 'worker.json')
    base.require(worker['budget_preflight_sha256'] == config['budget_preflight_sha256'] and
                 worker['command'] == contract['command'], 'Extended8 worker contract mismatch')
    base.verify_pins(contract['pins'])
    pins.update(contract['pins'])
    pins.update({str(p): base.sha(p) for p in (config_path, contract_path, root / 'worker.json')})
    return pins


def plan(out, previous_path, extended8):
    base.require(extended8.resolve() == EXPECTED, 'Only explicitly selected extended8_02 is authorized')
    previous = base.read(previous_path)
    base.verify_pins(previous['pins'])
    base.require(previous['status'] == 'PREPARED_NOT_LAUNCHED' and len(previous['cases']) == 38 and
                 previous['jobs'] == 4 and previous['stop_first_fail'], 'Unexpected reviewed plan scope')
    contract_path = extended8 / 'budget_preflight.json'
    contract = base.read(contract_path)
    preflight = base.read(extended8 / 'preflight.json')
    base.require(contract['status'] == 'BUDGET02_PREFLIGHT_PASS_NOT_LAUNCHED', 'Missing02 static contract')
    base.require(contract['image_sha256'] == previous['image_sha256'] == preflight['image_sha256'], 'Different image')
    base.require(contract['elf_sha256'] == preflight['elf_sha256'], 'Different gate ELF')
    base.verify_pins(preflight['pins'])
    base.verify_pins(contract['pins'])
    out.mkdir(parents=True, exist_ok=False)
    config_path = out / 'gate_config.json'
    config = dict(extended8_dir=str(extended8), expected_status='CANDIDATE02_EXTENDED8_PASS',
        preflight_sha256=base.sha(extended8 / 'preflight.json'),
        budget_preflight_sha256=base.sha(contract_path), elf_sha256=contract['elf_sha256'],
        image_sha256=contract['image_sha256'], inner_timeout_s=1800, outer_timeout_s=2100,
        terminal_files_not_read_during_preparation=True, no_polling=True)
    base.save(config_path, config)
    data = copy.deepcopy(previous)
    old_gate_preflight = str(Path(data['gates']['extended8']).parent / 'preflight.json')
    data['pins'].pop(old_gate_preflight)
    data['gates']['extended8'] = str(extended8 / 'complete.json')
    data['gate_config'] = str(config_path)
    data['predecessor_plan'] = str(previous_path)
    data['predecessor_plan_sha256'] = base.sha(previous_path)
    data['delta'] = 'Only gate successor selection and static gate pins; unchanged38 ELF scope, oracle, budgets,4jobs'
    for path in (Path(__file__).resolve(), previous_path, config_path,
                 extended8 / 'preflight.json', contract_path):
        data['pins'][str(path)] = base.sha(path)
    validate_config(config, data)
    base.require(data['cases'] == previous['cases'], 'Case/oracle/budget drift')
    base.save(out / 'plan.json', data)
    results = base.execute(data, out / 'dryrun', True)
    base.require(len(results) == 38 and all(r.status == 'DRY_RUN' for r in results), 'Unexpected execution')
    base.verify_pins(data['pins'])
    base.save(out / 'preflight.json', dict(status='PASS_PREPARE_ONLY', VCS_started=False,
        count=38, jobs=4, parent_approval=False, same_case_records_as_predecessor=True,
        plan_sha256=base.sha(out / 'plan.json'),
        dryrun_summary_sha256=base.sha(out / 'dryrun/summary.json'),
        terminal_gate_deferred_to_explicit_launch=True))
    print('READY_NOT_LAUNCHED plan SHA256 ' + base.sha(out / 'plan.json'))


def self_test():
    import unittest
    from unittest.mock import patch
    base.self_test()

    class Tests(unittest.TestCase):
        def test_explicit02(self):
            config = dict(extended8_dir=str(EXPECTED), image_sha256='same',
                inner_timeout_s=1800, outer_timeout_s=2100, expected_status='CANDIDATE02_EXTENDED8_PASS')
            data = dict(gates=dict(extended8=str(EXPECTED / 'complete.json')), image_sha256='same')
            self.assertEqual(validate_config(config, data), EXPECTED)
            config['extended8_dir'] = str(EXPECTED.with_name('candidate02_extended8_01'))
            with self.assertRaisesRegex(ValueError, 'extended8_02'):
                validate_config(config, data)

        def test_no_launch_without_review(self):
            with patch.object(base, 'execute') as execute:
                with self.assertRaisesRegex(ValueError, 'parent review'):
                    base.work(Path('/unused'), False, None)
                execute.assert_not_called()

        def test_gate_fail_and_cancel_remain_rejected(self):
            for status in ('RUNNING', 'CANCELLED', 'CANDIDATE02_EXTENDED8_NOT_PASS'):
                with self.assertRaisesRegex(ValueError, 'terminal PASS'):
                    base.validate_extended8(dict(status=status), {}, {}, [], {}, {}, '')

    base.require(unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful(),
                 'Successor host tests failed')


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=['plan', 'work', 'self-test'])
    cli.add_argument('--out', type=Path)
    cli.add_argument('--previous-plan', type=Path)
    cli.add_argument('--extended8-dir', type=Path)
    cli.add_argument('--authorize-run', action='store_true')
    cli.add_argument('--approved-plan-sha256')
    args = cli.parse_args()
    if args.mode == 'self-test':
        self_test()
        return 0
    base.require(args.out is not None, '--out required')
    environment = base.shared.environment()
    base.os.environ.clear()
    base.os.environ.update(environment)
    if args.mode == 'plan':
        base.require(args.previous_plan is not None and args.extended8_dir is not None,
                     'Explicit --previous-plan and --extended8-dir required')
        plan(base.owned(args.out), args.previous_plan.resolve(), args.extended8_dir.resolve())
        return 0
    base.gate = configured_gate
    return base.work(base.owned(args.out), args.authorize_run, args.approved_plan_sha256)


if __name__ == '__main__':
    raise SystemExit(main())

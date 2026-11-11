#!/usr/bin/env python3
"""Fresh same-BUILD07 three-guest successor; only exact INFO expectations change."""
import importlib.util
from pathlib import Path
import signal
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('execution_v4_check', HERE / 'check_v4.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
v3 = check.c.load(HERE / 'run_v3.py',
    '2ba39edd9dcf9b62b9a136aa87929b654d4721df814bd1e4b20f0a4e43af5118', 'info_census_sealed_worker_v3')
b = v3.b
OWN = (*v3.OWN, 'run_v4.py', 'check_v4.py', 'test_run_v4.py')
old_recipes, old_selection, old_service = v3.recipes, v3.selection, v3.service_argv
strict_gate = v3.checked_gate
b._source_info_total = check.info_total
v3.old_gate = check.rewrite_one_expression(b, 'checked_gate', "w['info_records'] == 4 * calls",
                                          "w['info_records'] == _source_info_total(kind)")


def recipes(out, qemu, reports, python):
    rows = old_recipes(out, qemu, reports, python)
    for row in rows:
        row['checker'][2] = str(out / 'inputs/check_v4.py')
    return rows


def selection(out, qemu, reports, g, python=None):
    result = old_selection(out, qemu, reports, g, python)
    result.update(schema='stage5-qemu-unchanged-execution-v4',
                  capability_query_contract='one-main-plus-eligible-paired-query-per-group')
    return result


def service_argv(out, selected, review):
    return [str(out / 'inputs/run_v4.py') if x == str(out / 'inputs/run_v3.py') else x
            for x in old_service(out, selected, review)]


v3.OWN = b.OWN = OWN
v3.check = check
v3.recipes = b.recipes = recipes
v3.selection = b.selection = selection
v3.service_argv = b.service_argv = service_argv
b.checked_gate = strict_gate
b.prepare = check.rewrite_one_expression(v3, 'prepare', repr('inputs/test_run_v3.py'),
                                         repr('inputs/test_run_v4.py'))
checked_result, checked_execution = b.checked_result, b.checked_execution


if __name__ == '__main__':
    def interrupted(sig, frame):
        raise InterruptedError('Signal ' + str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    raise SystemExit(b.main())

#!/usr/bin/env python3
"""Once-only independent acceptance of two closed CSVs; never run simulation."""
import csv
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import checker as n
from host import save

RUN = n.HERE.parent/'unmasked_strided_alignment_soc_m9_worker_successor01/prepared01'
PLAN_SHA = '80626a24d10affb79c5242eae19b9e849c0841fcceb7441c1bbbf6ba4aaf5e10'


def main():
    out = n.HERE/'closed_audit01'
    out.mkdir(exist_ok=False)
    save(out/'invocation.json', dict(pid=os.getpid(), command=sys.argv, started=time.time(),
                                    once_only=True, no_DUT=True, no_reference_execution=True))
    result = dict(status='NOT_ACCEPTED', results=[], original_batch_preserved=True)
    try:
        n.need(n.sha(RUN/'plan.json') == PLAN_SHA, 'Old actual plan')
        plan = json.loads((RUN/'plan.json').read_text())
        pins = dict(plan['pins'])
        host = json.loads((n.HERE/'host01/result.json').read_text())
        n.need(host['status'] == 'HOST_ENDPOINT_PASS_NOT_DUT'
               and host['checker_sha256'] == n.sha(n.HERE/'checker.py')
               and host['host_sha256'] == n.sha(n.HERE/'host.py'), 'Actual endpoint Host binding')
        for f in (RUN/'plan.json', RUN/'complete.json', RUN/'firstfailure.json', n.HERE/'checker.py',
                  n.HERE/'host.py', n.HERE/'host01/result.json', Path(__file__)):
            pins[str(f)] = n.sha(f)
        original = json.loads((RUN/'complete.json').read_text())
        n.need(original['status'] == 'NOT_ACCEPTED_LATE_ABORT' and original['aborted'] is True
               and original['firstfailure']['case'] == 'strided_alignment_store_m', 'Preserve exact old failure')
        result['original_metadata'] = original
        loader = importlib.util.spec_from_file_location('sealed_worker_gates', RUN.parent/'worker.py')
        w = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(w)
        ledger, _, _ = w.old.image_context()
        cases = [c for c in plan['cases'] if c['member'] in ('load_m', 'store_m')]
        for case in cases:
            root = RUN/'alignment4/tests'/case['id']
            for f in root.rglob('*'):
                if f.is_file():
                    pins[str(f)] = n.sha(f)
        w.m.base.verify_pins(pins)
        for case in cases:
            root = RUN/'alignment4/tests'/case['id']
            receipt = w.read(root/'child_exit.json')
            w.old.receipt_ok(receipt, 900)
            n.need(n.sha(root/'input.elf') == case['sha256'], 'Actual private ELF')
            inputs = w.read(root/'inputs.json')
            n.need(inputs['binary'] == dict(source=case['elf'], path=str(root/'input.elf'), sha256=case['sha256'])
                   and inputs['simv'] == dict(path=ledger['simv'], image_sha256=ledger['files']), 'Actual input/image provenance')
            command = [ledger['simv'], '-l', 'run.vcs.log', '+ntb_random_seed=1',
                       '+PRELOAD='+str(root/'input.elf'), '+TESTCASE='+case['id'], '+NO_FSDB',
                       '+COMMIT_TRACE='+str(root/'commit_trace.csv')]
            n.need(w.read(root/'command.json') == dict(command=command, cwd=str(root/'work'))
                   and receipt['command'] == command and receipt['cwd'] == str(root/'work'), 'Exact actual command')
            w.m.check_console(case, (root/'console.log').read_text())
            n.need(not w.m.BAD.search((root/'work/run.vcs.log').read_text()), 'Raw runlog veto')
            generic = w.read(root/'trace_summary.json')
            n.need(generic['status'] == 'VALID', 'Actual frozen generic validator result')
            checker = n.instance(case['member'])
            # One full traversal of each closed CSV; no changed rows or replayed DUT.
            with (root/'commit_trace.csv').open(newline='') as stream:
                rows = csv.DictReader(stream)
                n.need(rows.fieldnames == n.c.FIELDS, 'Actual CSV schema')
                for row in rows:
                    checker.row(row)
            actual = checker.finish()
            w.checker_result(actual, case)
            n.need((actual['rows'], actual['retired_rows'], actual['last_cycle']) ==
                   (generic['rows'], generic['retire_count'], generic['last_cycle']), 'Complete original CSV coverage')
            save(out/(case['member']+'.json'), actual)
            result['results'].append(dict(member=case['member'], result=str(out/(case['member']+'.json')),
                                          result_sha256=n.sha(out/(case['member']+'.json')),
                                          child_receipt=receipt, checks=actual['checks'], rows=actual['rows'],
                                          retired_rows=actual['retired_rows'], memory_owners=actual['memory_owner_count'],
                                          helper_owners=actual['helper_owner_count'], generic_result=generic))
        w.m.base.verify_pins(pins)
        result.update(status='M_MODE_CLOSED_CSV_ACCEPTED_OLD_BATCH_NOT_ACCEPTED', pins_unchanged=True,
                      pins=pins, pin_count=len(pins), no_simulation_retry=True,
                      source_scope='New directed M-mode load/store alignment/retry, not Sv39 or Linux closure')
        rc = 0
    except BaseException as error:
        result['firstfailure'] = repr(error)
        rc = 1
    save(out/'result.json', result)
    save(out/'audit_exit.json', dict(returncode=rc, pid=os.getpid(), finished=time.time()))
    print(json.dumps(dict(status=result['status'], firstfailure=result.get('firstfailure'), results=len(result['results']))))
    return rc


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Focused Host checks; never invoke simulation, reference or build."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import worker as w


def main():
    passed = []

    def rejects(name, call):
        try:
            call()
        except (ValueError, KeyError, FileExistsError):
            passed.append(name)
            return
        raise AssertionError('Accepted negative '+name)

    receipt = dict(returncode=0, elapsed_s=1, timed_out=False, failure_seen=False, abort_set=False)
    w.old.receipt_ok(receipt, 900)
    for key, value in [('returncode', False), ('returncode', None), ('returncode', 1),
                       ('elapsed_s', 901), ('elapsed_s', float('nan')), ('timed_out', True),
                       ('failure_seen', True), ('abort_set', True)]:
        bad = dict(receipt, **{key: value})
        rejects('receipt_'+key+repr(value), lambda: w.old.receipt_ok(bad, 900))

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for label, rc, failed in [('good', 0, False), ('bad_numeric', 7, False), ('fatal_zero', 0, True)]:
            d = root/label
            d.mkdir()
            abort = threading.Event()
            monitor = w.monitored(lambda *a: (rc, 1, False, failed), abort)
            if label == 'good':
                monitor(['simv'], d, d/'console.log', 900, abort)
                # A later postchecker exception must not erase/replace numeric0.
                before = (d/'child_exit.json').read_bytes()
                try:
                    raise ValueError('synthetic postcheck failure')
                except ValueError:
                    abort.set()
                assert (d/'child_exit.json').read_bytes() == before
                rejects('no_numeric_overwrite', lambda: w.save(d/'child_exit.json', {'returncode': None}))
            else:
                rejects(label, lambda: monitor(['simv'], d, d/'console.log', 900, abort))
                assert abort.is_set()
            assert type(w.read(d/'child_exit.json')['returncode']) is int
            assert w.read(d/'child_exit.json')['returncode'] == rc
        for label, cancel, expired in [('cancel', True, False), ('expired', False, True), ('ok', False, False)]:
            d = root/('terminal_'+label)
            d.mkdir()
            abort = w.terminal.TerminalAbort()
            if cancel:
                abort.set()
            state = dict(status=w.PASS)
            w.terminal.publish(d, state, abort, time.monotonic()+(-1 if expired else 60))
            actual = w.read(d/'complete.json')
            assert (actual['status'] == w.PASS) == (label == 'ok')
            if label != 'ok':
                assert actual['aborted'] is True
                passed.append('terminal_'+label)
            rejects('terminal_exclusive_'+label,
                    lambda: w.terminal.publish(d, {'status': 'PASS'}, w.terminal.TerminalAbort(), time.monotonic()+60))

        original = w.read(w.BASE/'vcs_m9_prepared01/plan.json')
        cases = [c for c in original['cases'] if c['kind'] == 'directed' and c['member'].endswith('sv39')]
        p = dict(cases=cases, unit=w.UNIT, jobs=2, service_s=4200, worker_s=4000, checker_s=60,
                 reserved_margin=2, no_build=True, retries=0, image=str(w.old.IMAGE),
                 image_sha256=w.old.IMAGE_SHA, checker=str(w.CHECK/'checker.py'), checker_sha256=w.CHECK_SHA)
        w.contract(p)
        for key, value in [('jobs', 3), ('service_s', 4201), ('checker', str(w.BASE/'check_case.py')),
                           ('checker_sha256', '0'*64), ('retries', False), ('image_sha256', '0'*64),
                           ('cases', original['cases']), ('cases', cases[:1])]:
            bad = dict(p, **{key: value})
            rejects('contract_'+key+str(len(passed)), lambda: w.contract(bad))
        review = dict(decision='ADMIT_SV39_ALIGNMENT2_M9_ENDPOINT02', no_blocker=True, plan_sha256='a'*64,
                      worker_sha256=w.sha(w.__file__), checker_sha256=w.CHECK_SHA)
        file = root/'review.json'
        w.save(file, review)
        w.review_gate(p, 'a'*64, file, w.sha(file))
        rejects('review_hash', lambda: w.review_gate(p, 'a'*64, file, 'b'*64))
        for key, value in [('no_blocker', False), ('plan_sha256', 'b'*64), ('worker_sha256', 'b'*64),
                           ('checker_sha256', 'b'*64), ('decision', 'CODE_ONLY')]:
            f = root/(key+'.json')
            w.save(f, dict(review, **{key: value}))
            rejects('review_'+key, lambda: w.review_gate(p, 'a'*64, f, w.sha(f)))

        gate = dict(status='STRIDED_ALIGNMENT_DUT_CSV_PASS',
                    lifecycle_successor='source-bound-nonempty-memory-owners01', checks=697,
                    restore_readback_checks=14, memory_owner_count=9, helper_owner_count=7,
                    target_requests=2, target_owners=[{}, {}], cvx_fault_cycles=[10])
        w.checker_result(gate, cases[0])
        for key, value in [('checks', 696), ('helper_owner_count', 6), ('memory_owner_count', 8),
                           ('restore_readback_checks', 13), ('lifecycle_successor', 'old_target_only')]:
            rejects('oracle_'+key, lambda: w.checker_result(dict(gate, **{key: value}), cases[0]))
        cmd = w.checker_command(cases[0], root)
        assert cmd[2] == str(w.CHECK/'checker.py') and cmd[-2] == str(root/'commit_trace.csv')
        assert str(w.BASE/'check_case.py') not in cmd

        results = [SimpleNamespace(name=c['id'], status='PASS', returncode=0) for c in cases]
        meta = dict(status='COMPLETE', status_counts={'PASS': 2})
        abort = threading.Event()
        w.result_gate(results, meta, cases, abort)
        bad = copy.deepcopy(results)
        bad[0].returncode = False
        rejects('aggregate_bool_zero', lambda: w.result_gate(bad, meta, cases, abort))
        rejects('aggregate_partial', lambda: w.result_gate(results[:1], meta, cases, abort))
        abort.set()
        rejects('aggregate_aborted', lambda: w.result_gate(results, meta, cases, abort))
        w.m.resource_math([], 32*1024**3, root, 2, 2)
        rejects('memory_floor', lambda: w.m.resource_math([], 31*1024**3, root, 2, 2))
        rejects('capacity24', lambda: w.m.resource_math([{'argv': ['simv']}] * 21, 64*1024**3, root, 2, 2))
        pin = root/'pin'
        pin.write_text('original')
        pins = {str(pin): w.sha(pin)}
        w.m.base.verify_pins(pins)
        pin.write_text('changed')
        rejects('actual_file_pin_drift', lambda: w.m.base.verify_pins(pins))

    result = dict(status='HOST_WORKER_PASS_NOT_DUT', negative_rejections=passed, tests=len(passed),
                  worker_sha256=w.sha(w.__file__), test_sha256=w.sha(__file__),
                  checker_sha256=w.sha(w.CHECK/'checker.py'), terminal_sha256=w.sha(w.TERM),
                  simulator_launched=False, scope='Synthetic worker gates plus real filesystem receipts/terminal publication')
    w.save(w.HERE/'host01.json', result)
    print(json.dumps(dict(status=result['status'], tests=len(passed))))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Synthetic protocol negatives, not a DUT/reference campaign or data PASS."""
import copy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.dont_write_bytecode = True
import checker as c

ROOT = c.BASE.parents[3]
spec = importlib.util.spec_from_file_location('generic_trace', ROOT / 'verification/ara_verify/trace.py')
generic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generic)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def synthetic(spec):
    rows = []
    arch, retire = 0, 0

    def row(event, insn=0, **kw):
        nonlocal retire
        r = dict.fromkeys(c.old.c.FIELDS, '0')
        r.update(event=event, cycle=str(len(rows)), insn=f'{insn:x}',
                 order=str(retire if event == 'retire' else arch), port='-1', trans_id='3')
        r.update({k: str(v) for k, v in kw.items()})
        if event == 'retire':
            retire += 1
        rows.append(r)

    def transaction(op, pc=0, rd=0, value=0, backend=False, fault=False):
        nonlocal arch
        row('arch_start', op)
        if backend:
            row('uop_alloc', op, port=2)
            row('uop_done', op, port=2)
        row('cvx_req', op)
        row('cvx_resp', trap=int(fault))
        if not fault:
            row('retire', op, pc=f'{pc:x}', rd=rd, rd_wdata=f'{value:x}', trans_id=-1)
        arch += 1

    for e in c.recipe(spec):
        # The returned VL and actual vstart CSR operand are explicit, not inferred
        # from the expected number of memory owners. Test rows are synthetic.
        transaction(0x01837357, rd=6, value=e['vl'])  # vsetvli t1,t1,e64,m1
        if e['vstart']:
            transaction(0x0080d073)  # csrrwi zero,vstart,1
        transaction(e['insn'], pc=e['pc'], backend=True, fault=e['site']=='target_first')
        if e['site'] == 'target_first':
            row('retire', 0x13, pc=f'{spec["symbols"]["mt_handler"]:x}', trans_id=-1)
    # Zero-destination vector CSR reads legitimately have no backend allocation.
    transaction(0xc2002073)
    return rows


def evaluate(spec, rows):
    observer = c.MemoryOwners(spec)
    for row in rows:
        observer.row(row, {0: 0})
    return observer.finish()


def validate_generic(rows):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / 'synthetic.csv'
        with p.open('x', newline='') as f:
            w = csv.DictWriter(f, fieldnames=c.old.c.FIELDS)
            w.writeheader()
            w.writerows(rows)
        return generic.validate_trace(p)


def legacy_target_state(spec, rows):
    old = c.old.Checker(spec, False, False)
    for row in rows:
        if row['event'] != 'retire':
            old.row(row)
    return dict(requests=old.requests, pending=old.pending, arch=old.arch,
                done=old.done, target_count=old.target_count, faults=old.faults)


def main(out):
    results = []
    for member in ('load_m', 'store_m', 'load_sv39', 'store_sv39'):
        spec = json.loads((c.BASE / ('reference_'+member+'01') / 'soc.spec.json').read_text())
        rows = synthetic(spec)
        positive = evaluate(spec, rows)
        assert positive['memory_owner_count'] == 9 and positive['helper_owner_count'] == 7
        validate_generic(rows)
        negatives = []

        def reject(name, bad, match=None):
            try:
                evaluate(spec, bad)
            except ValueError as e:
                if match is not None:
                    assert match in str(e), str(e)
                negatives.append(dict(name=name, reason=str(e)))
                return
            raise AssertionError('Accepted negative '+name)

        original_legacy = legacy_target_state(spec, rows)
        for owner in positive['memory_owners']:
            if owner['site'].startswith('target_'):
                continue
            bad = [r for r in rows if not (r['event'] in ('uop_alloc', 'uop_done')
                                           and int(r['order']) == owner['seq'])]
            # Preserve every retire/CVX/arch event, both target owners and all
            # other uops. Generic balance plus the original target gate misses it.
            assert [r for r in bad if r['event'] not in ('uop_alloc', 'uop_done')] == [
                r for r in rows if r['event'] not in ('uop_alloc', 'uop_done')]
            validate_generic(bad)
            assert legacy_target_state(spec, bad) == original_legacy
            reject('delete_pair_'+owner['site'], bad, 'Missing completed memory owner: '+owner['site'])

        helper_seq = positive['memory_owners'][0]['seq']
        for event in ('uop_alloc', 'uop_done'):
            bad = [r for r in rows if not (r['event']==event and int(r['order'])==helper_seq)]
            reject('delete_'+event, bad)
        for field, value in [('order', '99'), ('trans_id', '4'), ('insn', '20e7407'), ('port', '5')]:
            bad = copy.deepcopy(rows)
            next(r for r in bad if r['event']=='uop_done')[field] = value
            reject('completion_'+field, bad)
        for event in ('uop_alloc', 'uop_done'):
            bad = copy.deepcopy(rows)
            i = next(i for i, r in enumerate(bad) if r['event']==event)
            bad.insert(i+1, dict(bad[i]))
            reject('duplicate_'+event, bad)
        bad = copy.deepcopy(rows)
        next(r for r in bad if r['event']=='retire')['rd_wdata']='0'
        reject('actual_VL_zero', bad, 'Actual nonempty')
        bad = copy.deepcopy(rows)
        next(r for r in bad if r['event']=='retire' and c.memory(int(r['insn'],16)))['pc']='80000000'
        reject('wrong_helper_PC', bad, 'Actual memory retire')
        bad = copy.deepcopy(rows)
        next(r for r in bad if r['event']=='cvx_resp')['trap']='1'
        # First response is vset: legacy target fault gate, not memory-only observer.
        try:
            legacy_target_state(spec, bad)
        except ValueError:
            negatives.append(dict(name='wrong_nonmemory_fault', reason='sealed target fault gate rejects'))
        else:
            raise AssertionError('Legacy CVX fault qualification lost')
        bad = copy.deepcopy(rows)
        next(r for r in bad if r['event']=='cvx_resp' and r['trap']=='1')['trap']='0'
        reject('missing_target_fault', bad, 'fault qualification')
        bad = copy.deepcopy(rows)
        next(r for r in bad if r['event']=='retire' and int(r['insn'],16)==0x0080d073)['insn']='805073'
        reject('retry_vstart_zero', bad, 'Actual nonempty')
        # Integration wiring only: no mocked scalar oracle is claimed as accepted.
        checker = c.Checker(spec, member.startswith('store'), member.endswith('sv39'))
        with patch.object(c.old.Checker, 'row', autospec=True) as sealed:
            checker.row(rows[0])
            assert sealed.call_args.args[1] is rows[0]
        results.append(dict(member=member, positive=positive, negatives=negatives,
                            generic_accepts_deleted_pairs=7, legacy_target_state_unchanged=True))

    result = dict(status='HOST_PROTOCOL_SUCCESSOR_PASS_NOT_DUT', results=results,
                  negatives=sum(len(x['negatives']) for x in results),
                  checker_sha256=sha(c.HERE/'checker.py'), test_sha256=sha(__file__),
                  sealed_checker_sha256=sha(c.BASE/'dut_check.py'),
                  generic_validator_sha256=sha(ROOT/'verification/ara_verify/trace.py'),
                  synthetic_only=True, reference_rerun=False, dut_run=False)
    with out.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps(dict(status=result['status'], negatives=result['negatives'], members=4)))


if __name__ == '__main__':
    main(Path(sys.argv[1]))

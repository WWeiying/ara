"""Host-only synthetic RVFI using real SoC PC/code and both complete byte oracles."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import subprocess
import time
from types import SimpleNamespace
import sys
sys.dont_write_bytecode = True
import checker as c
import csv_check as cc
import replay as r
o = c.source

def synthetic(spec):
    s = spec['symbols']; code = {int(k): v for k, v in spec['code'].items()}
    cfg = o.spec_values(spec['sew']); rows = []; labels = {}; checks = 0
    excluded = set(spec['helper'] + spec['unused'] + spec['capacity'] + list(s.values()))
    def emit(pc, rd=0, value=0, addr=0, rm=0, wm=0, data=0, trap=0, event='retire', tid=-1):
        rows.append(dict(zip(cc.FIELDS, map(str, [len(rows) + 80, event, 0, 0, tid,
            f'{pc:x}', f'{code[pc]:x}', rd, f'{value & o.MASK64:x}', f'{addr:x}', f'{rm:x}', f'{wm:x}', f'{data & o.MASK64:x}', trap]))))
    setters = {}
    def reg(n, v):
        if n == 0:
            c.require(v == 0, 'Host x0'); return
        if n not in setters:
            setters[n] = next(p for p, i in code.items() if p not in excluded and i & 127 in (0x13, 0x17, 0x1b) and (i >> 7) & 31 == n)
        emit(setters[n], rd=n, value=v)
    def mempc(kind, width):
        for p, i in code.items():
            d = cc.memory_op(i)
            if p not in excluded and d and d['kind'] == kind and d['size'] == width:
                try:
                    for n in (d['base'], d['register']):
                        if n and n not in setters:
                            setters[n] = next(q for q, z in code.items() if q not in excluded and z & 127 in (0x13, 0x17, 0x1b) and (z >> 7) & 31 == n)
                except StopIteration:
                    continue
                if d['base'] != d['register'] and d['base'] != 0 and d['register'] != 0:
                    return p, d
        raise ValueError(f'No real scalar {kind}/{width} opcode')
    ops = {(k, w): mempc(k, w) for k in ('read', 'write') for w in (1, 8)}
    def store(a, v, width=8, pc=None):
        p, d = (pc, cc.memory_op(code[pc])) if pc is not None else ops['write', width]
        reg(d['base'], a - d['offset']); reg(d['register'], v)
        emit(p, addr=a, wm=((1 << width) - 1) << (a % 8), data=v)
    def readbyteword(a, v, width):
        p, d = ops['read', width]
        reg(d['base'], a - d['offset'])
        if d.get('signed', width == 4) and v >> (width * 8 - 1):
            v |= o.MASK64 ^ ((1 << (width * 8)) - 1)
        emit(p, rd=d['register'], value=v, addr=a, rm=((1 << width) - 1) << (a % 8))
    def csr_read(k, v, handler=False, final=False):
        lo, hi = (s['fx_trap'], s['main']) if handler else (s['main'], s['fx_handler'])
        options = [p for p, i in code.items() if lo <= p < hi and i & 127 == 0x73
                   and (i >> 12) & 7 == 2 and (i >> 15) & 31 == 0 and i >> 20 == k]
        p = (max if final else min)(options)
        emit(p, rd=(code[p] >> 7) & 31, value=v)
    def csr_write(k, v):
        p = next(p for p, i in code.items() if p not in excluded and i & 127 == 0x73 and
                 (i >> 12) & 7 == 1 and (i >> 15) & 31 in (5, 10, 11, 15) and i >> 20 == k)
        reg((code[p] >> 15) & 31, v); emit(p)
    def oracle(n):
        nonlocal checks
        while checks < n:
            reg(10, 0); reg(11, 0); emit(s['check']); checks += 1
            store(s['fx_checks'], checks)
    def phase(n):
        reg(10, n); emit(s['check_state'])
        model = cc.Checker(spec)
        gold = o.expected(s, spec['sew'], n)
        for a, w in model.expected_reads(n):
            labels[f'p{n}_read_{a:x}'] = len(rows) + 1
            readbyteword(a, int.from_bytes(bytes(gold[a + j] for j in range(w)), 'little'), w)
        oracle(cfg['checkpoint_checks'][n]); store(s['fx_phase'], n)
        labels[f'checkpoint{n}'] = len(rows); emit(s['fx_checkpoint'])
    emit(s['_start'])
    for a in range(s['__bss_start'], s['__bss_end'], 8):
        reg(5, a); emit(s['_start'] + 0x46, addr=a, wm=255, data=0)
    labels['main'] = len(rows); emit(s['main'])
    saved = {k: 0 for k in o.RESTORE}; saved[0x300] = 0x6600; saved[0x305] = s['trap_entry']
    for k, value in saved.items():
        csr_read(k, value)
    for a, value in sorted(o.expected(s, spec['sew'], 0).items()):
        store(a, value, 1)
    for j, p in enumerate(spec['capacity']):
        emit(p, rd=10 if j == 1 else 0, value=1024 // spec['sew'] if j == 1 else 0)
    phase(0)
    csr_write(0x300, 0x2a00); csr_write(0x180, (8 << 60) | ((s['fx_pages'] + 8192) >> 12)); csr_write(0x341, s['fx_s_entry'])
    emit(s['fx_enter_mret'])
    for n, value in zip(range(10, 14), [cfg['base'], s['fx_out'] + cfg['width'], s['fx_mask'], 8]):
        reg(n, value)
    for i, p in enumerate(spec['helper']):
        if i == 3:
            emit(p, event='cvx_req', tid=0); emit(p, event='cvx_resp', tid=0)
        labels['helper' + str(i)] = len(rows)
        emit(p, rd=5 if i in (0, 8) else 10 if i == 4 else 6 if i == 5 else 0,
             value=8 if i in (0, 8) else cfg['returned_vl'] if i == 4 else 0)
    store(s['fx_return'], cfg['returned_vl'])
    for j, value in enumerate([8, cfg['vtype'], 0, 117, 5]):
        store(s['fx_post'] + 8 * j, value)
    store(s['fx_marker'], 1, pc=s['fx_younger_store'])
    emit(s['fx_ecall'], trap=1); emit(s['fx_handler'])
    values = [9, s['fx_ecall'], 0, 0x800, (8 << 60) | ((s['fx_pages'] + 8192) >> 12), 8, cfg['vtype'], 0, 117, 5]
    for k, j in o.FIELDS.items():
        csr_read(k, values[j], handler=True)
    for j, value in enumerate(values):
        store(s['fx_records'] + 8 * j, value)
    store(s['fx_count'], 1)
    csr_write(0x300, 0x1800); csr_write(0x341, s['fx_m_resume']); emit(s['fx_trap_mret'])
    phase(1)
    for k, value in saved.items():
        csr_read(k, value, final=True)
    oracle(cfg['checks']); store(s['fx_completed'], o.DONE)
    store(0xd0000000, 0, pc=spec['exit_store']); emit(spec['park'])
    return rows, labels

def exercise(rows, spec, snapshots=None, initial=None, offset=0):
    q = copy.deepcopy(initial) if initial is not None else cc.Checker(spec)
    order = q.retired
    try:
        for n, r0 in enumerate(rows):
            if snapshots is not None and n in snapshots:
                snapshots[n] = copy.deepcopy(q)
            row = dict(r0, order=str(order if r0['event'] == 'retire' else -1), cycle=str(80 + offset + n))
            if r0['event'] == 'retire':
                order += 1
            q.row(row)
        return q.finish()
    except (ValueError, KeyError, TypeError, IndexError) as error:
        return dict(status='REJECTED', error=str(error), row=q.rows, checks=q.checks, actions=q.actions)

def main(out):
    c.require(not out.exists(), 'Fresh Host output only'); out.mkdir()
    results = []
    def rejected(name, fn):
        try:
            fn()
        except (ValueError, KeyError, TypeError):
            results.append(dict(name=name, rejected=True)); return
        raise AssertionError('Accepted ' + name)
    for sew in c.SHAPES:
        spec = c.specification(sew); rows, labels = synthetic(spec)
        addresses = [spec['symbols']['fx_out'] + (sew // 8) * i for i in (0, 1, 9, 129)]
        addresses.append(spec['symbols']['fx_pages'] + 20472)
        selected_labels = ['helper3', 'helper4', 'helper5', 'helper8', 'checkpoint1']
        selected_labels += [f'p1_read_{a:x}' for a in addresses]
        snapshots = {labels[name]: None for name in selected_labels}
        # Fork negative suffixes from the same already-checked Host prefix.
        positive = exercise(rows, spec, snapshots=snapshots)
        c.common.save(out / f'positive_e{sew}.json', positive)
        c.require(positive['status'] == 'PASS_FOF_ORIGINAL_SINGLE', str(positive))
        results.append(dict(name=f'e{sew}_full_synthetic_oracle', positive=True, rows=len(rows)))
        s = spec['symbols']; w = sew // 8
        tests = [('active_or_typed_oldvd', f'p1_read_{s["fx_out"] + w:x}', 'rd_wdata', '0'),
                 ('guard0', f'p1_read_{s["fx_out"]:x}', 'rd_wdata', '0'),
                 ('guard9', f'p1_read_{s["fx_out"] + 9*w:x}', 'rd_wdata', '0'),
                 ('physical_tail129', f'p1_read_{s["fx_out"] + 129*w:x}', 'rd_wdata', '0'),
                 ('page_neighbor', f'p1_read_{s["fx_pages"] + 20472:x}', 'rd_wdata', '1'),
                 ('returned_VL', 'helper4', 'rd_wdata', '8' if sew == 8 else '4'),
                 ('returned_vstart', 'helper5', 'rd_wdata', '1'),
                 ('store_restore_VL', 'helper8', 'rd_wdata', '4'),
                 ('wrong_target_encoding', 'helper3', 'insn', '13')]
        for name, label, field, value in tests:
            bad = list(rows); at = labels[label]; bad[at] = dict(bad[at], **{field: value})
            result = exercise(bad[at:], spec, initial=snapshots[at], offset=at)
            c.require(result['status'] == 'REJECTED', f'{sew}:{name}')
            results.append(dict(name=f'e{sew}_{name}', rejected=True, diagnostic=result))
        for name, label in [('missing_full_read', f'p1_read_{s["fx_out"] + 129*w:x}'), ('missing_checkpoint', 'checkpoint1')]:
            at = labels[label]; bad = list(rows); del bad[at]
            result = exercise(bad[at:], spec, initial=snapshots[at], offset=at)
            c.require(result['status'] == 'REJECTED', name)
            results.append(dict(name=f'e{sew}_{name}', rejected=True, diagnostic=result))
        for name, pc in [('unused_internal', spec['unused'][6]), ('duplicate_op_internal', spec['helper'][6])]:
            bad = list(rows); bad.insert(labels['checkpoint1'], dict(rows[labels['helper6']], pc=f'{pc:x}', insn=f'{int(spec["code"][str(pc)]):x}'))
            at = labels['checkpoint1']
            result = exercise(bad[at:], spec, initial=snapshots[at], offset=at)
            c.require(result['status'] == 'REJECTED', name)
            results.append(dict(name=f'e{sew}_{name}', rejected=True, diagnostic=result))
        initial = o.expected(s, sew, 0)
        rejected(f'e{sew}_missing_initialization', lambda: o.compare({}, s, sew, 0))
        final = o.expected(s, sew, 1); final.update({s['fx_records'] + 24 + j: b for j, b in enumerate((0x800).to_bytes(8, 'little'))})
        if sew == 8:
            for i in range(5, 9): final[s['fx_out'] + i] = 0xa5
            o.compare(final, s, sew, 1)
            results.append(dict(name='e8_undefined5to8_arbitrary_accepted', positive=True))
        else:
            bad = dict(final)
            for j in range(8): bad[s['fx_out'] + 8 + j] = 0x5b
            rejected('e64_repeated_byte_oldvd_rejected', lambda: o.compare(bad, s, sew, 1))
    text = 'FOF_ORIGINAL_SINGLE_PASS\nCore Test *** SUCCESS *** (tohost = 0)\n$finish\n'
    c.console_gate(text)
    rejected('missing_oracle', lambda: c.console_gate(text.replace('FOF_ORIGINAL_SINGLE_PASS\n', '')))
    rejected('partial_original_failure_veto', lambda: c.console_gate(text + 'FOF_ORIGINAL_SINGLE_FAIL'))
    c.require(c.VETO.search('BOARD_REPLAY_MISMATCH'), 'Immediate raw mismatch veto')
    for case in c.scope():
        c.require(c.runtime_case(case)['original_name'] == case['id'], 'Distinct runtime mapping')
        rejected('wrong_historical_name', lambda: c.runtime_case(dict(case, original_name=case['id'])))
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        root = Path(tmp); command = root / 'command.json'
        c.common.save(command, dict(command=['simv', '+TESTCASE=test'], cwd=str(root)))
        monitored = r.durable_monitor(lambda *args: (0, 1.25, False, False))
        monitored(['simv'], root, root / 'console.log', 1800, threading.Event())
        c.require(c.read(root / 'monitor_outcome.unvalidated.json')['returncode'] == 0, 'Numeric monitor durable')
        result = SimpleNamespace(name='test', status='PASS', returncode=0, elapsed_s=1.25, reason='', artifact_dir=root)
        class Parent:
            def __init__(self): pass
            def _run_test(self, *args): return result
        abort = threading.Event()
        def throwing(_): raise ValueError('Host deliberate artifact exception')
        output = r.checked_runner(Parent, abort, throwing, lambda _: None)()._run_test(SimpleNamespace(name='test'), None)
        c.require(abort.is_set() and output.status == 'FAIL' and c.read(root / 'child_outcome.unvalidated.json')['returncode'] == 0,
                  'Sticky first failure retains precheck child outcome')
        results.append(dict(name='checker_throw_durable_monitor_child0_sticky_abort', positive=True))
        fake = root / 'plan.json'; c.common.save(fake, {'value': 1}); digest = c.sha(fake)
        c.common.save(fake, {'value': 2})
        rejected('late_disk_plan_drift', lambda: r.terminal_plan_gate(root, digest, r.IMAGE))
    # Reject drift before any runtime resource query or expensive pin walk.
    candidate = dict(status='PREPARED_NOT_RUN', image=str(r.IMAGE), image_sha256=c.IMAGE_SHA,
        cases=c.scope(), jobs=2, timeout_s=1800, worker_timeout_s=3000, service_timeout_s=3600,
        unit=r.UNIT, no_build=True, no_retry=True, no_fsdb=True, stop_first_fail=True)
    for name, key, value in [('jobs_drift', 'jobs', 3), ('case_budget_drift', 'timeout_s', 1801),
                             ('service_budget_drift', 'service_timeout_s', 3601), ('image_drift', 'image_sha256', '0'*64)]:
        bad = dict(candidate, **{key: value})
        rejected(name, lambda: r.validate(bad, r.IMAGE))
    bad = copy.deepcopy(candidate); bad['cases'][0]['sha256'] = '0'*64
    rejected('ELF_identity_drift', lambda: r.validate(bad, r.IMAGE))
    _, _, _ = c.common.image_context(r.IMAGE)
    import ara_verify.runner as engine
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        root = Path(tmp); log = root / 'console.log'
        command = [sys.executable, '-B', '-c', "import time; print('FOF_ORIGINAL_SINGLE_FAIL',end='',flush=True); time.sleep(8)"]
        old = engine.FAIL_RE; engine.FAIL_RE = c.VETO
        try:
            started = time.monotonic()
            rc, elapsed, timeout, failure = engine._run_monitored(command, root, log, 5, threading.Event())
        finally:
            engine.FAIL_RE = old
        c.require(type(rc) is int and failure and not timeout and time.monotonic()-started < 5,
                  'Actual partial-line monitor did not stop before timeout')
        results.append(dict(name='actual_partial_FAIL_immediate_monitor', positive=True, actual_rc=rc, elapsed_s=elapsed))
    pins = {str(p): c.sha(p) for p in (Path(__file__), Path(c.__file__), Path(cc.__file__), Path(r.__file__), c.REF / 'READY.json')}
    c.common.save(out / 'status.json', dict(status='PASS_HOST_ONLY_NOT_DUT', failures=0, tests=len(results),
        cases=results, pins=pins, synthetic_RVFI_not_measured_DUT=True))
    print('PASS_HOST_ONLY_NOT_DUT', len(results), 'checks')

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(); p.add_argument('--out', type=Path, required=True)
    main(p.parse_args().out)

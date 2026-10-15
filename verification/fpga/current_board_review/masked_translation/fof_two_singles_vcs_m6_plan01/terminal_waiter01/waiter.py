#!/usr/bin/env python3
"""Conditional terminal audit: no active CSV reads, no DUT control, one pass/case."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import time
from types import SimpleNamespace
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent
RUN = BASE / 'prepared01'
PLAN_SHA = 'da842f3be54dc8d15eaf4b6551766152c375e97321624c525f9350dbc16affa1'
sys.path.insert(0, str(BASE))
import checker as c
import csv_check as scalar_decoder
import replay as worker
old = c.load('fof_frozen_terminal_primitives', BASE.parent / 'negative_stride_load_vcs_m6_plan01/terminal_waiter01/waiter.py')
save, verify, wait_terminal, CombinedPath, validate_trace = old.save, old.verify, old.wait_terminal, old.CombinedPath, old.validate_trace
read, sha, require = c.read, c.sha, c.require
MASK64 = (1 << 64) - 1

def terminal_gate(complete, metadata, summary, monitors, children, cases):
    require(complete['status'] == worker.PASS and complete['aborted'] is False and
            complete['pins_unchanged'] is True and complete['retries'] == 0 and
            complete['plan_sha256'] == PLAN_SHA, 'Whole2 not clean terminal PASS')
    names = [case['id'] for case in cases]
    require(metadata['status'] == 'COMPLETE' and metadata['status_counts'] == {'PASS': 2} and
            metadata['tests'] == names and metadata['jobs'] == 2 and metadata['timeout_s'] == 1800,
            'Runner not exact two-case COMPLETE')
    require(summary == complete['results'] and [r['name'] for r in summary] == names and
            set(monitors) == set(children) == set(names), 'Exact result/durable outcome membership')
    for result in summary:
        name = result['name']; child, monitor = children[name], monitors[name]
        for row in (result, child, monitor):
            require(type(row['returncode']) is int and row['returncode'] == 0 and
                    0 < row['elapsed_s'] <= 1800, 'Persisted actual numeric0 and per-case budget required')
        require(child['name'] == name and result['status'] == child['status'] == 'PASS' and
                not result['reason'] and result['elapsed_s'] == child['elapsed_s'] == monitor['elapsed_s'],
                'Child/monitor/result mismatch')
        require(monitor['timed_out'] is False and monitor['failure_seen'] is False and
                monitor['abort_set'] is False and monitor['architectural_acceptance'] is False and
                child['architectural_acceptance'] is False, 'Monitor failure/abort/timeout')
    return summary

class Numerical:
    """Independent defined scalar-read values; full source maps stay bound to worker."""
    def __init__(self, spec):
        self.spec, self.s, self.sew = spec, spec['symbols'], spec['sew']
        self.code = {int(k): v for k, v in spec['code'].items()}
        self.width = self.sew // 8
        self.regs = {i: 0 for i in range(32)}
        self.phase = None; self.position = 0; self.points = []; self.helper = []; self.capacity = []
        self.checks = 0; self.handler = []; self.saved = {}; self.restored = {}
        self.completed = False; self.ctrl = []; self.park = 0
        self.expected = {phase: self.values(phase) for phase in (0, 1)}

    def values(self, phase):
        s, w = self.s, self.width
        raw = bytearray(20480)
        for i in range(4):
            a = 4096 - 4*w + i*w
            raw[a:a+w] = (37*i + 11).to_bytes(w, 'little')
        p = s['fx_pages']
        for i, value in {1025: ((p+12288) >> 12 << 10) | 1, 1026: 0x200000cf,
                         1536: ((p+16384) >> 12 << 10) | 1, 2048: (p >> 12 << 10) | 0xc7}.items():
            raw[8*i:8*i+8] = value.to_bytes(8, 'little')
        rows = [(p+8*i, 8, int.from_bytes(raw[8*i:8*i+8], 'little')) for i in range(2560)]
        rows += [(s[key]+8*i, 8, 0xe370697ce370697c) for i in range(8) for key in ('fx_guard_lo', 'fx_guard_hi')]
        for i in range(130):
            if self.sew == 8 and phase == 1 and 5 <= i <= 8:
                continue
            value = 37*(i-1)+11 if self.sew == 8 and phase == 1 and 1 <= i <= 4 else 0x5b
            rows.append((s['fx_out']+w*i, w, value))
        return rows + [(s['fx_mask']+i, 1, 255 if self.sew == 8 and i == 0 else 0) for i in range(16)]

    def row(self, row):
        if row['event'] != 'retire': return
        pc, insn, value = (int(row[k], 16) for k in ('pc', 'insn', 'rd_wdata'))
        rd, trap = int(row['rd']), int(row['trap'])
        require(self.code.get(pc) == insn and pc not in self.spec['unused'] and
                pc not in (self.s['trap_entry'], self.s['replay_mismatch']), 'Actual source PC/code/unused helper')
        require(not trap or pc == self.s['fx_ecall'], 'Unexpected architectural target trap')
        if self.ctrl:
            require(pc == self.spec['park'] and rd == 0 and not trap and
                    int(row['mem_rmask'], 16) == int(row['mem_wmask'], 16) == 0, 'Only original post-CTRL park')
            self.park += 1; return
        if pc == self.s['check']:
            require(self.regs[10] == self.regs[11], 'Actual scalar equality failure')
            self.checks += 1
        if pc == self.s['check_state']:
            require(self.phase is None and self.regs[10] == len(self.points) < 2, 'Original two read phases')
            self.phase, self.position = self.regs[10], 0
        if pc == self.s['fx_checkpoint']:
            n = self.phase
            require(n is not None and n == len(self.points) and self.position == len(self.expected[n]) and
                    self.checks == (2726 if n == 0 else 5463 if self.sew == 8 else 5467), 'Full phase oracle/count')
            self.points.append(dict(phase=n, cycle=int(row['cycle']), reads=self.position, checks=self.checks))
            self.phase = None
        if pc in self.spec['capacity']:
            require(len(self.capacity) < 3 and pc == self.spec['capacity'][len(self.capacity)], 'Capacity once/order')
            if len(self.capacity) == 1: require(rd == 10 and value == 1024//self.sew, 'Capacity value')
            self.capacity.append(pc)
        if 0 < len(self.helper) < 11:
            require(pc == self.spec['helper'][len(self.helper)], 'Original contiguous helper')
        if pc in self.spec['helper']:
            i = len(self.helper)
            require(i < 11 and pc == self.spec['helper'][i] and not trap, 'Exactly one original11 helper')
            if i == 0:
                require([self.regs[n] for n in range(10, 14)] ==
                        [0x40000ffc if self.sew == 8 else 0x40001000,
                         self.s['fx_out']+self.width, self.s['fx_mask'], 8], 'Original four arguments')
            if i in (0, 8): require(rd == 5 and value == 8, 'Original setup/store restore VL8')
            if i == 4: require(rd == 10 and value == (4 if self.sew == 8 else 8), 'Business return VL')
            if i == 5: require(rd == 6 and value == 0, 'Returned vstart')
            self.helper.append(pc)
        if pc == self.s['fx_handler']:
            require(not self.handler and len(self.helper) == 11, 'Only completion handler')
            self.handler.append({})
        if insn & 127 == 0x73 and (insn >> 12) & 7 == 2 and (insn >> 15) & 31 == 0 and rd:
            csr = insn >> 20
            if self.s['fx_trap'] <= pc < self.s['main'] and csr in c.source.FIELDS:
                k = c.source.FIELDS[csr]
                require(self.handler and k not in self.handler[0], 'Actual handler CSR ownership')
                self.handler[0][k] = value
            if self.s['main'] <= pc < self.s['fx_handler'] and csr in c.source.RESTORE:
                target = self.restored if len(self.points) == 2 else self.saved if not self.capacity else None
                if target is not None:
                    require(csr not in target, 'Duplicate original save/restore read'); target[csr] = value
        a, rm, wm, data = (int(row[k], 16) for k in ('mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata'))
        if rm or wm:
            d = scalar_decoder.memory_op(insn)
            require(d and not trap and not (rm and wm), 'Scalar memory operation')
            width = d['size']; bits = (1 << (width*8))-1
            require(width in (1, 2, 4, 8) and a%8+width <= 8 and (rm or wm) == ((1 << width)-1) << (a%8)
                    and a == (self.regs[d['base']]+d['offset']) & MASK64, 'Actual address/width/BE')
            if rm:
                require(d['kind'] == 'read' and rd == d['register'] and rd != 0, 'Scalar load destination')
                unsigned = value & bits
                extension = MASK64 ^ bits if d.get('signed', width == 4) and unsigned >> (width*8-1) else 0
                require(value == unsigned | extension, 'Scalar signed/unsigned data')
                objects = [(self.s['fx_pages'], 20480), (self.s['fx_guard_lo'], 64), (self.s['fx_guard_hi'], 64),
                           (self.s['fx_out'], 130*self.width), (self.s['fx_mask'], 16)]
                if self.phase is not None and any(base <= a < base+n for base, n in objects):
                    require(self.position < len(self.expected[self.phase]) and
                            (a, width, unsigned) == self.expected[self.phase][self.position],
                            'Independent full page/output/guard/mask value/order')
                    self.position += 1
            else:
                require(d['kind'] == 'write' and data & bits == self.regs[d['register']] & bits, 'Store source')
                if a == self.s['fx_completed'] and data != 0:
                    require(width == 8 and data == 0x666f6673696e6701 and not self.completed and
                            set(self.saved) == set(c.source.RESTORE) and self.saved == self.restored and
                            self.checks == (5477 if self.sew == 8 else 5481), 'Completion/full CSR restoration')
                    self.completed = True
                if a == 0xd0000000:
                    require(pc == self.spec['exit_store'] and width == 8 and data == 0 and self.completed,
                            'Actual CTRL0, not HTIF1')
                    self.ctrl.append(0)
        if rd and not trap: self.regs[rd] = value

    def finish(self):
        require(len(self.points) == 2 and self.phase is None and self.helper == self.spec['helper'] and
                self.capacity == self.spec['capacity'] and self.completed and self.ctrl == [0], 'Full independent scope')
        want = [9, self.s['fx_ecall'], 0, 0x800, (8 << 60) | ((self.s['fx_pages']+8192) >> 12),
                8, 0 if self.sew == 8 else 24, 0, 117, 5]
        require(len(self.handler) == 1 and set(self.handler[0]) == set(range(10)), 'Complete S-ECALL context')
        for i, value in enumerate(want):
            actual = self.handler[0][i]
            require((actual & 0x8000031888 if i == 3 else actual) == value, 'Actual handler context')
        return dict(sew=self.sew, checks=self.checks, checkpoints=self.points, full_page_word_reads=5120,
                    defined_output_reads=[130, 126 if self.sew == 8 else 130], mask_byte_reads=32,
                    page_guard_word_reads=32, original_guards=[0, 9], allowed_undefined_final=[5,6,7,8] if self.sew == 8 else [],
                    business_returned_vl=4 if self.sew == 8 else 8, completion_vl=8, returned_vstart=0,
                    actual_handler_csrs=self.handler, ctrl=self.ctrl, postexit_park=self.park)

def audit(out):
    require(sha(RUN/'plan.json') == PLAN_SHA, 'Sealed plan drift')
    plan = read(RUN/'plan.json'); cases = plan['cases']
    roots = {case['id']: RUN/'replay/tests'/case['id'] for case in cases}
    complete = read(RUN/'complete.json'); meta = read(RUN/'replay/run.json'); summary = read(RUN/'replay/summary.json')
    monitors = {n: read(root/'monitor_outcome.unvalidated.json') for n, root in roots.items()}
    children = {n: read(root/'child_outcome.unvalidated.json') for n, root in roots.items()}
    terminal_gate(complete, meta, summary, monitors, children, cases)
    worker.validate(plan, Path(plan['image']))
    launch = read(RUN/'launch.json'); verify(launch['approval_pins'])
    require(launch['plan_sha256'] == PLAN_SHA, 'Actual launch binding')
    evidence = dict(complete['evidence_pins'])
    required = [RUN/'launch.json', RUN/'replay/run.json', RUN/'replay/summary.json']
    names = ('input.elf', 'inputs.json', 'command.json', 'console.log', 'work/run.vcs.log', 'commit_trace.csv',
             'trace_summary.json', 'monitor_outcome.unvalidated.json', 'child_outcome.unvalidated.json',
             'strict_csv.json', 'strict_original.json')
    required += [root/name for root in roots.values() for name in names]
    require(set(evidence) == {str(p) for p in required}, 'Exact whole terminal evidence membership')
    csv_hashes = {n: evidence.pop(str(root/'commit_trace.csv')) for n, root in roots.items()}
    verify(evidence)
    evidence[str(RUN/'complete.json')] = sha(RUN/'complete.json')
    evidence[str(RUN/'plan.json')] = PLAN_SHA
    ledger = read(Path(plan['image'])/'image.json')
    require(meta['simv'] == ledger['simv'], 'Actual image')
    stricts = {}
    # All two-case metadata, commands and actual monitor outcomes gate any CSV opening.
    for case, result in zip(cases, summary):
        n = case['id']; root = roots[n]
        require(result['artifact_dir'] == str(root), 'Unexpected artifact directory')
        obj = SimpleNamespace(**dict(result, artifact_dir=root))
        c.common.check_artifacts(obj, c.runtime_case(case), ledger)
        for filename in ('console.log', 'work/run.vcs.log'): c.console_gate((root/filename).read_text())
        require(children[n]['command_sha256'] == monitors[n]['command_sha256'] == sha(root/'command.json'), 'Durable command binding')
        strict = read(root/'strict_original.json'); stricts[n] = strict
        require(strict['csv_sha256'] == csv_hashes[n] and strict['strict'] == read(root/'strict_csv.json') and
                strict['strict']['status'] == 'PASS_FOF_ORIGINAL_SINGLE', 'Bound worker full source maps/oracle')
    results = []
    for case in cases:
        n = case['id']; root = roots[n]; trace = root/'commit_trace.csv'; before = trace.stat()
        save(out/(n+'.csv_started.json'), dict(time=time.time(), csv=str(trace), expected_sha256=csv_hashes[n],
             whole_terminal_sha256=evidence[str(RUN/'complete.json')], actual_monitor_returncode=0))
        numerical = Numerical(plan['specs'][str(case['sew'])]); combined = CombinedPath(trace, numerical)
        try:
            generic = validate_trace(combined); data = numerical.finish()
        except BaseException as error:
            save(out/(n+'.csv_failure.json'), dict(error=f'{type(error).__name__}: {error}',
                 current_row=combined.current, checks=numerical.checks, checkpoints=numerical.points, no_retry=True))
            raise
        after = trace.stat()
        require((before.st_ino,before.st_size,before.st_mtime_ns) == (after.st_ino,after.st_size,after.st_mtime_ns), 'CSV changed during pass')
        require(combined.digest.hexdigest() == csv_hashes[n], 'One-pass CSV hash')
        strict = stricts[n]
        require(generic == strict['generic'] and generic['cvx_exception_count'] == 0 and
                generic['backend_uop_alloc_count'] == generic['backend_uop_done_count'] > 0, 'Protocol/event counts')
        require([p['cycle'] for p in data['checkpoints']] == [p['cycle'] for p in strict['strict']['checkpoints']] and
                data['checks'] == strict['strict']['checks'], 'Independent oracle/event coordinates')
        item = dict(name=n, generic=generic, numerical=data, actual_monitor_returncode=0,
                    elapsed_s=monitors[n]['elapsed_s'], csv_full_passes=1, csv_sha256=csv_hashes[n])
        save(out/(n+'.json'), item); results.append(item)
    verify(evidence); verify(plan['pins']); verify(launch['approval_pins'])
    require(sha(RUN/'plan.json') == PLAN_SHA, 'Late plan drift')
    evidence.update({str(roots[n]/'commit_trace.csv'): h for n,h in csv_hashes.items()})
    return dict(status='PASS_INDEPENDENT_TERMINAL_FOF_TWO_SINGLES', results=results, evidence_pins=evidence,
                plan_sha256=PLAN_SHA, original_input_pin_count=len(plan['pins']), source_reference_pins=118,
                source_oracle_executor_rerun=False, reference_raw_reparsed=False, csv_full_passes=2,
                service_exit='NOT_QUERIED_NOT_PROVEN; no collected-unit/default-state inference',
                zero_MMU_physical_activity_proved=False,
                scope='Two selected source-derived real Sv39 FOF singles, not Linux/all8 historical ELFs')

def seal():
    require(sha(RUN/'plan.json') == PLAN_SHA, 'Prepare plan drift')
    host = read(HERE/'host01/execution.json')
    require(host['actual_wait_returncode'] == 0, 'Host actual exit')
    pins = {str(p):sha(p) for p in (HERE/'waiter.py', HERE/'test_host.py', HERE/'README.md',
            HERE/'host01/execution.json', HERE/'host01/output.log', RUN/'plan.json', BASE/'parent_review.json')}
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(c.G.parents[2]):
            pins[str(Path(path).resolve())] = sha(Path(path))
    save(HERE/'READY.json', dict(status='PREPARED_WAIT_NOT_STARTED', pins=pins, plan_sha256=PLAN_SHA,
         requires_parent_authorization=True, wait_seconds=3600, offline_seconds=600, suggested_service_seconds=4300,
         no_active_CSV_reads=True))

def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('mode', choices=['seal','wait'])
    p.add_argument('--authorize-wait', action='store_true'); p.add_argument('--ready-sha256'); p.add_argument('--out', type=Path)
    args = p.parse_args()
    if args.mode == 'seal': seal(); return 0
    require(args.authorize_wait and sha(HERE/'READY.json') == args.ready_sha256, 'Explicit pinned main wait authorization')
    require(args.out is not None and args.out.resolve().parent == HERE and not args.out.exists(), 'Fresh owned output only')
    ready = read(HERE/'READY.json'); verify(ready['pins']); args.out.mkdir()
    save(args.out/'started.json', dict(time=time.time(), pid=os.getpid(), ready_sha256=args.ready_sha256, argv=sys.argv, no_DUT_control=True))
    def interrupted(*_): raise RuntimeError('Waiter interrupted/offline audit deadline')
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM): signal.signal(sig, interrupted)
    try:
        wait_terminal(RUN/'complete.json', 3600)
        signal.alarm(600)
        result = audit(args.out)
        verify(ready['pins']); require(sha(HERE/'READY.json') == args.ready_sha256, 'Late waiter pin drift')
    except BaseException as error:
        result = dict(status='NOT_ACCEPTED', error=f'{type(error).__name__}: {error}', no_retry=True,
                      csv_started=[p.name for p in args.out.glob('*.csv_started.json')])
    finally: signal.alarm(0)
    result.update(finished=time.time(), waiter_ready_sha256=args.ready_sha256)
    save(args.out/'result.json', result); print(result['status'], flush=True)
    return int(result['status'] != 'PASS_INDEPENDENT_TERMINAL_FOF_TWO_SINGLES')

if __name__ == '__main__': raise SystemExit(main())

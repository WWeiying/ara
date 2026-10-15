#!/usr/bin/env python3
"""Authorized terminal-event waiter; one CSV pass, no DUT control or reference execution."""
import argparse
import csv
import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent
RUN = BASE / 'prepared01'
PLAN_SHA = 'aa4c92d225e275b79626d8b732d97363ff5bcc85b71d4a29a1def3b9e367906f'
sys.path.insert(0, str(BASE))
import checker as c
import csv_check as scalar_decoder
sys.path.insert(0, str(c.G.parents[2] / 'verification'))
from ara_verify.trace import validate_trace

read, sha, require = c.read, c.sha, c.require


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def verify(pins):
    for path, digest in pins.items():
        require(sha(Path(path)) == digest, 'Pin drift: ' + path)


def terminal_gate(complete, metadata, summary, monitor, child):
    require(complete['status'] == 'PASS_M6_NEGATIVE_STRIDE_SOURCE_SINGLE_NOT_LINUX' and
            complete['aborted'] is False and complete['pins_unchanged'] is True and
            complete['retries'] == 0 and complete['plan_sha256'] == PLAN_SHA,
            'Whole terminal not clean PASS')
    require(metadata['status'] == 'COMPLETE' and metadata['status_counts'] == {'PASS': 1} and
            metadata['tests'] == [c.NAME] and metadata['jobs'] == 1 and metadata['timeout_s'] == 3600,
            'Runner not exact COMPLETE')
    require(summary == complete['results'] and len(summary) == 1, 'Terminal membership')
    result = summary[0]
    for row in (result, child, monitor):
        require(type(row['returncode']) is int and row['returncode'] == 0,
                'Missing actual persisted numeric zero')
        require(0 < row['elapsed_s'] <= 3600, 'Case time bound')
    require(result['name'] == child['name'] == c.NAME and
            result['status'] == child['status'] == 'PASS' and not result['reason'] and
            result['elapsed_s'] == child['elapsed_s'] == monitor['elapsed_s'], 'Child outcome mismatch')
    require(monitor['timed_out'] is False and monitor['failure_seen'] is False and
            monitor['abort_set'] is False and monitor['architectural_acceptance'] is False and
            child['architectural_acceptance'] is False, 'Monitor abort/failure/timeout')
    return result


def wait_terminal(path, seconds):
    # Register before checking existence: atomic rename cannot fall into a missed-event gap.
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    require(fd >= 0, 'inotify unavailable')
    try:
        wd = libc.inotify_add_watch(fd, os.fsencode(path.parent), 0x100 | 0x80 | 0x8 | 0x400 | 0x800)
        require(wd >= 0, 'Cannot watch original run directory')
        end = time.monotonic() + seconds
        while not path.is_file():
            left = end - time.monotonic()
            require(left > 0, 'No terminal publication within waiter bound; no CSV read')
            require(select.select([fd], [], [], left)[0], 'Terminal event wait expired; no CSV read')
            os.read(fd, 65536)
    finally:
        os.close(fd)


class Numerical:
    """Independent scalar-read synthesis, not re-execution of the frozen source oracle."""
    def __init__(self, spec):
        self.spec, self.s = spec, spec['symbols']
        self.code = {int(k): v for k, v in spec['code'].items()}
        self.regs = {i: 0 for i in range(32)}
        self.phase = None
        self.mem_reads = []
        self.points = []
        self.output = []
        self.checks = 0
        self.helper = []
        self.capacity = []
        self.traps = []
        self.csrs = {}
        self.retry = []
        self.ctrl = []
        self.refill = None
        self.refills = []
        self.park = 0

    def row(self, row):
        if row['event'] != 'retire':
            return
        pc, insn, value = (int(row[k], 16) for k in ('pc', 'insn', 'rd_wdata'))
        rd, trap = int(row['rd']), int(row['trap'])
        require(self.code.get(pc) == insn, 'Independent actual PC/code mismatch')
        require(pc not in self.spec['unused'] and pc not in (self.s['trap_entry'], self.s['replay_mismatch']),
                'Unused helper/default trap/mismatch')
        if self.ctrl:
            require(pc == self.spec['park'] and rd == 0 and not trap and
                    int(row['mem_rmask'], 16) == int(row['mem_wmask'], 16) == 0,
                    'Nonpark after actual CTRL')
            self.park += 1
            return
        if pc == self.s['check']:
            require(self.regs[10] == self.regs[11], 'Actual scalar equality failure')
            self.checks += 1
        if pc == self.s['check_memory']:
            require(self.phase is None and self.regs[10] == len(self.points), 'Memory phase/order')
            self.phase = self.regs[10]
            self.mem_reads = []
        if pc == self.s['mx_checkpoint']:
            require(self.phase == len(self.points) and len(self.mem_reads) == 4096 and
                    self.checks == (4117, 8450, 12563, 17052)[self.phase], 'Incomplete phase oracle')
            self.points.append(dict(phase=self.phase, cycle=int(row['cycle']), checks=self.checks))
            self.phase = None
        if pc in self.spec['capacity']:
            self.capacity.append(pc)
        if pc in self.spec['helper'] and not trap:
            require(pc == self.spec['helper'][len(self.helper)], 'Helper ordering')
            if len(self.helper) == 0:
                require([self.regs[i] for i in range(10, 16)] ==
                        [0x40001016, self.s['mx_input'], self.s['mx_out'] + 2,
                         self.s['mx_mask'], 64, self.s['mx_stride']], 'Original helper arguments')
            if len(self.helper) == 6:
                require(rd == 10 and value == 0, 'Returned vstart')
            self.helper.append(pc)
        if pc == self.s['mx_handler']:
            self.traps.append({})
        if insn & 127 == 0x73 and (insn >> 12) & 7:
            csr, f, src = insn >> 20, (insn >> 12) & 7, (insn >> 15) & 31
            if self.s['mx_trap'] <= pc < self.s['main'] and csr in scalar_decoder.CSR_FIELDS and rd and f == 2 and src == 0:
                key = scalar_decoder.CSR_FIELDS[csr]
                require(self.traps and key not in self.traps[-1], 'Handler CSR ownership')
                self.traps[-1][key] = value
            if f in (1, 5) or src:
                operand = src if f >= 5 else self.regs[src]
                old = self.csrs.get(csr, 0)
                self.csrs[csr] = operand if f in (1, 5) else old | operand if f in (2, 6) else old & ~operand
            elif rd:
                self.csrs[csr] = value
        if pc == self.s['mx_trap_mret'] and len(self.traps) == 1:
            require(self.csrs.get(0x341) == self.s['fault_0_pc'] and self.csrs.get(8) == 5 and
                    self.regs[10] == 0x40001016 and self.regs[28] == 0xfffffffffffffff8,
                    'Retry same PC/start5/original base/negative stride')
            self.retry.append(int(row['cycle']))
        if pc == self.s['mx_refill_page']:
            require(self.refill is None and not self.refills, 'Repeated refill')
            self.refill = 0
        if self.refill is not None and not self.s['mx_refill_page'] <= pc < self.s['mx_trap']:
            require(self.refill == 2048, 'Incomplete lower refill')
            self.refills.append(self.refill)
            self.refill = None
        a, rm, wm, data = (int(row[k], 16) for k in ('mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata'))
        if rm or wm:
            d = scalar_decoder.memory_op(insn, self.regs)
            require(d is not None and not trap and not (rm and wm), 'Unexpected scalar memory row')
            width = d['size']
            require(width in (1, 2, 4, 8) and a % 8 + width <= 8 and
                    (rm or wm) == ((1 << width) - 1) << (a % 8) and
                    a == (self.regs[d['base']] + d['offset']) & ((1 << 64) - 1), 'Actual memory address/BE')
            if rm:
                require(d['kind'] == 'read' and rd == d['register'] and rd != 0, 'Load destination')
                bits = (1 << (8 * width)) - 1
                unsigned = value & bits
                expected = unsigned
                if d.get('signed', width == 4) and unsigned >> (8 * width - 1):
                    expected |= ((1 << 64) - 1) ^ bits
                require(value == expected, 'Load sign/zero extension')
                if self.phase is not None and self.s['mx_pages'] <= a < self.s['mx_pages'] + 8192:
                    i = len(self.mem_reads)
                    want = 0x2821 if self.phase >= 2 and i == 2051 else (i * 37 + 11) & 65535
                    require(width == 2 and a == self.s['mx_pages'] + 2 * i and unsigned == want,
                            'Independent full8KiB phase data/order')
                    self.mem_reads.append(a)
                if len(self.helper) == 10 and self.s['mx_out'] <= a < self.s['mx_out'] + 260:
                    sequence = list(range(1, 65)) + [0, 65] + list(range(66, 130))
                    i = sequence[len(self.output)]
                    want = 0x287a if i == 3 else 0x26be if i == 6 else 0x5b
                    require(width == 2 and a == self.s['mx_out'] + 2 * i and unsigned == want,
                            'Independent result/prefix/guard value/order')
                    self.output.append(a)
            else:
                require(d['kind'] == 'write' and data & ((1 << (8 * width)) - 1) ==
                        self.regs[d['register']] & ((1 << (8 * width)) - 1), 'Store source')
                if self.refill is not None:
                    i = self.refill
                    require(width == 2 and a == self.s['mx_pages'] + i * 2 and
                            data & 65535 == (37 * i + 11) & 65535, 'Actual lower refill data/order')
                    self.refill += 1
                if a == 0xd0000000:
                    require(pc == self.spec['exit_store'] and width == 8 and data == 0 and
                            self.checks == 17274 and len(self.output) == 130, 'Actual CTRL0/oracle completion')
                    self.ctrl.append(0)
        if rd and not trap:
            self.regs[rd] = value

    def finish(self):
        require(len(self.points) == 4 and self.phase is None and self.checks == 17274 and
                len(self.output) == 130 and self.helper == self.spec['helper'] and
                self.capacity == self.spec['capacity'] and self.refills == [2048] and
                len(self.retry) == 1 and self.ctrl == [0], 'Independent data scope incomplete')
        satp = (8 << 60) | ((self.s['mx_pages'] + 8192) >> 12)
        expected = [[13, self.s['fault_0_pc'], 0x40000fee, 0x800, satp, 8, 8, 5, 117, 5],
                    [9, self.s['mx_ecall'], 0, 0x800, satp, 64, 8, 0, 117, 5]]
        require(len(self.traps) == 2, 'Actual two trap contexts')
        for actual, want in zip(self.traps, expected):
            require(set(actual) == set(range(10)), 'Incomplete actual CSR context')
            for i, value in enumerate(want):
                require((actual[i] & 0x8000031888 if i == 3 else actual[i]) == value,
                        'Actual fault/ecall CSR context')
        return dict(checks=self.checks, checkpoints=self.points, output_reads=len(self.output),
                    original_results=64, original_guards=2, extra_storage_guards=64,
                    memory_halfword_reads=16384, refills=self.refills, retry_cycles=self.retry,
                    actual_handler_csrs=self.traps, ctrl=self.ctrl, postexit_park=self.park)


class CombinedPath:
    def __init__(self, path, numerical):
        self.path, self.numerical = path, numerical
        self.digest = hashlib.sha256()
        self.current = None

    def open(self, **_):
        self.stream = self.path.open('rb')
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.stream.close()

    def __iter__(self):
        for n, raw in enumerate(self.stream):
            self.digest.update(raw)
            line = raw.decode('utf-8')
            fields = next(csv.reader([line]))
            if n == 0:
                require(fields == scalar_decoder.FIELDS, 'Exact CSV header')
            else:
                require(len(fields) == len(scalar_decoder.FIELDS), 'Truncated CSV row')
                self.current = dict(zip(scalar_decoder.FIELDS, fields))
                self.numerical.row(self.current)
            yield line


def audit(out):
    require(sha(RUN / 'plan.json') == PLAN_SHA, 'Sealed plan drift')
    plan = read(RUN / 'plan.json')
    root = RUN / 'replay/tests' / c.NAME
    complete = read(RUN / 'complete.json')
    metadata = read(RUN / 'replay/run.json')
    summary = read(RUN / 'replay/summary.json')
    monitor = read(root / 'monitor_outcome.unvalidated.json')
    child = read(root / 'child_outcome.unvalidated.json')
    result = terminal_gate(complete, metadata, summary, monitor, child)
    require(result['artifact_dir'] == str(root), 'Unexpected artifact directory')
    verify(plan['pins'])
    launch = read(RUN / 'launch.json')
    verify(launch['approval_pins'])
    require(launch['plan_sha256'] == PLAN_SHA, 'Launch plan mismatch')
    trace = root / 'commit_trace.csv'
    evidence = dict(complete['evidence_pins'])
    required = [RUN / 'launch.json', RUN / 'replay/run.json', RUN / 'replay/summary.json']
    required += [root / name for name in ('input.elf', 'inputs.json', 'command.json', 'console.log',
                'work/run.vcs.log', 'commit_trace.csv', 'trace_summary.json', 'strict_prefix.json')]
    require(set(evidence) == {str(p) for p in required}, 'Exact terminal evidence membership')
    expected_csv = evidence.pop(str(trace))
    verify(evidence)
    for p in (RUN / 'complete.json', root / 'child_outcome.unvalidated.json', root / 'monitor_outcome.unvalidated.json'):
        evidence[str(p)] = sha(p)
    ledger = read(Path(plan['image']) / 'image.json')
    obj = SimpleNamespace(**dict(result, artifact_dir=root))
    c.common.check_artifacts(obj, c.runtime_case(plan['case']), ledger)
    require(metadata['simv'] == ledger['simv'], 'Runner image identity')
    for name in ('console.log', 'work/run.vcs.log'):
        c.console_gate((root / name).read_text())
    command_sha = sha(root / 'command.json')
    require(child['command_sha256'] == monitor['command_sha256'] == command_sha, 'Durable command identity')
    strict = read(root / 'strict_prefix.json')
    require(strict['strict']['status'] == 'PASS_NEGATIVE_STRIDE_FULL_SINGLE' and
            strict['csv_sha256'] == expected_csv and strict['child_outcome_sha256'] == sha(root / 'child_outcome.unvalidated.json') and
            strict['monitor_outcome_sha256'] == sha(root / 'monitor_outcome.unvalidated.json'), 'Worker strict outcome binding')
    before = trace.stat()
    save(out / 'csv_started.json', dict(time=time.time(), csv=str(trace), expected_sha256=expected_csv,
                                      whole_terminal_sha256=sha(RUN / 'complete.json'), actual_monitor_returncode=0))
    numerical = Numerical(plan['spec'])
    combined = CombinedPath(trace, numerical)
    try:
        generic = validate_trace(combined)
        data = numerical.finish()
    except BaseException as error:
        save(out / 'csv_failure.json', dict(error=f'{type(error).__name__}: {error}',
             current_row=combined.current, checks=numerical.checks, checkpoints=numerical.points,
             output_reads=len(numerical.output), no_retry=True))
        raise
    require(combined.digest.hexdigest() == expected_csv, 'One-pass CSV digest differs')
    after = trace.stat()
    require((before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_ino, after.st_size, after.st_mtime_ns), 'CSV changed during read')
    require(generic == strict['generic'] and generic['cvx_exception_count'] == 1 and
            generic['backend_uop_alloc_count'] == generic['backend_uop_done_count'] > 0,
            'Independent generic protocol/count discrepancy')
    require([p['cycle'] for p in data['checkpoints']] == [p['cycle'] for p in strict['strict']['checkpoints']] and
            data['retry_cycles'] == [r['cycle'] for r in strict['strict']['retry_mrets']], 'Independent event coordinates')
    verify(evidence)
    verify(plan['pins'])
    verify(launch['approval_pins'])
    require(sha(RUN / 'plan.json') == PLAN_SHA, 'Late plan drift')
    evidence[str(trace)] = expected_csv
    return dict(status='PASS_INDEPENDENT_TERMINAL_SINGLE', generic=generic, numerical=data,
                evidence_pins=evidence, original_input_pin_count=len(plan['pins']), plan_sha256=PLAN_SHA,
                actual_monitor_returncode=0, elapsed_s=result['elapsed_s'],
                source_oracle_executor_rerun=False, raw_reference_reparsed=False, csv_full_passes=1,
                original_worker_full_oracle='Bound strict_prefix.json accepted; no second source-oracle execution',
                service_exit='NOT_QUERIED_NOT_PROVEN; launch ownership is separately pinned, no GC-default inference',
                scope='One source-derived real Sv39 single; not original Linux signalframe or parent96')


def seal():
    require(sha(RUN / 'plan.json') == PLAN_SHA, 'Plan drift during preparation')
    host = read(HERE / 'host02/execution.json')
    require(host['actual_wait_returncode'] == 0 and host['status'] == 'PASS_HOST_ONLY', 'Host gate')
    pins = {str(p): sha(p) for p in (HERE / 'waiter.py', HERE / 'test_host.py', HERE / 'README.md',
            HERE / 'host02/execution.json', HERE / 'host02/output.log', RUN / 'plan.json')}
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(c.G.parents[2]):
            pins[str(Path(path).resolve())] = sha(Path(path))
    save(HERE / 'READY.json', dict(status='PREPARED_WAIT_NOT_STARTED', pins=pins, plan_sha256=PLAN_SHA,
                                   requires_parent_authorization=True, no_active_csv_reads=True))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['seal', 'wait'])
    p.add_argument('--authorize-wait', action='store_true')
    p.add_argument('--ready-sha256')
    p.add_argument('--out', type=Path)
    args = p.parse_args()
    if args.mode == 'seal':
        seal()
        return 0
    require(args.authorize_wait and args.ready_sha256 == sha(HERE / 'READY.json'), 'Explicit pinned main authorization required')
    require(args.out is not None and args.out.resolve().parent == HERE and not args.out.exists(), 'Fresh owned output only')
    ready = read(HERE / 'READY.json')
    verify(ready['pins'])
    args.out.mkdir()
    save(args.out / 'started.json', dict(time=time.time(), pid=os.getpid(), ready_sha256=args.ready_sha256,
                                       argv=sys.argv, no_DUT_control=True))
    def interrupted(*_):
        raise RuntimeError('Waiter interrupted or offline audit deadline exceeded')
    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM):
        signal.signal(number, interrupted)
    result = dict(status='NOT_ACCEPTED', csv_full_passes=0)
    try:
        wait_terminal(RUN / 'complete.json', 5400)
        signal.alarm(600)
        result = audit(args.out)
        verify(ready['pins'])
        require(sha(HERE / 'READY.json') == args.ready_sha256, 'Late waiter READY drift')
    except BaseException as error:
        result = dict(status='NOT_ACCEPTED', error=f'{type(error).__name__}: {error}',
                      csv_started=(args.out / 'csv_started.json').exists(), no_retry=True)
    finally:
        signal.alarm(0)
    result.update(finished=time.time(), waiter_ready_sha256=args.ready_sha256)
    save(args.out / 'result.json', result)
    print(result['status'], flush=True)
    return int(result['status'] != 'PASS_INDEPENDENT_TERMINAL_SINGLE')


if __name__ == '__main__':
    raise SystemExit(main())

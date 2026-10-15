#!/usr/bin/env python3
"""One closed partial trace diagnosis, never architectural acceptance."""
import csv
import hashlib
import heapq
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time
from collections import Counter
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
A = HERE.parents[1]
OLD = A/'full_e8_m8_block_vcs_m9_plan01'
PREP = OLD/'prepared01'
ROOT = PREP/'replay/tests/arithmetic_original_e8_m8_full4095_block'
TRACE = ROOT/'commit_trace.csv'
FROZEN = Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/frozen/sources')
PLAN_SHA = 'd5499f1b6d2db2f9cc8cd9300caf13fc571f7f9c2738a94f29c0fc66b8da0339'
CHECKER_SHA = '9c01b3a5064bd820021ea13e099b75e6bda814cc8a3428a5e4de7085a3307c99'
aborted = False


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def need(ok, text):
    if not ok: raise ValueError(text)
def load(name, p):
    spec = importlib.util.spec_from_file_location(name, p)
    value = importlib.util.module_from_spec(spec); sys.modules[name] = value
    spec.loader.exec_module(value)
    return value
def save(p, value):
    with Path(p).open('x') as f:
        json.dump(value, f, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
def stat(p):
    s = Path(p).stat()
    return dict(dev=s.st_dev, inode=s.st_ino, size=s.st_size, mtime_ns=s.st_mtime_ns)
def clean(value):
    if isinstance(value, dict): return {str(k): clean(v) for k,v in value.items()}
    if isinstance(value, (tuple, list)): return [clean(v) for v in value]
    if isinstance(value, set): return sorted(value)
    return value


need(sha(OLD/'checker.py') == CHECKER_SHA, 'Own sealed e8m8 checker identity')
base = load('e8m8_partial_original_checker', OLD/'checker.py')
protocol = load('e8m8_partial_frozen_protocol', FROZEN/'verification/ara_verify/trace.py')
delta = load('e8m8_partial_exact_vi2', A/'full_m8_slideup_owner_templates01/owner_delta.py')


def inputs():
    need(sha(PREP/'plan.json') == PLAN_SHA, 'Original plan identity')
    plan = read(PREP/'plan.json')
    spec = plan['specs'][base.SHAPE]
    need(spec == base.specification(), 'Own actual spec/helper/ELF identity')
    need(sha(ROOT/'input.elf') == base.ELF_SHA, 'Private ELF identity')
    numeric = read(ROOT/'child_outcome.unvalidated.json')
    need(numeric['returncode'] == 255 and numeric['timed_out'] is True,
         'This is the existing timeout, not simulator0 recovery')
    need(read(PREP/'complete.json')['status'] == 'NOT_PASS' and
         read(PREP/'service_exit.json')['EXIT_STATUS'] == '1', 'Preserve old terminal failure')
    pins = {}
    for module in list(sys.modules.values()):
        f = getattr(module, '__file__', None)
        if not f: continue
        p = Path(f).resolve()
        if p.is_file() and (p.is_relative_to(A.parents[3]) or p.is_relative_to(FROZEN)):
            pins[str(p)] = sha(p)
            if str(p) in plan['pins']:
                need(pins[str(p)] == plan['pins'][str(p)], 'Imported sealed input drift: '+str(p))
    for p in [PREP/'plan.json', ROOT/'input.elf', ROOT/'command.json',
              ROOT/'child_outcome.unvalidated.json', PREP/'complete.json', PREP/'service_exit.json',
              base.REF/'sequence.json', base.REF/'model.py', base.REF/'soc/program.dis',
              HERE/'diagnostic.py', HERE/'test_small.py', HERE/'run_once.py',
              FROZEN/'hardware/tb/ara_commit_monitor.sv']:
        pins[str(p)] = sha(p)
    return spec, pins


class Prefix:
    def __init__(self, spec):
        Strict, _ = delta.make_types(base, spec)
        self.state = Strict(spec)
        self.observer = base.OwnerObserver(protocol)
        self.arch_index = 0
        self.bound = []
        self.bycall = {}
        self.closed_calls = 0
        self.last = self.last_retire = None
        self.gaps = []; self.retire_gaps = []; self.serial = 0
        self.bins = {}; self.pending_cvx = {}; self.pending_uop = {}
        self.owner_lifetimes = []; self.checkpoints = []
        self.counter_writes = {}; self.current_row = None
        self.mask_stores = 0

    def top(self, heap, size, value):
        self.serial += 1
        heapq.heappush(heap, (size, self.serial, value))
        if len(heap) > 32: heapq.heappop(heap)

    def bind(self, item):
        o = self.observer
        while self.arch_index < len(o.arch):
            order = self.arch_index; insn = o.arch[order]
            if insn == item['insn']:
                self.arch_index += 1
                bound = dict(item, arch_order=order)
                self.bound.append(bound)
                if item['call'] is not None: self.bycall.setdefault(item['call'], []).append(bound)
                return
            need(protocol._is_transport_replay(insn, o.arch[order-1] if order else None)
                 and o.owner_alloc[order] == o.owner_done[order] == 0,
                 'Unexpected non-retired architecture request before retired helper')
            self.arch_index += 1
        raise ValueError('Retired offload lacks preceding actual architecture owner')

    def check_call_owners(self, call):
        items = self.bycall[call]
        need([x['helper_index'] for x in items if x['kind'] == 'memory'] == [1,2,3,4,11],
             'Missing actual mandatory helper memory owner')
        for item in items:
            i = item['arch_order']; alloc = self.observer.owner_alloc[i]; done = self.observer.owner_done[i]
            need(alloc == done, 'Completed checked call retains unfinished backend owner: '+str(item))
            if item['required']: need(alloc > 0, 'Missing necessary architectural owner '+str(item))
            if item['kind'] == 'configuration': need(alloc == 0, 'Configuration allocated data owner')

    def consume(self, row):
        self.current_row = dict(row)
        s = self.state; old_calls = len(s.calls); old_offloads = len(s.offloads)
        s.consume(row)  # Unchanged original numeric/setup/PC/CSR/fresh checks.
        if len(s.offloads) > old_offloads: self.bind(s.offloads[-1])
        if len(s.calls) > old_calls and old_calls:
            self.check_call_owners(old_calls-1); self.closed_calls = old_calls
        cycle = int(row['cycle']); event = row['event']
        point = {k:row[k] for k in ('cycle','event','order','pc','insn')}
        point['call_entered'] = len(s.calls)
        if self.last is not None:
            gap = cycle-int(self.last['cycle'])
            if gap: self.top(self.gaps, gap, dict(from_event=self.last,to_event=point,
                pending_cvx=clean(self.pending_cvx), pending_uop=clean(self.pending_uop)))
        self.last = point
        self.bins.setdefault(cycle//1000000, Counter())[event] += 1
        if event == 'cvx_req': self.pending_cvx[int(row['trans_id'])] = point
        elif event == 'cvx_resp': self.pending_cvx.pop(int(row['trans_id']))
        elif event == 'uop_alloc': self.pending_uop[int(row['port'])] = point
        elif event == 'uop_done':
            begin = self.pending_uop.pop(int(row['port']))
            self.top(self.owner_lifetimes, cycle-int(begin['cycle']), dict(alloc=begin,done=point))
        elif event == 'retire':
            if self.last_retire is not None:
                gap = cycle-int(self.last_retire['cycle'])
                if gap: self.top(self.retire_gaps, gap, dict(from_event=self.last_retire,to_event=point))
            self.last_retire = point
            if int(row['mem_wmask'],16):
                addr = int(row['mem_addr'],16)
                if int(row['pc'],16) == 0x80000b2e: self.mask_stores += 1
                for name in ('checks','elements','errors'):
                    if addr == s.s[name]:
                        self.counter_writes[name] = dict(point,value=int(row['mem_wdata'],16))
                        if name == 'checks' and s.body_entered:
                            self.checkpoints.append(dict(point,value=int(row['mem_wdata'],16)))

    def partial(self):
        s,o = self.state,self.observer
        need(o.count['rows'] == o.count['unmodified_delivered_rows'] == s.rows and
             o.before.digest() == o.after.digest(), 'All original rows delivered unmodified')
        need(o.count['retire'] == s.retired and o.last == s.cycle, 'Strict/generic count mismatch')
        complete_reads = sum(x['reads'] == set(range(129)) and x['returned_vstart'] == 0 for x in s.calls)
        if s.active and s.helper is None and s.active['reads'] == set(range(129)) and s.active['returned_vstart'] == 0:
            self.check_call_owners(s.active['ordinal']); self.closed_calls = len(s.calls)
        # Run exact generic sequence validator only on the matched prefix. Never
        # supply fabricated rows or demand EOF completion of a timed-out program.
        ri=qi=0
        while ri < len(o.retvec) and qi < len(o.requests):
            if o.retvec[ri] == o.requests[qi]: ri+=1; qi+=1
            elif protocol._is_transport_replay(o.requests[qi],o.requests[qi-1] if qi else None): qi+=1
            else: raise ValueError('Generic retired/request prefix sequence mismatch')
        need(ri == len(o.retvec), 'Retired instruction missing actual accepted CVX request')
        replay = protocol._validate_retired_request_sequence(o.retvec, o.requests[:qi])
        # Apply the same generic replay rule, exposing unmatched EOF suffixes.
        ai=aq=0
        while ai<len(o.arch) and aq<len(o.requests):
            if o.arch[ai]==o.requests[aq]: ai+=1; aq+=1
            elif protocol._is_transport_replay(o.requests[aq],o.requests[aq-1] if aq else None): aq+=1
            else: raise ValueError('Arch/accepted CVX prefix order mismatch')
        protocol._validate_retired_request_sequence(o.arch[:ai],o.requests[:aq])
        counters = {name:s.value(s.s[name],8) if all(s.s[name]+i in s.memory for i in range(8)) else None
                    for name in ('checks','elements','errors')}
        current = clean(s.active)
        return dict(status='DIAGNOSTIC_ONLY_PARTIAL_EOF_NOT_PASS', architectural_acceptance=False,
            full_finish_called=False, full4095_complete=False, rows=s.rows,retired=s.retired,last_cycle=s.cycle,
            last_event=self.last,last_retire=self.last_retire,helper=s.helper,next_helper_index=s.index,
            calls_entered=len(s.calls),calls_with_all129_reads_vstart0=complete_reads,
            calls_with_checked_completed_owners=self.closed_calls,current_call=current,
            next_call={k:v for k,v in s.gold[len(s.calls)].items() if k in ('ordinal','seed','op','li','mode','si','vl','vstart')}
                if len(s.calls)<4095 else None,
            source_counters=counters,counter_writes=self.counter_writes,
            fresh={k:sorted(v) for k,v in s.fresh.items()},output_init_index=s.init_index,
            last_gpr={str(k):f'{v:016x}' for k,v in s.regs.items()},helper_counts=s.counts,
            packed_reads=sum(len(c['reads']) for c in s.calls),maskcopy_stores=self.mask_stores,
            source_counter_checkpoints=self.checkpoints,
            generic=dict(counts=dict(o.count),pending_cvx=clean(o.pending),pending_uop=clean(o.uops),
                pending_cvx_cycles=clean(self.pending_cvx),pending_uop_cycles=clean(self.pending_uop),
                unmatched_arch=o.arch[ai:],unmatched_arch_requests=o.requests[aq:],unretired_accepted_requests=o.requests[qi:],
                matched_retired_requests=ri,matched_prefix_replays=replay,
                before_sha256=o.before.hexdigest(),after_sha256=o.after.hexdigest(),
                required_owner_count=sum(x['required'] for x in self.bound),
                observed_arch_owners=len(self.bound)),
            top_event_gaps=[dict(gap_cycles=g,**v) for g,_,v in sorted(self.gaps,reverse=True)],
            top_retire_gaps=[dict(gap_cycles=g,**v) for g,_,v in sorted(self.retire_gaps,reverse=True)],
            top_owner_lifetimes=[dict(cycles=g,**v) for g,_,v in sorted(self.owner_lifetimes,reverse=True)],
            million_cycle_bins=clean(self.bins),final_simulator_cycle_known=False,
            diagnosis='COST_VS_STALL_UNDETERMINED_WITHOUT_FINAL_SIMULATOR_TIME')


def execute():
    out = HERE/'run01'; out.mkdir()
    start = time.monotonic(); prefix = None
    try:
        spec,pins = inputs(); need(read(HERE/'host.json')['status']=='HOST_ONLY_PASS','Small partial EOF Host required')
        pins[str(HERE/'host.json')]=sha(HERE/'host.json')
        before=stat(TRACE); need(before['size']==220110178,'Exact original closed CSV size')
        save(out/'inputs.json',dict(pins=pins,csv_before=before,limit_s=600,semantic_passes=1))
        prefix=Prefix(spec); digest=hashlib.sha256(); bytes_read=0
        def lines(stream):
            nonlocal bytes_read
            for raw in stream:
                digest.update(raw);bytes_read+=len(raw)
                need(raw.endswith(b'\n'),'Truncated final CSV record')
                yield raw.decode('ascii')
        with TRACE.open('rb') as stream:
            for row in prefix.observer.rows(csv.DictReader(lines(stream))):
                if prefix.state.rows%4096==0:
                    need(not aborted and time.monotonic()-start<595,'Diagnostic abort/deadline')
                prefix.consume(row)
        result=prefix.partial()
        need(bytes_read==before['size'] and stat(TRACE)==before,'Closed CSV drift')
        for name,value in pins.items(): need(sha(name)==value,'Input drift: '+name)
        need(not aborted,'Late abort')
        result.update(elapsed_s=time.monotonic()-start,csv_bytes=bytes_read,csv_sha256=digest.hexdigest(),
                      pins_unchanged=True,semantic_passes=1,csv_before=before,csv_after=stat(TRACE))
        save(out/'result.json',result)
        return 0
    except BaseException as e:
        save(out/'firstcause.json',dict(status='DIAGNOSTIC_STOPPED_NOT_ACCEPTED',
            cause=type(e).__name__+': '+str(e),elapsed_s=time.monotonic()-start,
            row=prefix.current_row if prefix else None,rows=prefix.state.rows if prefix else 0,
            current=clean(prefix.state.active) if prefix else None))
        return 1


if __name__=='__main__':
    def stop(signum,frame):
        global aborted
        aborted=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    raise SystemExit(execute())

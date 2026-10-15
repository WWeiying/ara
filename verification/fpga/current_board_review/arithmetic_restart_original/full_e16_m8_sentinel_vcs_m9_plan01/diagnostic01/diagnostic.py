#!/usr/bin/env python3
"""Single closed timeout-prefix diagnosis; never whole-run acceptance."""
import csv,hashlib,importlib.util,json,os,signal,sys,time
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
OLD=HERE.parent;A=OLD.parent;PREP=OLD/'prepared01'
ROOT=PREP/'replay/tests/arithmetic_original_e16_m8_full4095_sentinel'
TRACE=ROOT/'commit_trace.csv'
FROZEN=Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/frozen/sources')
PLAN_SHA='0a2820506439278384569a58f72b76fcb72ae5276f4f302ba6a31f0c65a6335e'
CHECKER_SHA='76ea70dc65aa74c3b0a117283ebe74b2a844211eae08689df7d10a8a404c4d85'
aborted=False
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def need(ok,msg):
    if not ok:raise ValueError(msg)
def load(name,p):
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m
def save(p,value):
    with Path(p).open('x') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def stat(p):
    s=Path(p).stat();return dict(dev=s.st_dev,inode=s.st_ino,size=s.st_size,mtime_ns=s.st_mtime_ns)
def small(items):
    return dict(count=len(items),first=list(items[:4]),last=list(items[-4:]) if len(items)>4 else [])
need(sha(OLD/'checker.py')==CHECKER_SHA,'Exact current sentinel width-corrected checker')
base=load('e16_sentinel_partial_sealed_checker',OLD/'checker.py')
protocol=load('e16_sentinel_partial_frozen_protocol',FROZEN/'verification/ara_verify/trace.py')
FIELDS=base.mature.transport.transport.FIELDS
def inputs():
    need(sha(PREP/'plan.json')==PLAN_SHA,'Actual current sentinel plan')
    plan=read(PREP/'plan.json');spec=plan['specs'][base.SHAPE]
    need(spec==base.specification(),'Actual SoC source/comparator spec')
    need(sha(ROOT/'input.elf')==base.ELF_SHA,'Actual private ELF')
    numeric=read(ROOT/'child_outcome.unvalidated.json')
    need(numeric['returncode']==255 and numeric['timed_out'] is True and numeric['failure_seen'] is False
        and numeric['cancelled'] is False,'Preserve actual timeout, not rc0 or pre-cancel')
    need(read(PREP/'complete.json')['status']=='NOT_PASS' and read(PREP/'service_exit.json')['EXIT_STATUS']=='1'
        and read(PREP/'collector_result.json')['status']=='NOT_ACCEPTED','Old producer/service/collector remain failed')
    paths=[Path(m.__file__) for m in (base,base.mature,base.mature.legacy,base.mature.transport,
        base.mature.transport.transport,base.mature.common,base.mature.common.base,protocol,base.eligibility)]
    paths += [PREP/'plan.json',ROOT/'input.elf',ROOT/'command.json',ROOT/'child_outcome.unvalidated.json',
        PREP/'complete.json',PREP/'service_exit.json',PREP/'collector_result.json',PREP/'collector_exit.json',
        OLD/'reset_profile.json',OLD/'soc_profile.json',base.REF/'model.py',base.REF/'sequence.json',
        base.SOURCE/'soc/program.elf',base.SOURCE/'soc/program.dis',base.SOURCE/'soc/symbols.json',
        base.SOURCE/'linked_cfg_cost02.py',A/'full_e16_mf4_prepare01/model.py',
        FROZEN/'hardware/tb/ara_commit_monitor.sv']
    paths += list(HERE.glob('*.py'))
    pins={}
    for p in paths:
        p=p.resolve()
        need(p!=TRACE.resolve() and p.name!='runner.py','Do not pin/read raw or current/frozen runner code')
        pins[str(p)]=sha(p)
        if str(p) in plan['pins']:need(pins[str(p)]==plan['pins'][str(p)],'Consumed sealed drift '+str(p))
    return spec,pins
class Prefix:
    def __init__(self,spec):
        self.state=base.Strict(spec);self.observer=base.OwnerObserver(protocol)
        self.arch_index=0;self.bycall={};self.bound=[];self.closed_calls=0
        self.current_row=None;self.last=None;self.last_retire=None;self.last_progress=None
        self.max_event=self.max_retire=self.max_progress=self.max_owner=None
        self.bins={};self.pending_cvx={};self.pending_uop={};self.counter_writes={}
    def bind(self,item):
        o=self.observer
        while self.arch_index<len(o.arch):
            j=self.arch_index;insn=o.arch[j];self.arch_index+=1
            if insn==item['insn']:
                item=dict(item,arch_order=j);self.bound.append(item)
                if item['call'] is not None:self.bycall.setdefault(item['call'],[]).append(item)
                return
            need(protocol._is_transport_replay(insn,o.arch[j-1] if j else None)
                 and o.owner_alloc[j]==o.owner_done[j]==0,'Unexpected architecture replay before retired offload')
        raise ValueError('Retired offload missing preceding architecture owner')
    def check_owners(self,call):
        items=self.bycall.get(call,[])
        need([x['helper_index'] for x in items if x['kind']=='memory']==[1,2,3,4,11],'Missing mandatory helper-memory owner')
        need(sum(x['kind']=='target' for x in items)==1,'Missing target architectural owner')
        for item in items:
            n=item['arch_order'];a=self.observer.owner_alloc[n];d=self.observer.owner_done[n]
            need(a==d,'Fully checked call retains unfinished owner '+str(item))
            if item['required']:need(a>0,'Missing necessary backend owner '+str(item))
            if item['kind']=='configuration':need(a==0,'Configuration owns data uop')
    @staticmethod
    def gap(previous,point,old):
        if previous is not None:
            n=int(point['cycle'])-int(previous['cycle'])
            if old is None or n>old['cycles']:return dict(cycles=n,from_event=previous,to_event=point)
        return old
    def consume(self,row):
        self.current_row=dict(row);s=self.state;calls=len(s.calls);offloads=len(s.offloads)
        s.consume(row)
        if len(s.offloads)>offloads:self.bind(s.offloads[-1])
        if len(s.calls)>calls and calls:self.check_owners(calls-1);self.closed_calls=calls
        cycle=int(row['cycle']);event=row['event']
        point={k:row[k] for k in ('cycle','event','order','pc','insn')};point['call_entered']=len(s.calls)
        self.max_event=self.gap(self.last,point,self.max_event);self.last=point
        self.bins.setdefault(cycle//1000000,Counter())[event]+=1
        if event in ('retire','cvx_req','cvx_resp','uop_alloc','uop_done'):
            self.max_progress=self.gap(self.last_progress,point,self.max_progress);self.last_progress=point
        if event=='cvx_req':self.pending_cvx[int(row['trans_id'])]=point
        elif event=='cvx_resp':self.pending_cvx.pop(int(row['trans_id']))
        elif event=='uop_alloc':self.pending_uop[int(row['port'])]=point
        elif event=='uop_done':
            begin=self.pending_uop.pop(int(row['port']));n=cycle-int(begin['cycle'])
            if self.max_owner is None or n>self.max_owner['cycles']:self.max_owner=dict(cycles=n,alloc=begin,done=point)
        elif event=='retire':
            self.max_retire=self.gap(self.last_retire,point,self.max_retire);self.last_retire=point
            if int(row['mem_wmask'],16):
                address=int(row['mem_addr'],16)
                for name in ('checks','elements','errors'):
                    if address==s.s[name]:self.counter_writes[name]=dict(point,value=int(row['mem_wdata'],16))
    def partial(self):
        s,o=self.state,self.observer
        need(s.rows>0 and o.count['rows']==o.count['unmodified_delivered_rows']==s.rows
             and o.before.digest()==o.after.digest(),'All raw rows delivered unchanged')
        need(o.count['retire']==s.retired and o.last==s.cycle,'Strict/generic count mismatch')
        complete_data=sum(c['reads']==set(range(129)) and c['returned_vstart']==0 for c in s.calls)
        if s.active and s.helper is None and s.active['reads']==set(range(129)) and s.active['returned_vstart']==0:
            s.finish_call() # exact IDs/gold/full oracle, NOT full4095 finish
            self.check_owners(s.active['ordinal']);self.closed_calls=len(s.calls)
        ri=qi=0
        while ri<len(o.retvec) and qi<len(o.requests):
            if o.retvec[ri]==o.requests[qi]:ri+=1;qi+=1
            elif protocol._is_transport_replay(o.requests[qi],o.requests[qi-1] if qi else None):qi+=1
            else:raise ValueError('Retired/request prefix ordering mismatch')
        need(ri==len(o.retvec),'Retired offload lacks accepted request')
        replay=protocol._validate_retired_request_sequence(o.retvec,o.requests[:qi])
        ai=aq=0
        while ai<len(o.arch) and aq<len(o.requests):
            if o.arch[ai]==o.requests[aq]:ai+=1;aq+=1
            elif protocol._is_transport_replay(o.requests[aq],o.requests[aq-1] if aq else None):aq+=1
            else:raise ValueError('Architecture/request prefix ordering mismatch')
        protocol._validate_retired_request_sequence(o.arch[:ai],o.requests[:aq])
        counters={n:s.value(s.s[n],8) if all(s.s[n]+i in s.memory for i in range(8)) else None for n in ('checks','elements','errors')}
        active=None
        if s.active:
            active={k:v for k,v in s.active.items() if k!='reads'}
            active['oracle_reads_seen']=len(s.active['reads'])
            active['oracle_reads_missing_first8']=sorted(set(range(129))-s.active['reads'])[:8]
        nextcall={k:v for k,v in s.gold[len(s.calls)].items() if k in ('ordinal','seed','op','li','mode','si','vl','vstart')} if len(s.calls)<4095 else None
        if nextcall is not None:nextcall['original_ordinal']=nextcall['ordinal']+1
        return dict(status='DIAGNOSTIC_ONLY_PARTIAL_EOF_NOT_PASS',architectural_acceptance=False,
            full4095_finish_called=False,whole4095_accepted=False,
            rows=s.rows,retired=s.retired,last_cycle=s.cycle,lastvalidrecord=self.last,last_retire=self.last_retire,
            last_watchdog_progress=self.last_progress,observed_tail_since_progress_cycles=s.cycle-int(self.last_progress['cycle']) if self.last_progress else None,
            completed_calls_with_data_and_owners=self.closed_calls,calls_entered=len(s.calls),
            calls_with_all129_reads_and_vstart0=complete_data,active_call=active,next_call=nextcall,
            active_phase=dict(helper=s.helper,next_helper_index=s.index,output_initializer_index=s.init_index,
                mask_store_index=s.mask_index,seed_store_index=s.seed_index,body_entered=s.body_entered,source_exited=s.exited),
            source_counters=counters,last_counter_writes=self.counter_writes,
            fresh_bytes={k:len(v) for k,v in s.fresh.items()},helper_instruction_counts=s.counts,
            packed_reads=sum(len(c['reads']) for c in s.calls),
            generic=dict(counts=dict(o.count),pending_cvx=o.pending,pending_uop=o.uops,
                pending_cvx_progress=self.pending_cvx,pending_uop_progress=self.pending_uop,
                unmatched_arch=small(o.arch[ai:]),unmatched_arch_requests=small(o.requests[aq:]),
                unretired_accepted_requests=small(o.requests[qi:]),matched_retired_requests=ri,
                matched_prefix_replays=replay,before_sha256=o.before.hexdigest(),after_sha256=o.after.hexdigest(),
                required_retired_owner_count=sum(x['required'] for x in self.bound)),
            max_event_gap=self.max_event,max_retire_gap=self.max_retire,max_watchdog_progress_gap=self.max_progress,
            max_observed_completed_owner_lifetime=self.max_owner,million_cycle_bins={str(k):dict(v) for k,v in self.bins.items()},
            final_simulator_cycle_known=False,diagnosis='ONLY_RECORDED_PREFIX_OBSERVED_NOT_A_POST_TRACE_STALL_PROOF')
class StreamState:
    def __init__(self):
        self.hash=hashlib.sha256();self.bytes=0;self.line=0;self.raw_preview=None;self.attempted=None
    def lines(self,stream):
        for raw in stream:
            self.hash.update(raw);self.bytes+=len(raw);self.line+=1;self.raw_preview=repr(raw[:192]);self.attempted=None
            need(raw.endswith(b'\n'),'Truncated final CSV row; not swallowed as EOF')
            need(raw.count(b',')==len(FIELDS)-1 and b'"' not in raw,'Exact frozen unquoted14-field CSV record')
            yield raw.decode('ascii')
class ContextReader:
    def __init__(self,reader,state):self.reader=reader;self.state=state;self.fieldnames=reader.fieldnames
    def __iter__(self):
        for row in self.reader:
            self.state.attempted=dict(row);yield row
def execute():
    out=HERE/'run01';out.mkdir();t=time.monotonic();prefix=None;streamstate=StreamState();before=None
    try:
        entry=read(HERE/'ENTRY.json')
        for p,h in entry['pins'].items():need(sha(p)==h,'Entry consumed pin drift '+p)
        spec,pins=inputs();before=stat(TRACE);need(before['size']==296607084,'Exact closed original CSV size')
        save(out/'inputs.json',dict(pins=pins,entry_sha256=sha(HERE/'ENTRY.json'),csv_before=before,semantic_passes=1,limit_s=600))
        prefix=Prefix(spec)
        with TRACE.open('rb') as stream: # the only captured CSV open
            reader=ContextReader(csv.DictReader(streamstate.lines(stream),strict=True),streamstate)
            for row in prefix.observer.rows(reader):
                if prefix.state.rows%4096==0:need(not aborted and time.monotonic()-t<595,'Abort/fixed diagnostic deadline')
                prefix.consume(row)
        result=prefix.partial();after=stat(TRACE)
        need(streamstate.bytes==before['size'] and after==before,'Closed CSV stat/byte drift')
        for p,h in pins.items():need(sha(p)==h,'Consumed post-pin drift '+p)
        need(not aborted and time.monotonic()-t<600,'Late abort/deadline')
        result.update(csv_before=before,csv_after=after,csv_sha256=streamstate.hash.hexdigest(),csv_bytes=streamstate.bytes,
            semantic_passes=1,raw_hash_computed_in_same_pass=True,pins_unchanged=True,
            elapsed_s=time.monotonic()-t,current_worktree_runner_consumed=False,original_timeout_preserved=True)
        save(out/'result.json',result);return 0
    except BaseException as error:
        row=streamstate.attempted or (prefix.current_row if prefix else None)
        save(out/'firstcause.json',dict(status='DIAGNOSTIC_STOPPED_NOT_ACCEPTED',cause=type(error).__name__+': '+str(error),
            row=row,physical_line=streamstate.line,raw_record_preview=streamstate.raw_preview,
            original_call=prefix.state.active['original_ordinal'] if prefix and prefix.state.active else None,
            lastvalidrecord=prefix.last if prefix else None,rows=prefix.state.rows if prefix else 0,
            bytes_hashed=streamstate.bytes,sha256_of_only_bytes_read=streamstate.hash.hexdigest(),
            csv_before=before,csv_after=stat(TRACE) if before is not None else None,
            elapsed_s=time.monotonic()-t,original_timeout_preserved=True,no_retry=True))
        return 1
if __name__=='__main__':
    def stop(signum,frame):
        global aborted
        aborted=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    raise SystemExit(execute())

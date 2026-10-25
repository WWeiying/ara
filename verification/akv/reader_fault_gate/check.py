"""Strict successor transcript and independent AXI ledger from settled wave rows.

This is not a standalone acceptance runner: actual unfiltered ara_verify.uvm_dut
and source/image/export provenance checks remain mandatory before overall PASS.
"""
import csv
from collections import deque
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'reader_handoff'))
import check_reader_handoff_v2 as old
require=old.require
INJECTOR='READER_FAULT_INJECTOR_PASS target_ar=1 younger_ar=1 errors=1 held_min=2 empty_hold=6'


def check_log(text,rtl,target):
    require(type(target) is int and target>0 and target%64==0 and target%4096<=4096-288,
            'Invalid ELF-bound target or page split')
    wanted=[s.replace('READER_HANDOFF_','READER_DRAIN_').replace('tval=0 qbs_words','tval=weight_base qbs_words')
            for s in old.markers()]
    software=[]; rows=[]; counts=dict(qbs=0,akv=0); severity=set()
    target_seen=begun=passed=terminal=injector=False
    for line in text.splitlines():
        require(not re.search(r'Fatal:|Error(?:-|:)|\b(?:FAIL|FAILED|TIMEOUT|SKIP)\b|READER_FAULT_ERROR',line,re.I),
                'Failure text')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            match=re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0',line)
            require(match is not None and match[1] not in severity,'UVM failure/duplicate')
            severity.add(match[1])
        if 'READER_FAULT_' in line:
            if line==f'READER_FAULT_TARGET address={target:x} ordinal=2 response=2':
                require(not target_seen and not begun and not rows,'Late/duplicate target')
                target_seen=True
            elif line==INJECTOR:
                require(passed and not injector,'Premature/duplicate injector final')
                injector=True
            else:
                raise ValueError('Unknown/malformed injection record')
        if 'READER_DRAIN_' in line or 'READER_HANDOFF_' in line:
            require(not terminal and len(software)<len(wanted) and line==wanted[len(software)],
                    'Program sequence/schema mismatch')
            software.append(line)
            if line==wanted[0]:
                require(target_seen and not rows and not begun,'Begin ordering')
                begun=True
            if line==wanted[-1]:
                require(len(rows)==71 and not passed,'Premature PASS')
                passed=True
        if ('QBS_PERF' in line or 'AKV_PERF' in line) and not line.startswith('Command:'):
            require(line.startswith(('[QBS_PERF] ','[AKV_PERF] ')),'Malformed metric')
            require(begun and not passed and not terminal and len(rows)<71,'Metric ordering')
            owner='qbs' if line.startswith('[QBS_PERF] ') else 'akv'
            counts[owner]+=1
            row=old.numeric_fields(line.split('] ',1)[1],old.schema(rtl) if owner=='qbs' else old.PERF_FIELDS)
            expected_owner,cmd=old.sequence()[len(rows)]
            require(owner==expected_owner and row['seq']==counts[owner] and row['busy_cycles']>0 and
                    row['read_outstanding_max']<=2,'Owner/sequence/outstanding')
            if owner=='qbs':
                fault=int(cmd==1); reuse=int(cmd>=4)
                require(tuple(row[k] for k in ('m','n','vlen','lanes','success','fault','validation_fault',
                        'read_fault','commit_groups','activation_access'))==
                        (1,3,1024,4,1-fault,fault,0,3*fault,4*(1-fault),(0,0,0,1,2,3)[cmd]),
                        'QBS geometry/atomicity/AXI fault')
                require(row['context_fill_count']==int(cmd==3) and row['context_reuse_count']==reuse and
                        row['context_reuse_block_count']==reuse and row['context_read_bytes']==292*reuse and
                        row['activation_axi_bytes_saved']==292*reuse,'Resident QBS work')
                if not fault:
                    require(row['useful_pairs']==768 and row['weight_bytes']==432,'Arithmetic work')
                else:
                    require(row['ar']>=4 and row['r_beats']>=row['ar'],'Fault never read real payload')
            else:
                require(row['command']==cmd and row['success']==1 and
                        row['fault']==row['validation_fault']==row['read_fault']==0 and
                        row['context_ready']==int(cmd!=3) and row['v2_bank_conflict_cycles']==0,'AKV status')
                require(row['q_external_bytes']==(256 if cmd==4 else 0) and
                        row['kv_external_bytes']==(768 if cmd==4 else 0) and
                        row['replay_bytes']==(128 if cmd==2 else 0) and
                        row['read_ranges']==(9 if cmd==4 else 0),'AKV bytes/ranges')
                require(row['v2_full']==int(cmd==4) and row['load']==int(cmd==2) and
                        row['v2_row_load']==int(cmd==2) and row['release']==int(cmd==3) and
                        row['v2_column_load']==0,'AKV commands')
                if cmd!=4:
                    require(row['ar']==row['r_beats']==0,'Resident command used memory')
                else:
                    require(row['ar']>=9 and row['r_beats']>=row['ar'] and
                            row['read_payload_bytes']==1088,'Missing FULL work')
            rows.append(row)
        if 'Core Test' in line:
            require(line==old.TERMINAL and passed and not terminal,'Core terminal')
            terminal=True
    require(software==wanted and terminal and injector and counts==dict(qbs=6,akv=65) and
            severity=={'UVM_ERROR','UVM_FATAL'},'Incomplete fixture')
    return dict(state='LOG_CHECKED_NOT_OVERALL_ACCEPTANCE',commands=71,qbs=6,akv=65,
                records=rows,read_fault=3,trap_cause=5,trap_tval=target,resident_rows=62)


def check_rows(rows,target):
    """Rows contain integers sampled at consecutive settled negedges, 1ns clock.

    The ledger advances on the NEXT posedge handshake represented by each row.
    No DUT queue entry or shim ledger is used as the expected transaction stream.
    """
    queue=deque(); bus_queue=deque(); cut_requests=deque(); cut_returns=deque()
    last_time=None; tracking=False; done=False
    target_ars=younger_ars=errors=drained_beats=held=empty_hold=0
    reader_faults=terminals=0; got_last=False; await_other=False
    context=None; previous=None; after_terminal=False
    ar_held=None; r_held=None; cut_held=0; drain_samples=0; sample_count=0; other_fire=False
    up_ars=up_beats=bus_ars=bus_beats=0
    def context_id(r):
        names=('ready_q','q_rows_q','head_dim_q','kv_length_q','q_base_q','k_base_q',
               'v_base_q','tile_count_q','v2_q')
        return tuple(r['akv_context_'+n] for n in names)
    for r in rows:
        if done: break
        if not tracking:
            if not (r['qbs_active_q']==1 and r['shim_ordinal_q']==2):
                continue
            require(r['reset_n']==1 and r['r_burst_fifo_count_q']==0,'Window omitted command start')
            tracking=True; context=context_id(r)
            require(context[0]==1,'Other owner context absent')
        require(last_time is None or r['time_100fs']-last_time==10000,'Missing settled cycle')
        last_time=r['time_100fs']
        sample_count+=1
        require(sample_count<=4096,'Scenario cycle bound')
        require(r['reset_n']==1,'Reset during scenario')
        controls=('qbs_command_fire','akv_command_fire','qbs_fault_valid','akv_fault_valid',
                  'r_fault_valid_o','r_fault_ready_i','r_fault_pending_q','r_response_drain_q',
                  'r_data_valid_o','r_completion_valid_q')
        require(all(r[k] in (0,1) for k in controls) and all(
            r[p+'_'+k] in (0,1) for p in ('up','down','bus')
            for k in ('ar_valid','ar_ready','r_valid','r_ready')),'Invalid handshake/control value')
        require(0<=r['shim_state_q']<=6 and r['r_burst_fifo_count_q']==len(queue)<=2,
                'Reader metadata differs from independent accepted ledger')
        # Inspect pre-handshake state: an older completion may still be valid
        # on the first error beat. Thereafter require quiescence even without R.
        quiet=(r['r_fault_pending_q'] or r['r_response_drain_q'] or
               (errors>0 and not other_fire))
        if quiet:
            require(r['r_data_valid_o']==r['r_completion_valid_q']==0,
                    'Fault drain published payload/completion between handshakes')
        require(context_id(r)==context,'Other owner context corrupted across fault')
        owner=r['qbs_active_q']+2*r['akv_active_q']
        require(owner in (0,1,2),'Invalid owner')
        if not await_other:
            require(owner==1,'Premature owner release')
        else:
            require(owner in (0,2) and r['qbs_command_fire']==0,'Wrong next owner')
        if after_terminal:
            require(owner!=1,'Owner persisted after terminal')
            after_terminal=False
        if await_other and r['akv_command_fire']:
            require(owner==0 and r['normal_vlsu_idle']==1 and r['akv_context_write_busy']==0,
                    'Unsafe other-owner admission')
            require(not queue and not bus_queue and all(r['r_'+n]==0 for n in
                    ('burst_fifo_count_q','ar_stalled_q','range_fifo_count_q','plan_state_q',
                     'completion_valid_q','fault_pending_q','busy_o')),'Reader not drained at admission')
            require(all(r[f'cut_{ch}_{slot}_full_q']==0 for ch in ('ar','r','aw','w','b')
                        for slot in ('a','b')),'Cut not drained at admission')
            require(not other_fire,'Repeated other-owner fire')
            other_fire=True
        if await_other and r['akv_terminal']:
            require(owner==2 and other_fire and r['akv_fault_valid']==0,'Other owner failed recovery')
            done=True
        for key in ('qbs_active_q','akv_active_q','qbs_terminal','akv_terminal','r_ar_stalled_q'):
            require(r[key] in (0,1),'Invalid boolean')
        up_ar=r['up_ar_valid'] and r['up_ar_ready']
        down_ar=r['down_ar_valid'] and r['down_ar_ready']
        up_r=r['up_r_valid'] and r['up_r_ready']
        down_r=r['down_r_valid'] and r['down_r_ready']
        require(up_ar==down_ar and up_r==down_r,'Split handshake across interposer')
        if ar_held is not None:
            require(r['up_ar_valid']==1 and r['up_ar']==ar_held,'Held AR withdrawn/changed')
        ar_held=r['up_ar'] if r['up_ar_valid'] and not r['up_ar_ready'] else None
        rp=tuple(r['up_r_'+n] for n in ('data','id','last','resp','user')) if r['up_r_valid'] else None
        if r_held is not None:
            require(r['up_r_valid']==1 and rp==r_held,'Held R changed')
        r_held=rp if r['up_r_valid'] and not r['up_r_ready'] else None
        if r['bus_ar_valid'] and not r['bus_ar_ready']: cut_held+=1
        if r['r_ar_stalled_q']:
            require(r['up_ar_valid']==1 and r['up_ar_ready']==0 or
                    (r['up_ar_valid']==1 and r['shim_state_q']==5),'Reader-held mismatch')
            held+=1
        if up_ar:
            up_ars+=1
            require(r['up_ar']==r['down_ar'],'AR payload modification')
            item=[r['up_ar_addr'],r['up_ar_id'],r['up_ar_len']+1,r['up_ar_size']]
            require(len(queue)<2,'Too many reader accepts')
            queue.append(item)
            cut_requests.append(r['up_ar'])
            if item[0]==target:
                target_ars+=1
                require(item[2:]==[9,4],'Target burst geometry')
            if item[0]==target+144:
                younger_ars+=1
                require(got_last and empty_hold>=6,'Held younger AR accepted too early')
        if r['bus_ar_valid'] and r['bus_ar_ready']:
            bus_ars+=1
            require(cut_requests and r['bus_ar']==cut_requests.popleft(),'Cut AR lacks matching reader acceptance')
            bus_queue.append([r['bus_ar_id'],r['bus_ar_len']+1])
        if r['bus_r_valid'] and r['bus_r_ready']:
            bus_beats+=1
            require(bus_queue and r['bus_r_id']==bus_queue[0][0] and
                    r['bus_r_last']==int(bus_queue[0][1]==1) and r['bus_r_resp']==0,
                    'Memory response not backed by actual bus AR')
            bus_queue[0][1]-=1
            if not bus_queue[0][1]: bus_queue.popleft()
            cut_returns.append(tuple(r['bus_r_'+f] for f in ('data','id','last','resp','user')))
        if up_r:
            up_beats+=1
            require(queue and r['up_r_id']==queue[0][1] and
                    r['up_r_last']==int(queue[0][2]==1),'Unissued response/RLAST/RID')
            require(all(r['up_r_'+f]==r['down_r_'+f] for f in ('data','id','last','user')) and
                    r['down_r_resp']==0,'Response data/identity changed')
            require(cut_returns and cut_returns.popleft()==
                    tuple(r['down_r_'+f] for f in ('data','id','last','resp','user')),
                    'Cut response lacks actual memory beat')
            if r['up_r_resp']!=0:
                require(r['up_r_resp']==2 and queue[0][0]==target and queue[0][2]==9 and
                        held>=2 and r['r_ar_stalled_q']==1 and r['r_burst_fifo_count_q']==1 and
                        r['shim_state_q']==2,'Error not at real reader-held older burst')
                errors+=1
                require(errors==1,'Repeated injected error')
            if errors:
                drained_beats+=1
                require(r['r_data_valid_o']==0,'Fault drain published payload on error/drain beat')
            if queue[0][0]==target and r['up_r_last']:
                got_last=True
            queue[0][2]-=1
            if not queue[0][2]: queue.popleft()
        if r['shim_state_q']==4:
            require(not queue and got_last and r['r_burst_fifo_count_q']==0 and
                    r['r_ar_stalled_q']==r['r_fault_pending_q']==1 and
                    r['r_fault_valid_o']==r['qbs_terminal']==0,'Fault escaped held-AR gap')
            empty_hold+=1
        if r['r_response_drain_q']:
            require(errors==1 and r['shim_state_q']==3,'Unexpected response-drain interval')
            drain_samples+=1
        if errors and not await_other and previous is not None and not r['qbs_terminal']:
            require(owner==1,'Fault lost ownership')
        if r['r_fault_valid_o']:
            require(not queue and not bus_queue and not cut_requests and not cut_returns and r['r_ar_stalled_q']==0 and
                    r['r_burst_fifo_count_q']==0 and r['r_fault_kind_o']==3 and
                    r['r_fault_vaddr_o']==target and younger_ars==1,'Premature/wrong reader fault')
            if r['r_fault_ready_i']: reader_faults+=1
        if r['qbs_terminal']:
            require(errors==1 and reader_faults==1 and not queue and not bus_queue and
                    r['qbs_fault_valid']==1 and r['r_busy_o']==0,'Bad engine fault terminal')
            terminals+=1; await_other=True; after_terminal=True
        previous=r
    require(done and target_ars==younger_ars==errors==reader_faults==terminals==1 and
            held>=2 and empty_hold==6 and drained_beats==18 and drain_samples>0,
            'Incomplete discriminating scenario')
    require(up_ars==bus_ars and up_beats==bus_beats,'Reader/bus traffic mismatch')
    return dict(state='WAVE_CHECKED_NOT_OVERALL_ACCEPTANCE',reader_held_samples=held,
                cut_held_samples=cut_held,empty_outstanding_held_ar_samples=empty_hold,
                injected_beats=1,drained_beats=18,response_drain_samples=drain_samples,
                reader_faults=1,other_owner_recovered=True,
                reader_ar=up_ars,reader_r_beats=up_beats,bus_ar=bus_ars,bus_r_beats=bus_beats)


def check_cycles(path,target):
    def rows():
        with Path(path).open(newline='') as handle:
            reader=csv.DictReader(handle)
            for raw in reader:
                # Unknown invalid payload is legal; only accessed valid fields must be integers.
                class Sample(dict):
                    def __getitem__(self,key):
                        value=super().__getitem__(key)
                        require(value is not None and re.fullmatch(r'[0-9a-fA-F]+',value) is not None,
                                'Missing/unknown required sample: '+key)
                        return int(value,10 if key=='time_100fs' else 16)
                yield Sample(raw)
    return check_rows(rows(),target)


def check_log_and_cycles(text,rtl,path,target):
    log=check_log(text,rtl,target)
    wave=check_cycles(path,target)
    faults=[r for r in log['records'] if r['fault']]
    require(len(faults)==1 and faults[0]['ar']==wave['reader_ar'] and
            faults[0]['r_beats']==wave['reader_r_beats'],'PERF/wave fault traffic disagreement')
    return dict(state='LOG_AND_WAVE_CHECKED_NOT_OVERALL_ACCEPTANCE',log=log,wave=wave)

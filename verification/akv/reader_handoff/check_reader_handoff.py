"""Strict synthetic owner-transfer transcript and settled-wave checks."""
import csv
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0,str(HERE.parent/'quantized_kv'))
from check_batch_qk import schema, TERMINAL
from check_rvv_qbs import require
sys.path.insert(0,str(HERE.parent))
from run_refill_overlap_probe import numeric_fields, PERF_FIELDS
from wave_profile import profile

BEGIN = 'READER_HANDOFF_BEGIN synthetic=1 lanes=4 vlen=1024 qbs_m=1 n=3 kb=1 akv_d=64 context_test=1'
PASS = ('READER_HANDOFF_PASS qbs=6 akv=65 traps=1 cause=5 tval=0 qbs_words=192 '
        'akv_rows=62 context_test=1 performance=not_measured')


def sequence():
    result = [('akv',4)] + [('akv',2)]*8
    for stage in range(6):
        result += [('qbs',stage),('akv',2)]
        if stage == 3:
            result += [('akv',4)]
        result += [('akv',2)]*8
    return result+[('akv',3)]


def markers():
    result = [BEGIN,'READER_HANDOFF_RESIDENT stage=0 epoch=0 rows=8 bytes=1024 external_poison=1']
    for stage,access in enumerate((0,0,0,1,2,3)):
        epoch = int(stage>=4)
        result.append(f'READER_HANDOFF_PAIR stage={stage} access={access} fault={int(stage==1)} '
                      'qbs_words=32 akv_row=1 scratch_preserved=1')
        if stage != 3:
            resident = stage+1
            result.append(f'READER_HANDOFF_RESIDENT stage={resident} epoch={epoch} '
                          'rows=8 bytes=1024 external_poison=1')
        else:
            result.append('READER_HANDOFF_RESIDENT stage=4 epoch=1 rows=8 bytes=1024 external_poison=1')
    return result+[PASS]


def check_log(text,rtl):
    observed, records, software, severity = [], [], [], set()
    counts = {'qbs':0,'akv':0}
    declared = passed = terminal = False
    expected = sequence()
    for line in text.splitlines():
        require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT|SKIP)\b',line,re.I), 'Failure or skipped fixture')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            match = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0',line)
            require(match is not None and match[1] not in severity, 'UVM failure/duplicate')
            severity.add(match[1])
        if 'READER_HANDOFF_' in line:
            require(not terminal,'Program record after terminal')
            software.append(line)
            if line == BEGIN:
                require(not declared and not records,'Duplicate/late begin')
                declared=True
            elif line == PASS:
                require(declared and not passed and len(records)==71,'Premature/duplicate PASS')
                passed=True
        if ('QBS_PERF' in line or 'AKV_PERF' in line) and not line.startswith('Command:'):
            require(line.startswith(('[QBS_PERF] ','[AKV_PERF] ')), 'Malformed/unknown hardware metric')
        if line.startswith(('[QBS_PERF] ','[AKV_PERF] ')):
            require(declared and not passed and not terminal and len(records)<71,'Unexpected command')
            owner = 'qbs' if line.startswith('[QBS_PERF] ') else 'akv'
            counts[owner]+=1
            row = numeric_fields(line.split('] ',1)[1],schema(rtl) if owner=='qbs' else PERF_FIELDS)
            wanted_owner, command = expected[len(records)]
            require(owner==wanted_owner and row['seq']==counts[owner] and row['read_outstanding_max']<=2 and
                    row['busy_cycles']>0,
                    'Wrong owner order, command sequence or capacity')
            if owner=='qbs':
                fault = int(command==1)
                require((row['m'],row['n'],row['success'],row['fault'],row['validation_fault'])==
                        (1,3,1-fault,fault,0), 'QBS shape/result fault contract')
                require(row['activation_access']==(0,0,0,1,2,3)[command] and
                        row['commit_groups']==1-fault, 'QBS context/atomic commit mismatch')
                require(row['read_fault']==(5 if fault else 0), 'Need the specified PMA reader fault')
                if not fault:
                    require(row['useful_pairs']==768 and row['weight_bytes']==432, 'QBS arithmetic work mismatch')
            else:
                require(row['command']==command and row['success']==1 and row['fault']==0 and
                        row['validation_fault']==0 and row['read_fault']==0 and
                        row['context_ready']==int(command!=3) and row['v2_bank_conflict_cycles']==0,
                        'AKV command/context/fault mismatch')
                require(row['q_external_bytes']==(256 if command==4 else 0) and
                        row['kv_external_bytes']==(768 if command==4 else 0) and
                        row['replay_bytes']==(128 if command==2 else 0) and
                        row['read_ranges']==(9 if command==4 else 0), 'AKV external/resident work mismatch')
                require(row['v2_full']==int(command==4) and row['load']==int(command==2) and
                        row['v2_row_load']==int(command==2) and row['release']==int(command==3) and
                        row['v2_column_load']==0, 'AKV operation flags differ')
                if command!=4:
                    require(row['ar']==row['r_beats']==0, 'Resident load unexpectedly read external memory')
                else:
                    require(row['ar']>=9 and row['r_beats']>=row['ar'] and
                            row['read_payload_bytes']==1088 and row['read_outstanding_max']>0,
                            'Missing real FULL traffic')
            observed.append(owner)
            records.append(row)
        if 'Core Test' in line:
            require(line==TERMINAL and passed and not terminal,'Bad core terminal')
            terminal=True
    require(software==markers() and passed and terminal and counts==dict(qbs=6,akv=65) and
            severity=={'UVM_ERROR','UVM_FATAL'}, 'Incomplete transcript')
    return dict(state='READER_HANDOFF_LOG_CHECKED',commands=71,qbs=6,akv=65,
                hardware_records=records,reader_faults=1,validation_faults=0,
                resident_rows_self_checked=62,performance=False,whole_model=False)


def check_cycles(path):
    required = {item['alias'] for item in profile()['signals']}
    fires, terminals = [],[]
    counts = {'qbs':0,'akv':0}
    pending = None
    rows=0
    contexts = {}
    fault_seen=0
    read_faults=[]
    captures = {'qbs':0,'akv':0}
    after_terminal=False
    started=False
    with Path(path).open(newline='') as handle:
        reader=csv.DictReader(handle)
        require(required<=set(reader.fieldnames or []),'Missing required wave signals')
        previous_time=-1
        for raw in reader:
            rows+=1
            def value(name):
                text=raw[name].strip()
                require(re.fullmatch(r'[0-9a-fA-F]+',text) is not None,'Unknown required control: '+name)
                return int(text,16)
            time=int(raw['time_100fs'])
            require(time>previous_time,'Wave sampling times not strictly increasing')
            if started:
                require(time-previous_time==10000,'Missing settled sample in command interval')
            previous_time=time
            if value('reset_n')==0:
                require(not started,'Reset interrupts owner-transfer evidence')
                continue
            require(value('reset_n')==1,'Invalid reset level')
            active=[owner for owner in counts if value(owner+'_active_q')]
            require(len(active)<=1,'Simultaneous special owners')
            if after_terminal:
                require(not active,'Owner did not leave after terminal')
                after_terminal=False
            elif pending is not None:
                require(active==[pending],'Owner changed/disappeared before terminal')
            else:
                require(not active,'Owner became active without a captured acquisition')

            def identity(client):
                prefix='akv_context_' if client=='akv' else 'activation_context_'
                valid=value(prefix+('ready_q' if client=='akv' else 'valid_q'))
                require(valid in (0,1),'Invalid resident valid bit')
                if not valid:
                    return (0,)
                fields=(('q_rows_q','head_dim_q','kv_length_q','q_base_q','k_base_q','v_base_q',
                         'tile_count_q','v2_q') if client=='akv' else
                        ('id_q','generation_q','profile_q','layout_q','m_q','k_blocks_q'))
                return (1,*(value(prefix+field) for field in fields))

            # Check from the original owner's completed terminal snapshot,
            # including idle/acquisition and the other owner's first cycle.
            for client,checkpoint in contexts.items():
                if active!=[client]:
                    require(identity(client)==checkpoint,'Resident context changed outside its owner')
                    if active and checkpoint[0]:
                        captures[client]+=1
            for owner in counts:
                require(value(owner+'_counters_clear_i')==value(owner+'_command_fire'),
                        'Reader counter/subrequest reset not aligned with command acceptance')
                require(value(owner+'_range_fifo_count_q')<=2 and value(owner+'_burst_fifo_count_q')<=2,
                        'Reader capacity increased')
                if value(owner+'_command_fire'):
                    require(not active and pending is None and value('normal_vlsu_idle')==1 and
                            value('prepare_inflight')==0 and value('ar_hold_empty')==1,'Unsafe command acquisition')
                    for client in counts:
                        for field in ('range_fifo_count_q','burst_fifo_count_q','plan_state_q','ar_stalled_q',
                                      'completion_valid_q','fault_pending_q','busy_o','mmu_req_o','axi_ar_valid_o'):
                            require(value(client+'_'+field)==0,'Reader not drained at acquisition: '+client+'_'+field)
                    require(value('akv_context_write_busy')==0,'AKV writes not drained at acquisition')
                    for channel in ('ar','r','aw','w','b'):
                        for slot in ('a_full_q','b_full_q'):
                            require(value('cut_'+channel+'_'+slot)==0,'Registered AXI cut not drained')
                    require(len(fires)<71 and owner==sequence()[len(fires)][0],'Unexpected fire owner/order')
                    fires.append(dict(owner=owner,time_100fs=time))
                    pending=owner
                    counts[owner]+=1
                    started=True
                if value(owner+'_fault_valid_o'):
                    require(owner=='qbs' and active==['qbs'] and counts['qbs']==2 and
                            value('qbs_fault_kind_o')==5 and value('qbs_fault_vaddr_o')==0 and
                            value('qbs_burst_fifo_count_q')==0 and value('qbs_ar_stalled_q')==0,
                            'Unexpected reader fault or premature fault publication')
                    if value(owner+'_fault_ready_i'):
                        read_faults.append(dict(owner=owner,kind=5,vaddr=0,time_100fs=time))
                        require(len(read_faults)==1,'Duplicate reader fault handshake')
                if value(owner+'_terminal'):
                    require(active==[owner] and pending==owner,'Terminal without matched owner')
                    require(value(owner+'_busy_o')==0 and value(owner+'_ar_stalled_q')==0,
                            'Reader still busy at terminal')
                    if owner=='qbs':
                        fault_seen+=value('qbs_fault_valid')
                        require(value('qbs_fault_valid')==int(counts['qbs']==2), 'Wrong fault terminal ordinal')
                        if value('qbs_fault_valid'):
                            require(len(read_faults)==1,'Fault terminal lacks matched reader fault')
                    else:
                        require(value('akv_fault_valid')==0,'Unexpected AKV fault terminal')
                    require(value('akv_context_write_busy')==0,'AKV writes still busy at terminal')
                    terminals.append(dict(owner=owner,time_100fs=time))
                    contexts[owner]=identity(owner)
                    pending=None
                    after_terminal=True
    require(counts==dict(qbs=6,akv=65) and len(terminals)==71 and pending is None and not after_terminal and fault_seen==1 and
            len(read_faults)==1,
            'Wave omits expected commands or fault terminal')
    require(captures['qbs']>0 and captures['akv']>0,'Missing live-context cross-owner observations')
    return dict(state='READER_HANDOFF_SETTLED_WAVE_CHECKED',rows=rows,fires=fires,terminals=terminals,
                resident_samples=captures,fault_terminals=1,reader_fault_handshakes=read_faults,
                sampling='Settled negedge levels; not pre-NBA posedge monitor equivalence',
                stalled_ar_fault_exercised=False,physical_sharing_implemented=False)

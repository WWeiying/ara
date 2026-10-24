"""Correct the legacy-register commit-word contract without changing old evidence."""
import re

from check_reader_handoff import (BEGIN, PASS, PERF_FIELDS, TERMINAL, markers,
                                 numeric_fields, require, schema, sequence, check_cycles)


def check_log(text,rtl):
    records,software,severity=[],[],set()
    counts={'qbs':0,'akv':0}
    declared=passed=terminal=False
    expected=sequence()
    for line in text.splitlines():
        require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT|SKIP)\b',line,re.I),'Failure or skipped fixture')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            match=re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0',line)
            require(match is not None and match[1] not in severity,'UVM failure/duplicate')
            severity.add(match[1])
        if 'READER_HANDOFF_' in line:
            require(not terminal,'Program record after terminal')
            software.append(line)
            if line==BEGIN:
                require(not declared and not records,'Duplicate/late begin')
                declared=True
            elif line==PASS:
                require(declared and not passed and len(records)==71,'Premature/duplicate PASS')
                passed=True
        if ('QBS_PERF' in line or 'AKV_PERF' in line) and not line.startswith('Command:'):
            require(line.startswith(('[QBS_PERF] ','[AKV_PERF] ')),'Malformed/unknown hardware metric')
        if line.startswith(('[QBS_PERF] ','[AKV_PERF] ')):
            require(declared and not passed and not terminal and len(records)<71,'Unexpected command')
            owner='qbs' if line.startswith('[QBS_PERF] ') else 'akv'
            counts[owner]+=1
            row=numeric_fields(line.split('] ',1)[1],schema(rtl) if owner=='qbs' else PERF_FIELDS)
            wanted_owner,command=expected[len(records)]
            require(owner==wanted_owner and row['seq']==counts[owner] and row['read_outstanding_max']<=2 and
                    row['busy_cycles']>0,'Wrong owner order, sequence or capacity')
            if owner=='qbs':
                fault=int(command==1)
                require((row['m'],row['n'],row['vlen'],row['lanes'],row['success'],row['fault'],row['validation_fault'])==
                        (1,3,1024,4,1-fault,fault,0),'QBS shape/result fault contract')
                # Legacy M1 writes all 1024 bits, including zeroed tails.
                # Each completed aggregate word is 4 lanes * 64 bits.
                expected_words=(1024//(4*64))*(1-fault)
                require(row['activation_access']==(0,0,0,1,2,3)[command] and
                        row['commit_groups']==expected_words,'QBS context/atomic commit-word mismatch')
                require(row['read_fault']==(5 if fault else 0),'Need specified PMA reader fault')
                reuse=int(command in (4,5))
                require(row['context_fill_count']==int(command==3) and row['context_reuse_count']==reuse and
                        row['context_reuse_block_count']==reuse and row['context_read_bytes']==292*reuse and
                        row['activation_axi_bytes_saved']==292*reuse,'QBS resident-context work mismatch')
                if not fault:
                    require(row['useful_pairs']==768 and row['weight_bytes']==432,'QBS arithmetic work mismatch')
            else:
                require(row['command']==command and row['success']==1 and row['fault']==0 and
                        row['validation_fault']==0 and row['read_fault']==0 and
                        row['context_ready']==int(command!=3) and row['v2_bank_conflict_cycles']==0,
                        'AKV command/context/fault mismatch')
                require(row['q_external_bytes']==(256 if command==4 else 0) and
                        row['kv_external_bytes']==(768 if command==4 else 0) and
                        row['replay_bytes']==(128 if command==2 else 0) and
                        row['read_ranges']==(9 if command==4 else 0),'AKV external/resident work mismatch')
                require(row['v2_full']==int(command==4) and row['load']==int(command==2) and
                        row['v2_row_load']==int(command==2) and row['release']==int(command==3) and
                        row['v2_column_load']==0,'AKV operation flags differ')
                if command!=4:
                    require(row['ar']==row['r_beats']==0,'Resident load read external memory')
                else:
                    require(row['ar']>=9 and row['r_beats']>=row['ar'] and
                            row['read_payload_bytes']==1088 and row['read_outstanding_max']>0,'Missing FULL traffic')
            records.append(row)
        if 'Core Test' in line:
            require(line==TERMINAL and passed and not terminal,'Bad core terminal')
            terminal=True
    require(software==markers() and passed and terminal and counts==dict(qbs=6,akv=65) and
            severity=={'UVM_ERROR','UVM_FATAL'},'Incomplete transcript')
    return dict(state='READER_HANDOFF_LOG_V2_CHECKED',commands=71,qbs=6,akv=65,
                hardware_records=records,reader_faults=1,validation_faults=0,
                resident_rows_self_checked=62,performance=False,whole_model=False,
                legacy_commit_words_per_success=4)

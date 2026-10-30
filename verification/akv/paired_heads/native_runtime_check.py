"""Strict whole-call candidate log checker; not simulator or UVM acceptance."""
import re
import attention_run as s

CASES = [dict(d=64,heads=3,kv=1),dict(d=96,heads=3,kv=65),
         dict(d=128,heads=6,kv=7),dict(d=128,heads=2,kv=64)]
CAP = 'NATIVE_PAIR_CAP cases=4 runs=12 production_candidate=1'
SUITE = 'NATIVE_PAIR_SUITE_PASS cases=4 runs=12 exact_outputs=1 exact_flags=1 guards=1'
RESULT = re.compile(r'NATIVE_PAIR_RESULT case=([0-3]) trial=([0-2]) requested=([01]) '
    r'outputs=([0-9]+) compared=4096 hash=([0-9a-f]{16}) fcsr=([0-9]+) vcsr=5 errors=0')


def begin(case,trial):
    c = CASES[case]
    return f"NATIVE_PAIR_BEGIN case={case} trial={trial} requested={int(trial == 1)} d={c['d']} heads={c['heads']} kv={c['kv']}"


def work(case,enabled):
    """command, panel, active tile tokens; GQA6 retains six-head shared leaves."""
    d,heads,kv = (case[k] for k in ('d','heads','kv'))
    special = heads == 6 and d == 128
    paired = enabled and not special
    seq = []
    for tile in range(0,kv,64):
        tokens = min(64,kv-tile)
        seq.append((4 if tile == 0 else 5,0,tokens))
        if special:
            seq += [(6,0,tokens)]*d
        elif paired:
            seq += [(6,1,tokens)]*((heads//2)*(d//4))
            seq += [(6,0,tokens)]*((heads%2)*d)
        else:
            seq += [(6,0,tokens)]*(heads*d)
        seq += [(2,0,tokens)]*(tokens*(1 if special else (heads+1)//2 if paired else heads))
    return seq+[(3,0,0)]


def expected_record(case,item,sequence):
    command,panel,tokens = item
    d,heads = case['d'],case['heads']
    full,refill,column,row,release = (int(command == k) for k in (4,5,6,2,3))
    logical = column*(4 if panel else 1)
    return dict(seq=sequence,command=command,success=1,fault=0,validation_fault=0,
        validation_error=0,read_fault=0,context_ready=1-release,full=0,refill=0,
        load=row,release=release,v2_full=full,v2_refill=refill,v2_row_load=row,
        v2_column_load=column,v2_column_panel=panel,v2_logical_column=logical,
        v2_k_view_bank_cycles=((tokens+7)//8)*column,v2_bank_conflict_cycles=0,v2_rejected=0,
        q_external_bytes=2*d*heads*full,kv_external_bytes=4*d*tokens*(full+refill),
        read_payload_bytes=(64+2*d*heads)*full+4*d*tokens*(full+refill),
        read_ranges=(1+heads)*full+2*tokens*(full+refill),
        replay_bytes=2*tokens*logical+2*d*row,translations=0)


def check_log(text):
    active = cap = suite = terminal = False
    trials,records,group,severity = [],[],[],set()
    summary = None
    for line in text.splitlines():
        s.require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT)\b',line,re.I),'Failure text')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            m = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0',line)
            s.require(m is not None and m[1] not in severity,'UVM failure/duplicate')
            severity.add(m[1])
        if 'Core Test' in line:
            s.require(line == s.TERMINAL and suite and not terminal,'Bad/early core success')
            terminal = True
        if 'QBS_PERF' in line and not line.startswith('Command:'):
            raise ValueError('Unrelated QBS workload')
        if 'AKV_PERF' in line and not line.startswith('Command:'):
            if line.startswith('[AKV_PERF] '):
                s.require(active,'Command outside call')
                case,trial = divmod(len(trials),3)
                seq = work(CASES[case],trial == 1)
                s.require(len(group) < len(seq),'Extra command')
                row = s.numeric_fields(line[len('[AKV_PERF] '):],s.PERF_FIELDS)
                wanted = expected_record(CASES[case],seq[len(group)],len(records)+1)
                s.require(all(row[k] == v for k,v in wanted.items()),'Command/order/traffic/fault mismatch')
                s.require(row['id'] < 8 and row['busy_cycles'] > 0 and row['read_outstanding_max'] <= 2,
                          'Invalid command ID/cycles/outstanding')
                if row['command'] in (4,5):
                    s.require(row['ar'] >= row['read_ranges'] and row['r_beats'] >= row['ar'] and
                              row['read_outstanding_max'] > 0,'Missing external traffic')
                else:
                    s.require(all(row[k] == 0 for k in ('ar','r_beats','read_outstanding_max',
                        'read_outstanding_occ_sum','read_outstanding_full_cycles')),'Unexpected external traffic')
                records.append(row)
                group.append(row)
            elif line.startswith('[AKV_PERF_SUMMARY] '):
                s.require(suite and not active and summary is None,'Early/duplicate hardware summary')
                summary = s.numeric_fields(line[len('[AKV_PERF_SUMMARY] '):],s.SUMMARY_FIELDS)
            else:
                raise ValueError('Malformed hardware record')
        if 'NATIVE_PAIR_' in line:
            case,trial = divmod(len(trials),3)
            if line == CAP:
                s.require(not cap and not active and not trials,'Duplicate capability marker')
                cap = True
            elif line.startswith('NATIVE_PAIR_BEGIN '):
                s.require(cap and not active and not suite and case < 4 and line == begin(case,trial),
                          'Call order/shape mismatch')
                active,group = True,[]
            elif line.startswith('NATIVE_PAIR_RESULT '):
                m = RESULT.fullmatch(line)
                s.require(active and m is not None and (int(m[1]),int(m[2]),int(m[3])) ==
                          (case,trial,int(trial == 1)),'Malformed call result')
                s.require(int(m[4]) == CASES[case]['d']*CASES[case]['heads'] and int(m[6]) <= 31,
                          'Output/rounding-state mismatch')
                s.require(len(group) == len(work(CASES[case],trial == 1)),'Incomplete call work')
                trials.append(dict(case=case,trial=trial,requested=int(m[3]),checksum=m[5],
                    fcsr=int(m[6]),vcsr=5,hardware_totals=s.totals(group)))
                active = False
            elif line == SUITE:
                s.require(cap and not active and len(trials) == 12 and not suite,'Incomplete suite')
                suite = True
            else:
                raise ValueError('Unknown/malformed candidate evidence')
    s.require(cap and suite and terminal and not active and len(records) == 3680 and
              severity == {'UVM_ERROR','UVM_FATAL'},'Incomplete candidate run')
    s.require(summary == s.totals(records),'Raw hardware summary mismatch')
    for case in range(4):
        values = {(t['checksum'],t['fcsr'],t['vcsr']) for t in trials if t['case'] == case}
        s.require(len(values) == 1,'Candidate results/CSR or restored OFF differ')
    return dict(state='PASS',trials=trials,raw_hardware_summary=summary,
        scope='Derived real-data full native OFF/ON/OFF; not independent full Attention oracle or performance evidence',
        ggml_deployed=False)

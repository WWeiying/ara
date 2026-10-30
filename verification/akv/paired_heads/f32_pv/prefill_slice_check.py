"""Strict raw-record acceptance for the complete real Prefill slice ABBA."""
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import attention_run as s
from native_runtime_check import expected_record

ORDER = (0,1,1,0)
SOURCE = 'PREFILL_PV_SLICE source=smollm2_m64 positions=32-35 heads=9 kvheads=3 d=64 outputs=2304 derived=1'
SUITE = 'PREFILL_PV_SUITE_PASS trials=4 outputs=2304 generic_pair_exact=1 golden_tolerance=1'
END = re.compile(r'PREFILL_PV_RESULT trial=([0-3]) paired=([01]) outputs=2304 '
    r'cycles=([1-9][0-9]*) fcsr=([0-9]+) vcsr=5 hash=([0-9a-f]{16}) guards=256 errors=0')


def sequence(paired):
    body = [4]
    for active in (33,34,35,36):
        body += [6]*192+[2]*(active*(2 if paired else 3))
    return (body+[3])*3


def check_log(text):
    declared = active = suite = terminal = False
    trials,records,group,severity = [],[],[],set()
    summary = None
    for line in text.splitlines():
        s.require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT)\b',line,re.I),'Failure text')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            m = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0',line)
            s.require(m is not None and m[1] not in severity,'UVM failure/duplicate')
            severity.add(m[1])
        if 'Core Test' in line:
            s.require(line == s.TERMINAL and suite and not terminal,'Bad/early terminal')
            terminal = True
        if 'QBS_PERF' in line and not line.startswith('Command:'):
            raise ValueError('Unrelated QBS work')
        if 'AKV_PERF' in line and not line.startswith('Command:'):
            if line.startswith('[AKV_PERF] '):
                s.require(active,'Command outside timed call')
                seq = sequence(ORDER[len(trials)])
                s.require(len(group) < len(seq),'Extra command')
                row = s.numeric_fields(line[len('[AKV_PERF] '):],s.PERF_FIELDS)
                command = seq[len(group)]
                expected = expected_record(dict(d=64,heads=3,kv=36),(command,0,36),len(records)+1)
                s.require(all(row[k] == v for k,v in expected.items()),'Command/order/traffic mismatch')
                s.require(row['id'] < 8 and row['busy_cycles'] > 0 and row['read_outstanding_max'] <= 2,
                          'Command ID/cycles/outstanding')
                if command == 4:
                    s.require(row['ar'] >= 76 and row['r_beats'] >= row['ar'] and
                              row['read_outstanding_max'] > 0,'Missing FULL traffic')
                else:
                    s.require(all(row[k] == 0 for k in ('ar','r_beats','read_outstanding_max',
                        'read_outstanding_occ_sum','read_outstanding_full_cycles')),'Unexpected external read')
                records.append(row)
                group.append(row)
            elif line.startswith('[AKV_PERF_SUMMARY] '):
                s.require(suite and not active and summary is None,'Bad hardware summary order')
                summary = s.numeric_fields(line[len('[AKV_PERF_SUMMARY] '):],s.SUMMARY_FIELDS)
            else:
                raise ValueError('Malformed hardware metric')
        if 'PREFILL_PV_' in line:
            if line == SOURCE:
                s.require(not declared and not active and not trials,'Duplicate source')
                declared = True
            elif line.startswith('PREFILL_PV_BEGIN '):
                n = len(trials)
                s.require(declared and not active and not suite and n < 4 and
                    line == f'PREFILL_PV_BEGIN trial={n} paired={ORDER[n]}','Wrong ABBA order')
                active,group = True,[]
            elif line.startswith('PREFILL_PV_RESULT '):
                m = END.fullmatch(line)
                n = len(trials)
                s.require(active and m is not None and (int(m[1]),int(m[2])) == (n,ORDER[n]),
                          'Malformed result or wrong mode')
                s.require(len(group) == len(sequence(ORDER[n])),'Incomplete call commands')
                total = s.totals(group)
                s.require(int(m[4]) <= 31 and int(m[3]) >= total['busy_cycles'],'FRM or impossible cycles')
                s.require(total['replay_bytes'] == (271872 if ORDER[n] else 324864) and
                    total['q_external_bytes'] == 1152 and total['kv_external_bytes'] == 27648 and
                    total['read_payload_bytes'] == 28992 and total['read_ranges'] == 228,
                    'Complete native work totals')
                trials.append(dict(trial=n,paired=ORDER[n],cycles=int(m[3]),fcsr=int(m[4]),
                    vcsr=5,checksum=m[5],hardware_totals=total))
                active = False
            elif line == SUITE:
                s.require(declared and not active and len(trials) == 4 and not suite,'Incomplete suite')
                suite = True
            else:
                raise ValueError('Unknown Prefill evidence')
    s.require(declared and suite and terminal and not active and len(records) == 13380 and
              severity == {'UVM_ERROR','UVM_FATAL'},'Incomplete Prefill evidence')
    s.require(summary == s.totals(records),'Raw final summary mismatch')
    s.require(len({(t['checksum'],t['fcsr'],t['vcsr']) for t in trials}) == 1,'Output/CSR differs')
    for field in ('ar','r_beats','read_ranges','read_payload_bytes','q_external_bytes','kv_external_bytes'):
        s.require(len({t['hardware_totals'][field] for t in trials}) == 1,'External traffic changed')
    sums = {str(mode):sum(t['cycles'] for t in trials if t['paired'] == mode) for mode in (0,1)}
    return dict(state='PASS',trials=trials,raw_hardware_summary=summary,sums=sums,
        speedup=sums['0']/sums['1'],cycle_reduction_percent=100*(1-sums['1']/sums['0']),
        performance='improved' if sums['1'] < sums['0'] else 'neutral' if sums['1'] == sums['0'] else 'regressed',
        scope='Complete real Prefill slice native API, all9 Query/3 KV heads, positions32--35; not full M64/GGML admission/model timing',
        production_deployed=False)

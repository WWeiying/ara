#!/usr/bin/env python3
"""Exact all-head QK transcript/work and independent per-output host replay."""
import hashlib
import re

from batch_spec import expected, sequence
from check_rvv_qbs import require

CAP = ('QUANT_QK_BATCH_CAP profiles=2 d=128 query_heads=12 kv_heads=2 '
       'visible=128 capacity=256 commands=40 outputs=3336')
SUITE = ('QUANT_QK_BATCH_SUITE_PASS commands=40 outputs=3336 guards=1 '
         'inactive_memory=1 deployment_accepted=0')
QUERY = re.compile(r'QUANT_QK_BATCH_QUERY kind=([01]) head=([0-9]+) bytes=136 '
                   r'fcsr=([0-9]+) vcsr=5 hex=([0-9a-f]{272})')
SCORE = re.compile(r'QUANT_QK_BATCH_SCORE seq=([0-9]+) kind=([01]) kv_head=([01]) '
    r'first_q=([0-9]+) m=([24]) first_token=([0-9]+) n=([0-9]+) '
    r'fcsr=([0-9]+) vcsr=5 errors=0 hex=([0-9a-f]+)')
TERMINAL = 'Core Test *** SUCCESS *** (tohost = 0)'


def schema(rtl):
    formats = re.findall(r'\$display\("\[QBS_PERF\] ([^"\n]+)"',rtl)
    require(len(formats) == 1,'Unknown QBS work source schema')
    names = re.findall(r'([a-z][a-z0-9_]*)=%0d',formats[0])
    require(len(names) == len(set(names)) and 'weight_bytes' in names,'Invalid source fields')
    return names


def check_command(row, command, seq):
    c = command
    wanted = dict(seq=seq,m=c.m,n=c.n,vlen=1024,lanes=4,success=1,fault=0,
        validation_fault=0,validation_error=0,read_fault=0,translations=0,
        read_ranges=c.read_ranges,payload_bytes=c.payload_bytes,
        weight_bytes=c.weight_row_bytes*c.n,activation_bytes=136*c.m,
        useful_pairs=128*c.outputs,activation_access=0,context_fill_count=0,
        context_reuse_count=0,context_reuse_block_count=0,context_read_bytes=0,
        activation_axi_bytes_saved=0,context_replay_cycles=0,
        context_replay_compute_overlap_cycles=0,context_validation_fault_count=0)
    require(all(row.get(k) == v for k,v in wanted.items()),'Batch command geometry/bytes/context/fault')
    require(row['id'] < 8 and row['busy_cycles'] > 0 and
        row['ar'] >= c.read_ranges and row['r_beats'] >= row['ar'] and
        0 < row['read_outstanding_max'] <= 2 and row['commit_groups'] > 0,
        'Missing actual batch read/commit work')


def check_log(text, key_data, oracle, rtl, previous_queries):
    fields, commands = schema(rtl),sequence()
    queries,records,score_rows = {},[],[]
    declared = suite = terminal = False
    severity = set()
    for line in text.splitlines():
        require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT)\b',line,re.I),'Failure text')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            m = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0',line)
            require(m is not None and m[1] not in severity,'UVM error/duplicate summary')
            severity.add(m[1])
        if 'Core Test' in line:
            require(line == TERMINAL and suite and not terminal,'Core termination')
            terminal = True
        if 'AKV_PERF' in line:
            raise ValueError('Unexpected AKV work')
        if 'QBS_PERF' in line and not line.startswith('Command:'):
            require(declared and not suite and not terminal and len(records) == len(score_rows) and
                    len(records) < 40,'Extra/misordered batch command')
            c = commands[len(records)]
            require(len(queries) == 12*(c.kind+1),'QBS work before all real Query exports')
            require(re.fullmatch(r'\[QBS_PERF\](?: [a-z][a-z0-9_]*=[0-9]+)+',line) is not None,
                    'Malformed QBS work')
            pairs = re.findall(r'([a-z][a-z0-9_]*)=([0-9]+)',line)
            require([k for k,_ in pairs] == fields,'Missing/extra/duplicate QBS fields')
            row = {k:int(v) for k,v in pairs}
            check_command(row,c,len(records)+1)
            records.append(row)
        if 'QUANT_QK_BATCH_' not in line:
            continue
        require(not terminal,'Program record after termination')
        if line == CAP:
            require(not declared and not queries and not records,'Duplicate capability record')
            declared = True
        elif QUERY.fullmatch(line):
            m = QUERY.fullmatch(line)
            index = len(queries)
            kind,head = divmod(index,12)
            require(declared and not suite and index < 24 and
                    (int(m[1]),int(m[2])) == (kind,head) and int(m[3]) <= 31 and
                    len(records) == len(score_rows) == 20*kind,'Query identity/order/FRM')
            query = bytes.fromhex(m[4])
            if head in (0,6):
                require(previous_queries.get((kind,head)) == query,'Prior actual Query export mismatch')
            queries[kind,head] = query
        elif SCORE.fullmatch(line):
            m = SCORE.fullmatch(line)
            index = len(score_rows)
            require(declared and not suite and index < 40 and len(records) == index+1,
                    'Score without exact actual command')
            c = commands[index]
            require(tuple(map(int,m.groups()[:7])) ==
                    (index+1,c.kind,c.kv_head,c.first_q,c.m,c.first_token,c.n),
                    'Score geometry/order mismatch')
            flags = 0
            require(len(m[9]) == 8*c.outputs and int(m[8]) <= 31,'Score extent/FRM')
            for row in range(c.m):
                for column in range(c.n):
                    start,end = c.key_range(column)
                    wanted,fflags = oracle(c.kind,key_data[c.kind][start:end],queries[c.kind,c.first_q+row])
                    offset = 8*(row*c.n+column)
                    actual = int(m[9][offset:offset+8],16)
                    require(actual & 0x7f800000 != 0x7f800000 and actual == wanted,
                            'Independent multioutput host score mismatch')
                    flags |= fflags
            require(int(m[8]) == flags,'Independent aggregate command flags mismatch')
            score_rows.append(dict(seq=index+1,kind=c.kind,kv_head=c.kv_head,first_q=c.first_q,
                m=c.m,first_token=c.first_token,n=c.n,outputs=c.outputs,fcsr=flags,
                score_hex_sha256=hashlib.sha256(m[9].encode('ascii')).hexdigest()))
        elif line == SUITE:
            require(declared and not suite and len(queries) == 24 and
                    len(records) == len(score_rows) == 40,'Incomplete/duplicate suite')
            suite = True
        else:
            raise ValueError('Unknown/malformed batch program record')
    require(suite and terminal and severity == {'UVM_ERROR','UVM_FATAL'},'Incomplete batch transcript')
    want = expected()
    require(sum(row['payload_bytes'] for row in records) == want['payload_bytes'] and
            sum(row['read_ranges'] for row in records) == want['read_ranges'] and
            sum(row['outputs'] for row in score_rows) == want['outputs'],'Batch total work mismatch')
    return dict(state='HOST_BATCH_NUMERICAL_AND_WORK_CHECKED',expected=want,
        score_rows=score_rows,hardware_records=records,
        query_exports=[dict(kind=k,head=h,hex=value.hex()) for (k,h),value in queries.items()],
        hardware_host_exact=True,whole_attention_accepted=False,
        deployment_approved=False,performance_measured=False)

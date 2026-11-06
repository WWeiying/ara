"""Check the full GQA6 native-call ABBA, including original captured golden."""
import math
import re
import struct

from audit import require
from check_projection_native import fields

SCOPE = 'OUTPUT_GQA6_SCOPE model=qwen25 query=0 heads=6 kv=1 dim=128 visible=128 token_major=1 trials=4 whole_call=1'


def check(text, golden):
    require(not re.search(r'Fatal:|Error:|^UVM_(?:ERROR|FATAL)\s+@', text, re.M), 'Simulator failure')
    require(len(golden) == 12*128*4 and text.splitlines().count(SCOPE) == 1 and
            text.splitlines().count('OUTPUT_GQA6_FORMAT q4=0') == 1 and
            text.splitlines().count('OUTPUT_GQA6_SUITE_PASS') == 1, 'Wrong fixture or missing terminal')
    gold = struct.unpack('<1536f', golden); rows = []; pending = None; commands = []; reference = None
    for line in text.splitlines():
        if line.startswith('OUTPUT_GQA6_BEGIN '):
            require(pending is None and len(rows) < 4, 'Nested/extra call')
            pending = fields(line, 'OUTPUT_GQA6_BEGIN'); commands = []
            require(pending == dict(trial=len(rows), candidate=(0,1,1,0)[len(rows)]), 'ABBA order')
        elif line.startswith('[QBS_PERF] '):
            require(pending is not None, 'Command outside call'); commands.append(fields(line, '[QBS_PERF]'))
        elif line.startswith('OUTPUT_GQA6_RESULT '):
            require(pending is not None and len(commands) == 8, 'Missing native work')
            header, sep, hexdata = line.partition(' hex='); row = fields(header, 'OUTPUT_GQA6_RESULT')
            require(sep and len(hexdata) == 6*128*8 and all(c in '0123456789abcdef' for c in hexdata), 'Output bits')
            expected = dict(**pending, commands=8, groups=1, values=128, panels=4, key_bytes=128*136, vcsr=5, errors=0)
            require(all(row.get(k) == v for k,v in expected.items()) and row['cycles'] > 0 and
                    0 <= row['fcsr'] <= 31 and row['fcsr'] & 8, 'Call/state failure')
            if reference is None: reference = (hexdata, row['fcsr'])
            require(reference == (hexdata, row['fcsr']), 'Output or final FCSR differs')
            actual = [struct.unpack('<f', struct.pack('<I', int(hexdata[i:i+8],16)))[0]
                      for i in range(0, len(hexdata), 8)]
            max_error = 0.0
            for value, want in zip(actual, gold):
                require(math.isfinite(value) and math.isfinite(want) and
                        abs(value-want) <= 2e-5+2e-5*abs(want), 'Captured golden mismatch')
                max_error = max(max_error, abs(value-want))
            for i, command in enumerate(commands):
                m = 4 if i%2 == 0 else 2
                geometry = dict(seq=len(rows)*8+i+1, m=m, n=32, vlen=1024, lanes=4,
                    success=1, fault=0, validation_fault=0, read_fault=0,
                    weight_bytes=32*136, useful_pairs=m*32*128, activation_access=0)
                require(all(command.get(k) == v for k,v in geometry.items()), 'Wrong QK work or geometry')
            row.update(max_abs=max_error, qbs_busy=sum(c['busy_cycles'] for c in commands),
                       useful_pairs=sum(c['useful_pairs'] for c in commands))
            require(row['qbs_busy'] <= row['cycles'], 'Inconsistent cycle intervals')
            rows.append(row); pending = None
    require(pending is None and len(rows) == 4, 'Incomplete calls')
    base = sum(r['cycles'] for r in rows if not r['candidate'])
    candidate = sum(r['cycles'] for r in rows if r['candidate'])
    return dict(trials=rows, baseline_cycles=base/2, candidate_cycles=candidate/2,
                speedup=base/candidate, paired_bitexact=True, outputs_per_trial=768,
                commands_per_trial=8, useful_pairs_per_trial=98304,
                scope='Real Qwen2.5 first KV group, GQA6 D128 visible128 complete call',
                value_decodes_is_logical_rows_not_physical_decode_count=True, whole_model=False)

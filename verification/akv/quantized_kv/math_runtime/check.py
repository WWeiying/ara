"""Compare actual library outputs; Newlib bytes are provenance, not a golden."""
import math
import re
import struct


def as_float(bits):return struct.unpack('<f',struct.pack('<I',bits))[0]


def check(text,pairs):
    lines=text.splitlines();rows=[]
    if lines.count('EXP_REPLAY_CAP calls=768 library=linked_linux_libm performance=not_measured')!=1:
        raise ValueError('Missing Linux library scope')
    if lines.count('GUEST_TEST_EXIT=0')!=1:raise ValueError('Guest failed/incomplete')
    pattern=re.compile(r'EXP_REPLAY i=(\d+) input=([0-9a-f]{8}) result=([0-9a-f]{8}) flags=(\d+) errno=(\d+)')
    summaries=[]
    for line in lines:
        if line.startswith('EXP_REPLAY i='):
            m=pattern.fullmatch(line)
            if not m or int(m[1])!=len(rows) or len(rows)>=len(pairs):raise ValueError('Replay order/schema')
            pair=pairs[len(rows)];x=int(m[2],16);y=int(m[3],16);flags=int(m[4]);error=int(m[5])
            if x!=int(pair['input_bits'],16) or y>0x3f800000 or flags&~3 or error not in (123,34):
                raise ValueError('Input/result/state mismatch')
            # Independent binary64 exp rounded to binary32 is a diagnostic
            # reference, not a proof of correctly rounded expf for all inputs.
            want=struct.unpack('<I',struct.pack('<f',math.exp(as_float(x))))[0]
            if abs(y-want)>1:raise ValueError('Unexpected >1 ULP reference difference')
            if x==0xff800000 and (y or flags or error!=123):raise ValueError('Negative infinity semantics')
            rows.append(dict(input_bits=m[2],linux_bits=m[3],newlib_bits=pair['output_bits'],
                             flags=flags,errno=error,reference_ulp=abs(y-want)))
        elif line.startswith('EXP_REPLAY_RESULT '):summaries.append(line)
    differences=sum(r['linux_bits']!=r['newlib_bits'] for r in rows)
    if len(pairs)!=768 or len(rows)!=768 or summaries!=[
            f'EXP_REPLAY_RESULT calls=768 differences={differences} errors=0']:
        raise ValueError('Incomplete library replay')
    return dict(state='LINUX_LIBM_REAL_ARGUMENT_REPLAY_PASS',calls=768,
                linux_newlib_bit_differences=differences,
                max_linux_newlib_ulp=max(abs(int(r['linux_bits'],16)-int(r['newlib_bits'],16)) for r in rows),
                max_diagnostic_reference_ulp=max(r['reference_ulp'] for r in rows),
                underflow_flagged_calls=sum(bool(r['flags']&2) for r in rows),
                errno_range_calls=sum(r['errno']==34 for r in rows),
                rows=rows,performance_measured=False,
                scope='Actual linked Linux expf on real captured arguments; not RTL timing or whole Attention execution')

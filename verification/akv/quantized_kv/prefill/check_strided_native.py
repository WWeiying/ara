"""Whole-call checks plus strict token-major layout and K-panel accounting."""
import re
from check_full_native import check_full_log

LAYOUT='PREFILL_LAYOUT token_major=1 physical_kv_heads=8 selected_head=0'


def check_strided_log(text,golden,q4):
    lines=text.splitlines()
    assert [l for l in lines if l.startswith('PREFILL_LAYOUT')]==[LAYOUT]
    row=72 if q4 else 136
    panels=[l for l in lines if l.startswith('PREFILL_PANEL')]
    assert panels==[f'PREFILL_PANEL trial={i} panels={p} key_bytes={n*row}'
                    for i,p,n in [(0,4,74),(1,1,20),(2,1,20),(3,4,74)]]
    for i,line in enumerate(panels):
        start=f'PREFILL_BEGIN trial={i} shared={int(i in (1,2))}'
        ends=[j for j,l in enumerate(lines) if re.match(f'PREFILL_RESULT trial={i} ',l)]
        assert len(ends)==1 and lines.index(start)<lines.index(line)<ends[0]
    result=check_full_log(text,golden,q4)
    result.update(token_major=True,physical_kv_heads=8,
                  key_panels=[4,1,1,4],key_bytes=[n*row for n in (74,20,20,74)],
                  scope='QBS token-major strided per-query versus grouped Prefill, whole call')
    return result

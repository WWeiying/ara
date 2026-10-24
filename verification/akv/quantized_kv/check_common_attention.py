"""Public-entry evidence plus the unchanged full Attention numerical/work gate."""
import re

from check_attention import check_log as check_attention, ORDER
from check_batch_qk import TERMINAL
from check_rvv_qbs import require

CAP='QUANT_COMMON_CAP map_timed=1 admission_timed=1 workspace=4352'
ENTRY=re.compile(r'QUANT_COMMON_ENTRY trial=([12]) map=0 status=0 selection=0 groups=1 commands=8 values=128')


def check_log(text,kind,golden,rtl):
    cap=terminal=False
    active=None
    finished=[]
    entries=[]
    for line in text.splitlines():
        if line==TERMINAL:
            terminal=True
        if 'QUANT_COMMON_' in line:
            require(not terminal,'Common-entry record after termination')
            if line==CAP:
                require(not cap and active is None and not finished,'Duplicate/late common capability')
                cap=True
            elif ENTRY.fullmatch(line):
                trial=int(ENTRY.fullmatch(line)[1])
                require(cap and active==trial and trial not in entries,'Unexpected/duplicate common entry')
                entries.append(trial)
            else:
                raise ValueError('Malformed/unknown common-entry evidence')
        if line.startswith('QUANT_ATTN_CAP '):
            require(cap,'Missing public-entry capability declaration')
        if line.startswith('QUANT_ATTN_BEGIN '):
            trial=len(finished)
            require(cap and active is None and trial<4 and line==
                f'QUANT_ATTN_BEGIN trial={trial} shared={ORDER[trial]}','Wrong common-entry order')
            active=trial
        elif line.startswith('QUANT_ATTN_RESULT '):
            require(active is not None and ((active in entries)==bool(ORDER[active])),
                    'Missing native entry or native work attributed to baseline')
            finished.append(active)
            active=None
    require(cap and terminal and finished==[0,1,2,3] and entries==[1,2],
            'Incomplete public-entry experiment')
    result=check_attention(text,kind,golden,rtl)
    result.update(state='COMMON_ENTRY_NUMERICAL_AND_WORK_CHECKED',
        mapping_timed=True,admission_timed=True,workspace_bytes=4352,
        public_entry_trials=entries,
        scope='Real six-head KV group; candidate includes GGML mapping and shared runtime admission, not model execution')
    return result

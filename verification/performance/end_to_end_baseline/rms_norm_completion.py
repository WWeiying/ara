"""Registered caller-only timer correction; keep the compiled kernels frozen."""
from audit import require

BEFORE='''            const uint64_t elapsed=cycle()-begin;
            const unsigned fc=fcsr(),vc=vcsr(),vs=vstart();
'''
AFTER='''            const unsigned vc=vcsr(),fc=fcsr(),vs=vstart();
            const uint64_t elapsed=cycle()-begin;
'''


def completed_caller(source):
    require(source.count(BEFORE)==1 and source.count('timing=complete_call')==1,'Completion caller anchors')
    return source.replace(BEFORE,AFTER,1).replace('timing=complete_call','timing=call_and_csr_completion',1)

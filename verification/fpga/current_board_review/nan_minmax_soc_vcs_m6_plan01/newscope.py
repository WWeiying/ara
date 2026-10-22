"""Exact two source-single scope, never an original full Linux parent."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF = HERE.parent/'nan_minmax_soc_prepare01'
READY = REF/'observer_recovery01/complete01/READY.json'
READY_SHA = '11cc4d306bdc5a37976d13eca3ec164ab597b42406e47c294ba714ef8bcf7cfc'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image')
NAMES = ['nan_minmax_call1294','nan_minmax_call1234']
ELF_SHA = {
    NAMES[0]:'f9f3950cb84244d964747c45482d73f7d960270095cbd309a2b956460cf56275',
    NAMES[1]:'b93e81cc92e625c04094f67531d2aa8ad2a6bb7c3c3b4947478310cec737e28d',
}
TIMEOUT, OUTER, JOBS = 5400, 7200, 2
UNIT = 'ara-nan-minmax-two-source-singles-m6-01.service'
PASS = 'PASS_TWO_NAN_MAX_SOURCE_SINGLES_M6_NOT_PARENT'
REFERENCE_RETIRED = 1857110
MARKER = 'RVV_FP_REDSPECIAL_PASS sew=32 cases=1 flags_seen=0 errors=0'
EVENTS = {'retire','cvx_req','cvx_resp','arch_start','uop_alloc','uop_done'}


def shape(name):
    if name not in NAMES:
        raise ValueError('exact runtime membership')
    return name.removeprefix('nan_minmax_')

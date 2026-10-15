"""Exact two source-single scope, never an original full Linux parent."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF = HERE.parent/'nan_min_soc_prepare01'
READY = REF/'READY.json'
READY_SHA = '2183b27009b1a9891346b99c753719908192905bb093f6090ec251753dac6ee2'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image')
NAMES = ['nan_min_call1292','nan_min_call1232']
ELF_SHA = {
    NAMES[0]:'86b198a47a06426b0a4b127a14c446a8495652407b8fb722729e78e7c7e68c0f',
    NAMES[1]:'0ab53076d2ed4adc3d3a8cecefe19ca07c006219cbb477fd4db432e54c824674',
}
TIMEOUT, OUTER, JOBS = 5400, 7200, 2
UNIT = 'ara-nan-min-two-source-singles-m6-01.service'
PASS = 'PASS_TWO_NAN_MIN_SOURCE_SINGLES_M6_NOT_PARENT'
REFERENCE_RETIRED = 1857014
MARKER = 'RVV_FP_REDSPECIAL_PASS sew=32 cases=1 flags_seen=0 errors=0'
EVENTS = {'retire','cvx_req','cvx_resp','arch_start','uop_alloc','uop_done'}


def shape(name):
    if name not in NAMES:
        raise ValueError('exact runtime membership')
    return name.removeprefix('nan_min_')

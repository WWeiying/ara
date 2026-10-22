"""Exact first50 original alias-v8 calls on current frozen M6, not full parent."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=HERE.parents[1]
REFROOT=HERE.parent/'fp_alias50_m6_prepare01'
REF=REFROOT/'prepared01'
READY=REFROOT/'READY.json'
READY_SHA='feae4a0dc86ea2e5222655469f574634eaae03741d777bb015f71af6644ee004'
NAME='alias_v8_e16m8_prefix50'
NAMES=[NAME]
HISTORICAL='rvv_fp_compare_unmasked_alias_v8_e16_m8'
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image')
IMAGE_SHA='a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
TIMEOUT,OUTER,JOBS=7200,9000,1
UNIT='ara-fp-alias-original50-m6-01.service'
PASS='PASS_FP_ALIAS_ORIGINAL50_M6_NOT_FULL_PARENT'
MARKER='RVV_FP_COMPARE_PASS sew=16 cases=50 errors=0'
EVENTS={'retire','cvx_req','cvx_resp','arch_start','uop_alloc','uop_done'}

from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
PARENT = HERE.parent
PREVIOUS = PARENT/'full682_vcs_m8_plan01'
PREP = PARENT/'full700_m9_prepare01'
READY = PREP/'READY.json'
READY_SHA = 'e4e0f6bf8c65808eaf629ccfe1efb7c8da5afb6c88a0949e5fbf8701aa20c1d9'
BOUND = 700
NAME = 'alias_v8_e16m8_prefix700'
NAMES = [NAME]
HISTORICAL = 'rvv_fp_compare_unmasked_alias_v8_e16_m8'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image')
IMAGE_SHA = '48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a'
TIMEOUT, OUTER, JOBS = 7200, 9000, 1
UNIT = 'ara-fp-alias-original700-m9-01.service'
PASS = 'PASS_M9_ORIGINAL_ALIAS700_NOT_FULL17920_OR_LINUX'
MARKER = 'RVV_FP_COMPARE_PASS sew=16 cases=700 errors=0'
EVENTS = {'retire','cvx_req','cvx_resp','arch_start','uop_alloc','uop_done'}

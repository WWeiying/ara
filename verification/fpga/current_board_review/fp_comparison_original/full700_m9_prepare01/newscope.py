from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
PARENT = HERE.parent
PREVIOUS = PARENT / 'full682_vcs_m8_plan01'
PACKED = PARENT / 'full682_packed_prepare01'
CASE = PARENT / 'prepared02/prepared/alias_v8_e16m8_prefix682'
NAME = 'alias_v8_e16m8_prefix700'
HISTORICAL = 'rvv_fp_compare_unmasked_alias_v8_e16_m8'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image')
IMAGE_SHA = '48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a'
EVENTS = {'retire', 'cvx_req', 'cvx_resp', 'arch_start', 'uop_alloc', 'uop_done'}
BOUND = 700
MARKER = 'RVV_FP_COMPARE_PASS sew=16 cases=700 errors=0'

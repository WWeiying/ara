from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=HERE.parents[1]
PREP=HERE.parent/'full682_packed_prepare01'
READY=PREP/'READY.json'
READY_SHA='64f82d0e893179b253b4cced76f6f73b7820f1427b865889bd127c7d9eee62e4'
MAIN_REVIEW=PREP/'MAIN_STATIC_REVIEW.md'
NAME='alias_v8_e16m8_prefix682'
NAMES=[NAME]
HISTORICAL='rvv_fp_compare_unmasked_alias_v8_e16_m8'
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate08/campaign/image')
IMAGE_SHA='bd27bf6f7bb90b2b05c4546faaed8a8e32b8e545c182167fef72c170e40bdfd0'
TIMEOUT,OUTER,JOBS=10800,13200,1
UNIT='ara-fp-alias-original682-m8-01.service'
PASS='PASS_M8_ORIGINAL_ALIAS682_NOT_FULL17920_OR_LINUX'
MARKER='RVV_FP_COMPARE_PASS sew=16 cases=682 errors=0'
EVENTS={'retire','cvx_req','cvx_resp','arch_start','uop_alloc','uop_done'}

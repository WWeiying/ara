"""Masked parent identity; this preparation never authorizes a launch."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;G=HERE.parent
SHARED=G/'fp_compare_unboxed_e32_mf2_full17920_vcs_m9_plan01'
PREP=G/'fp_compare_unboxed_masked_full17920_prepare01';REF=PREP/'reference01'
SOFTWARE=PREP/'build01/soc';ELF=SOFTWARE/'program.elf'
ELF_SHA='18294ae7aa7a2a503e0ab82d532f6c7dcc6f92ad752e3972e50038a7c03173ea'
NAME='fp_compare_unboxed_masked_e16_mf4_full17920'
HISTORICAL='rvv_fp_compare_unboxed_e16_mf4'
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image')
IMAGE_SHA='48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a'
TIMEOUT,WORKER,OUTER,JOBS=10800,12000,13200,1
UNIT='ara-fp16-masked-unboxed-full17920-m9-01.service'
MARKER='RVV_FP_COMPARE_PASS sew=16 cases=17920 errors=0'
PASS='PASS_M9_FULL17920_MASKED_FP16_UNBOXED_SOURCE_PORT_NOT_LINUX'
REVIEW=G/'fp_compare_unboxed_masked_full17920_reference_review_hilbert01/TERMINAL_REVIEW.json'
REVIEW_SHA='cb91428fee275298c6c7c5e61d68a6948e467d2398ebdc612a52d43598f9f1d0'
FPR_REVIEW=G/'fp_compare_unboxed_full17920_worker_review01/FPR_OBSERVABILITY01.json'
FPR_REVIEW_SHA='45746196ae655f4782efe694f46dfb2e5efddd3c307517de6eda17c8a028b5b2'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok,why):
    if not ok:raise ValueError(why)
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m

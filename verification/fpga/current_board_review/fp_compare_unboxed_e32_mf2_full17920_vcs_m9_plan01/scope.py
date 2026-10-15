"""One immutable original parent, new SoC observer; no launch at preparation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
G = HERE.parent
PREP = G/'fp_compare_unboxed_e32_mf2_full17920_prepare01'
REF = PREP/'reference_entry02'
STAGE = PREP/'software01'
SOFTWARE = STAGE/'execution01/soc'
ELF = SOFTWARE/'program.elf'
ELF_SHA = '520b652eb8a4d4dc634a17a36a9d5e71c382a4679afeb8aeb54746d18a37be73'
NAME = 'fp_compare_unboxed_e32_mf2_full17920'
HISTORICAL = 'rvv_fp_compare_unboxed_unmasked_e32_mf2'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image')
IMAGE_SHA = '48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a'
TIMEOUT, WORKER, OUTER, JOBS = 10800, 12000, 13200, 1
UNIT = 'ara-fp32-unboxed-full17920-m9-01.service'
MARKER = 'RVV_FP_COMPARE_PASS sew=32 cases=17920 errors=0'
PASS = 'PASS_M9_FULL17920_FP32_UNBOXED_SOURCE_PORT_NOT_LINUX'
REVIEW = PREP/'independent_terminal_review01/REVIEW.json'
REVIEW_SHA = '90c394e3f20887b9902047a933e2fbad85c9b0a95850e4987c704e9c51eb2a4f'
FPR_REVIEW = G/'fp_compare_unboxed_full17920_worker_review01/FPR_OBSERVABILITY01.json'
FPR_REVIEW_SHA = '45746196ae655f4782efe694f46dfb2e5efddd3c307517de6eda17c8a028b5b2'

def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok, why):
    if not ok: raise ValueError(why)
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

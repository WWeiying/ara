"""One immutable original parent, new SoC observer; no launch at preparation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
G = HERE.parent
PREP = G/'fp_compare_unboxed_full17920_prepare01'
REF = PREP/'reference_entry02'
SOFTWARE = PREP/'compile01/run02/soc'
ELF = SOFTWARE/'program.elf'
ELF_SHA = '19afd0c6fd9c0810efbfdd9a635d092672554e6a1f3d4a3a537af00c4de13e37'
NAME = 'fp_compare_unboxed_e16_mf4_full17920'
HISTORICAL = 'rvv_fp_compare_unboxed_unmasked_e16_mf4'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image')
IMAGE_SHA = '48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a'
TIMEOUT, WORKER, OUTER, JOBS = 10800, 12000, 13200, 1
UNIT = 'ara-fp-unboxed-full17920-m9-01.service'
MARKER = 'RVV_FP_COMPARE_PASS sew=16 cases=17920 errors=0'
PASS = 'PASS_M9_FULL17920_UNBOXED_SOURCE_PORT_NOT_LINUX'
REVIEW = G/'fp_compare_unboxed_full17920_source_review01/REFERENCE_TERMINAL01_REVIEW.json'
REVIEW_SHA = '50a0025d6c03a2df9e4396631b8431b8a36535d45962cc3ac7c837228b9c13c9'
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

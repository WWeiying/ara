import hashlib
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
G=HERE.parents[1]
PREP=HERE.parent/'full6720_e16_mf4_software01'
REF=HERE.parent/'full6720_e16_mf4_reference01'
SOFTWARE=PREP/'execution01/soc'
ELF=SOFTWARE/'program.elf'
ELF_SHA='5242911cb3a64d2bab02be8babdad363d75796a5f25dd351b82706c6279aca7c'
NAME='fp_redspecial_e16_mf4_full6720'
HISTORICAL='rvv_fp_redspecial_e16_mf4'
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image')
IMAGE_SHA='48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a'
TIMEOUT,WORKER,OUTER,JOBS=10800,12000,13200,1
UNIT='ara-redspecial-e16-mf4-full6720-m9-01.service'
MARKER='RVV_FP_REDSPECIAL_PASS sew=16 cases=6720 flags_seen=21 errors=0'
PASS='PASS_M9_FULL6720_REDSPECIAL_SOURCE_PORT_NOT_LINUX'
REVIEW=HERE.parent/'full6720_e16_mf4_reference_review01/TERMINAL_REVIEW.json'
REVIEW_SHA='05488c3fe4aa56eab93011a7903ff0bfc5a7a7a9eece9a56bd6210e1b47ff9ff'
MATURE=G/'fp_compare_unboxed_full17920_vcs_m9_plan01'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def require(ok,why):
    if not ok:raise ValueError(why)
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m

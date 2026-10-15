"""Generate a new M9 profile from identical reviewed reset/trace RTL."""
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'full_small2_reset_gpr_recovery01/reset_profile.json'
REF=HERE.parent/'full_e8_mf4_optimized_compile01'
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image/image.json')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(OLD)=='308784d27eaf81e2a608cd7cd37a9ac61a22a58ce9eda994715cec58dcd682a4'
assert sha(IMAGE)=='48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a'
p=json.loads(OLD.read_text());ledger=json.loads(IMAGE.read_text())
p['rtl_pins']={k.replace('candidate06','candidate09'):v for k,v in p['rtl_pins'].items()}
for path,digest in p['rtl_pins'].items():assert sha(Path(path))==digest,path
p.update(schema='EXACT_M9_FROM_RESET_INTEGER_GPR_PROFILE_V1',image=str(IMAGE),image_sha256=sha(IMAGE),
    snapshot_sha256=ledger['snapshot_sha256'],compiled_manifest_sha256=ledger['manifest_sha256'],
    configuration_sha256=ledger['configuration_sha256'],allowed_shape='rvv_matrix_e8_mf4',
    source_profile_sha256=sha(OLD),original_soc_elf_sha256='33fac90cb3c541657ede2d3b01e2cbd52d7ddd97cd0b78599ac237f237c16f44',
    original_linux_elf_sha256='da5d08b60f2b68567aea7254fc3c3ab1ce8c14369e5f473b384fa91248fce823',
    reference_bound_sha256=sha(REF/'bound.json'))
with (HERE/'reset_profile.json').open('x') as f:json.dump(p,f,indent=2);f.write('\n')
print(sha(HERE/'reset_profile.json'))

"""E8-only exact frozen-M6 reset-state successor; inherited oracle unchanged."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'full_small2_vcs_m6_plan01'
REF=HERE.parent/'full_small2_prepare01'
PROFILE_SHA='308784d27eaf81e2a608cd7cd37a9ac61a22a58ce9eda994715cec58dcd682a4'
PLAN_SHA='7ec58e3f38f5877838c7edf898d4b85d4872437dcdc54e7542357e8f2736f9ee'
OLD_SHA='18c9b86ab1a13b05d0f69823299d761a1f54a8d7c20c8b1ca30afd867ec8bf0f'
SHAPE='rvv_matrix_e8_mf8'


def need(ok,reason):
    if not ok: raise ValueError(reason)


def read(path): return json.loads(Path(path).read_text())


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def plan():
    path=OLD/'prepared01/plan.json'
    need(sha(path)==PLAN_SHA,'Exact original M6 plan required')
    return read(path)


def load_legacy():
    pinned=plan()['pins']
    need(sha(OLD/'checker.py')==OLD_SHA,'Unchanged legacy checker required')
    # Verify imported project Python inputs without touching reference/DUT raw files.
    for path,digest in pinned.items():
        if path.endswith('.py'): need(sha(path)==digest,'Legacy dependency drift: '+path)
    spec=importlib.util.spec_from_file_location('frozen_small2_legacy_checker',OLD/'checker.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy=load_legacy()


def validate_profile(profile=None):
    path=HERE/'reset_profile.json'
    need(sha(path)==PROFILE_SHA,'Reset profile pin drift')
    expected=read(path)
    if profile is not None: need(profile==expected,'Mismatched reset profile')
    p=plan()
    image=Path(expected['image'])
    need(sha(image)==expected['image_sha256']==p['image_sha256'],'Exact M6 image profile')
    ledger=read(image)
    snapshot=Path(ledger['snapshot'])
    need(sha(snapshot/'snapshot.json')==expected['snapshot_sha256']==p['snapshot_sha256'],'Exact M6 snapshot')
    build=Path(ledger['simv']).parent
    need(sha(build/'vcs_source_manifest.json')==expected['compiled_manifest_sha256'] and
         sha(build/'simulator.conf')==expected['configuration_sha256'],'Compiled image/config profile')
    for path,digest in expected['rtl_pins'].items():
        need(p['pins'].get(path)==digest and sha(path)==digest,'Reset RTL profile drift: '+path)
    for path,digest in ledger['files'].items():
        need(p['pins'].get(path)==digest and sha(path)==digest,'M6 executable image drift: '+path)
    need(expected['FpgaEn']==0 and expected['regfile']=='ariane_regfile_ff.sv' and
         expected['initial_gpr_values']==[0]*32 and expected['allowed_shape']==SHAPE,'Strict reset semantics')
    return expected,p


class Strict(legacy.Strict):
    def __init__(self,spec,gold,*,profile=None):
        bound,p=validate_profile(profile)
        need(spec==p['specs'][SHAPE],'Only exact original e8 SoC specification accepted')
        model_path=REF/SHAPE/'model.json'
        need(sha(model_path)==p['pins'][str(model_path)] and gold==read(model_path),'Unchanged full4095 oracle')
        elf=Path(spec['backend']['elf'])
        need(sha(elf)==spec['backend']['sha256']==p['pins'][str(elf)],'Unchanged original SoC ELF')
        super().__init__(spec,gold)
        # Only semantic delta: hardware-proven reset values, never observed wdata.
        self.regs=dict(enumerate(bound['initial_gpr_values']))
        self.reset_profile_sha256=PROFILE_SHA


if __name__=='__main__':
    raise SystemExit('PREPARATION ONLY: independent review and main authorization required before offline CSV audit')

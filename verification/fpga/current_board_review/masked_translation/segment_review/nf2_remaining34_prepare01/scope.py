"""Exact archived40 minus two accepted identities and the four live-pilot inputs."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'nf2_remaining4_01'
ARCHIVE=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_segment_fault_handoff01')
EXCLUDED_J2=('u0_s0_b3_m2_f1','u0_s1_b3_m2_f1')
EXCLUDED_PILOT4=('u0_s0_b1_m2_f1','u1_s1_b3_m2_f0','u0_s1_b5_m3_f1','u1_s0_b1_m3_f0')
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def save(path,value):
    with Path(path).open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
def verify(pins):
    for p,h in pins.items():require(sha(p)==h,'Input drift: '+p)

def inventory():
    pins={}
    def pin(path,want=None):
        got=sha(path);require(want is None or got==want,'Archive identity drift: '+str(path))
        pins[str(path)]=got;return got
    ev=ARCHIVE/'evidence'
    pin(ev/'single_manifest.json','97082460c49c616812562991c6a1fd1fee4e516c68538b869d221a2dd2249535')
    pin(ev/'single_board_report.json','48469c93985bab5737ceacb20c04705b0f16e23183643103171e9eb3471e3706')
    pin(ev/'single_symptoms.json')
    manifest=read(ev/'single_manifest.json')['cases'];board=read(ev/'single_board_report.json')['results']
    symptoms=read(ev/'single_symptoms.json')['cases']
    require(len(manifest)==40 and len({c['name'] for c in manifest})==40,'Exact40 unique manifest identities')
    records=[]
    for meta in manifest:
        name=meta['name'];path=ARCHIVE/'singles'/name
        digest=pin(path/'case.json');require(read(path/'case.json')==meta,'Case/manifest metadata differs')
        require(meta['sew']==16 and meta['lmul']=='m1' and meta['scenario_role']=='single_current_oracle_trial',
                'Wrong archived source kind')
        for n,h in meta['scenario_sources'].items():pin(path/n,h)
        pin(path/'scenario.elf',meta['sha256'])
        b=[r for r in board if r['name']==name];sym=[r for r in symptoms if r['name']==name]
        require(len(b)==len(sym)==1 and b[0]['status']=='failed' and b[0]['exit_code']==1 and
                sym[0]['status']=='failed' and sym[0]['confirmed'] is True,'Missing measured standalone failure')
        cfg=dict(meta['selected_trial']);u,s,bound,m,f=[cfg[k] for k in ('unmapped','store','boundary','mode','split')]
        ident=f'u{u}_s{s}_b{bound}_m{m}_f{f}'
        require(name=='rvv_small_fault_segment_nf2_e16_m1_'+ident,'Name/tuple mismatch')
        selector=' && '.join(f'{k if k!="store" else "store_case"}=={v}' for k,v in cfg.items())
        require('if(!('+selector+'))continue;' in (path/'scenario.c').read_text(),'Actual source selector differs')
        mask=0x24 if m==2 else 0
        base=4096-4*bound-2*f
        start=next((i for i in range(8) if mask&(1<<i) and base+4*i+2>=4096),8)
        require(m in (2,3) and start in (2,5,8),'Unsupported source geometry')
        records.append(dict(id=ident,historical_name=name,**cfg,base=base,mask=mask,start=start,fault=start<8,
            case_sha256=digest,source_directory=str(path),elf_sha256=meta['sha256'],
            source_hashes=meta['scenario_sources'],measured_failure=b[0],symptoms=sym[0]))
    require(len({r['case_sha256'] for r in records})==40,'Duplicate actual caseSHA')
    pilot=read(PRIOR/'source_manifest.json')
    require([c['id'] for c in pilot['cases']]==list(EXCLUDED_PILOT4),'Pilot exclusion source identity differs')
    for c in pilot['cases']:
        r=next(r for r in records if r['id']==c['id'])
        require(r['case_sha256']==sha(Path(c['source_directory'])/'case.json'),'Pilot caseSHA mismatch')
    pin(PRIOR/'source_manifest.json');pin(PRIOR/'READY.json','d427f9c9846e0c59d9374efb6fbae020df08c8f6a4472ce740e05ddf4306aa2f')
    pin(HERE.parent/'SELECTION.md');pin(HERE.parent/'sv39/DUT_REPORT.md')
    excluded=set(EXCLUDED_J2+EXCLUDED_PILOT4)
    require(len(excluded)==6 and excluded<={r['id'] for r in records},'Exact distinct six exclusions')
    selected=[r for r in records if r['id'] not in excluded]
    groups=[dict(id=f'group{i//4+1:02d}',runtime_id=f'nf2_remaining34_g{i//4+1:02d}',
                 cases=selected[i:i+4]) for i in range(0,len(selected),4)]
    require(len(selected)==34 and [len(g['cases']) for g in groups]==[4]*8+[2],'Exact34 / nine groups')
    return dict(status='SOURCE_IDENTITIES_VERIFIED_NOT_REFERENCE_OR_DUT',archive_count=40,all_cases=records,
        exclusion_versions=dict(J2='OLD_M2_ACCEPTANCE_NOT_CURRENT_M6',pilot4='M6_ACTIVE_NOT_TERMINAL_ACCEPTED'),
        current_M6_J2_accepted=False,current_M6_closure_requires_existing_J4_same_ELF_replay=True,
        excluded_J2=list(EXCLUDED_J2),excluded_pilot4=list(EXCLUDED_PILOT4),groups=groups,pins=pins,
        current_pilot_status='NOT_QUERIED_NO_ACCEPTANCE_INFERRED',historical_original_parent_byte_identity=False,
        mask_domain=dict(original_bytes=128,fixture_bytes=16,consumed_bytes=8),Linux_signalframe_proved=False)

if __name__=='__main__':
    require(not (HERE/'source_manifest.json').exists(),'New inventory only')
    result=inventory();save(HERE/'source_manifest.json',result)
    for g in result['groups']:
        out=HERE/g['id'];out.mkdir();save(out/'group.json',g)
    print('EXACT40_MINUS6_EQUALS34_GROUPS9',sha(HERE/'source_manifest.json'))

"""Authorized frozen745 prefix + independently qualified FPU reset; no EDA."""
import argparse
from pathlib import Path
import qualify_external_reset_fixture as q

life,require=q.life,q.require
QUAL=q.OUT
QUAL_SHA='2abcf5a4e2fc82b3e1ce05ea5f87b992adb5aa7328087be845de7a2f937e4a85'
OUT=life.OUT/'external-reset-fpu-half-offline-admitted-746-agent-20261007-01'


def merge(before,single):
    require(len(before['tests'])==len(set(before['tests']))==745 and single['tests']==[str(q.run.OUT/'code.vdb')]
            and single['tests'][0] not in before['tests'],'Exact unique745 plus new VDB required')
    result=q.coverage.bitmap.combine(before,single); count=0
    for metric,rows in before['metrics'].items():
        for scope,old in rows.items():
            a=single['metrics'][metric][scope]; b=result['metrics'][metric][scope]
            require(int(b['bits'],16)==(int(old['bits'],16)|int(a['bits'],16)), 'Independent full OR differs')
            count+=1
    require(count==6162 and result['tests']==before['tests']+single['tests'] and len(set(result['tests']))==746,
            'Complete6162 OR/746 prefix differs')
    return result


def check():
    base=life.read_bound(q.BASE/'admission-manifest.json',q.BASE_SHA)
    qual=life.read_bound(QUAL/'qualification.json',QUAL_SHA)
    require(qual['status']=='EXTERNAL_TBPIN_HALF_EX2_WAVE_ARCHITECTURE_PASS_NOT_ADMITTED' and
            qual['software_checks']==679 and qual['full_vrf_bytes']==4096 and qual['csr_words']==5 and
            qual['epoch_count']==2 and qual['axi_all_channels_verified'] is True and
            qual['uvm_check_report_pass'] is False and qual['coverage_admitted'] is False,
            'Exact independent qualification required')
    pins=life.merge_pins(base['input_pins'],base['output_pins'])
    pins=life.merge_pins(pins,qual['output_pins'])
    pins=life.merge_pins(pins,life.read_bound(QUAL/'evidence-pins.json',pins[str(QUAL/'evidence-pins.json')]))
    pins=life.merge_pins(pins,{str(q.BASE/'admission-manifest.json'):q.BASE_SHA,str(QUAL/'qualification.json'):QUAL_SHA})
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_external_reset_half746.py')):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    def read(path): return life.read_bound(path,pins[str(path)])
    status=read(q.BASE/'status.json')
    require(status['aggregate_passed']==745 and status['coverage_admitted'] is True,'Formal745 required')
    before=read(q.BASE/'combined-bits.json'); single=read(QUAL/'single-bits.json')
    require(all(pins.get(p)==sha for p,sha in single['input_hashes'].items()),'Native singleton unbound')
    inputs=(q.BASE/'combined-inputs.txt').read_text().splitlines()
    require(inputs==[str(q.coverage.DESIGN)]+before['tests'],'Exact745 input ledger differs')
    combined=merge(before,single); delta=q.coverage.all_delta(before,combined)
    require(delta==read(QUAL/'raw-delta.json') and delta['metrics']==dict(line=0,cond=3,branch=0,fsm=16),
            'Measured sixteen-FSM/three-condition positive gain differs')
    require(read(QUAL/'recovery-scalar.json')['mismatch'] is None and read(QUAL/'recovery-vector.json')['status']=='PASS',
            'Architecture result differs')
    life.check(pins)
    status=dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=746,baseline=745,new_passed=1,
        exact745_prefix=True,unique_new_vdb=True,full_OR_instances=6162,raw_delta=delta['metrics'],coverage_admitted=True,
        independent_external_reset_wave_and_architecture_pass=True,uvm_check_report_pass=False,
        missing_uvm_summary_preserved=True,official_denominator_verified=False,rtl_changed=False,simulation_rerun=False)
    return pins,{'single-bits.json':single,'combined-bits.json':combined,'raw-delta.json':delta,'status.json':status},inputs+single['tests']


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent-authorized',action='store_true');p.add_argument('--verify-seal')
    args=p.parse_args();require(bool(args.parent_authorized)!=bool(args.verify_seal),'One exact mode required')
    pins,values,inputs=check();texts={'combined-inputs.txt':'\n'.join(inputs)+'\n',
        'single-inputs.txt':str(q.coverage.DESIGN)+'\n'+str(q.run.OUT/'code.vdb')+'\n'}
    if args.verify_seal:
        manifest=life.read_bound(OUT/'admission-manifest.json',args.verify_seal)
        require(manifest['input_pins']==pins and manifest['baseline_seal']==q.BASE_SHA and
                manifest['qualification_seal']==QUAL_SHA and manifest['schema']=='EXTERNAL_TBPIN_HALF746_ADMISSION_V1'
                and manifest['output']==str(OUT) and manifest['explicit_parent_authorized'] is True,'Manifest replay differs')
        require(set(manifest['output_pins'])=={str(OUT/n) for n in (*values,*texts)},'Output inventory differs')
        life.check(manifest['output_pins'])
        for n,v in values.items():require(life.read_bound(OUT/n,manifest['output_pins'][str(OUT/n)])==v,'Output replay differs')
        for n,v in texts.items():require((OUT/n).read_text()==v,'Ledger replay differs')
        print('EXTERNAL_RESET746_OFFLINE_REVERIFIED '+args.verify_seal);return
    require(not OUT.exists(),'Fresh output required');OUT.mkdir()
    for n,v in values.items():life.save(OUT/n,v)
    for n,v in texts.items():
        with (OUT/n).open('x') as f:f.write(v)
    life.check(pins)
    life.save(OUT/'admission-manifest.json',dict(schema='EXTERNAL_TBPIN_HALF746_ADMISSION_V1',output=str(OUT),baseline=str(q.BASE),
        baseline_seal=q.BASE_SHA,qualification=str(QUAL/'qualification.json'),qualification_seal=QUAL_SHA,
        input_pins=pins,output_pins={str(p):life.digest(p) for p in OUT.iterdir()},explicit_parent_authorized=True))
    print('EXTERNAL_RESET746_ADMITTED '+life.digest(OUT/'admission-manifest.json'))


if __name__=='__main__':main()

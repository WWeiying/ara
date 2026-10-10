"""Qualified singleton vs sealed791 raw OR; diagnostic only, never admission."""
import argparse
from pathlib import Path
import json

import scalar_misalign789_soc_width_adapter as adapter

c = adapter.original
life, require = c.life, c.require
BASE = life.OUT/'akv-canonical-kfault-offline-admitted791-agent-20261008-01'
BASE_SHA = '8b732015035c1f716940598f05d8a8063e4b4829eb5cd67cfebcbb2728ee2b30'
QUAL = life.OUT/'scalar-misalign789-soc-qualified-agent-20261008-03'
CORE_SHA = '21d1221c9d2760cacbfe51172771e8842eebc7b59b1bedf9bffa7cc9a0024052'
CLOSURE_SHA = 'eae0cef384adaf5d3a5ec8a225616ffc7c5bfb379cdcf38be9f1d763ac158c86'


def merge_rows(before, sample):
    require(set(before)==set(sample), 'Exact Toggle scope universe')
    after, gains = {}, {}
    for scope,a in before.items():
        b=sample[scope]
        require(type(a['width']) is type(b['width']) is int and a['width']>=0
            and (a['width'],a['checksum'])==(b['width'],b['checksum']), 'Exact Toggle scope shape')
        aa,bb=int(a['bits'],16),int(b['bits'],16)
        require(min(aa,bb)>=0 and max(aa,bb).bit_length()<=a['width'], 'Bounded raw Toggle bitvector')
        after[scope]=dict(a,bits=hex(aa|bb));new=bb&~aa
        if new:gains[scope]=dict(width=a['width'],checksum=a['checksum'],new_directions=bin(new).count('1'))
    return after,gains


def measure(out):
    out=Path(out).absolute()
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Canonical fresh diagnostic')
    q=life.read_bound(QUAL/'qualification.json',CORE_SHA)
    cl=life.read_bound(QUAL/'soc-width-closure.json',CLOSURE_SHA)
    require(cl['core_sha256']==CORE_SHA and cl['core_qualification']==str(QUAL/'qualification.json')
        and q['status']=='SCALAR_MISALIGN789_FULL_SCALAR_SIX_NATIVE_FAULTS_QUALIFIED_NOT_ADMITTED'
        and cl['coverage_admitted'] is q['coverage_admitted'] is False, 'Joint closed qualification')
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    pins={}
    for p in (q['input_pins'],q['output_pins'],cl['input_pins'],cl['output_pins'],base['input_pins'],base['output_pins']):
        pins=life.merge_pins(pins,p)
    for p,h in ((QUAL/'qualification.json',CORE_SHA),(QUAL/'soc-width-closure.json',CLOSURE_SHA),
                (BASE/'admission-manifest.json',BASE_SHA)):
        pins=life.merge_pins(pins,{str(p):h})
    pins[str(Path(__file__).resolve())]=life.digest(Path(__file__))
    pins[str(Path(__file__).with_name('test_measure_scalar_misalign791.py'))]=life.digest(Path(__file__).with_name('test_measure_scalar_misalign791.py'))
    life.check(pins)
    status=life.read_bound(BASE/'status.json',base['output_pins'][str(BASE/'status.json')])
    require(type(status['aggregate_passed']) is int and status['aggregate_passed']==791
        and status['coverage_admitted'] is True, 'Formal791 population')
    before=life.read_bound(BASE/'combined-bits.json',base['output_pins'][str(BASE/'combined-bits.json')])
    bt=life.read_bound(BASE/'combined-toggle-bits.json',base['output_pins'][str(BASE/'combined-toggle-bits.json')])
    run=Path(q['run']); ledger=(BASE/'combined-inputs.txt').read_text().splitlines()
    require(ledger==[str(c.shared.oracle.inventory.BUILD/'sim/simv.vdb'),*before['tests']] and len(before['tests'])==len(set(before['tests']))==791
        and str(run/'code.vdb') not in before['tests'],'Exact791 prefix/new singleton')
    out.mkdir()
    inputs=out/'single-inputs.txt'
    with inputs.open('x') as f:f.write(ledger[0]+'\n'+str(run/'code.vdb')+'\n')
    sample=c.shared.bitmap.collect(inputs)
    require(sample['design']==before['design'] and sample['tests']==[str(run/'code.vdb')]
        and all(pins.get(p)==h for p,h in sample['input_hashes'].items()),'Bound singleton metric bytes')
    after=c.shared.bitmap.combine(before,sample)
    require(after['tests']==before['tests']+sample['tests'] and sum(len(v) for v in after['metrics'].values())==6162,
        'Full6162 exact prefix OR')
    for metric,oldrows in before['metrics'].items():
        require(set(oldrows)==set(sample['metrics'][metric]), 'Exact metric scopes')
        merge_rows(oldrows,sample['metrics'][metric])
    delta=c.shared.bitmap.delta(before,after)
    tglpath=run/'code.vdb/snps/coverage/db/testdata'/c.runner.NAME/'tgl.verilog.data.xml'
    st,sha=c.oracle.review.toggle.rows(tglpath,set(bt))
    require(pins.get(str(tglpath))==sha,'Qualified Toggle bytes')
    at,tg=merge_rows(bt,st)
    target=life.read_bound(c.runner.PRE/'target-before.json',q['input_pins'][str(c.runner.PRE/'target-before.json')])
    fields=[]
    for field in target['fields']:
        scope=field['scope'];start=field['serialized_field_offset'];old,new=bt[scope],st[scope]
        require(old['checksum']==new['checksum']==field['checksum'],'Compiled target checksum')
        gained=[i for i in range(start,start+128) if int(new['bits'],16)>>(new['width']-1-i)&1
            and not int(old['bits'],16)>>(old['width']-1-i)&1]
        fields.append(dict(scope=scope,name=field['name'],checksum=field['checksum'],gained=gained))
    for name,value in (('single-bits.json',sample),('combined-bits.json',after),('raw-delta.json',delta),
                       ('combined-toggle-bits.json',at),('typed-target-gain791.json',fields)):
        life.save(out/name,value)
    life.check(pins)
    system='ara_tb.dut.i_ara_soc.i_system'
    result=dict(status='SCALAR_MISALIGN_791_RELATIVE_GAIN_DIAGNOSTIC_NOT_ADMITTED',baseline=791,
        baseline_seal=BASE_SHA,core_sha256=CORE_SHA,closure_sha256=CLOSURE_SHA,input_pins=pins,
        output_pins={str(p):life.digest(p) for p in out.iterdir() if p.is_file()},four_metrics=delta['metrics'],
        Toggle_all_scopes=sum(v['new_directions'] for v in tg.values()),
        Toggle_system=sum(v['new_directions'] for s,v in tg.items() if s==system or s.startswith(system+'.')),
        target_new_directions=sum(len(f['gained']) for f in fields),Toggle_scope_gains=tg,
        actual_serialized_directions_not_official_percentage=True,coverage_admitted=False,EDA_launched=False)
    life.save(out/'gain-receipt.json',result)
    print(json.dumps({k:result[k] for k in ('four_metrics','Toggle_all_scopes','Toggle_system','target_new_directions')}))
    print('seal '+life.digest(out/'gain-receipt.json'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    measure(p.parse_args().output)

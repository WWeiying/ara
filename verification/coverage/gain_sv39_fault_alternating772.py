"""Fresh772 diagnostic: sealed baseline plus one already-qualified fault VDB."""
import argparse
from pathlib import Path
import collect_sv39_fault_alternating771_completed as q

life,require=q.life,q.require
BASE=life.OUT/'scalar-fpu-backpressure-offline-admitted-772-agent-20261007-01'
BASE_SHA='28cc362f64c2c48e8a3b8a1dbf568903434464cc4dcea7e2dfad2aae282ca332'
QUAL=life.OUT/'sv39-fault-alternating-full-qualified771-agent-20261007-01/qualification.json'
QUAL_SHA='4b67bcf6d8ca43e732a80bc620c05fc8d92443d7330b3a2cec227efe4c1ad04a'
old=q.csr.old

def design_contract(before,design,manifest):
    pins={}
    require(set(before['design'])=={'design/verilog.design.xml',*[f'shape/{m}.verilog.shape.xml' for m in old.bitmap.METRICS]},
      'Exact four-metric compiled design shape set')
    for name,h in before['design'].items():
        path=design/'snps/coverage/db'/name
        require(manifest['input_pins'].get(str(path))==h and life.digest(path)==h,'Sealed compile design/shape hash: '+name)
        pins[str(path)]=h
    return pins

def collect(output):
    require(not output.exists(),'Fresh diagnostic, never admission')
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(base['coverage_admitted'] is True and base['baseline_seal']==old.p.BASE_SHA,'Exact admitted772 from771')
    pins={str(BASE/'admission-manifest.json'):BASE_SHA,str(QUAL):QUAL_SHA}
    def bound(name):
        path=BASE/name;h=base['output_pins'][str(path)]
        require(life.digest(path)==h,'772 product drift');pins[str(path)]=h;return path
    before=life.read_bound(bound('combined-bits.json'),pins[str(BASE/'combined-bits.json')])
    ledger=bound('combined-inputs.txt').read_text().splitlines()
    prior=(old.p.BASE/'combined-inputs.txt').read_text().splitlines()
    require(len(ledger)==len(set(ledger))==773 and ledger[:-1]==prior and before['tests']==ledger[1:],
      '772 exact771 prefix+one; tests excludes compiled VDB')
    design=Path(ledger[0]);pins=life.merge_pins(pins,design_contract(before,design,base))
    qualified=life.read_bound(QUAL,QUAL_SHA);life.check(qualified['input_pins'])
    require(qualified['status']=='FULL_SCALAR_VECTOR_EXACT_FAULT_MEMORY_CSR_GUARDS_PASS_NOT_ADMITTED'
      and qualified['run']==str(q.csr.prefix.RUN) and qualified['baseline']==771 and
      qualified['baseline_seal']==old.p.BASE_SHA and qualified['coverage_admitted'] is False,'Exact prior full architecture qualification')
    candidate=q.csr.prefix.RUN/'code.vdb';require(str(candidate) not in ledger,'No duplicate VDB')
    pins=life.merge_pins(pins,qualified['input_pins'])
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_gain_sv39_fault772.py')):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    manifest=life.read_bound(q.csr.prefix.RUN.with_name(q.csr.prefix.RUN.name+'.prepared.json'),q.csr.prefix.RUN_SHA)
    output.mkdir();inputs=output/'single-inputs.txt'
    with inputs.open('x') as f:f.write(str(design)+'\n'+str(candidate)+'\n')
    single=old.bitmap.collect(inputs)
    require(single['design']==before['design'],'Actual candidate compiled design compatible')
    combined=old.bitmap.combine(before,single);delta=old.bitmap.delta(before,combined)
    # Only the one newly-admitted772 suffix is appended to the already-sealed771
    # scoped union. No historical population re-collection or EDA.
    scoped=manifest['scoped_toggle_before'];paths=list((Path(ledger[-1])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(paths)==1,'Unique772 suffix Toggle')
    sample,h=old.toggle.rows(paths[0],list(scoped))
    require(base['input_pins'].get(str(paths[0]))==h,'772 suffix native pin');pins[str(paths[0])]=h
    scoped=old.toggle.union(scoped,sample)
    paths=list((candidate/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(paths)==1,'One candidate Toggle');sample,h=old.toggle.rows(paths[0],list(scoped))
    require(qualified['input_pins'].get(str(paths[0]))==h,'Qualified native Toggle hash')
    gains=old.toggle.gains(scoped,old.toggle.union(scoped,sample))
    for name,value in (('single-bits.json',single),('proposed-combined-bits.json',combined),
      ('raw-delta.json',delta),('scoped-toggle-gain.json',gains)):life.save(output/name,value)
    pins=life.merge_pins(pins,single['input_hashes']);life.check(pins)
    result=dict(status='QUALIFIED_SINGLE_FAULT_RAW772_DIAGNOSTIC_NOT_ADMITTED',baseline=772,baseline_seal=BASE_SHA,
      qualification=str(QUAL),qualification_seal=QUAL_SHA,compiled_design=str(design),candidate=str(candidate),
      metrics=delta['metrics'],scoped_binary_toggle_gain=sum(len(p) for p in gains.values()),input_pins=pins,
      output_pins={str(p):life.digest(p) for p in output.iterdir() if p.is_file()},
      coverage_admitted=False,EDA_launched=False,official_percentage=None,
      caveat='Raw serialized positions, not native direction IDs; custom-scope broadcast inputs do not prove custom transactions.')
    life.save(output/'diagnostic.json',result);print('DIAGNOSTIC_PASS '+life.digest(output/'diagnostic.json'),result['metrics'],result['scoped_binary_toggle_gain'],flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--output',type=Path,required=True)
    collect(a.parse_args().output.resolve())

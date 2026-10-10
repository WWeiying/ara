"""Population-only765 successor, unchanged reviewed764 native scope and audits."""
import argparse
import inspect
from pathlib import Path
from types import FunctionType

import report_native_batch764 as predecessor
import run_native_batch764_entry as metadata

life, require, merge = predecessor.life, predecessor.require, predecessor.merge
HERE = Path(__file__).resolve().parent
TCL = predecessor.TCL
SCHEMA = 'FORMAL765_RETAINED763_VMFPU10_SLDU2_C910240_V1'
MANIFEST = life.OUT/'vmfpu-ured-reset-offline-admitted-765-agent-20261007-01/admission-manifest.json'
MANIFEST_SHA = '834b457b607b9b73b21e4e2c8decaf5140d8e23cd8cc04c04bc7267d592d757c'


def full_or(before,bits,single):
    require(len(before['tests'])==764 and bits['tests'][:-1]==before['tests'] and
            len(bits['tests'])==len(set(bits['tests']))==765 and single['tests']==bits['tests'][-1:] and
            bits['design']==before['design']==single['design'],'Exact764 prefix/design differs')
    require(set(bits['metrics'])==set(before['metrics'])==set(single['metrics']),'Metric family differs')
    count=0
    for metric,rows in before['metrics'].items():
        require(set(rows)==set(bits['metrics'][metric])==set(single['metrics'][metric]),'Full hierarchy differs')
        count+=len(rows)
        for scope,p in rows.items():
            now,one=bits['metrics'][metric][scope],single['metrics'][metric][scope]
            require((p['width'],p['checksum'])==(now['width'],now['checksum'])==(one['width'],one['checksum']),
                    'Compiled shape differs')
            require(int(now['bits'],16)==int(p['bits'],16)|int(one['bits'],16) and
                    int(now['bits'],16).bit_length()<=now['width'],'Full OR/overflow differs')
    require(count==6162,'Not full6162')


def population(original):
    ledger764,_,pins=predecessor.population(original)
    b=life.read_bound(MANIFEST,MANIFEST_SHA)
    require(b['schema']=='EXACT764_PLUS_ONE_URED_RESET765_V1' and b['output']==str(MANIFEST.parent) and
            b['baseline']==str(predecessor.prep.MANIFEST.parent) and b['baseline_seal']==predecessor.prep.MANIFEST_SHA and
            b['coverage_admitted'] is True,'Exact formal765 authority differs')
    pins=merge(pins,b['input_pins'],b['output_pins'],{str(MANIFEST):MANIFEST_SHA})
    def read(name):
        path=MANIFEST.parent/name
        require(str(path) in b['output_pins'],'Unsealed formal765 output')
        return life.read_bound(path,b['output_pins'][str(path)])
    beforepath=predecessor.prep.MANIFEST.parent/'combined-bits.json'
    require(str(beforepath) in pins,'Unsealed764 bitmap')
    before=life.read_bound(beforepath,pins[str(beforepath)])
    bits=read('combined-bits.json'); full_or(before,bits,read('single-bits.json'))
    s=read('status.json')
    require(s['aggregate_passed']==765 and s['coverage_admitted'] is True and s['exact764_prefix'] is True and
            s['full_OR_instances']==6162 and s['raw_delta']==dict(line=0,cond=0,branch=0,fsm=4),
            'Formal765 admission status differs')
    ledger=(MANIFEST.parent/'combined-inputs.txt').read_text().splitlines()
    require(ledger[:-1]==ledger764 and ledger==[original['input_ledger'][0],*bits['tests']], 'Exact ledger prefix differs')
    selected=[str(Path(db).with_suffix('')/test.name) for db in ledger
              for test in sorted((Path(db)/'snps/coverage/db/testdata').glob('*')) if test.is_dir()]
    require(len(selected)==len(set(selected))==765,'Actual765 population differs')
    life.check(pins)
    return ledger,selected,pins


def snapshot_stdout(data,out):
    predecessor.snapshot_stdout(data,out)
    data.update(population=765, raw_population_fsm_gain=4, exact764prefix=True,
                formal765_manifest_seal=MANIFEST_SHA)


def namespace():
    ns=dict(vars(predecessor),__file__=__file__,SCHEMA=SCHEMA,HERE=HERE,TCL=TCL,population=population,
            snapshot_stdout=snapshot_stdout)
    body=inspect.getsource(predecessor.prepare)
    changes={
        'population=764':'population=765',
        'manifest=str(prep.MANIFEST), seal=prep.MANIFEST_SHA':'manifest=str(MANIFEST), seal=MANIFEST_SHA',
        "HERE/'test_report_native_batch764.py'":"HERE/'test_report_native_batch765.py'",
        "Path(prior.__file__).resolve()]":"Path(prior.__file__).resolve(), Path(predecessor.__file__).resolve(),\n"
            "            Path(metadata.__file__).resolve(), HERE/'test_report_native_batch764.py']",
    }
    for old,new in changes.items():
        require(old in body,'Exact765 prepare adapter anchor differs: '+old)
        body=body.replace(old,new)
    ns.update(MANIFEST=MANIFEST,MANIFEST_SHA=MANIFEST_SHA,predecessor=predecessor,metadata=metadata)
    exec(compile(body,__file__,'exec'),ns)
    body=inspect.getsource(predecessor.check)
    for old,new in {"c['population'] == 764":"c['population'] == 765",
                    "c['admission']['seal'] == prep.MANIFEST_SHA":"c['admission']['seal'] == MANIFEST_SHA",
                    '== 764,':'== 765,'}.items():
        require(old in body,'Exact765 check adapter anchor differs');body=body.replace(old,new)
    exec(compile(body,__file__,'exec'),ns)
    runtime=predecessor.namespace()
    ns.update({k:v for k,v in runtime.items() if k not in ns})
    exec(compile(metadata.verifier_body(),__file__,'exec'),ns)
    ns['run']=FunctionType(runtime['run'].__code__,ns)
    return ns


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','check','run','verify'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');a=p.parse_args()
    ns=namespace();out=a.output.resolve()
    if a.mode=='prepare':ns['prepare'](out)
    else:
        require(a.seal,'Sealed config required');ns[a.mode](out,a.seal)
        if a.mode=='check':print('BATCH765_CHECK_PASS_NO_EDA')

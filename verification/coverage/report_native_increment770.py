"""Thin formal770 population adapter; frozen full768/769 native gates retained."""
import argparse
import inspect
from pathlib import Path
from types import FunctionType

import report_native_increment769 as frozen

life,require=frozen.life,frozen.require
HERE=Path(__file__).resolve().parent
TCL=Path(__file__).with_suffix('.tcl')
SCHEMA='FORMAL770_INCREMENT_QUALIFIED768_LZC_QUEUE312_V1'
FROZEN_SHA='a46835f564f0aff9de7b1269c9fa62b0cce9c14e713194581ff357707fc52d7f'


def manifest_gate(path,seal):
    require(path.is_file() and path.name=='admission-manifest.json' and path.parent.parent==life.OUT
            and isinstance(seal,str) and len(seal)==64 and all(c in '0123456789abcdef' for c in seal),
            'HOLD: explicit sealed formal770 manifest absent')
    book=life.read_bound(path,seal)
    require(book['coverage_admitted'] is True and book['baseline']==str(frozen.FORMAL)
            and book['baseline_seal']==frozen.MANIFEST_SHA,'Only admitted770 exact formal769 baseline')
    pins=frozen.base.merge(book['input_pins'],book['output_pins'],{str(path):seal})
    formal=path.parent
    status=life.read_bound(formal/'status.json',pins[str(formal/'status.json')])
    require(status['coverage_admitted'] is True and type(status['aggregate_passed']) is int
            and status['aggregate_passed']==770,'Formal770 status, not candidate or relabelled769')
    return book,pins


def population(original,manifest,seal):
    _,pins=manifest_gate(manifest,seal)
    previous,selected,oldpins=frozen.population(original)
    pins=frozen.base.merge(oldpins,pins)
    formal=manifest.parent
    def bound(p):return life.read_bound(p,pins[str(p)])
    bits=bound(formal/'combined-bits.json')
    frozen.base.full_or(bound(frozen.FORMAL/'combined-bits.json'),bits,bound(formal/'single-bits.json'),770)
    path=formal/'combined-inputs.txt';require(life.digest(path)==pins[str(path)],'Actual770 ledger pin')
    ledger=path.read_text().splitlines()
    require(ledger[:-1]==previous and ledger==[ledger[0],*bits['tests']], 'Full ordered769 prefix and unique770')
    selected=[str(Path(db).with_suffix('')/p.name) for db in ledger for p in
              sorted((Path(db)/'snps/coverage/db/testdata').glob('*')) if p.is_dir()]
    require(len(selected)==len(set(selected))==770,'All770 tests exact and unique')
    life.check(pins)
    return ledger,selected,pins


def context(manifest,seal):
    require(life.digest(frozen.__file__)==FROZEN_SHA,'Frozen769 adapter source drift')
    ns=dict(vars(frozen),__file__=__file__,HERE=HERE,TCL=TCL,SCHEMA=SCHEMA,
            FORMAL=manifest.parent,MANIFEST=manifest,MANIFEST_SHA=seal)
    ns['population']=lambda original:population(original,manifest,seal)
    def private():
        inner=FunctionType(frozen.private_namespace.__code__,ns)()
        body=inspect.getsource(frozen.base.check)
        anchor="require(item['local_qualified'] == (key != 'csr1193'), 'Separate qualification origins')"
        require(body.count(anchor)==1,'Frozen origin anchor changed')
        body=body.replace(anchor,'origin_gate(key,item)').replace("c['population'] == 768","c['population'] == 770")
        body=body.replace('== 768\n','== 770\n')
        exec(compile(body,__file__,'exec'),inner)
        return inner
    ns['private_namespace']=private
    # Rebind the same substantive verify/run and exact host walker, not a permissive wrapper.
    body=inspect.getsource(frozen.namespace).replace('population=769','population=770')
    body=body.replace('formal769_manifest_seal','formal770_manifest_seal')
    exec(compile(body,__file__,'exec'),ns)
    ns['rehearsal']=FunctionType(frozen.rehearsal.__code__,ns)
    body=inspect.getsource(frozen.prepare).replace('population=769','population=770')
    anchor="HERE/'test_report_native_increment769.py'"
    require(body.count(anchor)==1,'Frozen prepare dependency anchor changed')
    body=body.replace(anchor,"HERE/'test_report_native_increment770.py', Path(frozen.__file__), frozen.TCL")
    ns['frozen']=frozen
    exec(compile(body,__file__,'exec'),ns)
    return ns


def prepare(out,manifest,seal,predecessor_seal):
    manifest_gate(manifest,seal)  # Missing770 rejects before predecessor or output creation.
    context(manifest,seal)['prepare'](out,frozen.PREDECESSOR/'qualification.json',predecessor_seal)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','check','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--manifest-seal',required=True);p.add_argument('--seal');p.add_argument('--predecessor-seal')
    p.add_argument('--authorize-reviewed-run',action='store_true')
    p.add_argument('--authorize-source-first-full-session',action='store_true');a=p.parse_args()
    out=a.output.resolve();manifest=a.manifest.resolve()
    if a.mode=='prepare':prepare(out,manifest,a.manifest_seal,a.predecessor_seal)
    else:
        manifest_gate(manifest,a.manifest_seal)
        ns=context(manifest,a.manifest_seal)['namespace']()
        if a.mode=='run':frozen.inherited.authorize(a.authorize_reviewed_run,a.authorize_source_first_full_session)
        require(a.seal,'Exact runtime config seal');ns[a.mode](out,a.seal)

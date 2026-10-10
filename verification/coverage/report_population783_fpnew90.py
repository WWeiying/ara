"""One formal783 report, existing9700 plus qualified90 fields. No auto launch."""
import argparse
import json
from pathlib import Path
import re
from types import FunctionType

import report_population_plus9700 as prior
import fpnew_tied90_local as native

stable,life,need=prior.stable,prior.life,prior.need
HERE=Path(__file__).resolve().parent
BASE=life.OUT/'qbs-k2-pending-offline-admitted783-agent-20261008-01/admission-manifest.json'
BASE_SHA='8d0d58bf873e0b0f4c601d1e9fb88fca74babb572f822a0580967eef9e5d23f0'
LOCAL=life.OUT/'fpnew-tied90-local-prepared781-parent-20261008-02'
LOCAL_CONFIG_SHA='dc049f1066dc8c6451b981ed9323edc3e3a6e422ad69d055a805733cad9cc71d'
SCHEMA='EXACT_FORMAL783_QUALIFIED9700_FPNEW8520_REPORT_V1'


def receipt_gate(q):
    need(q['status']=='FPNEW_TIED90_LOCAL_NATIVE_QUALIFIED_NOT_APPLIED' and
         q['config_seal']==LOCAL_CONFIG_SHA and q['fields']==90 and q['directions']==8520 and
         q['terminal_returncode']==0 and q['stages']==list(native.STAGES) and
         q['population_application'] is False,'Only actual parent02 full five-stage qualification')


def local(reader,receipt_sha):
    path=LOCAL/'capture-result.json'
    need(path.is_file(),'HOLD: parent02 qualification receipt absent; before-only is not qualification')
    need(type(receipt_sha) is str and len(receipt_sha)==64 and all(c in '0123456789abcdef' for c in receipt_sha),
         'Explicit parent-reviewed receipt SHA required')
    q=reader.read(path,receipt_sha,True);receipt_gate(q)
    c=reader.read(LOCAL/'config.json',LOCAL_CONFIG_SHA,True)
    # Substantive full replay, not status-only reuse; frozen verifier is idempotent.
    need(native.verify(LOCAL,LOCAL_CONFIG_SHA)==q,'Exact local replay differs from sealed receipt')
    pins=stable.merge(q['pins'],c['pins'])
    first=reader.read(LOCAL/'first.el',pins[str(LOCAL/'first.el')]).decode('ascii')
    second=reader.read(LOCAL/'second.el',pins[str(LOCAL/'second.el')]).decode('ascii')
    need(native.el_gate(first,c)==native.el_gate(second,c),'Full90 semantic reload')
    reader.finish(pins)
    return second,stable.merge(pins,{str(path):receipt_sha,str(LOCAL/'config.json'):LOCAL_CONFIG_SHA}),c


def union_gate(base,addition):
    old=stable.semantic(base);extra=stable.semantic(addition)
    occupied=prior.frozen.physical(old);targets=prior.frozen.physical(extra)
    need(not extra[0] and sum(bin(v).count('1') for v in targets.values())==8520,'Exact8520 Toggle-only addition')
    headers={r for r in old[0] if exact_fsm_header(r)}
    opaque=[r for r in old[0] if not exact_fsm_record(r,headers)]
    for key,mask in targets.items():
        scope,checks,name,prefix,direction=key
        need(not any(scope==r[0] or scope.startswith(r[0]+'.') for r in opaque),'Opaque/whole ancestor collision')
        for previous,value in occupied.items():
            if previous[0]!=scope:continue
            # Checksums must not create distinct ownership for the same scope.
            need(previous[1]==checks,'Same-scope checksum fingerprint collision')
            if name==previous[2] and prefix==previous[3] and direction==previous[4]:
                need(not value&mask,'Already-owned physical direction')
            need(not (name.startswith(previous[2]+'.') or previous[2].startswith(name+'.')),
                 'Packed parent/child field ownership collision')
    combined=base.rstrip('\n')+'\n'+addition.rstrip('\n')+'\n'
    actual=stable.semantic(combined);want=dict(occupied)
    for key,mask in targets.items():want[key]=want.get(key,0)|mask
    need(actual[0]==old[0] and prior.frozen.physical(actual)==want,'Exact prior EL preservation and disjoint union')
    return combined


def exact_fsm_header(record):
    scope,checks,machine,line=record
    match=re.fullmatch(r'Fsm ([^\s"]+) "(\d+)"',line)
    checksum=re.fullmatch(r'(\d+) (\d+)',checks)
    return bool(scope and machine=='' and match and checksum and match[2]==checksum[2])


def exact_fsm_record(record,headers):
    if record in headers:return True
    scope,checks,machine,line=record
    if (scope,checks,'',machine) not in headers:return False
    return bool(re.fullmatch(r'State [^\s"]+ "\d+"',line) or
                re.fullmatch(r'Transition [^\s"<>]+->[^\s"<>]+ "\d+->\d+"',line))


def suffix_zero(reader,source,pins,chain,config):
    proof=reader.read(native.SOURCE,native.SOURCE_SHA,True)
    by_scope={i['scope']:i for i in config['instances']}
    groups={}
    for row in proof['candidates']:groups.setdefault(row['scope'],[]).extend(row['coordinates'])
    audits=[]
    for record in chain:
        if record['population']<=781:continue
        folder=Path(record['new_vdb'])/'snps/coverage/db/testdata'
        paths=list(folder.glob('*/tgl.verilog.data.xml'))
        need(len(paths)==1,'One explicit admitted suffix Toggle file')
        path=paths[0];need(str(path) in pins,'Suffix native raw ownership')
        reader.read(path,pins[str(path)])
        rows,sha=native.proof.rank.t.rows(path,set(groups))
        need(sha==pins[str(path)] and set(rows)==set(groups),'Exact suffix scopes and SHA')
        for scope,positions in groups.items():
            i=by_scope[scope]
            width=sum(2*(1 if n['kind']=='node' else abs(int(n['left'])-int(n['right']))+1)
                      for n in i['typed_objects'] if n['kind'] in ('node','vectornode'))
            prior.prior.zero_row(rows[scope],width,i['toggle_checksum'],positions)
        audits.append(dict(population=record['population'],path=str(path),sha256=sha,targets90_zero=True))
    need([r['population'] for r in audits]==[782,783],'Exact781-to783 native zero recheck')
    return audits


def context(receipt_sha):
    def approved(reader,manifest,seal):
        need(manifest==BASE and seal==BASE_SHA,'Exact formal783; no population relabel/fork')
        source,pins,text,bits,chain,activity=prior.approved(reader,manifest,seal)
        need(len(bits['tests'])==783 and len(source['input_ledger'])==784 and
             len(source['expected_selected'])==783,'Full783 ledger/design population')
        extra,more,config=local(reader,receipt_sha)
        audit=suffix_zero(reader,source,pins,chain,config)
        return source,stable.merge(pins,more),union_gate(text,extra),bits,chain,dict(activity,fpnew90=audit)
    def dependencies():
        return stable.merge(prior.dependencies(),{str(Path(__file__).resolve()):life.digest(__file__),
            str(HERE/'test_report_population783_fpnew90.py'):life.digest(HERE/'test_report_population783_fpnew90.py'),
            str(HERE/'test_report_population783_metric_collision.py'):life.digest(HERE/'test_report_population783_metric_collision.py')})
    def metadata():
        old=prior.metadata()
        return dict(old,additional_direction_count=18220,
            local_qualifications=[*old['local_qualifications'],dict(family='FPNEW90',path=str(LOCAL/'capture-result.json'),
                sha256=receipt_sha,config_seal=LOCAL_CONFIG_SHA,directions=8520)],
            protection_basis=old['protection_basis']+'; FPNEW90 exact70 scopes/full3196 object complement; no other rounding fields')
    namespace=dict(prior.frozen.prepare.__globals__,__file__=__file__,BASE=BASE,BASE_SHA=BASE_SHA,
                   SCHEMA=SCHEMA,approved=approved,dependencies=dependencies,metadata=metadata)
    check=FunctionType(prior.frozen.check.__code__,namespace)
    verify=FunctionType(prior.frozen.verify.__code__,dict(namespace,check=check))
    run=FunctionType(prior.frozen.run.__code__,dict(namespace,check=check,verify=verify))
    def prepare(out,unit):
        # Fail before any output creation when no completed local receipt exists.
        local(stable.Reader(),receipt_sha)
        return FunctionType(prior.frozen.prepare.__code__,namespace)(out,unit)
    return prepare,check,verify,run


def runtime(out,seal):
    c=stable.Reader().read(out/'config.json',seal,True)
    need(c['schema']==SCHEMA and c['population']==783,'Exact783 runtime entry')
    matches=[q for q in c['local_qualifications'] if q['family']=='FPNEW90']
    need(len(matches)==1 and matches[0]['path']==str(LOCAL/'capture-result.json') and
         matches[0]['config_seal']==LOCAL_CONFIG_SHA,'Exact local receipt identity')
    return context(matches[0]['sha256'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','check','verify','run-reviewed'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--receipt-seal');p.add_argument('--seal')
    p.add_argument('--service-unit');p.add_argument('--parent-reviewed-seal');a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':
        need(a.receipt_seal and a.service_unit and not a.seal and not a.parent_reviewed_seal,'Host prepare, explicit receipt and unit')
        context(a.receipt_seal)[0](out,a.service_unit)
    else:
        need(a.seal and not a.receipt_seal and not a.service_unit,'Sealed runtime only')
        functions=runtime(out,a.seal)
        if a.mode=='check':functions[1](out,a.seal);print('CHECK_PASS_NO_EDA')
        elif a.mode=='verify':functions[2](out,a.seal)
        else:functions[3](out,a.seal,a.parent_reviewed_seal)

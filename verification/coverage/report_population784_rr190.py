"""Formal785-only consumer (historical filename), no intermediate784 report."""
import argparse
from pathlib import Path
from types import FunctionType
import report_population783_classpadding as previous
import report_current_population as population
import rr_disabled190_local as native

stable, life, need = previous.stable, previous.life, previous.need
HERE = Path(__file__).resolve().parent
REPORT = life.OUT/'current-population783-classpadding-parent-20261008-01'
REPORT_SHA = '1250b130e7b16a0f883b098dc6559752506858971be73324810573b58d55202e'
REPORT_QUAL_SHA = '827565bba59ccf990845367f102cb1ecc6a0ebb68b5eb2b044c3e411c67e6100'
LOCAL = life.OUT/'rr-disabled190-local-prepared783-agent-20261008-01'
LOCAL_SHA = '1bb663d10d36b8040b5000b1ff301d93095bc5f983f143054a9001ffd40033b4'
LOCAL_QUAL_SHA = '303c6e64596d0cfb7dd6bcc201dadecb2673471633a178fadc19bc28c4957152'
SCHEMA = 'FORMAL785_EXISTING23536_PLUS_RR190_22528_V1'
FORMAL784 = life.OUT/'fclass-divsqrt-offline-admitted784-agent-20261008-01/admission-manifest.json'
FORMAL784_SHA = '721845f0b7423db3346fbf62f77970351a1640eefc8e2a87a307f3e0ec95bb4e'
engine = previous.engine


def inherited(reader):
    q = reader.read(REPORT/'qualification.json', REPORT_QUAL_SHA, True)
    c = reader.read(REPORT/'config.json', REPORT_SHA, True)
    need(q['status']=='CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED' and
         q['config_seal']==REPORT_SHA and q['admission_seal']==previous.BASE_SHA and
         q['population']==q['actual_selected_tests']==c['population']==783 and
         c['schema']==previous.SCHEMA and c['additional_direction_count']==23536,
         'Exact completed parent783 class-padding authority')
    need(all(q[k] is True for k in ('complete_approved_EL_bitmask_union','all_other_bits_protected',
         'raw_reset_final_equal','applied_reloaded_equal','raw_hierarchy_vs_rooted_six_metrics_equal',
         'supported_roots_all_six_metrics_present','historical_PASS_only_no_new_RTL_signoff')) and
         q['source_design_native_pins']==c['pins'], 'Complete inherited five-stage protection')
    pins = stable.merge(c['pins'], q['output_pins'],
        {str(REPORT/'qualification.json'):REPORT_QUAL_SHA,str(REPORT/'config.json'):REPORT_SHA})
    blobs = [reader.read(REPORT/n,pins[str(REPORT/n)]).decode('ascii')
             for n in ('combined.el','applied.el','reloaded.el')]
    need(all(stable.semantic_seal(stable.semantic(t))==c['expected_EL_semantic_sha256'] for t in blobs),
         'Full inherited EL semantics')
    for n in ('initial-empty.el','reset-empty.el','final-empty.el','cleanup-empty.el'):
        need(reader.read(REPORT/n,pins[str(REPORT/n)])==b'', 'Inherited empty states')
    return c,pins,blobs[0]


def local(reader):
    q = reader.read(LOCAL/'capture-result.json',LOCAL_QUAL_SHA,True)
    c = reader.read(LOCAL/'config.json',LOCAL_SHA,True)
    need(q['status']=='RR_DISABLED190_LOCAL_NATIVE_QUALIFIED_NOT_APPLIED' and
         q['config_seal']==LOCAL_SHA and (q['fields'],q['directions'],q['protected_objects'])==(190,22528,5160)
         and type(q['terminal_returncode']) is int and q['terminal_returncode']==0 and
         q['stages']==list(native.STAGES) and q['population_application'] is False,
         'Exact parent-reviewed RR190 qualification')
    need(native.verify(LOCAL,LOCAL_SHA)==q,'Unchanged local full verifier replay')
    pins = stable.merge(c['pins'],q['pins'],
        {str(LOCAL/'config.json'):LOCAL_SHA,str(LOCAL/'capture-result.json'):LOCAL_QUAL_SHA})
    blobs = [reader.read(LOCAL/n,pins[str(LOCAL/n)]).decode('ascii') for n in ('first.el','second.el')]
    need(native.el_gate(blobs[0],c)==native.el_gate(blobs[1],c),'Exact190 semantic reload')
    return c,pins,blobs[1]


def union_gate(base, addition, config):
    native.el_gate(addition,config)
    old, extra = stable.semantic(base), stable.semantic(addition)
    occupied, targets = engine.physical(old), engine.physical(extra)
    need(not extra[0] and sum(bin(v).count('1') for v in targets.values())==22528,
         'Exact RR190 Toggle-only physical membership')
    headers = {r for r in old[0] if previous.previous.exact_fsm_header(r)}
    opaque = [r for r in old[0] if not previous.previous.exact_fsm_record(r,headers)]
    for key,mask in targets.items():
        scope,checks,name,prefix,direction = key
        need(not any(scope==r[0] or scope.startswith(r[0]+'.') for r in opaque),
             'Opaque whole ancestor collision')
        for prior,value in occupied.items():
            if prior[0]!=scope: continue
            need(prior[1]==checks,'Same physical scope checksum conflict')
            if prior[2:]==(name,prefix,direction):
                need(not value&mask,'Already-owned physical direction')
            need(not(name.startswith(prior[2]+'.') or prior[2].startswith(name+'.')),
                 'Packed parent/child ownership collision')
    text = base.rstrip('\n')+'\n'+addition.rstrip('\n')+'\n'
    actual = stable.semantic(text); expected = dict(occupied)
    for key,mask in targets.items(): expected[key]=expected.get(key,0)|mask
    need(actual[0]==old[0] and engine.physical(actual)==expected,
         'All old non-Toggle and physical masks preserved')
    return text


def target_groups(proof, config, coordinates):
    instances = {i['scope']:i for i in config['instances']}
    groups = {}
    for row in proof['candidates']:
        scope = row['scope']; i = instances[scope]
        width = sum(2*(1 if n['kind']=='node' else abs(int(n['left'])-int(n['right']))+1)
                    for n in i['typed_objects'] if n['kind'] in ('node','vectornode'))
        entry = groups.setdefault(scope,dict(width=width,checksum=i['toggle_checksum'],positions=[]))
        entry['positions'].extend(row[coordinates])
    for entry in groups.values():
        need(len(entry['positions'])==len(set(entry['positions'])),'Duplicate source-zero coordinates')
    return groups


def suffix_chain(chain):
    suffix = [r for r in chain if r['population']>783]
    need([r['population'] for r in suffix]==[784,785],
         'Exact consecutive fclass784 and VALU785 formal suffixes')
    need(suffix[0]['manifest']==str(FORMAL784) and suffix[0]['seal']==FORMAL784_SHA,
         'Exact parent-admitted fclass784 ancestor, not a parallel fork')
    return suffix


def suffix_rows(rows, families):
    scopes = {s for _,groups in families for s in groups}
    need(set(rows)==scopes,'Exact suffix native scope inventory')
    for _,groups in families:
        for scope,g in groups.items():
            population.zero_row(rows[scope],g['width'],g['checksum'],g['positions'])


def suffix_zero(reader, pins, chain, rr_config):
    rr = reader.read(native.SOURCE,native.SOURCE_SHA,True)
    native.source_gate(rr)
    class_config = reader.read(previous.LOCAL/'config.json',previous.LOCAL_CONFIG_SHA,True)
    class_proof = reader.read(previous.native.SOURCE,previous.native.SOURCE_SHA,True)
    fp = previous.previous.native
    fp_config = reader.read(previous.previous.LOCAL/'config.json',previous.previous.LOCAL_CONFIG_SHA,True)
    fp_proof = reader.read(fp.SOURCE,fp.SOURCE_SHA,True)
    families = [('RR190',target_groups(rr,rr_config,'missing_coordinates')),
                ('CLASS_PADDING',target_groups(class_proof,class_config,'raw_coordinates')),
                ('FPNEW90',target_groups(fp_proof,fp_config,'coordinates'))]
    suffix = suffix_chain(chain)
    audits = []
    for record in suffix:
        paths = list((Path(record['new_vdb'])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        need(len(paths)==1,'One suffix native Toggle file')
        path = paths[0]; need(str(path) in pins,'Admitted suffix data pin')
        reader.read(path,pins[str(path)])
        scopes = {s for _,groups in families for s in groups}
        rows, sha = native.source.rank.t.rows(path,scopes)
        need(sha==pins[str(path)] and set(rows)==scopes,'Exact suffix scopes and native SHA')
        suffix_rows(rows,families)
        audits.append(dict(population=record['population'],path=str(path),sha256=sha,
                           RR190_zero=True,class_padding_zero=True,FPNEW90_zero=True))
    return audits


def population_gate(source,bits,chain,old):
    need(len(bits['tests'])==785 and len(source['input_ledger'])==786 and
         source['input_ledger'][:784]==old['input_ledger'] and
         any(r['manifest']==str(previous.BASE) and r['seal']==previous.BASE_SHA and r['population']==783 for r in chain)
         and source['input_ledger'][0]==old['input_ledger'][0], 'Exact formal785 preserving parent783 lineage')
    suffix_chain(chain)


def approved(reader, manifest, seal):
    source,pins,_,bits,chain,activity = population.approved(reader,manifest,seal)
    old,oldpins,text = inherited(reader)
    population_gate(source,bits,chain,old)
    need(chain[-1]['manifest']==str(manifest) and chain[-1]['seal']==seal,
         'Exact explicit frozen785 manifest/seal endpoint')
    config,more,extra = local(reader)
    need(config['design']==source['input_ledger'][0],'Same compiled image')
    pins = stable.merge(pins,oldpins,more)
    audit = suffix_zero(reader,pins,chain,config)
    return source,pins,union_gate(text,extra,config),bits,chain,dict(activity,RR190_and_fclass=audit)


def dependencies():
    return stable.merge(previous.dependencies(),{str(p):life.digest(p) for p in
        (Path(__file__).resolve(),HERE/'test_report_population784_rr190.py',Path(native.__file__).resolve())})


def metadata():
    c = life.read_bound(REPORT/'config.json',REPORT_SHA)
    return dict(additional_direction_count=46064,local_qualifications=[*c['local_qualifications'],
        dict(family='RR_DISABLED190',path=str(LOCAL/'capture-result.json'),sha256=LOCAL_QUAL_SHA,
             config_seal=LOCAL_SHA,directions=22528)],
        protection_basis=c['protection_basis']+'; RR190 full5160 typed complement; exact physical disjoint union; fclass784 and VALU785 source-zero suffixes checked')


def context(manifest,seal):
    namespace = dict(engine.prepare.__globals__,__file__=__file__,BASE=manifest,BASE_SHA=seal,
                     SCHEMA=SCHEMA,approved=approved,dependencies=dependencies,metadata=metadata)
    prepare = FunctionType(engine.prepare.__code__,namespace)
    check = FunctionType(engine.check.__code__,namespace)
    verify = FunctionType(engine.verify.__code__,dict(namespace,check=check))
    run = FunctionType(engine.run.__code__,dict(namespace,check=check,verify=verify))
    return prepare,check,verify,run


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','check','verify','run-reviewed'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--manifest',type=Path)
    p.add_argument('--manifest-seal');p.add_argument('--seal');p.add_argument('--service-unit')
    p.add_argument('--parent-reviewed-seal');a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':
        need(a.manifest and a.manifest_seal and a.service_unit and not a.seal,'Explicit formal785 host prepare; no784 report')
        context(a.manifest.resolve(),a.manifest_seal)[0](out,a.service_unit)
    else:
        need(a.seal and not a.manifest and not a.manifest_seal and not a.service_unit,'Sealed runtime only')
        c=stable.Reader().read(out/'config.json',a.seal,True)
        need(c['schema']==SCHEMA and c['population']==785,'Exact sealed785 runtime')
        f=context(Path(c['admission']['path']),c['admission']['sha256'])
        if a.mode=='check': f[1](out,a.seal); print('CHECK_PASS_NO_EDA')
        elif a.mode=='verify': f[2](out,a.seal)
        else: f[3](out,a.seal,a.parent_reviewed_seal)

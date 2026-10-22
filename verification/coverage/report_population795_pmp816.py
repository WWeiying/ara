"""Full795 population with sealed794 PMP union and strict DIV suffix-zero audit."""
import argparse
from pathlib import Path
from types import FunctionType
import xml.etree.ElementTree as ET

import report_population794_pmp816 as inherited

engine, stable, life, need = inherited.engine, inherited.stable, inherited.life, inherited.need
prior, handoff = inherited.prior, inherited.handoff
HERE = Path(__file__).resolve().parent
BASE = life.OUT/'scalar-div-subnormal-offline-admitted795-parent-20261008-01/admission-manifest.json'
BASE_SHA = '4d13a15758c65791a43798467bb63c516d0747d631f6fede476eb63202001660'
HANDOFF = life.OUT/'pmp816-global794-handoff-parent-20261008-01/handoff.json'
HANDOFF_SHA = '401c57fd7e6fc3bd85c2d53bec197522dc39297823093f9c5901d1f8b1103da9'
SCHEMA = 'FORMAL795_EXACT794_PMP_UNION_TYPED_DIV_SUFFIX_ZERO_V1'
older = prior.prior.inherited.prior


def corpus_gate(source, bits, chain, old_source, old_chain):
    ledger = source['input_ledger']
    need(len(ledger) == len(set(ledger)) == 796 and ledger[:-1] == old_source['input_ledger'] and
         len(old_source['input_ledger']) == 795 and bits['tests'] == ledger[1:] and
         len(bits['tests']) == len(set(bits['tests'])) == 795, 'Exact794 prefix plus unique DIV795')
    need(chain[:-1] == old_chain and chain[-1] == dict(manifest=str(BASE),seal=BASE_SHA,
         population=795,new_vdb=ledger[-1]), 'Exact795 lineage and suffix VDB')
    need({k:len(v) for k,v in bits['metrics'].items()} == engine.METRIC_COUNTS and
         sum(len(v) for v in bits['metrics'].values()) == 6162, 'Complete per-metric6162 shapes')
    need(source['hierarchy_roots'] == old_source['hierarchy_roots'] and
         len(source['hierarchy_roots']) == 72 and
         source['tool_identity'] == old_source['tool_identity'], 'Same official roots and frozen tool identity')


def toggle_or_gate(before, current, single):
    need(len(before) == len(current) == len(single) == 2989 and
         set(before) == set(current) == set(single), 'Complete exact2989 Toggle scopes')
    need(prior.prior.suffix.native.union(before,single) == current, 'All2989 exact794 OR DIV795; no lost/additional bits')


def typed_added_zero(rows, definitions, soc_proof, pmp_proof, qbs_nodes, qbs_targets):
    soc_scopes = {r['scope'] for r in soc_proof['candidates']}
    pmp_scopes = {r['scope'] for r in pmp_proof['fresh_candidates']}
    qbs_scope = prior.prior.suffix.SCOPE
    need(set(rows) == soc_scopes | pmp_scopes | {qbs_scope}, 'Exact added constant-family scope set')
    prior.constant_rows({s:rows[s] for s in soc_scopes},definitions,soc_proof)
    handoff.zero_gate(pmp_proof,{s:rows[s] for s in pmp_scopes},
                     {s:definitions[s] for s in pmp_scopes})
    fields = prior.prior.suffix.fields(qbs_nodes,rows[qbs_scope],qbs_targets)
    need(not any(f['candidate_raw_hit_coordinates'] for f in fields), 'HOLD DIV795 activated QBS3232 source-zero bit')
    return dict(SOC61_directions=7686,PMP816_directions=2176,QBS3232_directions=3232,
                all_source_zero=True,full_QBS_fields=len(fields),MDA13_retained=True)


def suffix_zero(reader,pins,record,source):
    paths = list((Path(record['new_vdb'])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    need(len(paths) == 1 and str(paths[0]) in pins, 'One admitted complete DIV795 native Toggle file')
    path = paths[0]; reader.read(path,pins[str(path)])
    manifests = []
    for directory,sha in ((prior.BASE.parent,prior.BASE_SHA),(BASE.parent,BASE_SHA)):
        m = reader.read(directory/'admission-manifest.json',sha,True)
        up = directory/'combined-toggle-bits.json'
        manifests.append(reader.read(up,m['output_pins'][str(up)],True))
    native = prior.prior.suffix.native
    single,measured = native.rows(path,set(manifests[0]))
    need(measured == pins[str(path)], 'Exact suffix native SHA')
    toggle_or_gate(manifests[0],manifests[1],single)
    # Reuse the reviewed serializers/coordinate maps for the old three
    # constant families, but audit only the new suffix, not trusted datapaths.
    rr_c = reader.read(older.LOCAL/'config.json',older.LOCAL_SHA,True)
    old_zero = FunctionType(older.suffix_zero.__code__,
        dict(older.suffix_zero.__globals__,suffix_chain=lambda chain:[record]))
    old_audit = old_zero(reader,pins,[record],rr_c)
    soc = reader.read(prior.native.old.SOURCE,prior.native.old.SOURCE_SHA,True)
    pmp = reader.read(handoff.local.SOURCE,handoff.local.SOURCE_SHA,True)
    qbs_c = reader.read(prior.prior.suffix.LOCAL/'config.json',prior.prior.suffix.CONFIG_SHA,True)
    qbs_path = life.OUT/'qbs-bank1-group-hit789-all-cycle-source-review-agent-20261008-01.json'
    qbs = reader.read(qbs_path,qbs_c['plan']['source_review_sha256'],True)
    targets = {r['name']:r for r in qbs['source_targets']}
    need(len(targets) == 72 and sum(len(t['source_zero_bit_indices']) for t in targets.values()) == 1616,
         'Exact partial QBS source mask; keep dynamic704 bits')
    scopes = {r['scope'] for r in soc['candidates']} | {r['scope'] for r in pmp['fresh_candidates']} | {qbs['scope']}
    trees = []; db = Path(source['input_ledger'][0])/'snps/coverage/db'
    for name in ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml'):
        p = db/name; reader.read(p,pins[str(p)]); trees.append(native.xml(p))
    _, definitions = native.definitions(*trees,scopes)
    nodes = list(ET.fromstring(definitions[qbs['scope']]['shape']).find('tglshape'))
    parent = next(i for i in qbs_c['instances'] if i['scope'] == qbs['scope'])
    need({n.get('name'):dict(n.attrib) for n in nodes} ==
         {b['attributes']['name']:b['attributes'] for b in parent['bindings']}, 'Full QBS native-qualified typed inventory')
    audits = [typed_added_zero({s:dataset[s] for s in scopes},definitions,soc,pmp,nodes,targets)
              for dataset in (single,manifests[1])]
    return dict(population=795,path=str(path),sha256=measured,complete_Toggle_OR_instances=2989,
        RR190_classpadding_FPNEW90=old_audit,suffix_and_full_population=audits,
        trusted_active_datapaths_not_claimed_zero=True)


def approved(reader,manifest,seal):
    need(Path(manifest) == BASE and seal == BASE_SHA, 'Only published formal795 endpoint')
    source,pins,_,bits,chain,activity = engine.approved(reader,manifest,seal)
    old_source,old_pins,text,_,old_chain,old_activity = inherited.approved_for(HANDOFF,HANDOFF_SHA)(
        reader,prior.BASE,prior.BASE_SHA)
    corpus_gate(source,bits,chain,old_source,old_chain)
    pins = stable.merge(pins,old_pins,reader.pins)
    audit = suffix_zero(reader,pins,chain[-1],source)
    metadata = dict(old_activity['EL_additions'],population_rebased_from=794,
                    exact_DIV795_suffix_source_zero=True)
    activity = dict(activity,EL_additions=metadata,DIV795_constant_suffix_audit=audit,
                    policy='Exact sealed794 complete PMP union; actual full795 five-stage report only')
    return source,stable.merge(pins,reader.pins),text,bits,chain,activity


def dependencies():
    return stable.merge(inherited.dependencies(),{str(p):life.digest(p) for p in
        (Path(__file__).resolve(),HERE/'test_report_population795_pmp816.py')})


def context(path=HANDOFF,seal=HANDOFF_SHA):
    need(Path(path) == HANDOFF and seal == HANDOFF_SHA, 'Exact parent-sealed794 handoff only')
    prepared,checked,verified,_ = inherited.context(path,seal)
    namespace = dict(prepared.__globals__,__file__=__file__,SCHEMA=SCHEMA,
                     approved=approved,dependencies=dependencies)
    functions = [FunctionType(f.__code__,namespace,f.__name__,f.__defaults__)
                 for f in (prepared,checked,verified)]
    namespace.update(zip(('prepare','check','verify'),functions))
    return (*functions,FunctionType(engine.run.__code__,namespace))


runtime_context = FunctionType(inherited.runtime_context.__code__,
    dict(inherited.runtime_context.__globals__,__file__=__file__,SCHEMA=SCHEMA,context=context))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','check','verify','run-reviewed'))
    p.add_argument('--output',type=Path,required=True); p.add_argument('--seal',required=True)
    p.add_argument('--service-unit'); p.add_argument('--parent-reviewed-seal')
    a = p.parse_args(); out = a.output.resolve()
    if a.mode == 'prepare':
        need(a.service_unit is not None,'Explicit owning service required; no automatic launch')
        context()[0](out,BASE,a.seal,a.service_unit)
    else:
        need(a.service_unit is None,'Runtime service from sealed config only')
        f = runtime_context(out,a.seal)
        if a.mode == 'check':f[1](out,a.seal);print('FULL795_PMP816_CHECK_PASS_NO_EDA')
        elif a.mode == 'verify':f[2](out,a.seal)
        else:f[3](out,a.seal,a.parent_reviewed_seal)

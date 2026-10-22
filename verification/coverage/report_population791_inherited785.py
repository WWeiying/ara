"""Formal791 report, exactly the qualified785 EL; no new observer waiver."""
import argparse
from pathlib import Path
from types import FunctionType, SimpleNamespace
import report_population784_rr190 as prior

life, stable, need = prior.life, prior.stable, prior.need
HERE = Path(__file__).resolve().parent
BASE = life.OUT/'akv-canonical-kfault-offline-admitted791-agent-20261008-01/admission-manifest.json'
BASE_SHA = '8b732015035c1f716940598f05d8a8063e4b4829eb5cd67cfebcbb2728ee2b30'
REPORT = life.OUT/'current-population785-rr190-prepared-agent-20261008-01'
CONFIG_SHA = '796fbe9f3c009b8b6aed24b840d3699a965a9e257341757e5615d6b08b997a49'
QUAL_SHA = '8e0a97845146bd0296be674c65f889fae674d2726516c593be748c47d6f960c2'
CSR787 = life.OUT/'csr-satp-sepc-offline-admitted787-parent-20261008-01'
CSR787_SHA = 'aaef43fef3b8da3a1e854e4907b0823a3488270ddb8b7ae5af0c21be5cb8d5fc'
SCHEMA = 'FORMAL791_EXACT_QUALIFIED785_EL_NO_NEW_OBSERVERS_V1'


class Reader(stable.Reader):
    def read(self, path, sha, parse=False):
        value = super().read(path, sha, parse)
        if Path(path) == CSR787/'status.json' and parse:
            manifest = super().read(CSR787/'admission-manifest.json', CSR787_SHA, True)
            need(sha == manifest['output_pins'][str(path)] and
                 value['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and
                 value['coverage_admitted'] is True and value['aggregate_passed'] == 787 and
                 value['baseline'] == 786 and value['full_OR_instances'] == 6162 and
                 'full_OR_metric_instances' not in value, 'Exact historical787 schema authority')
            return dict(value, full_OR_metric_instances=value['full_OR_instances'])
        return value


def suffix_chain(chain):
    rows = [r for r in chain if r['population'] > 783]
    need([r['population'] for r in rows] == list(range(784,792)), 'Exact consecutive784..791 suffix')
    need(rows[0]['manifest'] == str(prior.FORMAL784) and rows[0]['seal'] == prior.FORMAL784_SHA and
         rows[-1]['manifest'] == str(BASE) and rows[-1]['seal'] == BASE_SHA, 'Frozen lineage endpoints')
    return rows


def corpus_gate(source, bits, old):
    ledger = source['input_ledger']
    need(len(ledger) == len(set(ledger)) == 792 and len(old['input_ledger']) == 786 and
         ledger[:786] == old['input_ledger'], 'Exact791 preserving qualified785 prefix')
    need(bits['tests'] == ledger[1:] and len(set(bits['tests'])) == 791, 'Exact raw test identities/order')
    need({k:len(v) for k,v in bits['metrics'].items()} ==
         dict(line=1892,cond=2023,branch=2155,fsm=92), 'Full6162 metric families')
    need(source['hierarchy_roots'] == old['hierarchy_roots'] and
         source['tool_identity'] == old['tool_identity'], 'Qualified root/tool identity differs')


def approved(reader, manifest, seal):
    need(Path(manifest) == BASE and seal == BASE_SHA, 'Only exact formal791 admitted endpoint')
    source,pins,_,bits,chain,activity = prior.population.approved(reader,BASE,BASE_SHA)
    old = reader.read(REPORT/'config.json',CONFIG_SHA,True)
    qualification = reader.read(REPORT/'qualification.json',QUAL_SHA,True)
    need(qualification['status'] == 'CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED' and
         qualification['config_seal'] == CONFIG_SHA and qualification['population'] ==
         qualification['actual_selected_tests'] == old['population'] == 785,
         'Actual qualified785 report authority')
    for flag in ('complete_approved_EL_bitmask_union','all_other_bits_protected',
                 'raw_reset_final_equal','applied_reloaded_equal'):
        need(qualification[flag] is True, 'Missing old native gate: '+flag)
    pins = stable.merge(pins,old['pins'],qualification['output_pins'],
        {str(REPORT/'config.json'):CONFIG_SHA,str(REPORT/'qualification.json'):QUAL_SHA})
    corpus_gate(source,bits,old); suffix_chain(chain)
    text = reader.read(REPORT/'combined.el',pins[str(REPORT/'combined.el')]).decode('ascii')
    need(stable.semantic_seal(stable.semantic(text)) == old['expected_EL_semantic_sha256'], 'Old EL semantics drift')
    for name in ('applied.el','reloaded.el'):
        path = REPORT/name
        content = reader.read(path,pins[str(path)]).decode('ascii')
        need(stable.semantic(content) == stable.semantic(text), 'Old saved/reloaded EL differs')
    rr = reader.read(prior.LOCAL/'config.json',prior.LOCAL_SHA,True)
    zero = FunctionType(prior.suffix_zero.__code__,dict(prior.suffix_zero.__globals__,suffix_chain=suffix_chain))
    audit = zero(reader,pins,chain,rr)
    activity = dict(activity,inherited785_constants=audit,inherited_report_seal=QUAL_SHA,
                    new_observer_exclusions=False,policy='Exact qualified785 EL, new791 data; no percentage extrapolation')
    return source,pins,text,bits,chain,activity


def dependencies():
    return stable.merge(prior.dependencies(),prior.population.dependencies(),{
        str(p):life.digest(p) for p in (Path(__file__),HERE/'test_report_population791_inherited785.py')})


def context():
    engine = prior.population
    namespace = dict(engine.prepare.__globals__,__file__=__file__,SCHEMA=SCHEMA,
                     approved=approved,dependencies=dependencies,
                     stable=SimpleNamespace(**dict(vars(stable),Reader=Reader)))
    prepare = FunctionType(engine.prepare.__code__,namespace)
    check = FunctionType(engine.check.__code__,namespace)
    verify = FunctionType(engine.verify.__code__,dict(namespace,check=check))
    run = FunctionType(engine.run.__code__,dict(namespace,check=check,verify=verify))
    return prepare,check,verify,run


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','check','verify','run-reviewed'))
    p.add_argument('--output',type=Path,required=True); p.add_argument('--seal')
    p.add_argument('--service-unit'); p.add_argument('--parent-reviewed-seal')
    a = p.parse_args(); out = a.output.resolve(); functions = context()
    if a.mode == 'prepare':
        need(a.service_unit and not a.seal,'Explicit fresh owning service')
        functions[0](out,BASE,BASE_SHA,a.service_unit)
    elif a.mode == 'check': functions[1](out,a.seal); print('FORMAL791_INHERITED785_CHECK_PASS_NO_EDA')
    elif a.mode == 'verify': functions[2](out,a.seal)
    else: functions[3](out,a.seal,a.parent_reviewed_seal)

"""Exact formal785 + one qualified two-phase QBS; parent-only publication."""
import json
from pathlib import Path
from types import FunctionType

import admit_valu_restart785 as publish
import collect_qbs_pending_m4_xml_successor as case

life, require = case.life, case.require
bitmap, toggle = case.original.bitmap, case.toggle
BASE = life.OUT/'valu-restart-offline-admitted785-agent-20261008-01'
BASE_SHA = '10273c45e4a4eb21929e0599a2bfc27bfb76afb2b36fe547de0198b5ee918cf5'
RUN = life.OUT/'qbs-pending-two-phase-m4-vcs783-agent-20261008-01'
QUAL = life.OUT/'qbs-pending-two-phase-m4-qualified-xml-successor-agent-20261008-01'
Q_SHA = 'f8198c6920c9afed0f787c2e439978164cf423fb22ef12d820da28a66d3a5736'
PREPARED_SHA = '8db9ab6f8f66508675302457dd1ddd3b12ac93e860fd4f3dd4efb8831b8b41e4'
COUNTS = publish.COUNTS


def full_union(before, single):
    require(len(before['tests']) == len(set(before['tests'])) == 785 and
            single['tests'] == [str(RUN/'code.vdb')] and single['tests'][0] not in before['tests'],
            'Exact785 prefix and one distinct candidate')
    require(set(before['metrics']) == set(single['metrics']) == set(COUNTS) and
            all(len(before['metrics'][m]) == n for m,n in COUNTS.items()), 'Full6162 universe')
    life.merge_pins(before['input_hashes'], single['input_hashes'])
    after = bitmap.combine(before, single)
    publish.inherited.publish.case.independent_or(before, single, after)
    require(after['tests'] == before['tests'] + single['tests'], 'Ordered786 append')
    for rows in after['metrics'].values():
        for r in rows.values():
            require(type(r['width']) is int and r['width'] >= 0 and
                    0 <= int(r['bits'],16) < (1 << r['width']), 'Binary bounds')
    return after


def architecture(q, audit, cycle):
    require(q['status'] == 'TWO_M4_FUNCTIONAL_NATIVE_CYCLE_AND_RAW_QUALIFIED_NOT_ADMITTED' and
            q['coverage_admitted'] is False and q['baseline'] == 783 and
            q['scalar_spike_verified'] is False and q['full_scalar_ISA_verified'] is False and
            q['custom_spike_pass'] is False, 'Qualified native QBS, not custom Spike')
    require(audit['status'] == 'TWO_M4_NATIVE_VRF_CSR_ALL_SOURCE_LIFECYCLE_PASS_NOT_FULL_SCALAR_ISA',
            'Complete sealed native architecture')
    for key,value in dict(custom_write_bytes=1024,custom_active_bytes=256,custom_preserved_vrf_bytes=7168,
                          full_vrf_bytes=8192,initial_vrf_bytes=8192,csr_values=24,
                          source_guard_bytes=24832,checks=12,custom_zero_tail_bytes=768).items():
        require(type(audit[key]) is int and audit[key] == value, 'Full obligation ' + key)
    contract = audit['contract']
    require(contract['requests'] == contract['responses'] == 46 and
            all(contract[k] == 0 for k in ('exceptions','protocol_errors','outstanding','mmu_request_cycles')),
            'Exact protocol and drain')
    require(len(audit['bindings']) == 2 and [b['phase'] for b in audit['bindings']] == [0,1] and
            len({b['arch_seq'] for b in audit['bindings']}) == 2 and
            all(b['backend_vl'] == 128 and b['software_vl'] == 8 for b in audit['bindings']), 'Two native owners')
    require(cycle['status'] == 'TWO_PHASE_FULL_WAVE_FIFO_SOURCE_RECURRENCE_VERIFIED' and
            cycle['hit13_falling_observed'] is True and q['hit13_falling_observed'] is True and
            cycle['phase1_different_context_partial_captured'] is True and
            any(e['from_value'] == 1 and e['to_value'] == 0 and
                e['retained_owner']['phase'] == 1 for e in cycle['transitions']), 'Actual falling witness')


def evaluate(base, base_sha):
    require(base == BASE and base_sha == BASE_SHA, 'Fixed actual formal785 authority')
    manifest = life.read_bound(base/'admission-manifest.json',base_sha)
    require(manifest['coverage_admitted'] is True and manifest['output'] == str(base), 'Formal785 admitted')
    authority = life.merge_pins(manifest['input_pins'],manifest['output_pins'])
    def previous(name): return life.read_bound(base/name,manifest['output_pins'][str(base/name)])
    before, status = previous('combined-bits.json'), previous('status.json')
    ledger = (base/'combined-inputs.txt').read_text().splitlines()
    require(ledger == [str(life.IMAGE)+'.vdb',*before['tests']] and len(set(ledger)) == len(ledger) == 786 and
            status['aggregate_passed'] == 785 and status['coverage_admitted'] is True, 'Exact785 ledger/status')
    q = life.read_bound(QUAL/'qualification.json',Q_SHA)
    life.check(q['input_pins']); life.check(q['output_pins'])
    pins = life.merge_pins(authority,life.merge_pins(q['input_pins'],q['output_pins']))
    def qualified(name): return life.read_bound(QUAL/name,q['output_pins'][str(QUAL/name)])
    audit, cycle, diagnostic = qualified('runtime-audit.json'), qualified('cycle-proof.json'), qualified('raw-gain.json')
    architecture(q,audit,cycle)
    record = life.read_bound(RUN.with_name(RUN.name+'.prepared.json'),PREPARED_SHA)
    require(record['collector_ready'] is True and record['command'] == case.original.runner.command(RUN), 'Sealed run command')
    case.original.core.native.terminal(RUN)
    db = RUN/'code.vdb'; native = db/'snps/coverage/db/testdata'/case.original.runner.NAME
    require(list(native.parent.iterdir()) == [native] and not any(p.is_symlink() for p in db.rglob('*')) and
            {str(p) for p in db.rglob('*') if p.is_file()} ==
            {p for p in q['input_pins'] if p.startswith(str(db)+'/')}, 'Complete one-sample immutable native inventory')
    identity = case.native_identity(RUN,toggle.xml(native/'siminfo.xml'),toggle.xml(native/'vcmArguments.xml'),record,ledger[0])
    design = Path(ledger[0])/'snps/coverage/db'
    require(all(life.digest(design/rel) == h == pins[str(design/rel)] for rel,h in before['design'].items()), 'Exact full compiled design')
    single = dict(design=before['design'],tests=[str(db)],input_hashes={},metrics={})
    for m in bitmap.METRICS:
        p = native/(m+'.verilog.data.xml');single['metrics'][m] = bitmap.read_metric(p)
        single['input_hashes'][str(p)] = pins[str(p)]
    require(single == diagnostic['single_bits'], 'Actual singleton equals qualified diagnostic')
    after = full_union(before,single); delta = bitmap.delta(before,after)
    old_base = case.original.runner.BASE
    old_manifest = life.read_bound(old_base/'admission-manifest.json',case.original.runner.BASE_SHA)
    old_ledger = old_base/'combined-inputs.txt'
    require(life.digest(old_ledger) == old_manifest['output_pins'][str(old_ledger)] and
            ledger[:784] == old_ledger.read_text().splitlines(), 'Exact sealed783 ancestor prefix')
    old_gain = old_base/'qbs-k2-payload-toggle-gain782.json'
    old = life.read_bound(old_gain,old_manifest['output_pins'][str(old_gain)])['combined_rows']
    scopes = sorted(old)
    checks,_ = toggle.definitions(*(toggle.xml(design/rel) for rel in
        ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml')),scopes)
    require(all(checks[s] == old[s]['checksum'] == '3657545390' and old[s]['width'] == 66340 for s in scopes), 'Compiled payload shapes')
    def sample(vdb, evidence):
        files = list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files) == 1, 'One native Toggle sample')
        rows,h = toggle.rows(files[0],scopes)
        require(evidence.get(str(files[0])) == h, 'Historical or candidate sample authority')
        return rows
    for vdb in ledger[784:]: old = toggle.union(old,sample(vdb,authority))
    add = sample(str(db),q['input_pins']); joined = toggle.union(old,add); gains = toggle.gains(old,joined)
    gain = dict(baseline=785,before=old,single=add,after=joined,new_coordinates=gains,
                new_directions=sum(map(len,gains.values())),official_percentage=False)
    require(gain['new_directions'] > 0 or any(delta['metrics'].values()), 'Positive fresh785 gain')
    require(pins[str(case.original.runner.ELF)] == case.original.runner.ELF_SHA ==
            life.digest(case.original.runner.ELF), 'Exact candidate ELF')
    elf = publish.inherited.prior.dedup(ledger,case.original.runner.ELF_SHA,authority)
    require(elf['ledger_members'] == 785 and elf['duplicate'] is False and
            [r['vdb'] for r in elf['members']] == ledger[1:] and
            all(authority.get(p) == h for p,h in elf['pins'].items()), 'Historical-only785 ELF dedup')
    pins = life.merge_pins(pins,elf['pins'])
    fixed = {str(base/'admission-manifest.json'):BASE_SHA,str(QUAL/'qualification.json'):Q_SHA,
             str(old_base/'admission-manifest.json'):case.original.runner.BASE_SHA,
             str(old_gain):old_manifest['output_pins'][str(old_gain)],str(old_ledger):old_manifest['output_pins'][str(old_ledger)]}
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_qbs_pending_m4_786.py').resolve(),
              Path(publish.__file__).resolve(),Path(publish.inherited.prior.dedup.__code__.co_filename).resolve()):
        fixed[str(p)] = life.digest(p)
    pins = life.merge_pins(pins,fixed);life.check(pins)
    products = {Path(p).name:previous(Path(p).name) for p in manifest['output_pins']
        if Path(p).parent == base and Path(p).suffix == '.json' and
        ('toggle-gain' in Path(p).name or Path(p).name.startswith('retained-'))}
    products.update({'single-bits.json':single,'combined-bits.json':after,'raw-delta.json':delta,
        'qbs-two-phase-payload-toggle-gain785.json':gain,'qbs-two-phase-cycle-proof.json':cycle,
        'qbs-two-phase-runtime-audit.json':audit,'native-vdb-identity.json':identity,
        'elf-ledger-dedup.json':dict(elf,baseline=785),'evidence-pins.json':pins,
        'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=786,baseline=785,
            new_passed=1,coverage_admitted=True,exact785_prefix=True,unique_new_vdb=True,duplicate_ELF=False,
            full_OR_metric_instances=6162,raw_delta=delta['metrics'],payload_new_directions=gain['new_directions'],
            hit13_falling_observed=True,qualification_seal=Q_SHA,full_scalar_ISA_verified=False,
            custom_Spike_verified=False,full_native_VRF_CSR_sourceguards_verified=True,
            direct_write_req_wave_observed=False,new_simulation=False,RTL_changed=False,official_percentage_claimed=False)})
    return products,'\n'.join([ledger[0],*after['tests']])+'\n'


if __name__ == '__main__':
    FunctionType(publish.main.__code__,dict(publish.main.__globals__,evaluate=evaluate,QUAL=QUAL,Q_SHA=Q_SHA))()

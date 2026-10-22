"""Offline formal774+VMACC; no EDA, explicit parent seal and admission required."""
import argparse
import hashlib
import json
from pathlib import Path

import collect_vmacc_c_fifo773 as case
from admit_stride_metadata768 import dedup
import admit_itlb_bulk774 as itlb

life, require, bitmap, toggle = case.life, case.require, case.runner.bitmap, case.runner.toggle
RUN = life.OUT / 'vmacc-C-fifo-vcs-parent-20261007-01'
AGENT = life.OUT / 'vmacc-C-fifo-qualified-parent-20261007-01/qualification.json'
AGENT_SHA = 'a327baa1917682657e1255273d94b4965de8fcc78fc502fcd6e253b38608d831'
PARENT_SHA = '3b2b157a5ff7ca50e0809ec8a8771d96e282b864185717adc6abc60828249524'


def architecture(q):
    require(q['status'] == 'VMACC_FULL_ARCHITECTURE_NATIVE_RAW773_PASS_NOT_ADMITTED' and
            q['run'] == str(RUN) and q['prepared_seal'] ==
            'f77870aa6f52c5bac88305b7e6a5e6c39e42c16c459d1dc1713ef8713e1c9305' and
            q['coverage_admitted'] is False and q['RTL_modified'] is False, 'Exact qualified VMACC run')
    pre = case.runner.preflight()
    reference = case.p.old.build.parse_spike_commits(Path(pre['reference']))[5:5 + 36339]
    case.common.scalar_exact(q['scalar'], case.common.reference_counts(reference, pre['symbols']))
    require(q['scalar_memory'] == dict(instructions=36339, scalar_memory_accesses=11496,
            compressed_memory_accesses=9113, unmodeled_memory_effects=0), 'Complete RVC memory differential')
    require(q['signature'] == dict(checks=2344, failures=0, full_VRF_bytes=16384,
            source_guard_bytes=2080, CSR_values=20, full_explicit_read_bytes=18752, retired_VMACC=12),
            'Complete independent VRF/source/CSR/guards')
    v = q['vector']
    require(all(v.get(k) == x for k, x in dict(status='PASS', compared_instructions=19,
            skipped_unknown_bytes=0, non_bit_exact_instructions=0, first_mismatch=None,
            incomplete_requests=[], unretired_requests=[], trapped_requests=[],
            unobservable_instructions=0, nr_lanes=4, vlen_bits=1024).items()), 'Full vector differential')
    n = q['native']; l = q['lifecycle']
    require(n['required_active_bytes'] == 18420 and n['observed_known_bytes'] == v['compared_bytes'] and
            n['observed_preserved_tail_bytes'] == n['observed_known_bytes'] - 18420 and
            n['duplicate_accepted_bytes'] == 0 and len(n['allocations']) == 12 and
            [r['vl'] for r in n['allocations']] == [1024]*4 + [1020]*4 + [1024]*4 and
            all(r['vstart'] == r['eew'] == 0 and r['allocations'] > 0 for r in n['allocations']) and
            l['requests'] == l['responses'] == 170 and l['backend_uops'] == 147 and
            l['exceptions'] == l['rejected_backend_uops'] == l['rejected_vrf_activities'] == 0 and
            not l['rejected_arch_seqs'] and l['exact_SID_owner_checked'] is True,
            'Every native writer and SID owner')


def full_union(before, single):
    require(len(before['tests']) == len(set(before['tests'])) == 774 and
            single['tests'] == [str(RUN/'code.vdb')] and single['tests'][0] not in before['tests'] and
            before['design'] == single['design'] and set(before['metrics']) == set(single['metrics']) ==
            set(bitmap.METRICS), 'Exact774 prefix/unique same-design single')
    after = bitmap.combine(before, single)
    count = 0
    for metric, rows in before['metrics'].items():
        require(set(rows) == set(single['metrics'][metric]) == set(after['metrics'][metric]), 'No dropped scope')
        for scope, old in rows.items():
            new = single['metrics'][metric][scope]; result = after['metrics'][metric][scope]
            require(old['width'] == new['width'] == result['width'] and
                    old['checksum'] == new['checksum'] == result['checksum'] and
                    int(result['bits'], 16) == int(old['bits'], 16) | int(new['bits'], 16), 'Exact native OR')
            count += 1
    require(count == 6162 and after['tests'] == before['tests'] + single['tests'], 'Full6162 OR/exact prefix')
    return after


def historical(ledger, elf_hash, authority):
    audit = dedup(ledger, elf_hash, authority)
    require(audit['ledger_members'] == 774 and not audit['duplicate'] and
            [r['vdb'] for r in audit['members']] == ledger[1:] and
            all(authority.get(p) == h for p, h in audit['pins'].items()),
            'Every historical774 ELF/command must have formal774 authority, not candidate pins')
    return dict(audit, baseline=774)


def evaluate(base_path, base_sha, qual_path, qual_sha, replay_path, replay_sha):
    base = life.read_bound(base_path/'admission-manifest.json', base_sha)
    require(base['coverage_admitted'] is True and base['output'] == str(base_path) and
            base['baseline'] == str(case.p.old.BASE) and base['baseline_seal'] == case.p.old.SEAL,
            'Formal774 exact773 ancestry')
    life.check(base['input_pins']); life.check(base['output_pins'])
    def document(name):
        path = base_path/name
        return life.read_bound(path, base['output_pins'][str(path)])
    status = document('status.json')
    require(status['aggregate_passed'] == 774 and status['coverage_admitted'] is True and
            status['scoped_toggle_new_serialized_positions'] == 948 and
            status['candidate_qualification_not_used_as_historical_ELF_owner'] is True,
            'Independent774 v2, preserved ITLB948')
    q = life.read_bound(qual_path, qual_sha); parent = life.read_bound(replay_path, replay_sha)
    require(qual_path == AGENT and qual_path != replay_path and qual_sha == AGENT_SHA and
            replay_sha == PARENT_SHA, 'Exact independently completed agent and parent replay')
    architecture(q); architecture(parent)
    require({k:v for k,v in q.items() if k != 'input_pins'} ==
            {k:v for k,v in parent.items() if k != 'input_pins'}, 'Full parent semantic replay equality')
    life.check(q['input_pins']); life.check(parent['input_pins'])
    before = document('combined-bits.json')
    ledger_path = base_path/'combined-inputs.txt'
    ledger = ledger_path.read_text().splitlines()
    require(life.digest(ledger_path) == base['output_pins'][str(ledger_path)] and
            len(ledger) == len(set(ledger)) == 775 and ledger[1:] == before['tests'] and
            ledger[-1] == str(itlb.RUN/'code.vdb'), 'Exact774 population includes ITLB')
    old_manifest = life.read_bound(case.p.old.BASE/'admission-manifest.json', case.p.old.SEAL)
    old_bits = life.read_bound(case.p.old.BASE/'combined-bits.json',
        old_manifest['output_pins'][str(case.p.old.BASE/'combined-bits.json')])
    require(before['tests'][:-1] == old_bits['tests'] and before['design'] == old_bits['design'],
            'Exact773 prefix for latest scoped baseline')
    pins = life.merge_pins(base['input_pins'], base['output_pins'])
    for value in (q, parent): pins = life.merge_pins(pins, value['input_pins'])
    path = qual_path.parent/'single-inputs.txt'
    require(q['input_pins'].get(str(path)) == life.digest(path) and
            path.read_text().splitlines() == [ledger[0], str(RUN/'code.vdb')], 'Bound real compileVDB/single')
    single = bitmap.collect(path)
    require(single == life.read_bound(qual_path.parent/'single-bits.json',
            q['input_pins'][str(qual_path.parent/'single-bits.json')]) and
            all(pins.get(p) == h for p,h in single['input_hashes'].items()), 'Independent candidate recollection')
    for name, sha in before['design'].items():
        path = Path(ledger[0])/'snps/coverage/db'/name
        require(base['input_pins'].get(str(path)) == sha == life.digest(path), 'Exact compiled design hash')
    after = full_union(before, single); delta = bitmap.delta(before, after)
    static = life.read_bound(case.p.old.STATIC, case.p.old.STATIC_SHA)
    scopes = list(static['baseline'])
    files = list((itlb.RUN/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(files) == 1, 'Unique admitted ITLB Toggle sample')
    itlb_file = files[0]
    itlb_rows, sha = toggle.rows(itlb_file, scopes)
    require(base['input_pins'].get(str(itlb_file)) == sha, 'Formal774-owned ITLB Toggle')
    latest = toggle.union(static['baseline'], itlb_rows)
    vmacc_file = RUN/'code.vdb/snps/coverage/db/testdata'/case.runner.NAME/'tgl.verilog.data.xml'
    sample, sha = toggle.rows(vmacc_file, scopes)
    require(q['input_pins'].get(str(vmacc_file)) == sha, 'Qualified candidate Toggle')
    merged = toggle.union(latest, sample); gained = toggle.gains(latest, merged)
    hits = [dict(scope=t['scope'], name=t['name'], serialized_position=i)
            for t in static['targets'] for i in t['zeros'] if i in gained[t['scope']]]
    require(sum(map(len, gained.values())) > 0, 'Positive measured latest774 Toggle gain')
    itlb_gain = document('itlb-toggle-gain.json')
    require(itlb_gain['new_positions'] == 948 and len(itlb_gain['new_serialized_positions']) == 948,
            'Sealed ITLB948 evidence retained')
    elf = historical(ledger, case.runner.ELF_SHA, base['input_pins'])
    pins = life.merge_pins(pins, elf['pins'])
    for path, sha in ((base_path/'admission-manifest.json', base_sha), (qual_path, qual_sha),
                      (replay_path, replay_sha), (case.p.old.STATIC, case.p.old.STATIC_SHA)):
        pins = life.merge_pins(pins, {str(path):sha})
    for module in (case, case.runner, bitmap, toggle, toggle.base):
        path = Path(module.__file__).resolve(); pins = life.merge_pins(pins, {str(path):life.digest(path)})
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_admit_vmacc_c_fifo775.py'),
                 Path(dedup.__code__.co_filename).resolve()):
        pins = life.merge_pins(pins, {str(path):life.digest(path)})
    life.check(pins)
    scoped = dict(baseline=774, before=latest, single=sample, after=merged, gained=gained,
        target_hits=hits, target_hit_count=len(hits), target_unhit_count=144-len(hits),
        scoped_new_positions=sum(map(len,gained.values())), official_percentage_claimed=False)
    products = {'combined-bits.json':after, 'single-bits.json':single, 'raw-delta.json':delta,
        'vmacc-toggle-gain774.json':scoped, 'retained-itlb-toggle-gain.json':itlb_gain,
        'elf-ledger-dedup.json':elf, 'evidence-pins.json':pins,
        'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', coverage_admitted=True,
            aggregate_passed=775, baseline=774, new_passed=1, exact774_prefix=True,
            full_OR_instances=6162, unique_new_vdb=True, duplicate_ELF=False, ITLB948_retained=True,
            full_scalar_vector_CSR_guards_lifecycle_verified=True, raw_delta=delta['metrics'],
            latest_target_hits=len(hits), scoped_toggle_new_positions=scoped['scoped_new_positions'],
            candidate_not_historical_ELF_authority=True, official_percentage_claimed=False,
            new_simulation=False, RTL_changed=False)}
    return products, '\n'.join([ledger[0], *after['tests']])+'\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare','verify','admit'))
    for name in ('baseline','qualification','parent-replay','output'): p.add_argument('--'+name,type=Path,required=True)
    for name in ('baseline-seal','qualification-seal','parent-replay-seal'): p.add_argument('--'+name,required=True)
    p.add_argument('--seal'); p.add_argument('--parent-authorized',action='store_true')
    a = p.parse_args(); out = a.output.resolve()
    require(a.parent_authorized == (a.mode == 'admit'), 'Separate parent admission authorization')
    require(out.parent == life.OUT and not out.exists(), 'Fresh formal775 output')
    values, text = evaluate(a.baseline.resolve(),a.baseline_seal,a.qualification.resolve(),a.qualification_seal,
                            a.parent_replay.resolve(),a.parent_replay_seal)
    hashes = {str(out/n):hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest() for n,v in values.items()}
    for name in ('combined-inputs.txt','generic-coverage-inputs.txt'): hashes[str(out/name)] = hashlib.sha256(text.encode()).hexdigest()
    proposal = dict(output=str(out),baseline=str(a.baseline.resolve()),baseline_seal=a.baseline_seal,
        qualification=str(a.qualification.resolve()),qualification_seal=a.qualification_seal,
        parent_replay=str(a.parent_replay.resolve()),parent_replay_seal=a.parent_replay_seal,
        input_pins=values['evidence-pins.json'],output_pins=hashes,coverage_admitted=False)
    record = out.with_name(out.name+'.prepared.json')
    if a.mode == 'prepare':
        life.save(record,proposal); print('PREPARED775',life.digest(record)); return
    require(a.seal and life.read_bound(record,a.seal) == proposal, 'Prepared775 drift')
    if a.mode == 'verify': print('VERIFY_PASS_NO_ADMISSION'); return
    out.mkdir()
    for name,value in values.items(): life.save(out/name,value)
    for name in ('combined-inputs.txt','generic-coverage-inputs.txt'):
        with (out/name).open('x') as f: f.write(text)
    life.check(proposal['input_pins']); life.check(hashes)
    life.save(out/'admission-manifest.json',dict(proposal,coverage_admitted=True,prepared=str(record),
        prepared_seal=a.seal,authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))
    print('ADMITTED775',life.digest(out/'admission-manifest.json'))


if __name__ == '__main__': main()

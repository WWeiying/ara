"""Formal779 plus one fully qualified PPN swap; offline prepare/check/admit."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex

import collect_dtlb_ppn_swap1200_schema as compat
import coverage_bitmap_delta as bitmap
import targeted_toggle_evidence_v2 as toggle
from admit_stride_metadata768 import dedup

f, life, require = compat.frozen, compat.life, compat.require
BASE, BASE_SHA = f.pre.BASE, f.pre.BASE_SHA
QUAL = life.OUT / 'dtlb-ppn-swap779-qualified-parent-20261008-02'
Q_SHA = '66e01ec60094614032e0303c7296a8b73b0fe323320a52200c581bdee25d5a75'
RECEIPT_SHA = 'd84641d1898dffb4624ebbe54cecb974620a92fd470d3667ef74392e1183066c'
CACHE = life.OUT / 'scalar-mmu-axi-post773-static-ranking-agent-20261007-01.json'
CACHE_SHA = '2e254ca9a304e0c20432c8b775f3c5917999d8fe1e2fabea88b80b34a24c3bfb'
COUNTS = dict(line=1892, cond=2023, branch=2155, fsm=92)
RUN = life.OUT / 'dtlb-ppn-swap1200-parent-20261008-01'
PREPARED_SHA = 'ea604a7eafc87133d3231f8f5f1c265ff60003cc50829759c632202401abf201'


def full_union(before, single):
    require(len(before['tests']) == len(set(before['tests'])) == 779 and
            single['tests'] == [str(RUN / 'code.vdb')] and single['tests'][0] not in before['tests'],
            'Exact779 prefix and unique singleton')
    life.merge_pins(before['input_hashes'], single['input_hashes'])
    after = bitmap.combine(before, single)
    require(set(before['metrics']) == set(single['metrics']) == set(COUNTS) and
            after['tests'] == before['tests'] + single['tests'], 'Four metrics / exact prefix')
    for metric, count in COUNTS.items():
        old, add, final = (x['metrics'][metric] for x in (before, single, after))
        require(len(old) == count and set(old) == set(add) == set(final), 'Full6162 universe')
        for scope, row in old.items():
            other, result = add[scope], final[scope]
            require(all(type(x['width']) is int and x['width'] >= 0 for x in (row, other, result)) and
                    (row['width'], row['checksum']) == (other['width'], other['checksum']) ==
                    (result['width'], result['checksum']), 'Exact width/checksum')
            values = [int(x['bits'], 16) for x in (row, other, result)]
            require(min(values) >= 0 and max(values).bit_length() <= row['width'] and
                    values[2] == values[0] | values[1], 'Independent complete OR/bounds')
    return after


def architecture(q, scalar, memory, vector, wave, gold, preflight):
    require(q['status'] == 'DTLB_PPN_SWAP779_FULL_ARCHITECTURE_AND_ACTUAL_SLOTS_QUALIFIED_NOT_ADMITTED'
            and q['baseline'] == 779 and q['run'] == str(RUN) and q['prepared_seal'] == PREPARED_SHA
            and q['coverage_admitted'] is False and q['vector_data_scope'] == 'UNOBSERVABLE_ZERO_REQUESTS',
            'Exact parent full qualification')
    for key, value in dict(scalar_memory_instructions=19071, slot_updates=48,
                           slots_per_phase=16, translated_loads=96, all_gold_checks=8297).items():
        require(type(q[key]) is int and q[key] == value, 'Qualification obligation: ' + key)
    scalar_counts = {key: preflight['counts'][key] for key in
                     ('matched_instructions', 'matched_scalar_writes', 'matched_floating_writes',
                      'matched_scalar_memory_accesses')}
    f.pre.shared.architecture.scalar_exact(scalar, scalar_counts)
    require(type(scalar['matched_instructions']) is int and scalar['matched_instructions'] == 191475
            and scalar['ara_trap_events'] == 0, 'Complete191475 scalar / no trap')
    expected = dict(status='ALL_INTEGER_RVC_AND_UNCOMPRESSED_MEMORY_EXACT', retired=191475,
        compressed=16823, uncompressed=2248, loads=8553, stores=10518, total=19071, skipped=0,
        expected_addresses_and_stores_from='Reference prior GPRs, never DUT feedback')
    require(set(memory) == set(expected) and all(type(memory[k]) is type(v) and memory[k] == v
            for k, v in expected.items()), 'Full19071 compressed/uncompressed memory')
    compat.vector_zero(vector)
    require(gold == preflight['counts'], 'Complete8297 independent gold/guards')
    require(wave['status'] == 'ACTUAL48_UPDATES_16_SLOTS_PER_PHASE_96_ACCEPTED_HITS_EXACT'
            and wave['inference_from_VA_count'] is False and len(wave['updates']) == 48
            and len(wave['accepted_loads']) == 96, 'Actual updates/load owners, not VA inference')
    expected_updates = [(p, e, f.pre.shared.plru_order()[p][e], f.pre.pa(f.pre.page(p, e)) >> 12)
                        for p in range(3) for e in range(16)]
    require([(u['phase'], u['entry'], u['slot'], u['ppn']) for u in wave['updates']] == expected_updates,
            '48 actual PPN/slot/phase bindings')
    require([(u['phase'], u['entry'], u['slot'], u['load_in_pair']) for u in wave['accepted_loads']] ==
            [(p, e, f.pre.shared.plru_order()[p][e], b)
             for p in range(3) for e in range(16) for b in range(2)], '96 actual load owner bindings')


def native_identity(sim, args, record, design):
    tests = sim.findall('srctest')
    require(sim.tag == 'test' and len(tests) == 1, 'One native test owner')
    test = tests[0]
    require(shlex.split(test.get('cmdline', '')) == record['command'] and
            test.get('workdir') == str(RUN) and test.get('seed') == '1' and
            test.get('starttime', '').isdigit() and test.get('finishtime', '').isdigit() and
            int(test.get('finishtime')) > int(test.get('starttime')), 'Native command/cwd/seed/times')
    require(args.tag == 'vcm_args' and args.get('compvdbpath') == design and
            sorted(n.get('vcm_opt') for n in args.findall('vcm_arg_data') if n.get('vcm_opt')) ==
            ['-cm branch', '-cm cond', '-cm fsm', '-cm line', '-cm tgl'], 'Frozen five-metric design')
    return dict(command=record['command'], workdir=str(RUN), design=design, seed=1,
                XML_teststatus=test.get('teststatus'), XML_teststatus_is_not_PASS_authority=True)


def historical(ledger, elf_hash, authority):
    audit = dedup(ledger, elf_hash, authority)
    require(audit['ledger_members'] == 779 and audit['duplicate'] is False and
            [r['vdb'] for r in audit['members']] == ledger[1:] and
            all(authority.get(p) == h for p, h in audit['pins'].items()), 'Historical-only sealed ELF dedup')
    return dict(audit, baseline=779, candidate_qualification_not_used_as_historical_owner=True)


def evaluate():
    base = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    require(base['coverage_admitted'] is True and base['output'] == str(BASE), 'Formal779 authority')
    authority = life.merge_pins(base['input_pins'], base['output_pins'])
    receipt_path = QUAL / 'postrun-schema-qualification.json'
    receipt = life.read_bound(receipt_path, RECEIPT_SHA)
    require(receipt['status'] == compat.STATUS and receipt['qualification'] == str(QUAL / 'qualification.json')
            and receipt['qualification_seal'] == Q_SHA and receipt['prepared_seal'] == PREPARED_SHA
            and receipt['coverage_admitted'] is False and receipt['full_original_gates_replayed'] is True
            and receipt['no_vector_PASS_claim'] is True and receipt['VCS_rerun'] is False,
            'Complete parent schema-consumer receipt')
    q = life.read_bound(QUAL / 'qualification.json', Q_SHA)
    pins = life.merge_pins(authority, receipt['input_pins'])
    pins = life.merge_pins(pins, life.merge_pins(q['input_pins'], q['output_pins']))
    fixed = {str(BASE / 'admission-manifest.json'): BASE_SHA, str(QUAL / 'qualification.json'): Q_SHA,
             str(receipt_path): RECEIPT_SHA, str(CACHE): CACHE_SHA}
    for p in (Path(__file__).resolve(), Path(__file__).with_name('test_admit_dtlb_ppn_swap780.py').resolve(),
              Path(bitmap.__file__).resolve(), Path(dedup.__code__.co_filename).resolve()):
        fixed[str(p)] = life.digest(p)
    pins = life.merge_pins(pins, fixed); life.check(pins)
    def bdoc(name):
        p = BASE / name; return life.read_bound(p, base['output_pins'][str(p)])
    def qdoc(name):
        p = QUAL / name; return life.read_bound(p, q['output_pins'][str(p)])
    before = bdoc('combined-bits.json'); status = bdoc('status.json')
    ledger = (BASE / 'combined-inputs.txt').read_text().splitlines()
    require(status['coverage_admitted'] is True and status['aggregate_passed'] == 779 and
            ledger == [str(life.IMAGE) + '.vdb', *before['tests']] and len(set(ledger)) == 780,
            'Exact formal779 ledger/status')
    prepared = RUN.with_name(RUN.name + '.prepared.json')
    record = f.runner.check(prepared, PREPARED_SHA); f.runner.validate_record(record)
    require(life.read_bound(RUN / 'manifest.json', pins[str(RUN / 'manifest.json')]) ==
            dict(record, pins=life.merge_pins(record['pins'], {str(prepared): PREPARED_SHA})), 'Executed manifest binding')
    f.terminal_gate(life.read_bound(RUN / 'simulation-status.json', pins[str(RUN / 'simulation-status.json')]))
    f.identity_gate(life.read_bound(RUN / 'live-simv-identity.json', pins[str(RUN / 'live-simv-identity.json')]), record)
    f.logs((RUN / 'console.log').read_text(), (RUN / 'run.vcs.log').read_text())
    preflight = life.read_bound(f.runner.PRE, f.runner.PRE_SHA)
    architecture(q, qdoc('scalar-comparison.json'), qdoc('full-memory-audit.json'),
                 qdoc('vector-comparison.json'), qdoc('tlb-slot-audit.json'), qdoc('gold-audit.json'), preflight)
    members = sorted(p for p in (RUN / 'code.vdb').rglob('*') if p.is_file())
    require(not any(p.is_symlink() for p in (RUN / 'code.vdb').rglob('*')) and
            {str(p) for p in members} == {p for p in q['input_pins'] if p.startswith(str(RUN / 'code.vdb') + '/')},
            'Complete terminal VDB membership pinned')
    folder = RUN / 'code.vdb/snps/coverage/db/testdata' / f.runner.CASE
    require(list(folder.parent.iterdir()) == [folder], 'Exact singleton native test')
    identity = native_identity(toggle.xml(folder / 'siminfo.xml'), toggle.xml(folder / 'vcmArguments.xml'), record, ledger[0])
    design_db = Path(ledger[0]) / 'snps/coverage/db'
    require(all(life.digest(design_db / rel) == h == pins[str(design_db / rel)]
                for rel, h in before['design'].items()), 'Full frozen design/shape fingerprint')
    single = dict(design=before['design'], tests=[str(RUN / 'code.vdb')], input_hashes={}, metrics={})
    for metric in bitmap.METRICS:
        p = folder / (metric + '.verilog.data.xml')
        single['metrics'][metric] = bitmap.read_metric(p); single['input_hashes'][str(p)] = pins[str(p)]
    after = full_union(before, single); delta = bitmap.delta(before, after)
    cache = life.read_bound(CACHE, CACHE_SHA)
    cp = next(Path(p) for p in cache['pins'] if p.endswith('/combined-inputs.txt'))
    require(life.digest(cp) == cache['pins'][str(cp)] and ledger[:774] == cp.read_text().splitlines(),
            'Exact cached773 prefix')
    require(all(str(Path(x['toggle']).parents[5]) in before['tests'] for x in cache['overlay_qualifications']),
            'Cached overlays must already be admitted779 members')
    prior = {f.SCOPE: cache['union'][f.SCOPE]}
    def sample(vdb, evidence):
        files = list((Path(vdb) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files) == 1, 'One native Toggle sample')
        rows, sha = toggle.rows(files[0], [f.SCOPE])
        require(evidence.get(str(files[0])) == sha, 'Toggle sample bound to authority')
        return rows
    for db in before['tests'][773:]: prior = toggle.union(prior, sample(db, authority))
    added = sample(str(RUN / 'code.vdb'), q['input_pins']); final = toggle.union(prior, added)
    positions = toggle.gains(prior, final)[f.SCOPE]
    require(prior[f.SCOPE]['width'] == 11852 and prior[f.SCOPE]['checksum'] == '817233724'
            and positions, 'Exact DTLB shape / positive measured Toggle gain')
    gain = dict(baseline=779, scope=f.SCOPE, before=prior[f.SCOPE], single=added[f.SCOPE], after=final[f.SCOPE],
                new_positions=len(positions), new_serialized_positions=positions,
                official_percentage=False, direction_labels_verified=False)
    elf = f.runner.PRE.parent / 'input.elf'
    elf_audit = historical(ledger, pins[str(elf)], authority)
    pins = life.merge_pins(pins, elf_audit['pins']); life.check(pins)
    retained = {Path(p).name: life.read_bound(Path(p), h) for p, h in base['output_pins'].items()
                if Path(p).parent == BASE and Path(p).suffix == '.json'
                and ('toggle-gain' in Path(p).name or Path(p).name.startswith('retained-'))}
    products = dict(retained, **{'single-bits.json': single, 'combined-bits.json': after, 'raw-delta.json': delta,
        'dtlb-toggle-gain.json': gain, 'native-vdb-identity.json': identity, 'elf-ledger-dedup.json': elf_audit,
        'evidence-pins.json': pins, 'status.json': dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', baseline=779,
            aggregate_passed=780, coverage_admitted=True, exact_previous_prefix=True, full_OR_metric_instances=6162,
            unique_new_vdb=True, duplicate_ELF=False, full_scalar_ISA=True, full_scalar_memory_instructions=19071,
            scalar_retired=191475, actual_updates=48, actual_slots_per_phase=16, actual_accepted_loads=96,
            checks=8297, vector_status='UNOBSERVABLE_ZERO_REQUESTS', vector_comparison_PASS=False,
            scoped_DTLB_new_toggle_positions=len(positions), raw_delta=delta['metrics'],
            historical_fixed_image_only=True, new_RTL_signoff=False, new_simulation=False,
            official_percentage_claimed=False, retained_prior_gain_not_recounted=True)})
    return products, '\n'.join([ledger[0], *after['tests']]) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'verify', 'admit'))
    p.add_argument('--output', type=Path, required=True); p.add_argument('--seal')
    p.add_argument('--parent-authorized', action='store_true'); a = p.parse_args()
    require(a.parent_authorized == (a.mode == 'admit') and bool(a.seal) == (a.mode != 'prepare'), 'Explicit authorization/seal')
    out = a.output.resolve(); require(out.parent == life.OUT and not out.exists(), 'Fresh output only')
    values, text = evaluate()
    hashes = {str(out / name): hashlib.sha256((json.dumps(value, indent=2) + '\n').encode()).hexdigest()
              for name, value in values.items()}
    for name in ('combined-inputs.txt', 'generic-coverage-inputs.txt'):
        hashes[str(out / name)] = hashlib.sha256(text.encode()).hexdigest()
    proposal = dict(output=str(out), baseline=str(BASE), baseline_seal=BASE_SHA,
        qualification=str(QUAL / 'postrun-schema-qualification.json'), qualification_seal=RECEIPT_SHA,
        input_pins=values['evidence-pins.json'], output_pins=hashes, coverage_admitted=False)
    prepared = out.with_name(out.name + '.prepared.json')
    if a.mode == 'prepare':
        require(not prepared.exists(), 'No overwrite of prepared proposal')
        life.save(prepared, proposal); print('PREPARED_NOT_ADMITTED', life.digest(prepared), flush=True); return
    require(life.read_bound(prepared, a.seal) == proposal, 'Prepared evidence/products drift')
    if a.mode == 'verify': print('PREPARED_VERIFY_PASS_NO_ADMISSION', flush=True); return
    out.mkdir()
    for name, value in values.items(): life.save(out / name, value)
    for name in ('combined-inputs.txt', 'generic-coverage-inputs.txt'):
        with (out / name).open('x') as stream: stream.write(text)
    life.check(proposal['input_pins']); life.check(hashes)
    life.save(out / 'admission-manifest.json', dict(proposal, coverage_admitted=True,
        prepared=str(prepared), prepared_seal=a.seal, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))
    print('ADMITTED', life.digest(out / 'admission-manifest.json'), flush=True)


if __name__ == '__main__': main()

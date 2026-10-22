"""Offline case-specific eight ECALL contract; never rerun or admit GAP114."""
import csv
from pathlib import Path
import run_gap114_fsm as run

life, require = run.life, run.require
PRE = life.OUT/'gap114-spec-load-flush-preflight-742-20261007-02'
RUN = life.OUT/'gap114-spec-load-flush-old-image-742-20261007-02'
OUT = life.OUT/'gap114-eight-trap-postprocess-742-20261007-01'


def traps_exact(rows, symbols):
    retired = [r for r in rows if r['event'] == 'retire']
    require([int(r['order']) for r in retired] == list(range(len(retired))), 'Retirement order differs')
    expected = [symbols[name] for phase in range(4) for name in
                ('g114_trap_a' if phase < 2 else 'g114_trap_b', 'g114_trap_recovery')]
    traps = [r for r in retired if int(r['trap'])]
    require(len(traps) == 8 and [int(r['pc'], 16) for r in traps] == expected and
            all(int(r['trap']) == 1 and int(r['insn'], 16) == 0x73 for r in traps),
            'Exact ECALL trap PC/instruction/type differs')
    return dict(traps=8, pcs=expected, instruction=0x73, trap_type='S-mode ECALL cause9 (independent ledger)',
                retired_including_traps=len(retired))


def collect():
    require(not OUT.exists(), 'Fresh postprocess directory required')
    pre = life.read_bound(PRE/'successor-preflight.json', life.digest(PRE/'successor-preflight.json'))
    manifest = life.read_bound(RUN/'manifest.json', life.digest(RUN/'manifest.json'))
    require(manifest['pins'][str(PRE/'successor-preflight.json')] == life.digest(PRE/'successor-preflight.json'),
            'Executed preflight differs')
    pins = life.merge_pins(pre['pins'], manifest['pins'])
    require(life.read_bound(RUN/'simulation-status.json', life.digest(RUN/'simulation-status.json'))['returncode'] == 0,
            'Simulation not successful terminal')
    for p in [PRE/'successor-preflight.json', RUN/'manifest.json', RUN/'failure.json',
              RUN/'simulation-status.json', RUN/'commit_trace.csv', RUN/'vector_trace.csv',
              RUN/'run.vcs.log', RUN/'console.log', Path(__file__).resolve(),
              Path(__file__).with_name('test_postprocess_gap114_traps.py')]:
        pins = life.merge_pins(pins, {str(p): life.digest(p)})
    life.check(pins); OUT.mkdir()
    try:
        with (RUN/'commit_trace.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        trap_audit = traps_exact(rows, pre['symbols']); life.save(OUT/'trap-audit.json', trap_audit)
        memory = {}
        for row in rows:
            if row['event'] == 'retire':
                store = run.shared.scalar_store(row)
                if store: memory.update({store[0]+i: b for i, b in enumerate(store[1])})
        def value(name, offset=0, size=8):
            address = pre['symbols'][name]+offset
            require(all(address+i in memory for i in range(size)), 'Missing oracle byte')
            return int.from_bytes(bytes(memory[address+i] for i in range(size)), 'little')
        run.oracle(value, pre['symbols'])
        scalar = run.shared.spike_trace.compare_commit_prefix(PRE/'spike.trace', RUN/'commit_trace.csv',
            0x80000000, terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
        life.save(OUT/'scalar-comparison.json', scalar)
        run.shared.scalar_exact(scalar, dict(pre['counts'], ara_trap_events=8))
        require(trap_audit['retired_including_traps'] == scalar['matched_instructions']+8,
                'Trap and compared retirement counts differ')
        vector = run.shared.compare_vector_commits(PRE/'spike.trace', RUN/'commit_trace.csv',
                                                  RUN/'vector_trace.csv', 0x80000000)
        life.save(OUT/'vector-comparison.json', vector)
        require(vector['status'] == 'PASS' and vector['compared_instructions'] == 32 and
                vector['compared_bytes'] == 4096 and vector['skipped_unknown_bytes'] ==
                vector['non_bit_exact_instructions'] == vector['unobservable_instructions'] == 0 and
                not vector['incomplete_requests'] and not vector['unretired_requests'] and
                all(i['unknown_write_bytes'] == i['skipped_unknown_bytes'] == i['mismatch_count'] == 0
                    for i in vector['instructions']), 'Complete vector contract differs')
        require((RUN/'console.log').read_text().count('Core Test *** SUCCESS ***') == 1 and
                not run.shared.check_contract_log(RUN/'run.vcs.log'), 'Terminal/contract differs')
        basepath = run.reviewed.base.BASE/'combined-bits.json'
        book = life.read_bound(run.reviewed.base.BASE/'admission-manifest.json', run.reviewed.base.BASE_SHA)
        before = life.read_bound(basepath, book['output_pins'][str(basepath)])
        inputs = OUT/'measurement-inputs.txt'
        with inputs.open('x') as stream:
            stream.write(str(run.reviewed.base.capture.BUILD/'sim/simv.vdb')+'\n'+str(RUN/'code.vdb')+'\n')
        single = run.shared.bitmap.collect(inputs)
        delta = run.shared.bitmap.delta(before, run.shared.bitmap.combine(before, single))
        hits = []
        for scope, indices in pre['targets'].items():
            old, new = before['metrics']['fsm'][scope], single['metrics']['fsm'][scope]
            require((old['checksum'], old['width']) == (new['checksum'], new['width']), 'FSM identity differs')
            for index in indices:
                hits.append(dict(scope=scope, raw_index=index,
                                 hit=bool(int(new['bits'], 16)&(1 << (new['width']-1-index)))))
        for p in (RUN/'code.vdb').rglob('*'):
            if p.is_file(): pins = life.merge_pins(pins, {str(p): life.digest(p)})
        life.check(pins)
        life.save(OUT/'single-bits.json', single); life.save(OUT/'input-pins.json', pins)
        life.save(OUT/'qualification.json', dict(status='EIGHT_ECALL_ARCHITECTURE_PASS_RAW_DIAGNOSTIC_NOT_ADMITTED',
            checks=2619, traps=trap_audit, targets=hits, delta=delta, coverage_admitted=False,
            original_failure_preserved=str(RUN/'failure.json'), original_failure_is_rtl_bug=False))
    except Exception as exc:
        life.save(OUT/'failure.json', dict(reason=str(exc), coverage_admitted=False)); raise


if __name__ == '__main__': collect()

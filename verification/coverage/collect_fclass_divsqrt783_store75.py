"""Exact75 store-context successor; original collector and failed evidence immutable."""
import argparse
import copy
from pathlib import Path
from types import FunctionType, SimpleNamespace
import collect_fclass_divsqrt783 as original

life, require = original.life, original.require
ORIGINAL_SHA = 'e2d833bde979e3179acf734520d1b3c45bac496233851e98440376daa544710c'


def restore_stores(activities, rows, reference, mapping, symbols):
    require(all(seq in mapping for seq in activities), 'All native owners mapped')
    result = copy.deepcopy(activities)
    stores = {s: a for s, a in result.items() if a.instruction & 127 == 0x27}
    pc_widths = {symbols['matrix_store' + str(w)]: w for w in (16, 32, 64)}
    expected = {s: i for s, i in mapping.items() if reference[i].pc in pc_widths}
    require(len(stores) == len(expected) == 75 and set(stores) == set(expected), 'Exactly75 owned matrix store activities')
    grouped = {seq: [] for seq in stores}
    for row in rows:
        seq = int(row['arch_seq'])
        if seq in stores: grouped[seq].append(row)
    records = []
    for cell, (seq, a) in enumerate(sorted(stores.items())):
        commit = reference[expected[seq]]; width = pc_widths[commit.pc]; eew = {16: 1, 32: 2, 64: 3}[width]
        require(width == 16 << (cell // 25) and a.instruction == commit.instruction
            and a.instruction & 127 == 0x27 and (a.instruction >> 12 & 7) == eew + 4
            and not commit.vector_writes, 'Exact store PC/opcode/format/cell')
        rr = grouped[seq]
        require(all(r['event'] in ('alloc', 'done') and int(r['insn'], 16) == a.instruction for r in rr), 'Store only owned alloc/done, no writes')
        allocs = [r for r in rr if r['event'] == 'alloc']; dones = [r for r in rr if r['event'] == 'done']
        require(len(allocs) == len(dones) == a.allocations == a.completions == 1 and a.use_vd is False
            and a.vd == ((a.instruction >> 7) & 31) == 24 and not a.writes
            and (a.eew, a.vl, a.vstart) == (None, None, None), 'Exact non-writer parser contract/encoded vs3')
        alloc, done = allocs[0], dones[0]
        require(int(alloc['eew']) == eew and int(alloc['vl']) == 256 // width and int(alloc['vstart']) == 0
            and int(alloc['use_vd']) == int(alloc['vd']) == 0, 'Instruction-derived store context')
        require(all(alloc[k] == done[k] for k in ('use_vd', 'vd', 'eew', 'vl', 'vstart', 'vid'))
            and 0 <= int(alloc['vid']) < 8 and int(alloc['cycle']) <= int(done['cycle'])
            and all(int(r['nr_lanes']) == 4 and int(r['vlen_bits']) == 1024 for r in rr), 'Store VID/geometry/lifecycle ordering')
        before = copy.deepcopy(vars(a)); a.eew, a.vl, a.vstart = eew, 256 // width, 0
        after = vars(a)
        require({k for k in before if before[k] != after[k]} == {'eew', 'vl', 'vstart'}, 'Only missing context metadata restored')
        records.append(dict(cell=cell, arch_seq=seq, reference_index=expected[seq], pc=commit.pc,
            opcode=commit.instruction, alloc_cycle=int(alloc['cycle']), done_cycle=int(done['cycle']),
            vid=int(alloc['vid']), before=dict(eew=None, vl=None, vstart=None),
            after=dict(eew=eew, vl=256 // width, vstart=0)))
    require(set(result) == set(activities) and all(vars(result[s]) == vars(activities[s]) for s in result if s not in stores), 'All non-store activities unchanged')
    return result, dict(status='EXACT75_RAW_OWNED_STORE_CONTEXT_RESTORED', records=records,
        store_count=75, changes_only=['eew', 'vl', 'vstart'], no_writer_or_byte_filtered=True)


def actual_store_proof(run):
    pre = original.runner.preflight(); reference = original.reference_prefix(pre)
    lanes, vlen, activities = original.vc._parse_vector_trace(run / 'vector_trace.csv')
    rows = original.common.read_csv((run / 'vector_trace.csv').read_bytes(), original.common.VECTOR_FIELDS)
    starts, retires, rejected = original.vc._parse_architecture_mapping(run / 'commit_trace.csv')
    require((lanes, vlen) == (4, 1024) and not rejected, 'Exact geometry/no rejected owners')
    mapping = original.vc._map_spike_commits(original.vc._map_architecture_retires(starts, retires, rejected), reference)
    return restore_stores(activities, rows, reference, mapping, pre['symbols'])


def publish_closure(out, core_sha, proof, pins):
    result_path = out / 'qualification.json'
    result = life.read_bound(result_path, core_sha)
    require(result['status'] == 'FCLASS_DIVSQRT783_FULL_ARCHITECTURE_NATIVE_RAW_QUALIFIED_NOT_ADMITTED'
        and result['native']['operations']['store'] == 75, 'Original full strict qualification must pass')
    proof_path = out / 'store75-context-proof.json'
    closure_path = out / 'store75-closure.json'
    require(not proof_path.exists() and not closure_path.exists(), 'Exclusive fresh successor publication')
    require(proof['store_count'] == len(proof['records']) == 75, 'Complete source-bound store proof')
    life.save(proof_path, proof)
    pins = life.merge_pins(pins, {str(proof_path): life.digest(proof_path), str(result_path): core_sha})
    pins = life.merge_pins(result['input_pins'], pins)
    life.check(pins)
    closure = dict(status='FCLASS_DIVSQRT783_STORE75_FULL_SUCCESSOR_QUALIFIED_NOT_ADMITTED',
        core_qualification=str(result_path), core_qualification_sha=core_sha,
        original_collector_sha=ORIGINAL_SHA, proof=str(proof_path), proof_sha=life.digest(proof_path),
        original_checks_preserved=True, input_pins=pins, coverage_admitted=False,
        EDA_launched=False, RTL_modified=False, core_qualification_unchanged=True)
    life.save(closure_path, closure)
    require(life.digest(result_path) == core_sha, 'Core qualification must remain byte-identical')
    return closure_path


def collect(run, seal, out):
    original_path = Path(original.__file__).resolve()
    require(life.digest(original_path) == ORIGINAL_SHA, 'Original frozen collector identity')
    paths = (Path(__file__).resolve(), Path(__file__).with_name('test_collect_fclass_divsqrt783_store75.py').resolve())
    pins = {str(path): life.digest(path) for path in paths}; pins[str(original_path)] = ORIGINAL_SHA
    proofs = []
    def restore(activities, rows):
        pre = original.runner.preflight(); reference = original.reference_prefix(pre)
        starts, retires, rejected = original.vc._parse_architecture_mapping(run / 'commit_trace.csv')
        require(not rejected, 'No trapped/rejected store owners')
        mapping = original.vc._map_spike_commits(original.vc._map_architecture_retires(starts, retires, rejected), reference)
        result, proof = restore_stores(activities, rows, reference, mapping, pre['symbols'])
        proofs.append(proof); return result
    proxy = SimpleNamespace(**vars(original.reused))
    proxy.store_adapter = SimpleNamespace(restore_stores=restore)
    life.check(pins)
    FunctionType(original.collect.__code__, dict(original.collect.__globals__, reused=proxy))(run, seal, out)
    require(len(proofs) == 1, 'Exactly one store restoration, no retry')
    result_path = out / 'qualification.json'
    closure_path = publish_closure(out, life.digest(result_path), proofs[0], pins)
    print('STORE75_FULL_QUALIFIED_NOT_ADMITTED', life.digest(closure_path), flush=True)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__); cli.add_argument('--run', type=Path, required=True)
    cli.add_argument('--seal', required=True); cli.add_argument('--output', type=Path, required=True)
    args = cli.parse_args(); collect(args.run.resolve(), args.seal, args.output.resolve())

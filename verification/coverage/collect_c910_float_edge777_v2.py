"""Strict raw store context adapter; frozen failed collector remains unchanged."""
import argparse
import copy
import csv
from pathlib import Path
from types import FunctionType
import collect_c910_float_edge777 as old

life, require = old.life, old.require
OLD_SHA = 'ffb6404656a6174f43d619281a88870d4b4d7039249ef501219c9360ce772eb3'


def store_context(rows, reference, activities, mapping, symbols):
    roles = {symbols['edge_store' + str(w)]: w for w in (16, 32, 64)}
    stores = {seq: (reference[i], roles[reference[i].pc]) for seq, i in mapping.items()
              if reference[i].pc in roles}
    require(len(stores) == 48, 'Exactly48 mapped stores')
    result = dict(activities)
    for seq, (commit, width) in stores.items():
        events = [r for r in rows if r['event'] != 'config' and int(r['arch_seq']) == seq]
        alloc = [r for r in events if r['event'] == 'alloc']
        done = [r for r in events if r['event'] == 'done']
        require(len(alloc) == len(done) == 1 and len(events) == 2, 'Store exact single alloc/done; no VRF writes')
        a, d = alloc[0], done[0]
        require(int(a['cycle']) < int(d['cycle']) and a['vid'] == d['vid'] and 0 <= int(a['vid']) < 8,
                'Store VID/completion identity')
        for row in events:
            require(int(row['insn'], 16) == commit.instruction and int(row['use_vd']) == 0
                and int(row['vd']) == 0 and int(row['eew']) == {16: 1, 32: 2, 64: 3}[width]
                and int(row['vl']) == 256 // width and int(row['vstart']) == 0
                and int(row['nr_lanes']) == 4 and int(row['vlen_bits']) == 1024,
                'Exact raw store opcode/nonwriter/EEW/VL/vstart/geometry')
        activity = activities[seq]
        require(activity.instruction == commit.instruction and not activity.use_vd and not activity.writes
            and activity.allocations == activity.completions == 1, 'Parsed store lifecycle/nonwriter agrees')
        bound = copy.copy(activity)
        bound.eew, bound.vl, bound.vstart = int(a['eew']), int(a['vl']), int(a['vstart'])
        result[seq] = bound
    return result


def native(run, reference, symbols):
    with (run / 'vector_trace.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    def state(ref, activities, mapping, syms):
        return old.native_state(ref, store_context(rows, ref, activities, mapping, syms), mapping, syms)
    namespace = dict(old.native.__globals__, native_state=state)
    return FunctionType(old.native.__code__, namespace)(run, reference, symbols)


def collect(run, seal, out):
    require(life.digest(Path(old.__file__).resolve()) == OLD_SHA, 'Frozen predecessor identity')
    def evidence(*args):
        pins = old.inherited.evidence_pins(*args)
        for name in ('collect_c910_float_edge777_v2.py', 'test_collect_c910_float_edge777_v2.py'):
            path = Path(__file__).with_name(name).resolve(); pins[str(path)] = life.digest(path)
        return pins
    from types import SimpleNamespace
    inherited = SimpleNamespace(**vars(old.inherited)); inherited.evidence_pins = evidence
    namespace = dict(old.collect.__globals__, native=native, inherited=inherited)
    return FunctionType(old.collect.__code__, namespace)(run, seal, out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True); parser.add_argument('--seal', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); collect(args.run.resolve(), args.seal, args.output.resolve())

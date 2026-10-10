"""Restore store alloc metadata omitted by the writer-oriented trace parser."""
import argparse
import copy
from pathlib import Path
from types import FunctionType, SimpleNamespace

import collect_c910_float_edge777 as original

life, require = original.life, original.require


def restore_stores(activities, rows):
    result = copy.deepcopy(activities)
    stores = {seq: a for seq, a in result.items() if a.instruction & 127 == 0x27}
    require(len(stores) == 48, 'Exactly48 vector store activities')
    allocations = {seq: [] for seq in stores}
    completions = {seq: [] for seq in stores}
    for row in rows:
        seq = int(row['arch_seq'])
        if seq not in stores:
            continue
        require(int(row['insn'], 16) == stores[seq].instruction, 'Store raw opcode identity')
        if row['event'] == 'alloc':
            allocations[seq].append(row)
        elif row['event'] == 'done':
            completions[seq].append(row)
        else:
            require(False, 'Store must not generate VRF write events')
    for seq, activity in stores.items():
        require(len(allocations[seq]) == len(completions[seq]) == 1 and
                activity.allocations == activity.completions == 1 and
                activity.use_vd is False and not activity.writes and
                (activity.eew, activity.vl, activity.vstart) == (None, None, None),
                'Exact non-writer store parser contract/lifecycle')
        alloc, done = allocations[seq][0], completions[seq][0]
        eew = {5: 1, 6: 2, 7: 3}.get(activity.instruction >> 12 & 7)
        require(eew is not None and int(alloc['eew']) == eew and
                int(alloc['vl']) == 256 // (8 << eew) and int(alloc['vstart']) == 0,
                'Instruction-bound32-byte store EEW/VL/vstart')
        require(int(alloc['use_vd']) == int(alloc['vd']) == 0 and
                all(alloc[k] == done[k] for k in ('use_vd', 'vd', 'eew', 'vl', 'vstart')) and
                int(alloc['vid']) == int(done['vid']) and 0 <= int(alloc['vid']) < 8 and
                int(alloc['cycle']) <= int(done['cycle']) and
                all(int(r['nr_lanes']) == 4 and int(r['vlen_bits']) == 1024
                    for r in (alloc, done)), 'Raw store VID/geometry/ordering identity')
        activity.eew, activity.vl, activity.vstart = eew, int(alloc['vl']), 0
    return result


def native(run, reference, symbols):
    def parse(path):
        lanes, vlen, activities = original.vc._parse_vector_trace(path)
        rows = original.common.read_csv(Path(path).read_bytes(), original.common.VECTOR_FIELDS)
        return lanes, vlen, restore_stores(activities, rows)
    proxy = SimpleNamespace(**{**vars(original.vc), '_parse_vector_trace': parse})
    return FunctionType(original.native.__code__,
                        {**original.native.__globals__, 'vc': proxy})(run, reference, symbols)


def collect(run, seal, out):
    files = (Path(__file__).resolve(), Path(__file__).with_name(
        'test_collect_c910_store_context_parent.py').resolve())
    pins = {str(path): life.digest(path) for path in files}
    FunctionType(original.collect.__code__,
                 {**original.collect.__globals__, 'native': native})(run, seal, out)
    life.check(pins)
    qualification = out / 'qualification.json'
    result = life.read_bound(qualification, life.digest(qualification))
    require(result['status'] == 'C910_FLOAT_EDGE_FULL_SCALAR_NATIVE_CSR_RAW777_PASS_NOT_ADMITTED'
            and result['native']['primary']['operations']['store'] == 48,
            'Original full qualification passed with all48 raw stores')
    life.check(result['input_pins'])
    life.save(out / 'store-context-closure.json', dict(
        status='FULL_C910_QUALIFICATION_RAW_STORE_CONTEXT_CLOSED_NOT_ADMITTED',
        original_qualification=str(qualification), qualification_sha256=life.digest(qualification),
        adapter_pins=pins, original_input_pins=result['input_pins'],
        change='Restore only48 non-writer store contexts from exact native alloc/done records',
        original_checks_preserved=True, EDA_launched=False, RTL_modified=False,
        coverage_admitted=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--seal', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    collect(args.run.resolve(), args.seal, args.output.resolve())

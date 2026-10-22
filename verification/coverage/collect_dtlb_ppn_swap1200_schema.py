"""Private zero-vector schema correction; replay every frozen postrun gate."""
import argparse
from pathlib import Path
from types import FunctionType

import collect_dtlb_ppn_swap1200 as frozen

life, require = frozen.life, frozen.require
FROZEN_SHA = '3a8f1b0be0d4910ee1c2a67f903bd19e4aaa9b6ed8a1ae2453efe6368711bd3e'
VECTOR_SHA = 'ed9e2cae2be4ab6d79eed5bf2499ad0f217bd116d3cba11b4454d42623c5a133'
TEST = Path(__file__).with_name('test_collect_dtlb_ppn_swap1200_schema.py').resolve()
STATUS = 'DTLB_PPN_SWAP779_FULL_POSTRUN_SCHEMA_QUALIFIED_NOT_ADMITTED'


def zero_schema():
    return dict(
        status='UNOBSERVABLE',
        method=('non-intrusive accepted VRF writeback comparison, grouped by architectural '
                'request and deshuffled by destination EEW'),
        nr_lanes=4, vlen_bits=1024, selected_index=None,
        vector_destination_requests=0, prefix_vector_destination_requests=0,
        stopped_at_spike_index=None, compared_instructions=0, compared_bytes=0,
        skipped_unknown_bytes=0, non_bit_exact_instructions=0,
        unobservable_instructions=0, incomplete_requests=[], unretired_requests=[],
        trapped_requests=[], verified_zero_write_traps=[], verified_identity_write_traps=[],
        verified_probed_load_faults=[], verified_trapped_destination_requests=[],
        first_mismatch=None, instructions=[])


def vector_zero(result):
    expected = zero_schema()
    require(type(result) is dict and set(result) == set(expected), 'Exact vector schema keys')
    for key, value in expected.items():
        require(type(result[key]) is type(value) and result[key] == value,
                'Exact UNOBSERVABLE zero scope differs: ' + key)


def consumer():
    require(life.digest(Path(frozen.__file__)) == FROZEN_SHA, 'Frozen collector drift')
    require(life.digest(Path(frozen.vector_commit.__file__)) == VECTOR_SHA, 'Vector source drift')
    namespace = dict(frozen.collect.__globals__, vector_zero=vector_zero)
    return FunctionType(frozen.collect.__code__, namespace, frozen.collect.__name__,
                        frozen.collect.__defaults__, frozen.collect.__closure__)


def collect(prepared, seal, output):
    pins = {str(Path(__file__).resolve()): life.digest(Path(__file__)),
            str(TEST): life.digest(TEST), str(Path(frozen.__file__).resolve()): FROZEN_SHA,
            str(Path(frozen.vector_commit.__file__).resolve()): VECTOR_SHA}
    life.check(pins)
    # No mutation of frozen module globals or executed manifests. The original
    # collector retains its complete scalar, memory, wave, owner and pin gates.
    consumer()(prepared, seal, output)
    qpath = output / 'qualification.json'
    qsha = life.digest(qpath)
    q = life.read_bound(qpath, qsha)
    require(q['status'] == 'DTLB_PPN_SWAP779_FULL_ARCHITECTURE_AND_ACTUAL_SLOTS_QUALIFIED_NOT_ADMITTED'
            and q['coverage_admitted'] is False and q['vector_data_scope'] == 'UNOBSERVABLE_ZERO_REQUESTS',
            'Full frozen consumer qualification required')
    require((q['scalar_memory_instructions'], q['slot_updates'], q['slots_per_phase'],
             q['translated_loads'], q['all_gold_checks']) == (19071, 48, 16, 96, 8297),
            'Full original obligations differ')
    vector_zero(life.read_bound(output / 'vector-comparison.json',
                              q['output_pins'][str(output / 'vector-comparison.json')]))
    pins = life.merge_pins(pins, q['input_pins'])
    pins = life.merge_pins(pins, q['output_pins'])
    pins = life.merge_pins(pins, {str(qpath): qsha})
    life.check(pins)
    receipt = output / 'postrun-schema-qualification.json'
    life.save(receipt, dict(status=STATUS, baseline=779, coverage_admitted=False,
        qualification=str(qpath), qualification_seal=qsha, input_pins=pins,
        prepared=str(prepared), prepared_seal=seal,
        change='Only zero-vector schema gate; actual integer counters0, evidence lists empty',
        full_original_gates_replayed=True, vector_data_scope='UNOBSERVABLE_ZERO_REQUESTS',
        no_vector_PASS_claim=True, VCS_rerun=False))
    print(STATUS, life.digest(receipt), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--seal', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    collect(a.prepared.absolute(), a.seal, a.output.absolute())


if __name__ == '__main__':
    main()

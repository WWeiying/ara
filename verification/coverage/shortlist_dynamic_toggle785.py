"""Small source-bound dynamic shortlist, not a waiver or native gain claim."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
RANK = OUT / 'conservative-toggle785-static-agent-20261008-01.json'
RANK_SHA = '035172c63269024e6e2171426fa8616dedaf6da442f766934806dcb181cdd1d5'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert digest(RANK) == RANK_SHA
    ranking = json.loads(RANK.read_bytes())
    book_path = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    assert digest(book_path) == ranking['input_pins'][str(book_path)]
    book = json.loads(book_path.read_bytes())
    pins = {str(RANK): RANK_SHA, str(book_path): digest(book_path)}
    for relative in (
        'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
        'hardware/src/ara_soc.sv',
        'hardware/deps/cva6/core/store_unit.sv',
        'hardware/deps/cva6/core/amo_buffer.sv',
        'hardware/deps/cva6/core/cache_subsystem/wt_dcache_missunit.sv',
    ):
        path = ROOT / relative
        assert digest(path) == book[str(path)], str(path)
        pins[str(path)] = book[str(path)]
    names = {'amo_req_o.operand_b', 'amo_req_i.operand_b', 'amo_data',
             'amo_data_a', 'amo_data_b', 'data_o.data', 'mem_q[0].data', 'mem_n[0].data'}
    objects = []
    for row in ranking['ranking']:
        scope = row['scope']
        if not ('i_amo_buffer' in scope or scope.endswith('lsu_i') or scope.endswith('i_wt_dcache_missunit')):
            continue
        for obj in row['objects']:
            if obj['name'] in names:
                assert not obj['partial_EL_direction_binding_HOLD']
                assert obj['width'] == 64 and obj['missing_binary_positions'] == 128
                objects.append(dict(scope=scope, checksum=row['checksum'], name=obj['name'],
                                    width=64, missing_binary_positions=128))
    assert len(objects) == 9
    result = dict(
        status='SOURCE_BOUND_DYNAMIC_SHORTLIST_NO_EDA_NO_NATIVE_GAIN_CLAIM', population=785,
        input_pins=pins, objects=objects, total_missing_binary_positions=1152,
        source_path=[
            'config_pkg:29/102 RVA=1; ara_soc configuration does not disable RVA',
            'store_unit:254 unshifted AMO source operand; :258..276 operation decode',
            'store_unit:283 amo_buffer_valid; :322..341 st_data_q -> amo_buffer',
            'amo_buffer:56..58 input data; FIFO push valid_i, pop ack, flush speculative only',
            'amo_buffer:50 commit && stores_drained && valid; :54 operand_b=data_out.data',
            'wt_dcache_missunit:254..272 .W replicated low32 / .D full64 data selection',
            'wt_dcache_missunit:306..311 AMO data/op/address -> normal memory request',
        ],
        stimulus=dict(
            instructions='Fence, aligned AMOSWAP.D A -> ~A -> A; AMOSWAP.W B -> ~B -> B; Fence',
            A='0x96696996a55a5aa5', B='0xa55a5aa5',
            memory='One naturally aligned L2 word, surrounding immutable guards; no MMU fault or unsupported burst',
            oracle='Spike exact entry-to-tohost scalar/GPR/memory; independent old-value and final-memory table; .W old value sign-extended to XLEN',
            distinguishing_evidence='Each AMO decoded op/size, FIFO push/data and non-speculative request/ack; operand_b and selected missunit data follow A/~A/A or replicated B/~B/B',
            budget_estimate='Short six-AMO representative, proposed <=600s; not executed',
        ),
        limitations=[
            '1152 is repeated physical signal coverage capacity, not 1152 independent software bits or official Toggle denominator.',
            'No duplicate identity inferred from ledger filename search; actual new ELF and historical instruction ledger dedup required before launch.',
            'No native direction labels inferred from serialized coordinates; actual VDB gain is authoritative.',
            'Other large scopes remain mixed fixed/dynamic: scalar fault tval and normal PTE writers are dynamic, but no all-bit reachability or exact gain bound established.',
            'FP accumulator normal binary numeric fields already covered; remaining50 slots do not justify a large scale sweep. MDA/child metrics separately unbound.',
        ],
        constant_candidates='Separate frozen conservative report; no boot/hart/RVH0 fields counted as AMO stimulus targets.',
        EDA_launched=False, RTL_changed=False, waiver_applied=False,
    )
    for path, expected in pins.items():
        assert digest(Path(path)) == expected
    path = OUT / 'dynamic-toggle785-compact-shortlist-agent-20261008-01.json'
    with path.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(path, digest(path), '9_OBJECTS_1152_SERIALIZED_SLOTS_SOURCE_BOUND')


if __name__ == '__main__':
    main()

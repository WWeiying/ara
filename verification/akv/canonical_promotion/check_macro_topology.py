"""Check exact bound macro identities; not a computation or physical-area test."""
import re

PREFIX = 'akv_engine_synth_wrapper.i_akv_engine.i_unified_context.'
EXPECTED = {
    PREFIX + 'i_q_store.i_q_sram.i_q_geometry_probe': ('q', 6, 256),
    **{PREFIX + f'i_kv_store.gen_context_bank[{bank}].i_context_sram.i_kv_geometry_probe':
       ('kv', 7, 256) for bank in range(8)},
}
RECORD = re.compile(r'AKV_RESOURCE_MACRO role=(q|kv) address_bits=([0-9]+) '
                    r'data_bits=([0-9]+) path=(\S+)')


def check(text):
    seen = {}
    ended = False
    for line in text.splitlines():
        if re.search(r'Fatal:|Error(?:-|:)|\b(?:FAIL|FAILED|TIMEOUT)\b', line, re.I):
            raise ValueError('Structural smoke contains failure text')
        if line == 'AKV_RESOURCE_TOPOLOGY_END':
            if ended:
                raise ValueError('Duplicate end marker')
            ended = True
        elif line.startswith('AKV_RESOURCE_MACRO'):
            row = RECORD.fullmatch(line)
            if not row or ended or row[4] in seen:
                raise ValueError('Malformed, late or duplicate macro record')
            seen[row[4]] = (row[1], int(row[2]), int(row[3]))
        elif line.startswith('AKV_RESOURCE_'):
            raise ValueError('Unknown structural marker')
    if not ended or seen != EXPECTED:
        raise ValueError('Need exactly one Q64x256 and eight KV128x256 bound identities')
    return dict(state='BOUND_FUNCTIONAL_MACRO_TOPOLOGY_PASS', q_macros=1, kv_macros=8,
                logical_capacity_bytes=34816, computation_verified=False, ppa_measured=False)

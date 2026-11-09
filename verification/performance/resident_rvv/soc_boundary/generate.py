#!/usr/bin/env python3
"""Generate bit-pattern fixtures with explicit sealed model/snapshot provenance."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
from cases import SCHEMA, control, dest_pattern, guard_pattern, native_indices, scenarios

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
PREP = OUT/'resident_pv_prepare_vcs_20261109_01'
REAL = OUT/'resident_pv_real_operands_20261108_01.json'
DATA = OUT/'e2e_qwen3_f16_native_data_20261106_02'
BASE = OUT/'akv_pair_integration_build_20261107_01'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify(pins):
    for p, digest in pins.items():
        require(sha(p) == digest, 'Pinned input drift: '+p)


def provenance():
    # Validate the accepted receipts before parsing their recorded bit patterns.
    receipt = PREP/'result.json'
    require(sha(receipt) == '31be648df0fc3eb080cb26849900936923514f47764af214120eb367bdadd0e9',
            'Preparation receipt drift')
    report = json.loads(receipt.read_text())
    require(report['state'] == 'PASS', 'Preparation capture did not pass')
    pinfile = PREP/'source-pins.json'
    require(sha(pinfile) == report['source_pins_sha256'], 'Preparation inventory drift')
    log = PREP/'work/run.vcs.log'
    pins = {str(receipt): sha(receipt), str(log): report['artifacts'][str(log)]}
    verify(pins)
    pins.update(json.loads(pinfile.read_text()))
    pins[str(pinfile)] = sha(pinfile)
    verify(pins)
    parser = load(HERE.parent/'pv_prepare/experiment.py', 'boundary_sealed_preparation')
    parsed = parser.parse_preparation(log.read_text())
    require(len(parsed['records']) == 6, 'Expected three original and three repeated snapshots')
    snapshots = {}
    for line in log.read_text().splitlines():
        if line.startswith('PV_PREP_DATA '):
            fields = dict(w.split('=', 1) for w in line.split()[1:])
            width = 8 if fields['kind'] in ('probability', 'scale') else 4
            bits = fields['bits']
            snapshots[int(fields['id']), fields['kind']] = [int(bits[i:i+width], 16)
                                                           for i in range(0, len(bits), width)]
    corpus = json.loads(REAL.read_text())
    require(corpus['state'] == 'REAL_PV_OPERANDS_INDEPENDENTLY_CHECKED' and
            len(corpus['cases']) == 12 and corpus['checked_scalar_fmas'] == 35072,
            'Wrong prepared real corpus')
    verify(corpus['artifacts'])
    pins.update(corpus['artifacts'])
    pins[str(REAL)] = sha(REAL)
    primary = load(ROOT/'verification/performance/akv_pair_eval/build.py', 'boundary_primary_data')
    pins.update(primary.validate_data(DATA))
    for p in (HERE.parent/'pv_prepare/experiment.py', HERE.parent/'pv_prepare/prepare.S',
              HERE.parent/'ordered_reference.py', ROOT/'verification/performance/akv_pair_eval/build.py'):
        pins[str(p)] = sha(p)
    require(pins[str(HERE.parent/'pv_prepare/prepare.S')] ==
            '8d039dd90da0b00497429be90483d0ed9f3576c1400f458889e9e8cd380968be', 'Prepare helper drift')
    return snapshots, corpus, pins


def prepared_fma(ref, seed, coefficient, values, rm):
    accum = [r[:] for r in seed]
    flags, lanes = 0, [0]*4
    for t, value in enumerate(values):
        for h in range(len(seed)):
            for i, v in enumerate(value):
                accum[h][i], ex = ref.sf.evaluate('fma', 16, 16, rm,
                                                 coefficient[h][t], v, accum[h][i])
                flags |= ex
                lanes[i % 4] |= ex
    return accum, flags, lanes


def construct(snapshots, corpus, ref, values, query, key):
    result = []
    for spec in scenarios():
        r = dict(spec)
        d, h, t, tile = (r[k] for k in ('dimension', 'heads', 'tokens', 'tile'))
        start = (0, 64, 128)[tile]
        probability = snapshots[tile, 'probability'][:]
        scale = snapshots[tile, 'scale'][:]
        seed = [0]*512
        for head in range(2):
            seed[head*256:head*256+128] = snapshots[tile, 'seed'][head*128:(head+1)*128]
        v = [row[:] for row in values[start:start+t]]
        patches = []
        if r['kind'] == 'nv':
            scale = [0x3f800000]*2
            probability[0] = probability[64] = 0
            v[0][0] = 0x7c00
            patches = ['scale[0:2]=1', 'probability[head][0]=+0', 'V[0][0]=+Inf']
        elif r['kind'] == 'tiny':
            scale = [0x3f800000, 0x7f800001]
            probability[0] = 0x3f000000
            probability[64:] = [0x7f800001]*64
            seed[0] = 0
            seed[256:384] = [0x7c01]*128
            v[0][0] = 1
            patches = ['scale0=1', 'probability0[0]=0.5', 'seed0[0]=0',
                       'V[0][0]=min-subnormal', 'inactive head=sNaN']
        p = [probability[64*head:64*head+t] for head in range(h)]
        s = [seed[256*head:256*head+d] for head in range(h)]
        active_v = [row[:d] for row in v]
        if r['kind'] == 'mixed':
            src = snapshots[tile, 'source'][:]
            expected_seed = [[0]*128 for _ in range(2)]
            expected_v = [[0]*128 for _ in range(t)]
            selected = [x for x in corpus['cases'] if x['name'].startswith(f'qwen3_tile{tile}_lane')]
            require(len(selected) == 4, 'Missing four prepared lanes')
            for lane, raw in enumerate(selected):
                require(raw['name'] == f'qwen3_tile{tile}_lane{lane}', 'Prepared lane ordering drift')
                for w in range(8):
                    for part, idx in enumerate(native_indices(lane, w)):
                        for head in range(2):
                            expected_seed[head][idx] = raw['seed'][head][4*w+part]
                        for token in range(t):
                            expected_v[token][idx] = raw['values'][token][4*w+part]
            # The raw helper snapshot has the same actual prepared input contract.
            require(expected_seed == [src[:128], src[128:256]] and expected_v == v,
                    'Independent prepared snapshot/capture disagree')
            coeff = [[src[256+2*i+head] for i in range(t)] for head in range(h)]
            require(coeff == selected[0]['coefficient'], 'Prepared coefficients disagree')
            out, fflags, lane_flags = prepared_fma(ref, [row[:d] for row in expected_seed],
                                                  coeff, active_v, r['rm'])
            prepared_flags = 0
            source = src
        else:
            whole = ref.pv(p, scale[:h], s, active_v, r['rm'])
            out, fflags, lane_flags = prepared_fma(ref, whole['prepared_seed'], whole['coefficient'],
                                                  active_v, r['rm'])
            require(out == whole['output'] and whole['fflags'] == whole['prepared_fflags'] | fflags,
                    'Independent prep/FMA split mismatch')
            prepared_flags = whole['prepared_fflags']
            source = [0]*384
            for head in range(h):
                source[head*128:head*128+d] = whole['prepared_seed'][head]
                for i in range(t):
                    source[256+2*i+head] = whole['coefficient'][head][i]
        r.update(probability=probability, scale=scale, seed=seed, value=sum(v, []),
                 query=query[:256], key=sum(key[start:start+t], []), source=source,
                 expected=sum(out, []), prepared_flags=prepared_flags, pv_flags=fflags,
                 lane_flags=lane_flags, expected_fcsr=(r['rm'] << 5) | r['initial_flags'] | prepared_flags | fflags,
                 provenance=dict(tile=tile, token_start=start, original_dimension=128,
                     derived_from_D128=d != 128, dimension_slice=[0, d], head_slice=[0, h],
                     token_slice=[start, start+t], token_stride_bytes=256,
                     mode='already_prepared' if r['kind'] == 'mixed' else 'raw_FP32_prepare',
                     synthetic_ieee_patches=patches))
        if r['rejection']:
            gd, gh, gt = (r[k] for k in ('context_dimension', 'context_heads', 'context_tokens'))
            good = ref.pv([probability[64*head:64*head+gt] for head in range(gh)], scale[:gh],
                          [seed[256*head:256*head+gd] for head in range(gh)],
                          [row[:gd] for row in v[:gt]], r['rm'])
            good_out, good_flags, good_lanes = prepared_fma(ref, good['prepared_seed'], good['coefficient'],
                                                           [row[:gd] for row in v[:gt]], r['rm'])
            require(good_out == good['output'] and good['fflags'] == good['prepared_fflags'] | good_flags,
                    'Recovery oracle prep/FMA split mismatch')
            r['recovery'] = dict(dimension=gd, heads=gh, tokens=gt, control=control(gd, gh, gt),
                prepared_flags=good['prepared_fflags'], pv_flags=good_flags, lane_flags=good_lanes,
                expected=sum(good_out, []), expected_fcsr=(r['rm'] << 5) | r['initial_flags'] | good['fflags'])
        result.append(r)
    require(result[6]['pv_flags'] & 16 and result[7]['pv_flags'] & 3 == 3 and
            not result[7]['pv_flags'] & 16, 'Directed flag coverage did not materialize')
    return result


def header(rows, digest):
    fields = ('id dimension heads tokens rm initial_flags control bad_control prepared_flags pv_flags vtype_mode bad_mode '
              'context_dimension context_heads context_tokens')
    lines = ['#include <stdint.h>', '#include "akv/akv_abi.h"',
             '#define BOUNDARY_CASES 21', '#define BOUNDARY_DATA_SHA256 "'+digest+'"',
             'typedef struct {', 'uint64_t '+', '.join(fields.split())+';',
             'uint64_t kind, rejection;',
             'const uint32_t *probability, *scale;',
             'const uint16_t *seed, *query, *key, *value, *source, *expected;',
             'uint64_t recovery_prepared_flags, recovery_pv_flags;',
             'const uint16_t *recovery_expected;',
             '} boundary_case_t;']
    kinds = {r['kind']: i for i, r in enumerate(rows)}
    for kind, i in kinds.items():
        lines.append('#define KIND_'+kind.upper()+' '+str(i))
    arrays, pointers = {}, {}
    for r in rows:
        for name in ('probability', 'scale', 'seed', 'query', 'key', 'value', 'source', 'expected', 'recovery_expected'):
            width = 32 if name in ('probability', 'scale') else 16
            data = r.get('recovery', r)['expected'] if name == 'recovery_expected' else r[name]
            key = (width, tuple(data))
            if key not in arrays:
                arrays[key] = f'c{r["id"]}_{name}'
                lines.append(f'static const uint{width}_t {arrays[key]}[] __attribute__((aligned(64))) = {{'+
                             ','.join(hex(x) for x in data)+'};')
            pointers[r['id'], name] = arrays[key]
    for name, width, data in (('boundary_dest_pattern', 32, dest_pattern()),
                               ('boundary_guard_pattern', 64, guard_pattern())):
        lines.append(f'const uint{width}_t {name}[] __attribute__((aligned(64))) = {{'+
                     ','.join(hex(x)+('ULL' if width == 64 else 'u') for x in data)+'};')
    lines.append('static const boundary_case_t boundary_cases[21] = {')
    for r in rows:
        scalar = [str(r[k]) for k in fields.split()]+[str(kinds[r['kind']]),
                    str({None: 0, 'frontend': 1, 'backend': 2}[r['rejection']])]
        names = [pointers[r['id'], k] for k in ('probability', 'scale', 'seed', 'query', 'key', 'value', 'source', 'expected')]
        recovery = r.get('recovery', r)
        extra = [str(recovery['prepared_flags']), str(recovery['pv_flags']), pointers[r['id'], 'recovery_expected']]
        lines.append('{'+','.join(scalar+names+extra)+'},')
    return '\n'.join(lines+['};', ''])


def generate(output):
    output = Path(output)
    output.mkdir(exist_ok=False)
    snapshots, corpus, pins = provenance()
    module = load(HERE.parent/'ordered_reference.py', 'boundary_ordered_reference')
    ref = module.OrderedReference()
    identity = ref.identity()
    def halves(name):
        raw = (DATA/(name+'.bin')).read_bytes()
        return list(struct.unpack('<'+'H'*(len(raw)//2), raw))
    raw_v, raw_k = halves('decode_value'), halves('decode_key')
    rows = construct(snapshots, corpus, ref, [raw_v[i:i+128] for i in range(0, len(raw_v), 128)],
                     halves('decode_query_f16'), [raw_k[i:i+128] for i in range(0, len(raw_k), 128)])
    require(identity == ref.identity(), 'Oracle drift during generation')
    pins.update(identity)
    pins[str(Path(__file__).resolve())] = sha(__file__)
    pins[str(HERE/'cases.py')] = sha(HERE/'cases.py')
    verify(pins)
    payload = dict(schema=SCHEMA, cases=rows, source_pins=pins, oracle_pins=identity,
                   destination_pattern=dest_pattern(), guard_pattern=guard_pattern(),
                   scope='21 PV scenarios + 1 compat postlude; 21 successful + 12 rejected PV attempts; NOT_RUN')
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    payload['data_identity_sha256'] = digest
    (output/'vectors.json').write_text(json.dumps(payload, indent=2)+'\n')
    (output/'boundary_data.h').write_text(header(rows, digest))
    return payload


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    print(json.dumps(dict(cases=len(generate(args.output)['cases']), execution='NOT_RUN')))

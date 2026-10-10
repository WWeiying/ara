"""Source-first FP16 sublane residual audit. No simulator or exclusion actions."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
RANK = OUT / 'toggle796-net-static-agent-20261008-01.json'
RANK_SHA = 'b82696123a3510191bbc106d3a6b8fbb4d2dadeedf6b5d8e5e8f8b1d39274346'
VENDOR = 'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/'


def need(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def focused(scope):
    return ('gen_thmulti_c910_divsqrt' in scope and
            any('.gen_num_lanes[%d].active_lane.' % n in scope for n in (2, 3)))


def assert_wrapper(definition):
    need('FpFmtConfig=8,' in definition and 'WIDTH=16,' in definition,
         'Exact compiled FP16-only wrapper required')


def collect():
    pins = {}
    def read(path, expected=None):
        sha = digest(path)
        need(expected is None or sha == expected, 'Input drift: ' + str(path))
        pins[str(path)] = sha
        return json.loads(Path(path).read_text())
    rank = read(RANK, RANK_SHA)
    for path, sha in rank['pins'].items():
        need(digest(path) == sha, 'Ranking authority drift: ' + path)
    pins.update(rank['pins'])
    book_path = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    book = read(book_path)
    files = ['hardware/deps/fpnew/src/' + name for name in
             ('fpnew_pkg.sv', 'fpnew_opgroup_multifmt_slice.sv', 'fpnew_divsqrt_th_64_multi.sv')]
    files += [VENDOR + name for name in ('ct_vfdsu_prepare.v', 'ct_vfdsu_ctrl.v',
              'ct_vfdsu_srt.v', 'ct_vfdsu_srt_radix16_with_sqrt.v',
              'ct_vfdsu_srt_radix16_bound_table.v')]
    sources = []
    for relative in files:
        path = ROOT / relative
        need(digest(path) == book[str(path)], 'Not frozen source: ' + relative)
        pins[str(path)] = book[str(path)]
        sources.append(dict(path=str(path), sha256=book[str(path)]))
    objects = [o for o in rank['objects'] if focused(o['scope'])]
    wrappers = {o['scope']: o['definition'] for o in objects
                if o['definition'].startswith('fpnew_divsqrt_th_64_multi ')}
    need(len(wrappers) == 8, 'Eight exact active wrappers')
    for definition in wrappers.values():
        assert_wrapper(definition)
    families = {}
    for suffix in ('x_ct_vfdsu_srt', 'x_ct_vfdsu_srt_radix16_with_sqrt',
                   'x_ct_vfdsu_srt_radix16_bound_table'):
        scopes = [r for r in rank['scopes'] if focused(r['scope']) and r['scope'].endswith('.' + suffix)]
        need(len(scopes) == 8, 'Eight distinct scopes: ' + suffix)
        families[suffix] = dict(scopes=scopes, net_missing=sum(r['net_binary_missing'] for r in scopes))
    old = read(OUT / 'fp16-c910-additional8-source-evidence742-agent-20261007-01.json')
    q = read(OUT / 'fclass-divsqrt783-qualified-agent-20261008-02/qualification.json')
    ledger = Path(next(p for p in rank['pins'] if p.endswith('/combined-inputs.txt'))).read_text().splitlines()
    # Original command option order is not an identity contract.
    preload = next(x.split('=', 1)[1] for x in old['original_command'] if x.startswith('+PRELOAD='))
    old_vdb = str(Path(preload).parent / 'work/code.vdb')
    matrix_vdb = str(Path(q['run']) / 'code.vdb')
    need(old_vdb in ledger and matrix_vdb in ledger, 'Both actual evidence VDBs in formal796')
    for path, sha in q['input_pins'].items():
        if path.endswith('/fclass_divsqrt_matrix783.c'):
            need(digest(path) == sha, 'Matrix source not qualification bound')
            pins[path] = sha
    writers = [w for w in q['native']['writers'] if 10 <= w['cell'] < 25 and w['role'] in ('div', 'sqrt')]
    need(len(writers) == 15 and all(w['compared_bytes'] == 32 for w in writers),
         'Actual 10 DIV + 5 SQRT FP16 full16-element writers')
    need(q['terminal']['returncode'] == 0 and q['signature']['failures'] == 0 and q['native']['skip'] == 0,
         'Passed native architecture evidence')
    return dict(status='C910_FP16_ACTIVE_SUBLANE796_STATIC_RESIDUAL_NOT_GAIN_FORECAST',
        source_pins=sources, pins=pins, wrappers=wrappers, residual_families=families,
        objects=objects, existing_fp16_evidence=dict(old=old['actual_evidence'],
            element_mapping=old['lane_subslot_mapping'], matrix_writers=writers,
            matrix_signature=q['signature'], matrix_vdb=matrix_vdb, old_vdb=old_vdb),
        source_conditions=[
            'Compiled FpFmtConfig=8 WIDTH=16: real FP16-only sublanes, not disabled instances.',
            'get_lane_formats gates width/fp_width > lane; local operands shift by sublane*SEW.',
            'WIDTH16 wrapper boxes srcf[63:16]=1; default format is also FP16.',
            'prepare normal-half fraction is {1,frac[9:0],42 zero bits}; subnormal producer is separate and protected.',
            'initial divisor={ex1_divisor,3 zero bits}; initial remainder includes format alignment.',
            'ctrl half count starts3 vs double13; schedule register reset0/init bit54/shift4 is not operand entropy.',
            'Existing matrix DIV divides tiny patterned numerators by2/4 in all5 rounding modes; SQRT includes2/minsubnormal/negative1/4.',
            'Old independent RTZ DIV uses non-power-of-two normal denominators and all16 shuffled elements.'],
        conclusion='91k gross is not new capacity. Existing EL leaves parent13072, child6406, boundtable3072; these disjoint owners still mix padding/schedule/literal outputs with dynamic bits. No justified >500 incremental reachable directions yet.',
        next_step='Intersect normal-half non-power-of-two DIV and non-perfect-square SQRT host/SRT witnesses with listed exact remaining coordinates before any preflight or EDA request. Do not repeat merely full16-element activation.',
        all_cycle_constant_proof=False, new_EL=False, EDA_started=False,
        measured_increment=None, official_denominator=None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    need(not args.output.exists(), 'Fresh output required')
    result = collect()
    result['pins'][str(Path(__file__).resolve())] = digest(__file__)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(output=str(args.output), sha256=digest(args.output))))

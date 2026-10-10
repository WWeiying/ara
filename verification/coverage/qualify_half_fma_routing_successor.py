"""Offline fixed-port/e16-shuffle audit; never launches or changes the DUT."""
from collections import deque
import argparse
import json
from pathlib import Path
import re
from types import FunctionType
import qualify_half_fma_finite as original
import run_half_fma_finite as run

life, require = original.life, original.require
SOURCE_HASHES = {
    'hardware/include/ara_pkg.sv': '49a4fd9879cad35c2c77241bd5114fb8d02ab520e833335fd916122854830971',
    'hardware/src/lane/vmfpu.sv': '1f8288ed2a50f8fa59a7ea3d6f3a7e3138f5219bbb1af52e864d9dfe359d8307',
}


def coordinates():
    for relative, seal in SOURCE_HASHES.items():
        require(life.digest(life.ROOT/relative) == seal, 'Frozen routing source drift')
    text = (life.ROOT/'hardware/include/ara_pkg.sv').read_text()
    block = text.split('4: unique case (ew)', 1)[1].split('rvv_pkg::EW16: begin', 1)[1].split('return idx', 1)[0]
    table = {int(a): int(b) for a, b in re.findall(r'idx\[(\d+)\]\s*=\s*(\d+)', block)}
    require(len(table) == 32 and set(table.values()) == set(range(32)), 'Exact shuffle byte bijection')
    inverse = {physical: logical for logical, physical in table.items()}
    result = {}
    for lane in range(4):
        for simd in range(4):
            physical = 8*lane+2*simd
            require(inverse[physical+1] == inverse[physical]+1 and inverse[physical] % 2 == 0,
                    'Halfword shuffle adjacency')
            result[lane, simd] = inverse[physical]//2
    require(set(result.values()) == set(range(16)), 'All16 coordinate bijection')
    return result


def wave(path, scopes):
    offsets = coordinates()
    require(scopes == run.scopes(), 'Exact sixteen scopes')
    reader = FunctionType(original.frozen_parser.vcd.__code__,
        dict(original.frozen_parser.vcd.__globals__, ROOT='ara_tb', WIDTHS={}))
    iterator = iter(reader(path)); _, decl = next(iterator)
    widths = {'ara_tb.clk': 1, 'ara_tb.rst_n': 1}
    simple = dict(in_valid_i=1, in_ready_o=1, out_valid_o=1, out_ready_i=1,
        mask_i=1, mask_o=1, op_i=5, rnd_mode_i=3, result_o=16)
    operands, statuses = {}, {}
    for scope in scopes:
        widths.update({scope+'.'+name: width for name, width in simple.items()})
        operands[scope] = ([(scope+'.operands_i', 48)] if scope+'.operands_i' in decl else
                           [(scope+'.operands_i[%d]' % i, 16) for i in range(3)])
        statuses[scope] = ([(scope+'.status_o', 5)] if scope+'.status_o' in decl else
                           [(scope+'.status_o.'+name, 1) for name in ('NX','UF','OF','DZ','NV')])
        widths.update(operands[scope]); widths.update(statuses[scope])
    require(all(decl.get(name, {}).get('width') == width for name, width in widths.items()),
            'Exact typed16-core waveform fields missing/drifted')
    codes = {name: decl[name]['code'] for name in widths}
    def value(state, name):
        bits = state.get(codes[name], 'x')
        require(set(bits) <= set('01'), 'Unknown accepted field '+name)
        return int(bits, 2)
    pending = {s: deque() for s in scopes}
    counts = {s: dict(accepted=0, completed=0) for s in scopes}
    phases = [(p, beat) for p in range(4) for beat in range(2 if p == 3 else 4)]
    for time, before, after in iterator:
        if before.get(codes['ara_tb.clk']) != '0' or after.get(codes['ara_tb.clk']) != '1': continue
        if before.get(codes['ara_tb.rst_n']) != '1': continue
        for scope in scopes:
            def val(name): return value(before, scope+'.'+name)
            if val('in_valid_i') and val('in_ready_o'):
                ordinal = counts[scope]['accepted']
                require(ordinal < len(phases), 'Extra FMA acceptance')
                phase, beat = phases[ordinal]
                lane, simd = map(int, re.search(r'gen_lanes\[(\d+)\].*gen_num_lanes\[(\d+)\]', scope).groups())
                index = 16*beat+offsets[lane, simd]
                packed = (sum(value(before, n) << (16*i) for i, (n, _) in enumerate(operands[scope]))
                          if len(operands[scope]) == 3 else value(before, operands[scope][0][0]))
                actual = tuple(packed >> (16*i) & 65535 for i in range(3))
                a, b, c = original.gold.PATTERNS[index % 8]
                expected = (b, a, c)
                detail = dict(time=time, scope=scope, ordinal=ordinal, phase=phase, beat=beat,
                    index=index, actual=actual, expected=expected, op=val('op_i'), rm=val('rnd_mode_i'),
                    mask=val('mask_i'))
                require(actual == expected and val('op_i') == 0 and val('rnd_mode_i') == int(phase == 1),
                        'Accepted operands/op/round mismatch '+json.dumps(detail))
                mask = int(index < (31 if phase == 3 else 64) and (phase != 2 or index % 2 == 1))
                require(val('mask_i') == mask, 'Accepted mask/tail mismatch '+json.dumps(detail))
                result, flags = original.gold.fused(a, b, c, int(phase == 1))
                pending[scope].append((result, flags, mask)); counts[scope]['accepted'] += 1
            if val('out_valid_o') and val('out_ready_i'):
                require(pending[scope], 'Orphan FMA completion')
                expected = pending[scope].popleft()
                status = (sum(value(before, n) << i for i, (n, _) in enumerate(statuses[scope]))
                          if len(statuses[scope]) == 5 else value(before, statuses[scope][0][0]))
                actual = (val('result_o'), status, val('mask_o'))
                require(actual == expected, 'Completed result/flags/mask mismatch '+json.dumps(
                    dict(time=time, scope=scope, actual=actual, expected=expected)))
                counts[scope]['completed'] += 1
    require(all(not pending[s] and counts[s] == dict(accepted=14, completed=14) for s in scopes),
            'Incomplete/missing16-core exact four-phase observations')
    return dict(status='ACTUAL16_HALF_FMA_FIXED_ROUTING_PASS', accepted=224, completed=224,
        per_scope=counts, logical_offsets={'%d,%d' % k: v for k, v in offsets.items()},
        fixed_operand_order=['B','A','C'], no_internal_force=True)


def audit(output):
    require(not output.exists(), 'Fresh evidence only')
    record = json.loads((run.OUT/'manifest.json').read_bytes())
    life.check(record['pins'])
    pins = life.merge_pins(record['pins'], {str(life.ROOT/p): h for p, h in SOURCE_HASHES.items()})
    for p in (Path(__file__), Path(__file__).with_name('test_half_fma_routing_successor.py'),
              run.OUT/'half-fma.vcd', run.OUT/'qualification-hold.json', run.OUT/'manifest.json'):
        pins[str(p.resolve())] = life.digest(p)
    try:
        result = wave(run.OUT/'half-fma.vcd', record['scopes'])
    except ValueError as error:
        result = dict(status='HOLD_NOT_QUALIFIED', reason=str(error))
    life.check(pins)
    output.mkdir()
    result.update(pins=pins, coverage_admitted=False, architectural_qualification_complete=False,
                  original_hold_preserved=True, vcs_rerun=False)
    life.save(output/'routing-audit.json', result)
    print(json.dumps(dict(status=result['status'], output=str(output), seal=life.digest(output/'routing-audit.json'))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    audit(parser.parse_args().output)

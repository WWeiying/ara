"""Strict offline FMA audit with frozen queue padding; reads the existing VCD."""
from collections import deque
import argparse
import json
from pathlib import Path
import re
from types import FunctionType, SimpleNamespace
import qualify_half_fma_routing_successor as routing

old, life, require = routing.original, routing.life, routing.require
PAD_HASHES = {
    'hardware/src/lane/operand_queue.sv': 'eafc82bfe3bd7413aa549015a2145e977d1ce01a9bd52c369993e5dac10e453d',
    'hardware/src/lane/operand_queues_stage.sv': '6b0150d900030585c4689e054cc7a47256e0663e9a9eb36780380549518c4676',
}
BUILD = life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'


def contract():
    offsets = routing.coordinates()
    build = json.loads(BUILD.read_bytes())
    for relative, sha in dict(routing.SOURCE_HASHES, **PAD_HASHES).items():
        path = life.ROOT/relative
        require(build[str(path)] == sha == life.digest(path), 'Frozen build padding/routing mismatch')
    return offsets


def expected(phase, index):
    require(0 <= phase < 4 and 0 <= index < 64, 'Finite phase/index')
    a, b, c = old.gold.PATTERNS[index % 8]
    # Only the VL31 tail element is padded: MFPU B/C support neutral values,
    # MFPU A does not. Predicate-inactive in-range operands remain unchanged.
    tail = phase == 3 and index >= 31
    ports = (0 if tail else b, a, 0 if tail else c)
    result, flags = old.gold.fused(ports[1], ports[0], ports[2], int(phase == 1))
    mask = int(not tail and (phase != 2 or index % 2 == 1))
    return ports, (result, flags, mask)


def accepted(phase, index, ports, op, rm, mask):
    wanted, completion = expected(phase, index)
    require((ports, op, rm, mask) == (wanted, 0, int(phase == 1), completion[2]),
            'Exact accepted operands/op/round/mask mismatch')
    return completion


def wave(path, scopes):
    offsets = contract()
    require(scopes == routing.run.scopes(), 'Exact sixteen scopes')
    reader = FunctionType(old.frozen_parser.vcd.__code__,
        dict(old.frozen_parser.vcd.__globals__, ROOT='ara_tb', WIDTHS={}))
    iterator = iter(reader(path)); _, decl = next(iterator)
    widths = {'ara_tb.clk': 1, 'ara_tb.rst_n': 1}
    operands, statuses = {}, {}
    simple = dict(in_valid_i=1, in_ready_o=1, out_valid_o=1, out_ready_i=1,
                  mask_i=1, mask_o=1, op_i=5, rnd_mode_i=3, result_o=16)
    for scope in scopes:
        widths.update({scope+'.'+n: w for n, w in simple.items()})
        operands[scope] = ([(scope+'.operands_i',48)] if scope+'.operands_i' in decl else
                           [(scope+'.operands_i[%d]' % i,16) for i in range(3)])
        statuses[scope] = ([(scope+'.status_o',5)] if scope+'.status_o' in decl else
                           [(scope+'.status_o.'+n,1) for n in ('NX','UF','OF','DZ','NV')])
        widths.update(operands[scope]); widths.update(statuses[scope])
    require(all(decl.get(n, {}).get('width') == w for n, w in widths.items()), 'Typed waveform drift')
    codes = {n: decl[n]['code'] for n in widths}
    def value(state, name):
        bits = state.get(codes[name], 'x')
        require(bool(bits) and set(bits) <= set('01'), 'Unknown observed field '+name)
        return int(bits, 2)
    pending = {s: deque() for s in scopes}
    counts = {s: dict(accepted=0, completed=0) for s in scopes}
    phases = [(p,b) for p in range(4) for b in range(2 if p == 3 else 4)]
    tail_observations = []
    for time, before, after in iterator:
        if before.get(codes['ara_tb.clk']) != '0' or after.get(codes['ara_tb.clk']) != '1': continue
        if before.get(codes['ara_tb.rst_n']) != '1': continue
        for scope in scopes:
            def val(n): return value(before,scope+'.'+n)
            if val('in_valid_i') and val('in_ready_o'):
                ordinal = counts[scope]['accepted']
                require(ordinal < len(phases), 'Extra acceptance')
                phase, beat = phases[ordinal]
                lane, simd = map(int,re.search(r'gen_lanes\[(\d+)\].*gen_num_lanes\[(\d+)\]',scope).groups())
                index = 16*beat+offsets[lane,simd]
                packed = (sum(value(before,n) << (16*i) for i,(n,_) in enumerate(operands[scope]))
                          if len(operands[scope]) == 3 else value(before,operands[scope][0][0]))
                ports = tuple(packed >> (16*i) & 65535 for i in range(3))
                completion = accepted(phase,index,ports,val('op_i'),val('rnd_mode_i'),val('mask_i'))
                pending[scope].append(completion); counts[scope]['accepted'] += 1
                if phase == 3 and index >= 31:
                    tail_observations.append(dict(scope=scope,time=time,index=index,ports=ports,completion=completion))
            if val('out_valid_o') and val('out_ready_i'):
                require(pending[scope], 'Orphan completion')
                wanted = pending[scope].popleft()
                status = (sum(value(before,n) << i for i,(n,_) in enumerate(statuses[scope]))
                          if len(statuses[scope]) == 5 else value(before,statuses[scope][0][0]))
                require((val('result_o'),status,val('mask_o')) == wanted, 'Exact result/flags/mask mismatch')
                counts[scope]['completed'] += 1
    require(all(not pending[s] and counts[s] == dict(accepted=14,completed=14) for s in scopes),
            'Incomplete sixteen-core observations')
    require(len(tail_observations) == 1 and tail_observations[0]['index'] == 31, 'Exact single padded tail')
    return dict(status='ACTUAL16_HALF_FMA_FIXED_ROUTING_PADDING_PASS', cores=16, accepted=224,
                completed=224, per_scope=counts, padded_tail=tail_observations,
                raw_results_and_flags_checked_even_when_mask_zero=True, no_internal_force=True)


def collect(output):
    require(not output.exists(), 'Fresh independent qualification')
    contract()
    record = json.loads((routing.run.OUT/'manifest.json').read_bytes())
    life.check(record['pins'])
    pins = dict(record['pins'])
    dependencies = [BUILD, Path(__file__), Path(__file__).with_name('test_half_fma_tail_source.py'),
        Path(routing.__file__), Path(old.__file__), routing.run.OUT/'manifest.json',
        routing.run.OUT/'qualification-hold.json', routing.run.OUT/'half-fma.vcd']
    dependencies += [life.ROOT/p for p in dict(routing.SOURCE_HASHES, **PAD_HASHES)]
    pins = life.merge_pins(pins, {str(p.resolve()): life.digest(p) for p in dependencies})
    record = dict(record,pins=pins)
    output.mkdir()
    allowed = {'scalar-comparison.json','vector-comparison.json','fma-wave-audit.json','qualification.json'}
    def save(path, data):
        require(path.parent == routing.run.OUT and path.name in allowed, 'Only fresh qualification writes')
        if path.name == 'qualification.json':
            data = dict(data, successor='FROZEN_FIXED_PORT_SHUFFLE_AND_QUEUE_TAIL_PADDING',
                original_hold_preserved=True, existing_run=str(routing.run.OUT), vcs_rerun=False)
            data['pins'] = life.merge_pins(data['pins'],
                {str(p.resolve()): life.digest(p) for p in output.iterdir() if p.is_file()})
        life.save(output/path.name,data)
    adapter = SimpleNamespace(**dict(vars(life), save=save, digest=lambda p: life.digest(
        output/p.name if p.parent == routing.run.OUT and p.name == 'qualification.json' else p)))
    namespace = dict(vars(old),wave=wave,life=adapter)
    try:
        FunctionType(old.collect.__code__,namespace)(routing.run.OUT,record)
    except Exception as error:
        life.save(output/'qualification-hold.json',dict(status='HOLD_NOT_ADMITTED',reason=str(error),pins=pins))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    collect(parser.parse_args().output.resolve())

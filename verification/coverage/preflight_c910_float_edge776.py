"""Software-only FP16/32/64 directed edges via frozen bounded preflight."""
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace
import preflight_vfirst_long_mask as base
import review_c910_top776 as review

life, require, build, old = base.life, base.require, base.build, base.old
ROOT, OUT = life.ROOT, life.OUT
APP = ROOT / 'apps/riscv-tests/isa/rv64uv/c910_float_edge.c'
GUARD = base.GUARD
SYMBOLS = ('tohost', 'num_failed', 'g75_result', 'trap_fail', 'edge_checks',
    'edge_a', 'edge_b', 'edge_dst', 'edge_ledger') + tuple('edge_' + op + str(width)
    for width in (16, 32, 64) for op in ('load_a', 'load_b', 'div', 'store'))


def gold(width, kind, rm):
    require(width in (16, 32, 64) and kind in range(8) and rm in (0, 1), 'Closed matrix')
    frac, bias = {16: (10, 15), 32: (23, 127), 64: (52, 1023)}[width]
    one = bias << frac; two = (bias + 1) << frac
    max_finite = (2 * bias << frac) | ((1 << frac) - 1)
    a = max_finite if kind in (2, 3) else 1 << frac if kind == 4 else 1 if kind in (5, 6) else one | (1 << (frac - 1)) if kind == 7 else one
    b = 1 << frac if kind in (2, 3) else two
    result = (max_finite if rm else (2 * bias + 1) << frac) if kind in (2, 3) else 1 << (frac - 1) if kind == 4 else 0 if kind in (5, 6) else ((bias - 1) << frac) | (1 << (frac - 1)) if kind == 7 else (bias - 1) << frac
    if kind in (1, 3, 6): a |= 1 << (width - 1); result |= 1 << (width - 1)
    flags = 5 if kind in (2, 3) else 3 if kind in (5, 6) else 0
    return a, b, result, flags


def word(value, width):
    require(0 <= value < 1 << width, 'Exact element bits')
    return int.from_bytes(value.to_bytes(width // 8, 'little') * (64 // width), 'little')


def vector_store_bytes(value, width):
    require(width in (16, 32, 64) and 0 <= value < 1 << width, 'Exact vector store element')
    return value.to_bytes(width // 8, 'little')


def source_pins():
    config = json.loads(review.CONFIG.read_bytes())
    require(life.digest(review.CONFIG) == review.CONFIG_SHA, 'Frozen source authority')
    paths = [Path(p) for p in config['pins'] if Path(p).name in
             ('fpnew_divsqrt_th_64_multi.sv', 'ct_vfdsu_pack.v', 'ct_vfdsu_prepare.v', 'ct_vfdsu_round.v')]
    require(len(paths) == 4, 'Exact C910 source chain')
    pins = {str(p): config['pins'][str(p)] for p in paths}
    for p in [review.CONFIG, APP, Path(__file__), Path(__file__).with_name('test_preflight_c910_float_edge776.py'),
              Path(base.__file__), Path(review.__file__)]: pins[str(p.resolve())] = life.digest(p)
    life.check(pins); return pins


def linked(dis):
    import re
    mnemonics = re.findall(r'^\s*[0-9a-f]+:\s+(?:[0-9a-f]{8}|[0-9a-f]{4}|(?:[0-9a-f]{2}\s+){1,3}[0-9a-f]{2})\s+([\w.]+)', dis, re.M)
    actual = [m for m in mnemonics if m.startswith('v')]
    expected = ['vsetvli', 'vfdiv.vv'] * 3 + [f'vle{w}.v' for w in (16, 32, 64) for _ in range(2)] + [f'vse{w}.v' for w in (16, 32, 64)]
    require(sorted(actual) == sorted(expected), 'Only fifteen explicit static RVV opcodes: ' + repr(actual))
    return actual


def validate(path, symbols):
    commits = build.parse_spike_commits(path)
    require('exception ' not in path.read_text() and not any(c.pc == symbols['trap_fail'] for c in commits), 'No unexpected trap')
    memory, stores, operations, writers = {}, {}, [], []
    mapped = {symbols['edge_' + op + str(w)]: (op, w) for w in (16, 32, 64) for op in ('load_a', 'load_b', 'div', 'store')}
    for c in commits:
        if c.pc in mapped:
            op, width = mapped[c.pc]
            if op == 'div': operations.append((c, width))
            if c.vector_writes: writers.append((c, op, width))
        elif c.vector_writes: require(False, 'Implicit/unbound vector writer')
        for address, value in c.memory_accesses:
            if value is None: continue
            decoded = old.rvc.decode(c.instruction)
            if decoded: require(decoded['kind'] == 'write', 'Memory writer role'); size = decoded['size']
            elif c.instruction & 127 == 0x23: size = 1 << (c.instruction >> 12 & 7); require(size <= 8, 'Scalar store width')
            else:
                require(c.instruction & 127 == 0x27 and c.pc in mapped and mapped[c.pc][0] == 'store', 'Exact vector store')
                size = len(vector_store_bytes(value, mapped[c.pc][1]))
            for i in range(size): memory[address + i] = value >> (8 * i) & 255
            if c.pc in mapped and mapped[c.pc][0] == 'store':
                for i, byte in enumerate(vector_store_bytes(value, mapped[c.pc][1])):
                    require(address + i not in stores, 'No duplicate vector-store footprint')
                    stores[address + i] = byte
    require(len(operations) == 48 and len(writers) == 144, 'Exact operations and writers')
    def observed(address, size):
        require(all(address + i in memory for i in range(size)), 'Missing memory evidence')
        return int.from_bytes(bytes(memory[address + i] for i in range(size)), 'little')
    for p in range(48):
        width = 16 << (p // 16); kind = p % 8; rm = p // 8 % 2
        a, b, result, flags = gold(width, kind, rm)
        for name, expected in [('edge_a', a), ('edge_b', b), ('edge_dst', result)]:
            for w in range(8): require(observed(symbols[name] + p * 64 + w * 8, 8) == (GUARD if w < 2 or w >= 6 else word(expected, width)), 'All source/destination/guard words')
        ledger = [16 >> (p // 16), 16 >> (p // 16), 11 + (p // 16) * 8, 0, 0, (rm << 5) | flags]
        require([observed(symbols['edge_ledger'] + p * 48 + i * 8, 8) for i in range(6)] == ledger, 'Exact results and fcsr flags/configuration')
        c, actual_width = operations[p]
        active = int.from_bytes(result.to_bytes(width // 8, 'little') * (256 // width), 'little')
        require(actual_width == width and set(c.vector_writes) == {24} and c.vector_writes[24] & ((1 << 256) - 1) == active, 'Every defined result bit')
        for index, op, value, reg in [(p * 3, 'load_a', a, 8), (p * 3 + 1, 'load_b', b, 16), (p * 3 + 2, 'div', result, 24)]:
            wr, role, actual_width = writers[index]
            require(role == op and actual_width == width and set(wr.vector_writes) == {reg}, 'Exact writer order/identity')
            expected = int.from_bytes(value.to_bytes(width // 8, 'little') * (256 // width), 'little')
            require(wr.vector_writes[reg] & ((1 << 256) - 1) == expected, 'Defined load/result bytes')
        dst = symbols['edge_dst'] + p * 64 + 16
        image = result.to_bytes(width // 8, 'little') * (256 // width)
        require(all(stores.get(dst + i) == v for i, v in enumerate(image)), 'Complete vector-store footprint')
    require(len(stores) == 1536, 'No extra store bytes')
    require([observed(symbols['g75_result'], 4), observed(symbols['g75_result'] + 4, 4), observed(symbols['num_failed'], 4), observed(symbols['edge_checks'], 4), observed(symbols['tohost'], 8)] == [1440, 0, 0, 1440, 1], '1440-check successful terminal')
    return dict(checks=1440, cases=48, CSR_values=288, defined_vector_writer_bytes=4608, result_store_bytes=1536, retirements=len(commits), no_skip=True)


def prepare(out):
    def save(path, value):
        if path.name == 'preflight.json':
            value = dict(value, status='C910_FLOAT_EDGE_HOST_SPIKE_PASS_NOT_DUT', target='Source-bound overflow/underflow/recovery; no target-hit promise',
                target_serialized_slots=None, baseline_note='776 static source review; future DUT gain must use latest formal ledger',
                VCS_budget_plan_seconds=600, initial_X_excluded=False)
        return life.save(path, value)
    proxy = SimpleNamespace(**vars(life)); proxy.save = save
    env = dict(base.prepare.__globals__, APP=APP, SYMBOLS=SYMBOLS, source_pins=source_pins,
               validate=validate, linked=linked, life=proxy)
    return FunctionType(base.prepare.__code__, env)(out, None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve()
    try: prepare(out)
    except Exception as error:
        if out.exists(): life.save(out / 'failure.json', dict(error=str(error), VCS_started=False, no_retry=True))
        raise

"""Independent initialized successor; frozen48-case matrix is included unchanged."""
import argparse
from pathlib import Path
from types import FunctionType, SimpleNamespace
import preflight_c910_float_edge776 as old

life, require, build = old.life, old.require, old.build
APP = life.ROOT / 'apps/riscv-tests/isa/rv64uv/c910_float_edge_initialized.c'
ORIGINAL_APP_SHA = 'eae8dc0990b77869cdc45aaf490409e3d2cb76f9f4df699c9aff9317d3b6f113'
SYMBOLS = old.SYMBOLS + ('edge_initial_config', 'edge_initial_v8', 'edge_initial_v16',
                         'edge_initial_v24', 'edge_initial_ledger')
gold, word, GUARD = old.gold, old.word, old.GUARD


def initialization(commits, symbols):
    configs = [c for c in commits if c.pc == symbols['edge_initial_config']]
    require(len(configs) == 1 and list(configs[0].gpr_writes.values()) == [1024], 'Initial VL1024')
    positions = []
    for base in (8, 16, 24):
        matches = [(i, c) for i, c in enumerate(commits) if c.pc == symbols['edge_initial_v' + str(base)]]
        require(len(matches) == 1, 'Exactly one initialization per LMUL8 group')
        i, c = matches[0]; positions.append(i)
        require(c.vector_writes == {reg: 0 for reg in range(base, base + 8)}
            and c.vector_vl == 1024 and c.vector_vstart == 0, 'All1024 group bytes zero at VL1024/vstart0')
    first = next(i for i, c in enumerate(commits) if c.pc == symbols['edge_load_a16'])
    require(positions == sorted(positions) and max(positions) < first, 'All initialization precedes original matrix')
    memory = {}
    for c in commits:
        decoded = old.old.rvc.decode(c.instruction)
        if decoded and decoded['kind'] == 'write': size = decoded['size']
        elif c.instruction & 127 == 0x23: size = 1 << (c.instruction >> 12 & 7)
        else: continue
        for address, value in c.memory_accesses:
            if value is not None:
                for b in range(size): memory[address + b] = value >> (8 * b) & 255
    ledger = [int.from_bytes(bytes(memory[symbols['edge_initial_ledger'] + 8*j + b] for b in range(8)), 'little') for j in range(5)]
    require(ledger == [1024, 1024, 3, 0, 0], 'Exact initialization VL/vtype/vstart/vcsr ledger')
    return dict(groups=3, bytes=3072, registers=24, VL=1024, vtype=3, vstart=0, vcsr=0)


def validate(path, symbols):
    commits = build.parse_spike_commits(path); proof = initialization(commits, symbols)
    init_pcs = {symbols['edge_initial_v' + str(base)] for base in (8, 16, 24)}
    filtered = [c for c in commits if c.pc not in init_pcs]
    proxy = SimpleNamespace(**vars(build)); proxy.parse_spike_commits = lambda _: filtered
    result = FunctionType(old.validate.__code__, dict(old.validate.__globals__, build=proxy))(path, symbols)
    result.update(initialization=proof, retirements=len(commits))
    return result


def linked(dis):
    import re
    mnemonics = re.findall(r'^\s*[0-9a-f]+:\s+(?:[0-9a-f]{8}|[0-9a-f]{4}|(?:[0-9a-f]{2}\s+){1,3}[0-9a-f]{2})\s+([\w.]+)', dis, re.M)
    actual = [m for m in mnemonics if m.startswith('v')]
    expected = ['vsetvli', 'vfdiv.vv'] * 3 + [f'vle{w}.v' for w in (16,32,64) for _ in range(2)] + [f'vse{w}.v' for w in (16,32,64)] + ['vsetvli'] + ['vmv.v.i'] * 3
    require(sorted(actual) == sorted(expected), 'Exactly19 explicit static RVV instructions: ' + repr(actual))
    return actual


def source_pins():
    require(life.digest(old.APP) == ORIGINAL_APP_SHA, 'Original48-case source unchanged')
    pins = old.source_pins()
    for path in (APP, Path(__file__), Path(__file__).with_name('test_preflight_c910_float_edge_initialized.py')):
        pins[str(path.resolve())] = life.digest(path)
    return pins


def prepare(out):
    def save(path, value):
        if path.name == 'preflight.json':
            value = dict(value, status='C910_INITIALIZED_FLOAT_EDGE_HOST_SPIKE_PASS_NOT_DUT',
                target='Original48 cases; three full LMUL8 groups initialized, zero unknown required',
                target_serialized_slots=None, coverage_admitted=False, VCS_started=False)
        return life.save(path, value)
    proxy = SimpleNamespace(**vars(life)); proxy.save = save
    namespace = dict(old.base.prepare.__globals__, APP=APP, SYMBOLS=SYMBOLS, source_pins=source_pins,
                     validate=validate, linked=linked, life=proxy)
    return FunctionType(old.base.prepare.__code__, namespace)(out, None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); out = args.output.resolve()
    try: prepare(out)
    except Exception as error:
        if out.exists(): life.save(out / 'failure.json', dict(error=str(error), VCS_started=False, no_retry=True))
        raise

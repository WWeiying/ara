"""Static-rodata expectation tables; exact oracle and fixed image remain unchanged."""
import argparse
from pathlib import Path
import struct

import build_readonly_csr_preflight_v2 as prior

frozen = prior.frozen
life, require = frozen.life, frozen.require
NAME, CHECKS, IMAGE_SHA = frozen.NAME, frozen.CHECKS, frozen.IMAGE_SHA
PRIOR_SHA = '8dae9dde197803a7e7db971897ccaee0ebaa5e86653e61d8ed434a73132fde0d'
APP = frozen.ROOT / 'apps/riscv-tests/isa/rv64uv/vreadonly_csr_trap_recovery_v2.c'
APP_SHA = 'b1e0d050c770d41d57894ac322bbd1e4d6e3a7c97027b753a7399097abbd707b'
FAILED = frozen.OUT / 'readonly-csr-preflight-v2-733-agent-20261006-01'
REPLACEMENTS = (('  const uint64_t cfg[10]', '  static const uint64_t cfg[10]'),
    ('  const char *pcs[12]', '  static const char *const pcs[12]'),
    ('  const unsigned csr[3]', '  static const unsigned csr[3]'))


def expected_app(source):
    for old, new in REPLACEMENTS:
        require(source.count(old) == 1 and new not in source, 'Exact table-storage replacements required')
        source = source.replace(old, new, 1)
    return source


def static():
    require(life.digest(Path(prior.__file__)) == PRIOR_SHA and life.digest(APP) == APP_SHA and
            APP.read_text() == expected_app(frozen.APP.read_text()), 'Only table storage may change')
    receipt = prior.static()
    deps = [APP, Path(prior.__file__).resolve(), Path(__file__).resolve(),
        Path(__file__).with_name('test_readonly_csr_preflight_v3.py'), FAILED / 'failure.json',
        FAILED / 'input.elf', FAILED / 'spike.trace', FAILED / 'compile-command.json']
    receipt['pins'] = life.merge_pins(receipt['pins'], {str(p): life.digest(p) for p in deps})
    receipt['table_storage_successor'] = dict(app_sha256=APP_SHA, predecessor_sha256=PRIOR_SHA,
        failed_output=str(FAILED), modification='three local expectation tables to static rodata only',
        compiler_flags_changed=False, oracle_changed=False, targets_changed=False,
        gain_requires_latest_formal_population_at_least=734)
    life.check(receipt['pins']); return receipt


def vector_population(blob):
    require(blob[:6] == b'\x7fELF\x02\x01', 'ELF64 LE required')
    h = struct.unpack_from('<HHIQQQIHHHHHH', blob, 16)
    require(h[10] == 64 and h[5] + 64 * h[11] <= len(blob), 'ELF section table bounds')
    vectors = []
    for i in range(h[11]):
        sec = struct.unpack_from('<IIQQQQIIQQ', blob, h[5] + i * 64)
        if sec[1] != 1 or not sec[2] & 4: continue
        require(sec[4] + sec[5] <= len(blob), 'ELF executable section bounds')
        code = blob[sec[4]:sec[4] + sec[5]]; off = 0
        while off < len(code):
            require(off + 2 <= len(code), 'Truncated instruction')
            half = int.from_bytes(code[off:off + 2], 'little')
            size = 2 if half & 3 != 3 else 4
            require(size == 2 or half >> 2 & 7 != 7, 'Unsupported long instruction')
            require(off + size <= len(code), 'Truncated opcode')
            word = int.from_bytes(code[off:off + size], 'little')
            if size == 4 and word & 127 in (0x07, 0x27, 0x57): vectors.append(word)
            off += size
    return vectors


def verify_vector_code(blob):
    words = vector_population(blob)
    require(len(words) == 8, 'Unexpected compiler-generated vector/FP instruction')
    configs = [w for w in words if w & 127 == 0x57 and w >> 12 & 7 == 7]
    require(configs == [0x0002f057, 0xc0047057, 0x0002f057] and
        [w for w in words if w & 127 == 0x57 and w >> 12 & 7 != 7] == [0x0281b557],
        'Only explicit e8/m1 configuration and recovery allowed')
    for op in (0x07, 0x27):
        selected = [w for w in words if w & 127 == op]
        require([w >> 7 & 31 for w in selected] == [8, 10] and
                all(w >> 12 & 7 == 0 and w >> 25 & 1 == 1 and w >> 20 & 31 == 0 and
                    w >> 26 == 0 for w in selected), 'Only explicit two e8 loads/stores allowed')


def load_adapter():
    require(life.digest(Path(prior.__file__)) == PRIOR_SHA, 'Frozen bootstrap adapter drift')
    path = Path(frozen.__file__).resolve()
    require(life.digest(path) == prior.FROZEN_SHA, 'Frozen preflight drift')
    source = prior.adapted_source(path.read_text())
    old = "APP = ROOT / ('apps/riscv-tests/isa/rv64uv/' + NAME + '.c')"
    require(source.count(old) == 1, 'Exact app-path replacement required')
    source = source.replace(old, 'APP = Path(' + repr(str(APP)) + ')', 1)
    ns = dict(__file__=str(path), __name__='readonly_csr_rodata_adapter')
    exec(compile(source, str(path), 'exec'), ns); ns['static'] = static
    original = ns['verify_elf']
    def verify_elf(elf, symbols):
        original(elf, symbols); verify_vector_code(elf.read_bytes())
    ns['verify_elf'] = verify_elf
    return ns


def build(out): load_adapter()['build'](out)
def verify(out, seal): return load_adapter()['verify'](out, seal)
def image_inputs(): return frozen.image_inputs()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('build', 'verify')); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal'); a = parser.parse_args()
    require((a.mode == 'verify') == bool(a.seal), 'Verify alone requires seal')
    if a.mode == 'build': build(a.output.absolute())
    else: verify(a.output.absolute(), a.seal); print('VERIFY_PASS exact24/733checks/only8explicitRVV NO_VCS')

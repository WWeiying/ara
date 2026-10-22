"""Frozen preflight successor: export bootstrap trap_fail, no oracle/ISA change."""
import argparse
from pathlib import Path

import build_readonly_csr_preflight as frozen

life, require = frozen.life, frozen.require
NAME, CHECKS, IMAGE_SHA = frozen.NAME, frozen.CHECKS, frozen.IMAGE_SHA
FROZEN_SHA = '5dfb4ca5c68ccfd1674d541c1c2da0ad618f7c523fa7687cdca2955fb590ed22'
APP_SHA = '01c76b7b3ecdefd9a802f48985fcc373e1fed4ae9b7c0f89ce5355445460559c'
START = frozen.ROOT / 'verification/tests/readonly_csr_start.S'
OLD_START = frozen.ROOT / 'verification/tests/gap75_start.S'
FAILED = frozen.OUT / 'readonly-csr-preflight-733-agent-20261006-01'


def adapted_source(source):
    old, new = "'gap75_start.S'", "'readonly_csr_start.S'"
    require(source.count(old) == 2 and new not in source, 'Exact two bootstrap path references required')
    result = source.replace(old, new)
    require(result.replace(new, old) == source, 'Non-bootstrap change rejected')
    return result


def static():
    require(life.digest(Path(frozen.__file__)) == FROZEN_SHA and life.digest(frozen.APP) == APP_SHA,
            'Frozen helper/app drift')
    old = OLD_START.read_text()
    require(old.count('trap_fail:\n') == 1 and START.read_text() ==
            old.replace('trap_fail:\n', '.globl trap_fail\ntrap_fail:\n', 1), 'Bootstrap may only export trap_fail')
    receipt = frozen.static()
    deps = [Path(__file__).resolve(), Path(__file__).with_name('test_readonly_csr_preflight_v2.py'),
        START, OLD_START, Path(frozen.__file__).resolve(), FAILED / 'failure.json',
        FAILED / 'compile-command.json', FAILED / 'compile.log']
    receipt['pins'] = life.merge_pins(receipt['pins'], {str(p): life.digest(p) for p in deps})
    receipt['bootstrap_successor'] = dict(predecessor_sha256=FROZEN_SHA, app_sha256=APP_SHA,
        modification='export trap_fail only', failed_output=str(FAILED), ISA_or_oracle_changed=False)
    life.check(receipt['pins'])
    return receipt


def load_adapter():
    path = Path(frozen.__file__).resolve()
    require(life.digest(path) == FROZEN_SHA, 'Frozen preflight drift')
    ns = dict(__file__=str(path), __name__='readonly_csr_bootstrap_adapter')
    exec(compile(adapted_source(path.read_text()), str(path), 'exec'), ns)
    ns['static'] = static
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
    else: verify(a.output.absolute(), a.seal); print('VERIFY_PASS exact24/733checks NO_VCS')

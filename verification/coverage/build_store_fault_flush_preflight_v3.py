"""Exact frozen software-build adapter: explicit fixed-image Spike RAM only."""
import argparse
from pathlib import Path

import build_store_fault_flush_preflight_v2 as guarded

life, require = guarded.life, guarded.require
V2_SHA = '9667dbf1319b56ed37ff793ac910815032f26b7631de13a462c94bbc3d767afe'
RAM = '-m0x80000000:0x200000'
OLD = "'--pmpregions=0', '-l', '--log-commits'"
NEW = "'--pmpregions=0', '" + RAM + "', '-l', '--log-commits'"
FAILED = life.OUT / 'store-fault-flush-preflight-v2-parent-20261006-01'


def adapted_source(source):
    require(source.count(OLD) == 1 and NEW not in source, 'Exact single Spike insertion required')
    result = source.replace(OLD, NEW, 1)
    require(result.replace(NEW, OLD, 1) == source, 'Non-memory source change rejected')
    return result


def static():
    require(life.digest(Path(guarded.__file__).resolve()) == V2_SHA, 'Frozen v2 drift')
    receipt = guarded.static()
    deps = [Path(__file__).resolve(), Path(__file__).with_name('test_build_store_fault_flush_preflight_v3.py'),
            FAILED / 'failure.json', FAILED / 'spike-command.json', FAILED / 'spike.trace',
            FAILED / 'input.elf']
    receipt['pins'] = life.merge_pins(receipt['pins'], {str(p): life.digest(p) for p in deps})
    receipt['spike_memory_successor'] = dict(option=RAM, base=0x80000000, size=0x200000,
        predecessor_failure=str(FAILED), predecessor_v2_sha256=V2_SHA,
        modification='one explicit Spike RAM option only', strict_oracle_checks=134,
        expected_cause=7, expected_vstart=0, static_provenance_population=731,
        gain_requires_latest_formal_population_at_least=732,
        DUT_run=False, automatic_admission=False)
    life.check(receipt['pins'])
    return receipt


def load_adapter():
    path = Path(guarded.frozen.__file__).resolve()
    require(life.digest(path) == guarded.FROZEN_SHA, 'Frozen software predecessor drift')
    namespace = dict(__file__=str(path), __name__='store_fault_flush_memory_adapter')
    exec(compile(adapted_source(path.read_text()), str(path), 'exec'), namespace)
    namespace['static'] = static
    return namespace


def build(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(),
            'Fresh independent output required')
    load_adapter()['build'](out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output.absolute())


if __name__ == '__main__':
    main()

"""Actual old-baseline audit with a fail-closed post-promotion read guard."""
import argparse
import os
from pathlib import Path
import sys

import baseline as b

PLAN = b.HERE.parent / 'coherent_package/prepared-01/plan.json'
PLAN_SHA = 'cfda0a82d1c909fb2a0ab3b90278ff339060c96ed4ac81e2f6c69118a3257cba'
AFTER = b.HERE.parent / 'historical_inputs/preflight-01/after-tree'
ADDED = ('admission_assertions.svh', 'shared_reader_types.svh', 'vlsu_shared_reader.svh')


class ReadGuard:
    def __init__(self, consumer):
        self.forbidden = {b.ROOT / p for p in b.a.CHANGED}
        self.forbidden.update(Path(p) for p in consumer.history.bindings())
        self.forbidden.update(b.ROOT / 'hardware/include' / p for p in ADDED)
        self.include = b.ROOT / 'hardware/include'
        self.opens = 0

    def __call__(self, event, args):
        if event == 'subprocess.Popen':
            raise ValueError('No external process permitted in offline preflight')
        if event not in ('open', 'os.scandir', 'os.listdir') or not args:
            return
        if not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        path = Path(os.fsdecode(args[0])).resolve()
        b.s.require(path not in self.forbidden, 'Forbidden promoted live input: ' + str(path))
        if event != 'open':
            b.s.require(not path.is_relative_to(self.include), 'Live include inventory scan forbidden')
        else:
            self.opens += 1


def after_tree(consumer):
    b.s.require(b.s.digest(PLAN) == PLAN_SHA, 'Unreviewed after-tree plan')
    plan = b.s.read_json(PLAN)
    pins = {str(AFTER / row['target']): row['after_sha256'] for row in plan['files']}
    b.s.verify_pins(pins)
    for name, before in b.a.CHANGED.items():
        b.s.require(pins[str(AFTER / name)] != before, 'After-tree did not replace ' + name)
    for name, sha in consumer.archive.report['include_files'].items():
        pins[str(AFTER / 'hardware/include' / name)] = sha
    b.s.require(all(str(AFTER / 'hardware/include' / p) in pins for p in ADDED), 'Missing new headers')
    b.s.verify_pins(pins)
    pins[str(PLAN)] = PLAN_SHA
    return pins


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    b.s.require(output.is_relative_to(b.HERE) and output != b.HERE and not output.exists(),
                'Use a fresh output beneath this owned directory')
    consumer = b.Consumer()
    tree_pins = after_tree(consumer)
    guard = ReadGuard(consumer)
    sys.addaudithook(guard)
    report, parsed, records, pins = consumer.checked_baseline()
    b.s.merge_pins(pins, tree_pins)
    b.s.verify_pins(pins)
    output.mkdir()
    b.s.atomic_json(output / 'pins.json', pins)
    b.s.atomic_json(output / 'result.json', dict(
        state='HISTORICAL_ORDINARY_BASELINE_OFFLINE_CHECK_PASS',
        archive_manifest_sha256=b.ARCHIVE_SHA, baseline=str(b.contract.DEFAULT_BASELINE),
        build=str(b.contract.DEFAULT_BUILD), elf=report['elf'], elf_sha256=report['elf_sha256'],
        image=report['simv'], commands=len(records), trials=parsed['trials'], raw_replay=parsed,
        raw_log_sha256=b.s.digest(b.contract.DEFAULT_BASELINE / 'work/run.vcs.log'),
        pins_sha256=b.s.digest(output / 'pins.json'), post_pins_match=True,
        guard=dict(forbidden_paths=sorted(map(str, guard.forbidden)),
                   live_include_scan_forbidden=True, observed_opens=guard.opens),
        source_mapping='Exactly five hardware/build and two separate frozen software identities',
        scope='Old dual-reader/legacy+v2 storage resource baseline, same frozen ELF; '
              'not a new canonical image acceptance or RVV acceleration result',
        compiler_invoked=False, simulator_invoked=False, production_promoted=False))
    print(b.s.digest(output / 'result.json'))


if __name__ == '__main__':
    main()

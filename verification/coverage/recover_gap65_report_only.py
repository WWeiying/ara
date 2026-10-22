#!/usr/bin/env python3
"""Recover completed gap65 reports into a NEW directory without launching tools.

Historical sealed scripts and runtime02 are inputs only. Cache SHA256 within
this process, binding every reuse to file identity, and rehash ALL inputs before
publishing an independent completion. No persistent cache or oracle override.
"""
import argparse
from contextlib import contextmanager, ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

sys.dont_write_bytecode = True
import finalize_gap65_observed as sealed
from ara_verify import artifacts

full, require = sealed.full, sealed.require
RAW_SHA256 = artifacts.sha256
SCRIPT = Path(__file__).resolve()
SCHEMA = 'gap65-report-only-recovery-v1'


def identity(path):
    stat = path.stat()
    link = path.lstat()
    require(path.is_file(), f'missing regular evidence: {path}')
    return (str(path.resolve(strict=True)), stat.st_dev, stat.st_ino,
            stat.st_size, stat.st_mode, stat.st_mtime_ns, stat.st_ctime_ns,
            stat.st_nlink, link.st_dev, link.st_ino, link.st_mode,
            link.st_mtime_ns, link.st_ctime_ns)


class HashSession:
    def __init__(self, hasher=RAW_SHA256):
        self.hasher = hasher
        self.entries = {}
        self.hits = 0
        self.bytes = 0
        self.reverified = 0
        self.started = time.monotonic()

    def digest(self, path):
        path = full.absolute(path).absolute()
        key = str(path)
        before = identity(path)
        if key in self.entries:
            bound, digest = self.entries[key]
            require(before == bound, f'evidence identity changed: {path}')
            self.hits += 1
            return digest
        digest = self.hasher(path)
        require(identity(path) == before, f'evidence changed while hashing: {path}')
        self.entries[key] = (before, digest)
        self.bytes += before[3]
        if len(self.entries) % 1000 == 0:
            print(f'HASHED unique={len(self.entries)} cache_hits={self.hits} '
                  f'elapsed_s={time.monotonic() - self.started:.1f}', flush=True)
        return digest

    def reverify(self):
        # Deliberately bypass every patched SHA alias, even on identical stat.
        for index, (key, (bound, digest)) in enumerate(self.entries.items(), 1):
            path = Path(key)
            require(identity(path) == bound, f'evidence changed before final rehash: {path}')
            actual = self.hasher(path)
            require(identity(path) == bound and actual == digest,
                    f'evidence changed during final rehash: {path}')
            self.reverified += 1
            if index % 1000 == 0:
                print(f'REHASHED {index}/{len(self.entries)}', flush=True)
        self.assert_unchanged()

    def assert_unchanged(self):
        for key, (bound, _) in self.entries.items():
            require(identity(Path(key)) == bound, f'evidence changed before publication: {key}')

    def stats(self):
        return dict(unique_files=len(self.entries), cache_hits=self.hits,
                    initial_bytes=self.bytes, final_rehashed=self.reverified,
                    elapsed_s=round(time.monotonic() - self.started, 3))


def refuse(*args, **kwargs):
    raise RuntimeError('report-only recovery forbids child processes and tool execution')


@contextmanager
def report_only(session):
    """Patch hash aliases only; all sealed validators remain authoritative."""
    with ExitStack() as stack:
        originals = (RAW_SHA256, sealed.targeted.bitmaps.digest)
        for module in list(sys.modules.values()):
            filename = getattr(module, '__file__', None)
            if (not filename or Path(filename).resolve() == SCRIPT
                    or not Path(filename).resolve().is_relative_to(full.ROOT / 'verification')):
                continue
            for name, value in list(vars(module).items()):
                if any(value is original for original in originals):
                    stack.enter_context(patch.object(module, name, session.digest))
        stack.enter_context(patch.object(sealed.evidence.Evidence, 'baseline_row', sealed.baseline_row))
        stack.enter_context(patch.object(full.batch, 'invoke', refuse))
        stack.enter_context(patch.object(subprocess, 'Popen', refuse))
        for name in ('system', 'execv', 'execve', 'execvp', 'execvpe', 'execl', 'execlp', 'execlpe',
                     'posix_spawn', 'posix_spawnp', 'fork'):
            if hasattr(os, name):
                stack.enter_context(patch.object(os, name, refuse))
        yield


def check_database(proof, directory, expected):
    require(full.base.inventory(Path(directory)) == expected, f'VDB inventory differs: {directory}')
    proof.hashes(expected)


def validate_completed_reports(proof, runtime):
    plan = proof.plan(runtime)
    require(runtime == sealed.RUNTIME and plan.get('gap65_report_only') == sealed.SCHEMA
            and plan['baseline'] == str(sealed.BASELINE) and plan['baseline_passed'] == 650
            and len(plan['cases']) == 1 and plan['cases'][0]['name'] == sealed.ROW,
            'not the sealed runtime02 producer')
    proof.hashes(plan['files'])
    base_collection = proof.collection(sealed.BASELINE, plan['image'])
    require(base_collection['status'] == 'PASS'
            and base_collection['passed'] == base_collection['total'] == 650
            and proof.read(sealed.BASELINE / 'checkpoint.json')['coverage_status'] == 'COMPLETE',
            'original checked650 baseline is not complete')
    old = proof.ledger(sealed.BASELINE, plan['image'])
    require(proof.read(runtime / 'inputs/baseline-ledger.json') == old,
            'prepared baseline differs from original 650')
    collection = proof.collection(runtime, plan['image'])
    require(collection['status'] == 'PASS' and collection['passed'] == collection['total'] == 651
            and collection['baseline_passed'] == 650 and collection['new_passed'] == 1
            and collection['cross_image_reuse'] is False and not collection['excluded']
            and collection['counts'] == {'PASS': 1}, 'completed 651 collection required')
    row = proof.read(runtime / 'outcomes/tests.json')
    require(proof.read(runtime / 'all-outcomes.json') == [row], 'new outcome list differs')
    rows = proof.ledger(runtime, plan['image'])
    require(rows == old + [row], '651 ledger does not preserve the entire original 650')
    require(row['name'] not in {r['name'] for r in old}
            and row['coverage_test'] not in {r['coverage_test'] for r in old}
            and row['elf_sha256'] not in {r['elf_sha256'] for r in old}, 'duplicate gap65 identity')
    require(len({r['vdb'] for r in rows}) == 651, 'duplicate merged VDB')
    return plan, rows, old


def validate_rows(proof, rows, plan):
    for index, row in enumerate(rows, 1):
        try:
            proof.baseline_row(row, plan['image'], plan['simv'])
            if row['kind'] != sealed.KIND:
                require(full.batch.valid_vdb(Path(row['vdb']), row['coverage_test'], plan['simv'])
                        == row['vdb_files'], 'original VDB validity/hash differs')
            # The narrow hook already performs this exact VDB validation for gap65.
            proof.hashes(row['vdb_files'])
        except Exception as error:
            raise ValueError(f'ledger row {index} {row.get("name")}: {error}') from error
        if index % 50 == 0 or index == len(rows):
            print(f'CHECKED ledger/oracle/VDB: {index}/{len(rows)}', flush=True)


def validate_producers(proof, plan):
    for directory, producer in list(proof.plans.items()):
        require(producer['image'] == plan['image'] and producer['simv'] == plan['simv']
                and producer['design_vdb'] == plan['design_vdb']
                and producer['design_files'] == plan['design_files'], f'producer image/design differs: {directory}')
        proof.hashes(producer['files'])
    require(full.batch.simulation_image(Path(plan['simv'])) == plan['image'], 'simulation image drift')
    check_database(proof, plan['design_vdb'], plan['design_files'])


def validate_deltas(proof, runtime, plan, rows, old):
    # The sealed report callback checks actual logs, DONE, diagnostics, waivers,
    # summary completeness, selected tests and membership without invoking DVE.
    sealed.report_callback(runtime, plan, rows, proof)
    membership = [plan['design_vdb'], *[r['vdb'] for r in rows]]
    require(proof.pin(runtime / 'combined-inputs.txt').read_text().splitlines() == membership
            and proof.pin(runtime / 'gap65-report-inputs.txt').read_text().splitlines() == membership,
            'existing report input membership differs')
    require(proof.pin(sealed.BASELINE / 'combined-dve/inputs.txt').read_text().splitlines()
            == [plan['design_vdb'], *[r['vdb'] for r in old]], 'original650 DVE membership differs')
    before = proof.read(sealed.BASELINE / 'combined-bits.json')
    require(before['tests'] == [r['vdb'] for r in old], 'original650 bitmap membership differs')
    proof.hashes(before['input_hashes'])
    listing = proof.pin(runtime / 'inputs/tests.vdbs.txt')
    require(listing.read_text().splitlines() == [plan['design_vdb'], rows[-1]['vdb']],
            'gap65 bitmap inputs differ')
    fresh = sealed.targeted.bitmaps.collect(listing)
    proof.hashes(fresh['input_hashes'])
    merged = sealed.targeted.bitmaps.combine(before, fresh)
    require(proof.read(runtime / 'combined-bits.json') == merged, 'merged bitmap union differs')
    proof.hashes(merged['input_hashes'])
    gains = sealed.targeted.bitmaps.delta(before, merged)
    require(proof.read(runtime / 'raw-bitmap-delta.json') == gains, 'raw bitmap delta differs')
    case = plan['cases'][0]
    matched = [r for r in gains['instances'] if any(r['instance'] == t or r['instance'].startswith(t + '.')
               for t in case['coverage_targets'])]
    per_case = [dict(name=rows[-1]['name'], new_bits=gains['metrics'], target_gains=matched,
                     all_gains=gains['instances'])]
    require(proof.read(runtime / 'per-case-gains.json') == per_case, 'per-case gains differ')
    prior = sealed.targeted.hierarchy_rows(sealed.BASELINE / 'combined-dve/summary.csv')
    after = sealed.targeted.hierarchy_rows(runtime / 'combined-dve/summary.csv')
    require(prior.keys() == after.keys(), 'DVE hierarchy changed')
    official = {}
    for name in after:
        changes = {}
        for metric in ('Line', 'Toggle', 'FSM', 'Condition', 'Branch'):
            a, b = prior[name][metric], after[name][metric]
            if a == b:
                continue
            require(a != 'NA' and b != 'NA', 'DVE denominator changed')
            diff = round(float(b.rstrip('%')) - float(a.rstrip('%')), 2)
            require(diff >= 0, 'DVE cumulative coverage decreased')
            changes[metric] = dict(before=a, after=b, percentage_points=diff)
        if changes:
            official[name] = changes
    require(proof.read(runtime / 'coverage-delta.json') == official, 'official DVE delta differs')


def validate(proof, runtime):
    plan, rows, old = validate_completed_reports(proof, runtime)
    print('CHECKED collections and full 651 ledger membership', flush=True)
    validate_rows(proof, rows, plan)
    validate_producers(proof, plan)
    validate_deltas(proof, runtime, plan, rows, old)
    return plan, rows


def recover(output):
    require(output.is_absolute() and not output.exists(), 'new absolute recovery output required')
    require(not output.is_relative_to(sealed.RUNTIME) and not output.is_relative_to(sealed.BASELINE),
            'recovery must not write into original evidence')
    output.mkdir(parents=True, exist_ok=False)
    session = HashSession()
    try:
        with report_only(session):
            proof = sealed.evidence.Evidence()
            proof.pin(SCRIPT)
            proof.pin(full.ROOT / 'verification/tests/test_gap65_report_only_recovery.py')
            plan, rows = validate(proof, sealed.RUNTIME)
            full.check(proof.files)
            print('FINAL uncached full evidence rehash', flush=True)
            session.reverify()
            # Detect additions/removals as well as changes to listed files.
            for directory, expected in [(plan['design_vdb'], plan['design_files']),
                                        *[(r['vdb'], r['vdb_files']) for r in rows]]:
                check_database(proof, directory, expected)
            require(len(session.entries) == session.reverified, 'unreverified late evidence')
            session.assert_unchanged()
            completion = dict(status='PASS', schema=SCHEMA, source_runtime=str(sealed.RUNTIME),
                              baseline=str(sealed.BASELINE), baseline_passed=650, aggregate_passed=651,
                              simulations_started=False, tools_launched=False, original_evidence_modified=False,
                              hash_policy='process-local stat-bound cache; final uncached full SHA256 recheck',
                              hash_stats=session.stats(), files={k: v[1] for k, v in session.entries.items()})
            sealed.new_json(output / 'completion.json', completion)
            sealed.new_json(output / 'checkpoint.json', dict(status='PASS', phase='complete',
                            coverage_status='COMPLETE', aggregate_passed=651, simulations_started=False,
                            tools_launched=False, source_runtime=str(sealed.RUNTIME),
                            completion_sha256=RAW_SHA256(output / 'completion.json')))
        print(json.dumps(dict(status='PASS', output=str(output), aggregate_passed=651,
                              hash_stats=session.stats())), flush=True)
        return completion
    except BaseException as error:
        sealed.new_json(output / 'rejected.json', dict(status='REJECTED', schema=SCHEMA,
                        coverage_status='NOT_ADMITTED', reason=str(error), hash_stats=session.stats(),
                        simulations_started=False, tools_launched=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    recover(args.output.resolve())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

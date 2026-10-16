#!/usr/bin/env python3
"""Offline current-run QBS/AKV strict-oracle audit. No ledger or RTL writes.

Old manifests supply reference identities, never a verdict or execution receipt.
Only pure original checker entry points and pinned VPD conversion are invoked.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
from pathlib import Path
import sys
import traceback
from types import FunctionType, SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'verification'), str(ROOT / 'verification/coverage'),
                str(ROOT / 'verification/tests')]
from audit_probe_semantics_20261015 import sha, save, require, install_guard, CONVERTER, CONVERTER_SHA
from ucli_runtime_log_20261015 import iter_runtime_lines

RUNS = ROOT / 'verification/out/full-regression-20261015-01/extensions'
LEDGER = ROOT / 'verification/out/full-regression-reviewed-20261015-01/case-ledger.json'
DEFAULT_OUT = ROOT / 'verification/out/pending-qbs-akv-audit-20261016-01'
NUMERIC = {724: 'qualify_gap105_native_v5', 726: 'qualify_gap106_native',
           728: 'qualify_gap107_native', 729: 'qualify_gap108_native',
           731: 'qualify_gap109_native', 733: 'qualify_gap110_native_v2'}
RESETS = {746, 758, 759, 760}
ACTIVE = None
IN_HOOK = False
HASH_CACHE = {}


def cached_sha(path):
    p = Path(path)
    s = p.stat()
    key = (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    old = HASH_CACHE.get(str(p))
    if old is None or old[0] != key:
        HASH_CACHE[str(p)] = (key, sha(p))
    return HASH_CACHE[str(p)][1]


def record_reads(event, args):
    """Bind references opened inside unchanged original helper functions too."""
    global IN_HOOK
    if event != 'open' or ACTIVE is None or IN_HOOK:
        return
    path, mode, flags = args
    if not isinstance(path, (str, bytes, os.PathLike)) or flags & (os.O_WRONLY | os.O_RDWR):
        return
    if mode and any(c in mode for c in 'wax+'):
        return
    IN_HOOK = True
    try:
        p = Path(os.fsdecode(path)).resolve()
        if p.is_file() and p.is_relative_to(ROOT) and not p.is_relative_to(ACTIVE.out):
            expected = ACTIVE.old.get('pins', {}).get(str(p))
            # Current compiled sources are authenticated by the current build,
            # not by a historical image's manifest at the same source pathname.
            expected = getattr(ACTIVE, 'current_sources', {}).get(str(p), expected)
            ACTIVE.bind(p, expected)
    finally:
        IN_HOOK = False


def selected(c):
    return c['status'] == 'CHECKER_REQUIRED' and (c['coverage_test'].startswith('qbs') or 'akv' in c['coverage_test'])


def verdict(components, required):
    rows = [components.get(k, {'status': 'CHECKER_REQUIRED'}) for k in required]
    if any(r['status'] == 'FAIL' for r in rows):
        return 'FAIL'
    return 'PASS' if all(r['status'] == 'PASS' for r in rows) else 'CHECKER_REQUIRED'


def reset_event_predicates(log, vector_trace, split):
    """Retain the original independent reset event checks and issue allowlist."""
    from ara_verify.uvm_dut import check_real_uvm_log
    from qualify_qbs_affine_external_reset import event_audit
    original = check_real_uvm_log(log, require_events=True, require_backend=True,
                                  require_axi=True, vector_trace=vector_trace, reset_kind='state')
    independent = event_audit(Path(log).read_text(), split, original)
    return dict(original_uvm_checker=original, independent_event_audit=independent,
                original_issue_allowlist_unmodified=True, UVM_report_qualification_claimed=False)


def gap65_snapshots(rows, base, gold):
    """Independent native scalar visibility for both full 512-byte snapshots."""
    import qualify_gap105_native_v5 as decoder
    reads = [r for r in rows if r['event'] == 'retire' and int(r['mem_rmask'], 16) and
             base <= int(r['mem_addr'], 16) < base + 512]
    require(len(reads) == 256 and len(gold) == 16, 'Complete two GAP65 native snapshots required')
    for ordinal, row in enumerate(reads):
        phase, index = divmod(ordinal, 128)
        address = base + 4 * index
        word = int(row['insn'], 16)
        require(decoder.scalar_access(word) == ('read', 4) and
                decoder.load_destination(word) == (False, int(row['rd'])) and int(row['rd']) != 0 and
                not int(row['trap']) and int(row['mem_addr'], 16) == address and
                int(row['mem_rmask'], 16) == 15 << (address & 7), 'GAP65 snapshot load identity/order/mask')
        expected = (0x41800000 + 7919 * index) if phase == 0 else (
            gold[(index // 32) * 4 + index % 32] if index % 32 < 4 else 0)
        require(int(row['rd_wdata'], 16) & 0xffffffff == expected,
                f'GAP65 native snapshot mismatch phase={phase} word={index}')
    return dict(fault_preserved_bytes=512, recovery_compared_bytes=512, recovery_numerical_values=16,
                recovery_zero_tail_words=112, actual_native_scalar_loads=256)


class Audit:
    def __init__(self, case, output):
        self.case = case
        self.index = case['index']
        self.run = RUNS / f'e{self.index:04d}'
        self.out = output / self.run.name
        self.out.mkdir()
        self.inputs = {}
        self.components = {}
        self.plan = self.read(self.run / 'plan.json')
        self.old = self.read(Path(self.plan['command_source']), self.plan['pins'][self.plan['command_source']])
        self.work = self.run / 'work'
        self.runtime = self.out / 'runtime'
        self.runtime.mkdir()

    def bind(self, path, expected=None):
        path = Path(path).resolve(strict=True)
        digest = cached_sha(path)
        require(expected is None or digest == expected, 'Input identity mismatch: ' + str(path))
        require(str(path) not in self.inputs or self.inputs[str(path)] == digest, 'Input drift: ' + str(path))
        self.inputs[str(path)] = digest
        return path

    def read(self, path, expected=None):
        return json.loads(self.bind(path, expected).read_text())

    def check(self, name, fn, oracle, context=False):
        try:
            value = fn()
            row = dict(status='PASS', oracle=oracle, result=value)
        except Exception as error:
            missing = isinstance(error, (FileNotFoundError, ModuleNotFoundError, PermissionError))
            context = context or missing or any(s in str(error).lower() for s in
                ('drift', 'source observer', 'source contract', 'input identity', 'abi', 'frozen comparator'))
            context = context or (name == 'microstructure' and any(s in str(error).lower() for s in
                ('layout', 'width', 'declaration', 'missing', 'scope')))
            row = dict(status='CHECKER_REQUIRED' if context else 'FAIL', oracle=oracle,
                       reason=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
        self.components[name] = row
        save(self.out / (name + '.json'), row)
        print(self.run.name, name, row['status'], row.get('reason', ''), flush=True)
        return row.get('result')

    def common(self):
        r = self.read(self.run / 'simulation-exit.json')
        require(r['executed'] is True and r['returncode'] == 0 and r['timed_out'] is False and
                r['cancelled'] is False, 'Current simulation did not exit successfully')
        require(r['command'] == self.plan['command'] and r['cwd'] == str(self.work) and
                r['pid'] > 0 and r['finished'] > r['started'], 'Current receipt identity mismatch')
        image = ROOT / 'verification/out/full-regression-build-20261015-01/build-image.json'
        book = self.read(image)
        self.current_sources = self.read(image.parent / 'build-source-pins.json')
        require(self.plan['command'][0] == str(image.parent / 'sim/simv'), 'Wrong current image path')
        self.bind(self.plan['command'][0], book[self.plan['command'][0]])
        self.bind(self.run / 'input.elf', self.plan['elf_sha256'])
        original = Path(next(a.split('=', 1)[1] for a in self.plan['original_command'] if a.startswith('+PRELOAD=')))
        self.bind(original, self.plan['elf_sha256'])
        self.original_elf = original
        sources = {str(p): self.bind(p, self.plan['pins'][str(p)]).read_text()
                   for p in sorted((self.run / 'ucli').glob('*.tcl'))}
        for name, path in [('console.log', self.run / 'console.log'), ('run.vcs.log', self.work / 'run.vcs.log')]:
            with self.bind(path).open(errors='replace') as stream:
                text = ''.join(iter_runtime_lines(stream, sources))
            require(text.count('Core Test *** SUCCESS ***') == 1, 'Unique actual firmware success missing: ' + name)
            from replay_historical_extensions_20261015 import RAW_FAIL
            from ara_verify.runner import FAIL_RE
            require(not RAW_FAIL.search(text) and not FAIL_RE.search(text), 'Actual runtime failure: ' + name)
            (self.runtime / name).write_text(text)
        for name in ('commit_trace.csv', 'vector_trace.csv'):
            path = self.work / name
            if not path.is_file() and name == 'vector_trace.csv' and self.index == 650:
                continue
            (self.runtime / name).write_bytes(self.bind(path).read_bytes())
        return dict(receipt=r, raw_logs_bound=True, Tcl_echo_removed=True,
                    clean_exit_is_semantic_acceptance=False)

    def module(self, name):
        m = importlib.import_module(name)
        self.bind(m.__file__)
        return m

    def native(self):
        i, run = self.index, self.runtime
        if i in NUMERIC:
            q = self.module(NUMERIC[i])
            f = q.frozen if i == 724 else q
            symbols, data, sites = f.elf_view()
            return q.runtime(run, symbols, data, sites, f.independent_native())
        if i in (740, 741, 763):
            if i == 740:
                q = self.module('qualify_gap113_payload_toggle')
                view = q.adapter()
            elif i == 741:
                q = self.module('run_gap113_full8_cached').qualifier(self.plan['pins'][self.plan['command_source']])
                view = q.adapter()
            else:
                q = self.module('qualify_qbs_payload_phase763')
                view = q.view()
            symbols, data, sites = view.elf_view()
            return view.runtime(run, symbols, data, sites, q.independent_native())
        if i in (765, 766):
            q = self.module('qualify_qbs_payload_matrix4_uart' if i == 765 else 'qualify_qbs_payload_residual4_766')
            return q.runtime(run)
        if i in RESETS:
            return self.reset_native()
        if i == 687:
            q = self.module('recheck_gap81_old_image')
            proof = self.read(self.original_elf.parent / 'elf-proof.json')
            return q.runtime(run / 'commit_trace.csv', run / 'vector_trace.csv', run / 'run.vcs.log', proof['site']['pc'])
        if i == 688:
            q = self.module('verify_gap82_offline')
            proof = self.read(self.original_elf.parent / 'elf-proof.json')
            return q.runtime(run, proof)
        if i == 650:
            q = self.module('gap65_late_fault_checks')
            proof = self.read(ROOT / 'verification/out/gap65-late-fault-preflight-20261004-04/elf-proof.json')
            require(proof['elf_sha256'] == self.plan['elf_sha256'], 'GAP65 reference ELF identity mismatch')
            q.check_runtime_log((run / 'run.vcs.log').read_text(), proof)
            from ara_verify.trace import validate_trace
            from ara_verify.contract import check_contract_log
            require(not check_contract_log(run / 'run.vcs.log'), 'GAP65 terminal contract failed')
            trace = validate_trace(run / 'commit_trace.csv')
            with (run / 'commit_trace.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            native = gap65_snapshots(rows, proof['buffer_symbols']['gap65_observed']['Value'] + 64,
                                     q.vectors()['expected_bits'])
            pending, custom = {}, []
            for row in rows:
                key = int(row['trans_id'])
                if row['event'] == 'cvx_req':
                    require(key not in pending, 'GAP65 duplicate pending request')
                    pending[key] = int(row['insn'], 16)
                elif row['event'] == 'cvx_resp':
                    require(key in pending, 'GAP65 orphan response')
                    word = pending.pop(key)
                    if word == 0x06b5045b:
                        custom.append(int(row['trap']))
            require(not pending and custom == [1, 0], 'GAP65 exact fault/recovery response outcomes')
            retires = [r for r in rows if r['event'] == 'retire' and int(r['insn'], 16) == 0x06b5045b]
            require(len(retires) == 1 and int(retires[0]['pc'], 16) == proof['sites']['gap65_recovery_site'] and
                    not int(retires[0]['trap']), 'GAP65 fault not retired and exact recovery retirement')
            self.bind(ROOT / 'apps/qbs_gap65_late_fault/main.c')
            return dict(original_oracle='GAP65 full 49 software checks, precise fault/site and numerical recovery',
                        proof=proof, trace=trace, independent_native=native, custom_response_traps=custom,
                        vector_trace_required=False, replacement_observer_required=True)
        return self.akv_native()

    def reset_native(self):
        q = self.module('qualify_qbs_affine_external_reset')
        epochs = q.epochs
        cf, cr = epochs.read_csv(self.runtime / 'commit_trace.csv')
        vf, vr = epochs.read_csv(self.runtime / 'vector_trace.csv')
        split, cycle = epochs.split_epochs(cr, vr)
        view = q.adapter()
        symbols, data, sites = view.elf_view()
        inputs = q.native()
        audits = []
        for i, (commits, vectors) in enumerate(split):
            p = self.out / f'epoch{i}'
            p.mkdir()
            epochs.write_csv(p / 'commit_trace.csv', cf, commits)
            epochs.write_csv(p / 'vector_trace.csv', vf, vectors)
            (p / 'run.vcs.log').write_bytes((self.runtime / 'run.vcs.log').read_bytes())
            if i == 0:
                adapter = SimpleNamespace(WORD=q.WORD, inherited=q.inherited, activity_bytes=q.full8.activity_bytes)
                result = epochs.cancelled_epoch(p, commits, vectors, adapter, symbols, sites)
                q.events.backend(commits, vectors, {result['cancelled_arch_seq']})
            else:
                result = view.runtime(p, symbols, data, sites, inputs)
                q.events.backend(commits, vectors, set())
            audits.append(result)
        event_proof = reset_event_predicates(self.runtime / 'run.vcs.log',
                                             self.runtime / 'vector_trace.csv', split)
        return dict(epochs=audits, reset_cycle=cycle, reset_event_predicates=event_proof,
                    internal_slot_state_acceptance=False)

    def akv_native(self):
        i, run = self.index, self.runtime
        pre = self.old['preflight']
        blob = self.bind(self.run / 'input.elf').read_bytes()
        if i == 720:
            q = self.module('check_akv_column_boundary_v5_offline')
            from elftools.elf.elffile import ELFFile
            from io import BytesIO
            symbols = dict(pre['symbols'])
            elf = ELFFile(BytesIO(blob))
            entries = {s.name: s.entry['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
            for n in ('query', 'key', 'value', 'descriptor', 'seed'):
                symbols[n] = entries[n]
            arch = q.commit_audit(q.commit_rows(run / 'commit_trace.csv'), symbols, blob)
            return dict(architecture=arch, vector=q.vector_audit(run / 'vector_trace.csv', arch),
                        stdout=q.stdout_audit((run / 'run.vcs.log').read_text()))
        if i == 723:
            q = self.module('check_akv_lifecycle_offline_v2')
            rows = q.native.commit_rows(run / 'commit_trace.csv')
            model, scalar = q.oracle.replay(blob, pre['symbols'], rows)
            arch = q.commit_audit(rows, model)
            return dict(scalar=scalar, architecture=arch,
                        vector=q.vector_audit(q.native.common.read_csv(run / 'vector_trace.csv', q.native.common.VECTOR_FIELDS), model, arch),
                        contract=q.stdout_audit((run / 'run.vcs.log').read_text()),
                        perf=q.perf_audit((run / 'run.vcs.log').read_text(), arch, model))
        name = {776: 'collect_akv_entropy', 780: 'collect_akv_tile_range_capture', 795: 'collect_akv_canonical_alias794'}[i]
        q = self.module(name)
        old = q if i == 776 else q.old
        rows = old.isa.base.native.commit_rows(run / 'commit_trace.csv')
        source_binding = None
        replay = q.replay
        if i == 795:
            successor = self.module('collect_akv_canonical_alias794_sd_v2')
            # Preserve the reviewed SD/ECALL predicates; only the compiled
            # source book is rebound to the actual current execution image.
            book = ROOT / 'verification/out/full-regression-build-20261015-01/build-source-pins.json'
            source_binding = FunctionType(successor.source.__code__,
                dict(successor.source.__globals__, BOOK=book, BOOK_SHA=cached_sha(self.bind(book))))()
            replay = successor.replay
        model, scalar = replay(blob, pre['symbols'], rows)
        lifecycle = q.lifecycle if i == 795 else old.lifecycle
        vectors = q.vectors if i == 795 else old.vectors
        arch = lifecycle(rows, model)
        self.akv_arch = arch
        return dict(scalar=scalar, architecture=arch, current_source_binding=source_binding,
                    vector=vectors(old.isa.base.native.common.read_csv(run / 'vector_trace.csv', old.isa.base.native.common.VECTOR_FIELDS), model, arch),
                    perf=q.perf((run / 'run.vcs.log').read_text(), arch),
                    contract=q.contract((run / 'run.vcs.log').read_text(), arch['requests']))

    def wave(self):
        import subprocess
        if self.index == 650:
            observer = self.module('run_gap65_late_fault_observed')
            path = self.bind(self.work / 'gap65-observer.tsv')
            return dict(observer_path=str(path), samples=observer.observer_samples(path.read_text()),
                        purpose='Required live COMPUTE_TILE fault arc during active integer compute; not numerical acceptance')
        name = 'external-reset.vpd' if self.index in RESETS else 'entropy-ranges.vpd'
        self.bind(CONVERTER, CONVERTER_SHA)
        source = self.bind(self.work / name)
        vcd = self.out / 'current.vcd'
        with (self.out / 'conversion.log').open('x') as log:
            flags = ['+includemda', '+splitpacked'] if self.index in RESETS else []
            subprocess.run([str(CONVERTER), *flags, str(source), str(vcd)],
                           cwd=self.out, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
        self.bind(vcd)
        if self.index in RESETS:
            q = self.module('qualify_qbs_affine_external_reset')
            selection = self.old['selection']
            if self.index == 760:
                successor = self.module('qualify_qbs_affine_min_slot15_v2')
                base = successor.old
                project = FunctionType(base.selected_wave.__code__, dict(base.selected_wave.__globals__, run=successor.run))
                reuse = FunctionType(base.slot_reuse.__code__, dict(base.slot_reuse.__globals__, run=successor.run))
            else:
                project, reuse = q.selected_wave, q.slot_reuse
            target = self.out / 'selected-reset.vcd'
            projection = project(vcd, target, selection)
            window = q.reset_wave.audit(target, selection)
            return dict(projection=projection, window=window,
                        reuse=reuse(target, selection, window['release_timestamp']))
        q = self.module({776: 'collect_akv_entropy', 780: 'collect_akv_tile_range_capture',
                         795: 'collect_akv_canonical_alias794'}[self.index])
        if self.index == 795 and not hasattr(self, 'akv_arch'):
            raise FileNotFoundError('Canonical-alias capture requires successful current architectural replay first')
        symbols = self.old['preflight']['symbols']
        return q.range_wave(vcd, symbols) if self.index == 776 else (
            q.native_wave(vcd, symbols, self.akv_arch) if self.index == 795 else q.native_wave(vcd, symbols))

    def finish(self):
        required = {'execution', 'architecture'}
        if self.index in RESETS or self.index in (650, 776, 780, 795):
            required.add('microstructure')
        status = verdict(self.components, required)
        for p, h in self.inputs.items():
            require(cached_sha(p) == h, 'Input changed during audit: ' + p)
        reasons = {k: self.components.get(k, {}).get('reason', 'not executed') for k in sorted(required)
                   if self.components.get(k, {}).get('status') != 'PASS'}
        result = dict(index=self.index, coverage_test=self.case['coverage_test'], status=status,
                      report=str(self.out / 'result.json'), current_work=str(self.work),
                      planpath=str(self.run / 'plan.json'), root=str(ROOT),
                      vector_trace_required=self.index != 650,
                      replacement_observer_required=self.index == 650,
                      replacement_observer=str(self.work / 'gap65-observer.tsv') if self.index == 650 else None,
                      actual_execution_identity_validated=self.components.get('execution', {}).get('status') == 'PASS',
                      architectural_status=self.components.get('architecture', {}).get('status', 'CHECKER_REQUIRED'),
                      microstructure_status=self.components.get('microstructure', {}).get('status', 'NOT_REQUIRED'),
                      microstructure_is_architectural_acceptance=False, required_components=sorted(required),
                      reason=reasons or 'Original strict oracle accepted actual current outputs',
                      components=self.components, input_pins=self.inputs,
                      coverage_admitted=False, old_PASS_reused=False, simulation_rerun=False,
                      needed_action=None if status == 'PASS' else
                      'Inspect failed original predicate and bound evidence. Missing traces/waves require a source-reviewed focused rerun; no rerun was launched.')
        save(self.out / 'result.json', result)
        return result


def main():
    global ACTIVE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT / 'verification/out') and not output.exists(), 'Fresh workspace output required')
    output.mkdir()
    install_guard(output)
    sys.addaudithook(record_reads)
    ledger = json.loads(LEDGER.read_text())
    results = []
    for case in ledger['cases']:
        if not selected(case):
            continue
        a = Audit(case, output)
        ACTIVE = a
        a.bind(LEDGER)
        a.check('execution', a.common, 'Actual current receipt, image, ELF and runtime-only logs', context=True)
        if a.components['execution']['status'] == 'PASS':
            a.check('architecture', a.native, 'Original specialized strict architectural oracle')
            if a.index in RESETS or a.index in (650, 776, 780, 795):
                a.check('microstructure', a.wave, 'Original reset/capture witness on current VPD (not architectural acceptance)')
        # Bind every imported checker/helper source used, including private adapters.
        for m in list(sys.modules.values()):
            p = getattr(m, '__file__', None)
            if p and Path(p).suffix == '.py' and Path(p).resolve().is_relative_to(ROOT / 'verification'):
                a.bind(p)
        results.append(a.finish())
        ACTIVE = None
    summary = dict(ledger=str(LEDGER), ledger_sha256=sha(LEDGER), cases=results,
                   counts={s: sum(r['status'] == s for r in results) for s in ('PASS', 'FAIL', 'CHECKER_REQUIRED')},
                   accepted_ids=[r['index'] for r in results if r['status'] == 'PASS'],
                   rejected_ids=[r['index'] for r in results if r['status'] == 'FAIL'],
                   pending_ids=[r['index'] for r in results if r['status'] == 'CHECKER_REQUIRED'])
    all_inputs = {}
    for row in results:
        for p, digest in row['input_pins'].items():
            require(p not in all_inputs or all_inputs[p] == digest, 'Cross-case input drift: ' + p)
            all_inputs[p] = digest
    for p, digest in all_inputs.items():
        require(sha(p) == digest, 'Final input verification failed: ' + p)
    save(output / 'audit.json', summary)
    print(json.dumps({k: v for k, v in summary.items() if k != 'cases'}, indent=2))


if __name__ == '__main__':
    main()

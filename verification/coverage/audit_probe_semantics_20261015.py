#!/usr/bin/env python3
"""Audit existing 11 probe cases only; never run simulations or old collectors.

Only the pinned VPD converter may be executed. Python writes are confined to a
fresh output directory. Old image/service manifests are evidence, not replacement
execution contexts. Pure checker failures and source-context holds stay visible.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback
from types import FunctionType, SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'verification'), str(Path(__file__).resolve().parent)]
CASES = (761, 771, 782, 785, 786, 788, 789, 790, 791, 792, 794)
RUNS = ROOT / 'verification/out/full-regression-20261015-01/extensions'
BUILD = ROOT / 'verification/out/full-regression-build-20261015-01'
DEFAULT_OUT = ROOT / 'verification/out/full-regression-failure-review-20261015-01/probe-semantics/final02'
CONVERTER = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/linux64/bin/vpd2vcd.exe')
CONVERTER_SHA = '195fae31e4cbacabcbbd97bfd61c98a333f68ff2fd013002ab322e5108f97002'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def install_guard(output):
    """Defense in depth against accidentally calling an old lifecycle function."""
    output = output.resolve()

    def writable(path):
        return isinstance(path, (str, bytes, os.PathLike)) and Path(os.fsdecode(path)).resolve().is_relative_to(output)

    def guard(event, args):
        if event == 'open':
            path, mode, flags = args
            writing = (mode is not None and any(c in mode for c in 'wax+')) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
            if writing and not writable(path):
                raise PermissionError('Audit attempted write outside output: ' + str(path))
        elif event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.utime'):
            require(writable(args[0]), 'Audit mutation outside output: ' + str(args[0]))
        elif event in ('os.rename', 'os.link', 'os.symlink'):
            raise PermissionError('Audit does not need filesystem relinking')
        elif event == 'subprocess.Popen':
            require(Path(args[0]).resolve() == CONVERTER.resolve(), 'Only VPD conversion permitted')
            require(args[2] is not None and writable(args[2]), 'Converter must run in new output')
        elif event in ('os.system', 'os.exec', 'os.posix_spawn', 'os.fork'):
            raise PermissionError('No simulation, shell or worker execution permitted')
    sys.addaudithook(guard)


class CaseAudit:
    def __init__(self, index, output):
        self.index = index
        self.case = RUNS / f'e{index:04d}'
        self.work = self.case / 'work'
        self.out = output / f'e{index:04d}'
        self.out.mkdir()
        self.inputs = {}
        self.components = {}
        self.plan = self.bind_json(self.case / 'plan.json')
        self.old = self.bind_json(self.plan['command_source'], self.plan['pins'][self.plan['command_source']])

    def bind(self, path, expected=None):
        path = Path(path).absolute()
        digest = sha(path)
        require(expected is None or expected == digest, 'Input pin mismatch: ' + str(path))
        require(str(path) not in self.inputs or self.inputs[str(path)] == digest, 'Input drift: ' + str(path))
        self.inputs[str(path)] = digest
        return path

    def bind_json(self, path, expected=None):
        return read(self.bind(path, expected))

    def old_bound(self, path):
        path = Path(path)
        expected = self.old['pins'].get(str(path))
        require(expected is not None, 'Original manifest lacks required reference pin: ' + str(path))
        return self.bind(path, expected)

    def check(self, name, function, checker):
        try:
            value = function()
            row = dict(status='PASS', checker=checker, result=value)
        except Exception as error:
            row = dict(status='CHECKER_REQUIRED', checker=checker,
                       failure_kind='ENVIRONMENT_DEPENDENCY' if isinstance(error, ModuleNotFoundError) else 'CHECKER_OR_SOURCE_CONTEXT',
                       reason=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
        self.components[name] = row
        save(self.out / f'{name}.json', row)
        print(f'e{self.index:04d} {name}: {row["status"]}' + (': ' + row['reason'] if 'reason' in row else ''), flush=True)
        return row.get('result') if row['status'] == 'PASS' else None

    def common(self):
        from ucli_runtime_log_20261015 import iter_runtime_lines
        from replay_historical_extensions_20261015 import RAW_FAIL
        from ara_verify.runner import FAIL_RE, SUCCESS_RE
        from ara_verify.contract import check_contract_log, parse_contract_summary
        from ara_verify.trace import validate_trace

        receipt = self.bind_json(self.case / 'simulation-exit.json')
        require(receipt['executed'] is True and receipt['returncode'] == 0 and
                receipt['timed_out'] is False and receipt['cancelled'] is False,
                'Actual successful numeric simulation wait required')
        require(receipt['command'] == self.plan['command'] and receipt['cwd'] == str(self.work) and
                receipt['pid'] > 0 and receipt['finished'] > receipt['started'], 'Actual execution identity differs')
        image = self.bind_json(BUILD / 'build-image.json')
        require(self.plan['command'][0] == str(BUILD / 'sim/simv'), 'Unexpected current image')
        self.bind(self.plan['command'][0], image[self.plan['command'][0]])
        self.bind(self.case / 'input.elf', self.plan['elf_sha256'])
        sources = {str(p): self.bind(p, self.plan['pins'][str(p)]).read_text()
                   for p in sorted((self.case / 'ucli').glob('*.tcl'))}
        require(sources, 'Frozen Tcl missing')
        # This explicitly derived runtime-only view is not an old manifest/log.
        runtime = self.out / 'runtime'
        runtime.mkdir()
        ready = set(re.findall(r'\b([A-Z][A-Z0-9_]*PROBE_READY)\b', '\n'.join(sources.values())))
        require(len(ready) == 1, 'One source-bound probe-ready marker required')
        contracts_seen = {}
        for name in ('console.log', 'run.vcs.log'):
            path = self.case / name if name == 'console.log' else self.work / name
            self.bind(path)
            with path.open(errors='replace') as source:
                text = ''.join(iter_runtime_lines(source, sources))
            require(not RAW_FAIL.search(text) and not FAIL_RE.search(text), 'Runtime raw failure in ' + name)
            require(len(SUCCESS_RE.findall(text)) == 1, 'Exactly one firmware success in ' + name)
            require(all(text.splitlines().count(marker) == 1 for marker in ready), 'Actual probe setup not complete')
            target = runtime / name
            target.write_text(text)
            if self.index in (782, 785, 789, 790):
                require(not check_contract_log(target), 'Contract errors in ' + name)
            else:
                contracts = [parse_contract_summary(line) for line in text.splitlines() if '[ARA_CONTRACT]' in line]
                require(len(contracts) == 1 and contracts[0] is not None and
                        all(contracts[0][key] == 0 for key in ('requests', 'responses', 'exceptions', 'mmu_request_cycles',
                            'protocol_errors', 'outstanding', 'req_stalled', 'resp_stalled')),
                        'Original scalar-only zero-CVX contract differs in ' + name)
            contracts_seen[name] = [parse_contract_summary(line) for line in text.splitlines() if '[ARA_CONTRACT]' in line]
        self.bind(self.work / 'commit_trace.csv')
        self.bind(self.work / 'vector_trace.csv')
        generic = validate_trace(self.work / 'commit_trace.csv')
        return dict(receipt=receipt, image_sha256=image[self.plan['command'][0]],
                    trace=generic, runtime_view=str(runtime), contracts=contracts_seen,
                    traffic_scope='POSITIVE_CUSTOM_VECTOR' if self.index in (782, 785, 789, 790) else 'SCALAR_ZERO_CVXIF',
                    UVM_report_qualification_claimed=False, semantic_PASS_inferred=False)

    def preflight(self, runner, filename):
        path = runner.PRE / filename
        pre = self.bind_json(path, self.old['preflight_seal'])
        self.old_bound(runner.PRE / 'spike.trace')
        original_elf = next(x.split('=', 1)[1] for x in self.plan['original_command'] if x.startswith('+PRELOAD='))
        self.bind(original_elf, self.plan['elf_sha256'])
        self.pre = pre
        return pre

    def scalar(self, runner, pre, gate=None):
        from ara_verify.spike_trace import compare_commit_prefix
        reference_dir = runner if isinstance(runner, Path) else runner.PRE
        value = compare_commit_prefix(reference_dir / 'spike.trace', self.work / 'commit_trace.csv', 0x80000000,
                                      terminal_tohost_address=pre['symbols']['tohost'], rvfi_store_data_layout='unshifted')
        save(self.out / 'scalar-comparison.json', value)
        if gate:
            gate(value)
        else:
            from collect_gap103_strict import scalar_exact
            scalar_exact(value, pre.get('counts', self.old.get('scalar_reference_counts')))
        return value

    def convert(self, wave):
        self.bind(CONVERTER, CONVERTER_SHA)
        source = self.bind(self.work / wave)
        target = self.out / 'probe.vcd'
        flag = '+splitpacked' if self.index in (761, 782, 785, 789, 790) else '-splitpacked'
        command = [str(CONVERTER), flag, str(source), str(target)]
        with (self.out / 'vpd2vcd.log').open('x') as log:
            result = subprocess.run(command, cwd=self.out, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=120, check=True)
        require(target.is_file() and target.stat().st_size > 0, 'Empty VCD conversion')
        return dict(command=command, returncode=result.returncode, vpd_sha256=self.inputs[str(source)],
                    vcd=str(target), vcd_sha256=sha(target), simulation_started=False)

    def zero_vectors(self):
        with (self.work / 'vector_trace.csv').open() as stream:
            require(all(r['event'] == 'config' for r in csv.DictReader(stream)), 'Unexpected native vector writes')
        return dict(vector_data_writes=0)

    def memory(self):
        from collect_gap103_strict import scalar_store
        with (self.work / 'commit_trace.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        require(all(r['event'] == 'retire' and not int(r['trap']) for r in rows) and
                [int(r['order']) for r in rows] == list(range(len(rows))), 'Complete retire-only prefix')
        memory = {}
        for row in rows:
            store = scalar_store(row)
            if store:
                address, data = store
                memory.update({address + i: b for i, b in enumerate(data)})
        def word(address, size=8):
            return sum(memory[address + i] << (8 * i) for i in range(size))
        return rows, word

    def native_simple(self, runner, pre):
        rows, word = self.memory()
        sym = pre['symbols']
        if self.index == 761:
            observed = [word(sym['lnt_observed'] + 8 * i) for i in range(9)]
            require(observed == runner.expected(sym, word(sym['lnt_original_status'])), 'Native NI/TLB values/CSR differ')
            require([word(sym['g75_result'], 4), word(sym['g75_result'] + 4, 4), word(sym['num_failed'], 4)] == [14, 0, 0], 'Native14 signature')
            return dict(checks=14, observed=observed, retirements=len(rows))
        expected = [v for r in runner.cases() for v in r['expected']]
        require([word(sym['bp_observed'] + 8 * i) for i in range(16)] == expected, 'Native all16 FPU gold/NaNbox')
        csr = [word(sym['bp_csr'] + 8 * i) for i in range(5)]
        require(csr == [csr[0], 64, 64, 64, csr[0]], 'Native FCSR/flags/restoration')
        import diagnose_scalar_fpu_backpressure as diagnosed
        guards = diagnosed.guard_loads(rows, sym['bp_guards'])
        require([word(sym['g75_result'], 4), word(sym['g75_result'] + 4, 4), word(sym['num_failed'], 4),
                 word(sym['tohost'])] == [22, 0, 0, 1], 'Native checks/guards/tohost')
        return dict(checks=22, numeric_results=expected, csr=csr, guards=guards, retirements=len(rows))

    def run_simple(self):
        name = 'run_load_ni_tlb_control' if self.index == 761 else 'run_scalar_fpu_backpressure'
        runner = importlib.import_module(name)
        pre = self.preflight(runner, 'preflight.json')
        self.check('scalar', lambda: self.scalar(runner, pre), name + '.architecture.scalar_exact')
        self.check('native', lambda: self.native_simple(runner, pre), 'Original collect native memory/gold predicates')
        self.check('vector', self.zero_vectors, 'Original zero vector predicate')
        if self.index == 761:
            import qualify_load_ni_tlb_control as checker
            wave, fn = 'load-ni-tlb.vpd', checker.waveform
        else:
            import diagnose_scalar_fpu_backpressure_v2 as reviewed
            import diagnose_scalar_fpu_backpressure as diagnosed
            historical = self.bind_json(reviewed.predecessor.OUT / 'diagnostic.json', reviewed.OLD_SEAL)
            self.bind(Path(diagnosed.__file__), historical['input_pins'][str(Path(diagnosed.__file__).resolve())])
            # The sealed factory verifies source identity only. The returned
            # pure function receives this run's newly converted VCD, never old VPD.
            wave, fn = 'scalar-fpu-backpressure.vpd', reviewed.checked_wave_function()
            self.check('stdout', lambda: diagnosed.stdout_audit((self.out / 'runtime/console.log').read_text()), diagnosed.__name__ + '.stdout_audit')
        converted = self.check('conversion', lambda: self.convert(wave), 'Pinned vpd2vcd (not simulation)')
        if converted:
            self.check('wave', lambda: fn(Path(converted['vcd'])), fn.__module__ + '.' + fn.__name__)

    def run_qbs(self):
        name = 'collect_qbs_k2_row_pending782' if self.index == 782 else 'collect_qbs_pending_m4_783'
        checker = importlib.import_module(name)
        runner = checker.runner
        self.bind(runner.ELF, self.plan['elf_sha256'])
        self.old_bound(runner.PRE / 'dut.metadata.log')
        wave = 'qbs-k2-row-pending.vpd' if self.index == 782 else checker.WAVE
        self.check('native', lambda: checker.runtime(self.work), name + '.runtime')
        converted = self.check('conversion', lambda: self.convert(wave), 'Pinned vpd2vcd')
        if converted:
            fn = importlib.import_module('analyze_qbs_k2_pending782').cycles if self.index == 782 else checker.cycle_review
            self.check('wave', lambda: fn(Path(converted['vcd'])), fn.__module__ + '.' + fn.__name__)

    def run_csr(self):
        name = 'collect_csr_satp_sepc786' if self.index == 786 else 'collect_csr_cause_wlrl788'
        checker = importlib.import_module(name)
        runner = checker.runner
        pre = self.preflight(runner, 'preflight-manifest.json')
        ns = vars(checker) if self.index == 786 else checker.namespace()
        self.check('scalar', lambda: self.scalar(runner, pre, ns['scalar_gate']), name + '.scalar_gate')
        rows = ns['primitive'].parse_rows(self.work / 'commit_trace.csv')
        reference = runner.reference(pre)
        architecture = self.check('legacy_native', lambda: ns['architecture'](rows, reference, pre['symbols'], (self.case / 'input.elf').read_bytes()), name + '.architecture (original context gate preserved)')
        self.check('native', lambda: self.csr_architectural(rows, reference, pre, runner.oracle), 'Independent actual scalar/CSR/memory/guard oracle; no old source context')
        self.check('vector', self.zero_vectors, 'Original zero vector predicate')
        self.check('source_context', runner.source_contract, runner.__name__ + '.source_contract (unmodified)')
        converted = self.check('conversion', lambda: self.convert('csr-owner.vpd'), 'Pinned vpd2vcd')
        if architecture and converted and self.components['source_context']['status'] == 'PASS' and self.index == 786:
            # Cause successor reads an old RUN global. Never fabricate that context.
            self.check('wave', lambda: checker.wave_audit(Path(converted['vcd']), architecture['expected_CSR']), name + '.wave_audit')

    def csr_architectural(self, rows, reference, pre, oracle):
        """Architectural half of original CSR checker, with explicit real inputs.

        No internal operation enum, ready formula, TID or sampling-epoch claims.
        The original architecture function couples this part to old source proof
        when constructing its subsequent internal expected_CSR owner ledger.
        """
        import collect_csr_satp_sepc786 as shared
        import struct
        symbols = pre['symbols']
        expected_count = self.old['scalar_reference_counts']['matched_instructions']
        require(len(rows) == len(reference) == expected_count and
                [r['order'] for r in rows] == list(range(expected_count)) and
                all(r['event'] == 'retire' and r['trap'] == 0 for r in rows), 'Complete CSR retirements')
        require(shared.memory.elf_file_bytes((self.case / 'input.elf').read_bytes(), symbols['matrix_guards'], 16)
                == struct.pack('<QQ', *oracle.GUARDS), 'Independent initialized ELF guard values')
        regs, observed, guard_reads = {i: 0 for i in range(32)}, [], []
        counts = {'read': 0, 'write': 0}
        for row, ref in zip(rows, reference):
            require(row['pc'] == ref.pc and row['insn'] == ref.instruction and ref.instruction & 3 == 3
                    and not ref.vector_writes and not ref.fpr_writes, 'Complete scalar PC/opcode/no-FP identity')
            actual = {row['rd']: row['rd_wdata']} if row['rd'] else {}
            require(actual == {k: v for k, v in ref.gpr_writes.items() if k}, 'Actual CSR/GPR old/readback values')
            decoded = shared.primitive.memory_decode(row['insn'])
            accesses = []
            if decoded is None:
                require(not ref.memory_accesses and row['mem_rmask'] == row['mem_wmask'] == 0, 'Unexpected memory effect')
            else:
                size = decoded['size']
                address = (regs[decoded['base']] + decoded['offset']) & shared.memory.MASK64
                mask = ((1 << size) - 1) << (address & 7)
                require(address % size == 0 and row['mem_addr'] == address, 'Exact memory address/alignment')
                if decoded['kind'] == 'write':
                    value = regs[decoded['register']] & ((1 << (8 * size)) - 1)
                    require(row['mem_wmask'] == mask and row['mem_rmask'] == 0 and not actual and
                            row['mem_wdata'] & ((1 << (8 * size)) - 1) == value, 'Exact store source/data/mask')
                    require(address + size <= symbols['matrix_guards'] or address >= symbols['matrix_guards'] + 16, 'Immutable guards')
                    accesses = [(address, value)]
                else:
                    require(row['mem_rmask'] == mask and row['mem_wmask'] == 0 and
                            set(actual) == {decoded['register']}, 'Exact load owner/mask')
                    low = actual[decoded['register']] & ((1 << (8 * size)) - 1)
                    extended = shared.primitive.signed(low, 8 * size) if decoded['signed'] else low
                    require(actual[decoded['register']] == extended & shared.memory.MASK64, 'Load signedness')
                    accesses = [(address, None)]
                    if symbols['matrix_guards'] <= address < symbols['matrix_guards'] + 16:
                        i = (address - symbols['matrix_guards']) // 8
                        require(address == symbols['matrix_guards'] + 8 * i and size == 8 and
                                actual[decoded['register']] == oracle.GUARDS[i], 'Exact guard load values')
                        guard_reads.append(i)
                require(tuple(accesses) == ref.memory_accesses, 'Complete independent memory differential')
                counts[decoded['kind']] += 1
            observed.append(SimpleNamespace(pc=row['pc'], instruction=row['insn'], vector_writes={},
                            fpr_writes={}, gpr_writes=actual, memory_accesses=accesses))
            regs.update(actual)
            regs[0] = 0
        require(sum(counts.values()) == 168 and guard_reads == [0, 1], 'All168 memory effects/guards')
        gold = oracle.validate(observed, symbols)
        return dict(retirements=len(rows), memory_counts=counts, gold=gold,
                    CSR_values_and_restoration_verified=True, native_internal_TID_owner_claimed=False)

    def run_misalign(self):
        name = 'collect_scalar_misalign789' if self.index == 791 else 'collect_scalar_slot_rotation792'
        checker = importlib.import_module(name)
        runner = checker.runner
        if self.index == 792:
            # configure() checks old RTL dependencies and must not be spoofed.
            # Bind only the immutable software oracle, using explicit real paths.
            pre_dir = Path(self.old['preflight'])
            require(pre_dir == runner.APPROVED_PRE and self.old['preflight_seal'] == runner.APPROVED_PRE_SEAL, 'Exact software oracle authority')
            pre = self.bind_json(pre_dir / 'preflight-manifest.json', self.old['preflight_seal'])
            self.old_bound(pre_dir / 'spike.trace')
            self.bind(pre_dir / 'input.elf', self.plan['elf_sha256'])
            require(runner.oracle.elf_shape(self.case / 'input.elf') == pre['symbols'], 'Actual ELF symbol/landing/opcode identity')
            reference = runner.oracle.reference(pre_dir / 'spike.trace', pre['symbols'])
        else:
            pre = self.preflight(runner, 'preflight-manifest.json')
            pre_dir = runner.PRE
            reference = runner.reference(pre)
        from collect_csr_satp_sepc786 import primitive
        rows = primitive.parse_rows(self.work / 'commit_trace.csv')
        self.check('scalar', lambda: self.scalar(pre_dir, pre), 'Full scalar comparator against actual bound reference')
        ledger = runner.oracle.traps((pre_dir / 'spike.trace').read_text(), pre['symbols'])
        require(ledger == self.old['expected_traps'], 'Complete independent trap ledger identity')
        def native():
            if self.index == 791:
                return checker.architecture(rows, reference, pre['symbols'], (self.case / 'input.elf').read_bytes(), ledger)
            # Same reviewed pure workload adaptation as slot architecture(), but
            # explicit authenticated software counts instead of runner.PRE global.
            original = checker.original
            namespace = dict(original.architecture.__globals__, oracle=SimpleNamespace(
                GUARDS=original.oracle.GUARDS, validate=runner.oracle.validate))
            stats = pre['validation']
            fn = checker.rewrite(original.architecture, namespace,
                {866: stats['retired_instructions'], 226: stats['scalar_memory_accesses'], 6: 12},
                {'mis_guards': 'slot_guards', 'mis_handler': 'slot_handler',
                 'FULL_SCALAR_AND_SIX_TRAP_GOLD_EXACT': 'FULL_SCALAR_AND_TWELVE_TRAP_GOLD_EXACT'})
            return fn(rows, reference, pre['symbols'], (self.case / 'input.elf').read_bytes(), ledger)
        architecture = self.check('native', native, name + '.architecture pure predicates with explicit software authority')
        self.check('vector', self.zero_vectors, 'Original zero vector predicate')
        if self.index == 791:
            import scalar_misalign789_soc_width_adapter as wave
        else:
            wave = checker
        self.check('source_context', wave.source_proof, wave.__name__ + '.source_proof (unmodified)')
        converted = self.check('conversion', lambda: self.convert('scalar-misalign.vpd'), 'Pinned vpd2vcd')
        if architecture and converted and self.components['source_context']['status'] == 'PASS':
            self.check('wave', lambda: wave.wave_audit(Path(converted['vcd']), ledger, architecture['handlers'], rows[-1]['cycle']), wave.__name__ + '.wave_audit')

    def run_div(self):
        import collect_scalar_div_subnormal794 as checker
        import scalar_div_subnormal794_flush_v2 as wave
        runner = checker.runner
        pre = self.preflight(runner, 'preflight.json')
        scalar = self.check('scalar', lambda: self.scalar(runner, pre), 'Original full scalar comparator + scalar_exact')
        with (self.work / 'commit_trace.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        if scalar:
            self.check('native', lambda: checker.architecture(rows, pre, scalar), checker.__name__ + '.architecture')
        self.check('vector', self.zero_vectors, 'Original zero vector predicate')
        proof = self.check('source_context', runner.source_contract, runner.__name__ + '.source_contract (unmodified)')
        converted = self.check('conversion', lambda: self.convert('scalar-div-subnormal794.vpd'), 'Pinned vpd2vcd')
        if proof and converted:
            self.check('wave', lambda: wave.wave_audit(Path(converted['vcd']), proof, pre), wave.__name__ + '.wave_audit')

    def run_akv(self):
        import collect_akv_canonical_kfault as checker
        import collect_akv_canonical_kfault_epoch_offline as wave
        runner = checker.runner
        phase = self.old['phase']
        pre = self.bind_json(runner.PRE, self.old['preflight_seal'])
        self.bind(runner.elf_path(phase), self.plan['elf_sha256'])
        architecture = self.check('native', lambda: checker.architecture(self.work, self.out, pre['phases'][phase]['dut']['symbols'], phase), checker.__name__ + '.architecture')
        log = (self.out / 'runtime/run.vcs.log').read_text()
        perf = re.findall(r'(?m)^\[AKV_PERF\].*$', log)
        self.check('perf', lambda: checker.p.audit.runtime_perf('\n'.join(perf), 'gap71_akv_fault'), 'audit_gap71_custom.runtime_perf')
        self.check('source_context', wave.source_gate, wave.__name__ + '.source_gate (unmodified)')
        converted = self.check('conversion', lambda: self.convert('akv-canonical-kfault.vpd'), 'Pinned vpd2vcd')
        if architecture and converted and self.components['source_context']['status'] == 'PASS':
            self.check('wave', lambda: wave.wave_gate(Path(converted['vcd']), architecture['last_cycle'], phase, log), wave.__name__ + '.wave_gate')

    def finish(self):
        if self.components.get('conversion', {}).get('status') == 'PASS':
            self.check('probe_inventory', self.probe_inventory, 'Actual VCD declarations and honest old/current source-book comparison')
        for path, digest in self.inputs.items():
            require(sha(path) == digest, 'Audit input changed: ' + path)
        needed = {'execution', 'native', 'dispatch'}
        if self.index in (761, 771, 786, 788, 791, 792, 794):
            needed |= {'scalar', 'vector'}
        if self.index in (761, 789, 790):
            needed |= {'conversion', 'wave'}
        if self.index in (789, 790):
            needed |= {'source_context', 'perf'}
        if self.index == 771:
            needed |= {'stdout'}
        missing = sorted(name for name in needed if self.components.get(name, {}).get('status') != 'PASS')
        micro_pass = self.components.get('wave', {}).get('status') == 'PASS'
        purpose = {
            761: 'External AXI device read/data/drain is required; not emulated by Spike.',
            771: 'Internal natural backpressure/hold witness; numerical/FCSR correctness is checked independently.',
            782: 'Old pending word0/word1/hit13 stimulus witness; not architectural correctness gate.',
            785: 'Old pending/FIFO partial-capture recurrence witness; not architectural correctness gate.',
            786: 'Internal CSR issue/commit TID/ready/epoch witness; full actual scalar/CSR values checked separately.',
            788: 'Internal cause-CSR issue/commit TID/ready/epoch witness; actual WLRL matrix checked separately.',
            789: 'Required custom fault owner, drain, suppressed AXI, mapped retry and terminal evidence.',
            790: 'Required custom fault owner, drain, suppressed AXI, mapped retry and terminal evidence.',
            791: 'Internal LSU/CSR TID/cancel witness; six precise architectural trap frames and memory effects checked separately.',
            792: 'Internal allocation/flush slot/TID witness; twelve precise architectural trap frames checked separately.',
            794: 'Internal DIV/FMV issue/TID/exponent/rounding chain; all144 numerical/fflags/FCSR cells checked separately.',
        }[self.index]
        micro = dict(status='PASS' if micro_pass else 'CHECKER_REQUIRED', purpose=purpose,
                     required_for_functional=self.index in (761, 789, 790),
                     reason=None if micro_pass else self.components.get('source_context', self.components.get('wave', {})).get('reason', 'No safe current-context internal checker executed'),
                     old_internal_signal_absence_inferred=False, old_frozen_context_replaced=False)
        result = dict(index=self.index, status='CHECKER_REQUIRED' if missing else 'SEMANTIC_PASS_NOT_ADMITTED',
                      functional_status='CHECKER_REQUIRED' if missing else 'PASS', micro_witness=micro,
                      functional_requirements=sorted(needed),
                      missing_components=missing, components=self.components, input_pins=self.inputs,
                      simulation_started=False, old_collector_executed=False, old_context_fabricated=False,
                      coverage_admitted=False, full_scalar_ISA_claimed=self.index not in (782, 785, 789, 790) and not missing,
                      external_AXI_waveform_claimed=self.index in (761, 789, 790) and not missing)
        save(self.out / 'audit.json', result)
        return dict(index=self.index, status=result['status'], functional_status=result['functional_status'],
                    micro_witness=micro['status'], missing_components=missing, report=str(self.out / 'audit.json'))

    def probe_inventory(self):
        import audit_gap115_axi_v2 as parser
        # An inventory does not sample edges. AKV captures its gated clk_i only,
        # so requiring the uncaptured TB clk here would be a false missing field.
        parse = FunctionType(parser.vcd.__code__, dict(parser.vcd.__globals__, ROOT='ara_tb', WIDTHS={}))
        _, declarations = next(iter(parse(self.out / 'probe.vcd')))
        current = self.bind_json(BUILD / 'build-source-pins.json')
        historical_path = ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
        historical = self.bind_json(historical_path, '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
        relevant = ['hardware/deps/cva6/core/' + name for name in (
            'csr_regfile.sv', 'csr_buffer.sv', 'cva6.sv', 'cva6_rvfi.sv', 'load_unit.sv',
            'load_store_unit.sv', 'store_unit.sv', 'store_buffer.sv', 'controller.sv',
            'scoreboard.sv', 'issue_stage.sv', 'issue_read_operands.sv', 'ex_stage.sv',
            'fpu_wrap.sv', 'include/ariane_pkg.sv', 'include/riscv_pkg.sv',
            'include/build_config_pkg.sv', 'include/cv64a6_imafdcv_sv39_config_pkg.sv')]
        differences = []
        for relative in relevant:
            path = str(ROOT / relative)
            if historical.get(path) != current.get(path):
                actual = sha(self.bind(path, current[path]))
                differences.append(dict(path=path, historical_sha256=historical.get(path),
                                        current_build_sha256=current[path], actual_sha256=actual))
        return dict(status='DECLARATIONS_ONLY_NOT_TRANSACTION_QUALIFICATION', declarations=declarations,
                    historical_vs_current_observer_source_differences=differences,
                    observed_packed_parents={n: v for n, v in declarations.items() if v['width'] in (13, 136, 188, 203, 207, 438, 876)},
                    deleted_internal_signals_inferred=False,
                    next_step='If internal witness is needed, derive offsets/producer and sampling rules from the actual current build source book, then audit this captured VCD. Do not replace the old frozen book or image globals. Rerun only a specific case if a required signal is proven absent.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--cases', type=int, nargs='+', default=CASES, choices=CASES)
    args = parser.parse_args()
    output = args.output.absolute()
    require(not output.exists() and output.parent.resolve().is_relative_to(ROOT / 'verification/out'), 'Fresh independent verification/out output required')
    install_guard(output)
    output.mkdir()
    save(output / 'policy.json', dict(simulation_permitted=False, subprocess_allowlist=[str(CONVERTER)],
                                    writes_confined_to=str(output), old_manifest_is_execution_context=False,
                                    python_executable=sys.executable, python_version=sys.version, python_path=sys.path))
    rows = []
    for index in args.cases:
        audit = CaseAudit(index, output)
        if audit.check('execution', audit.common, 'Actual current replay receipt/ELF/frozen Tcl/log/trace') is not None:
            fn = audit.run_simple if index in (761, 771) else audit.run_qbs if index in (782, 785) else audit.run_csr if index in (786, 788) else audit.run_akv if index in (789, 790) else audit.run_misalign if index in (791, 792) else audit.run_div
            audit.check('dispatch', fn, 'Independent pure semantic components; no old collect')
        rows.append(audit.finish())
    modules = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename and Path(filename).suffix == '.py' and Path(filename).is_file() and (
                Path(filename).resolve().is_relative_to(ROOT / 'verification') or 'elftools' in filename or '/yaml/' in filename):
            modules[str(Path(filename).resolve())] = sha(filename)
    save(output / 'checker-code-pins.json', modules)
    tests = Path(__file__).resolve().parents[1] / 'tests/test_audit_probe_semantics_20261015.py'
    save(output / 'audit-test-pin.json', dict(path=str(tests), sha256=sha(tests)))
    save(output / 'audit.json', dict(cases=rows, simulation_runs=0, coverage_admitted=False,
                                   checker_code_pins=str(output / 'checker-code-pins.json'),
                                   semantic_pass=sum(r['status'] == 'SEMANTIC_PASS_NOT_ADMITTED' for r in rows),
                                   checker_required=sum(r['status'] == 'CHECKER_REQUIRED' for r in rows)))
    print(json.dumps(rows, indent=2), flush=True)


if __name__ == '__main__':
    main()

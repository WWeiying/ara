#!/usr/bin/env python3
"""Offline current-run system architecture audit; no simulation or admission.

Historical manifests authorize software/reference identity only. No historical
PASS, process exit, probe marker or coverage gain is an architecture oracle.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys
import traceback
from types import FunctionType, SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'verification'), str(Path(__file__).resolve().parent)]
CASES = (705, 707, 714, 716, 732, 734, 735, 738, 742, 768, 770,
         772, 773, 778, 779, 781, 787, 793)
RUNS = ROOT / 'verification/out/full-regression-20261015-01/extensions'
BUILD = ROOT / 'verification/out/full-regression-build-20261015-01'
DEFAULT_OUT = ROOT / 'verification/out/pending-system-audit-20261016-01'
ORACLES = {
    705: 'admit_gap97_offline', 707: 'admit_gap99_offline',
    714: 'check_gap100_runtime + replay_gap100_platform_matched + audit_gap100_trap_ledger',
    716: 'check_cache_port1_sv39_offline', 732: 'qualify_store_fault_flush_terminal',
    734: 'qualify_readonly_csr_terminal', 735: 'qualify_sv39_masked_unit_fault_terminal_v3',
    738: 'qualify_csr_frozen_counter_terminal', 742: 'postprocess_gap114_traps_v2',
    768: 'collect_tlb_asid_matrix', 770: 'qualify_sv39_alias770_known_tail',
    772: 'collect_sv39_fault_alternating771_csr_return', 773: 'collect_itlb_asid_exec_bulk_csr',
    778: 'collect_btb_target_ring_v3', 779: 'collect_dtlb_ppn_swap1200_schema',
    781: 'collect_dtlb_permissions780_scalar', 787: 'collect_scalar_entropy64',
    793: 'collect_itlb_ppn_aba_v2',
}
HASH_CACHE = {}
FUNCTIONAL_REQUIRED = ('source_binding', 'execution', 'runtime_logs',
                       'scalar_comparator', 'original_architecture')
OPTIONAL_PHYSICAL = frozenset(('fault_axi_safety',))
MASKED_FUNCTIONAL_PREDICATES = (
    'complete_scalar_differential_and_fault_CSR_return_alignment',
    'complete_compressed_memory', 'independent_full_snapshot_mask_tail_guards_and_retry',
    'exact_native_owner_transaction_and_request_exception_conservation',
    'exact_two_backend_allocations_and_completions',
    'current_compiled_grant_visibility_and_empty_prefix_completion_semantics',
    'all_128_maintenance_bytes_equal_unchanged_independent_seed',
    'zero_accepted_VLDU_grants_for_fault_owner',
    'exact_tracer_load_page_fault_and_ecall',
    'full_105_writer_13321_byte_vector_comparison_with_zero_unknown_or_skipped_bytes',
)


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def guard_writes(output):
    def inside(path):
        return isinstance(path, (str, bytes, os.PathLike)) and Path(os.fsdecode(path)).resolve().is_relative_to(output)

    def guard(event, args):
        if event == 'open':
            path, mode, flags = args
            if (mode and any(c in mode for c in 'wax+')) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                require(inside(path), 'Write outside fresh output: ' + str(path))
        elif event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.utime'):
            require(inside(args[0]), 'Mutation outside fresh output')
        elif event in ('subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn', 'os.fork',
                       'os.rename', 'os.link', 'os.symlink'):
            raise PermissionError('Offline audit forbids process execution and relinking')
    sys.addaudithook(guard)


def functional_required(gates):
    # Only a named physical claim can be optional. A false flag cannot waive a
    # mandatory oracle, known physical failure, or unknown newly added gate.
    extra = {name for name, row in gates.items()
             if name not in OPTIONAL_PHYSICAL or row.get('required_for_functional') is not False
             or row.get('status') not in ('NOT_MEASURED', 'PASS')}
    return sorted(set(FUNCTIONAL_REQUIRED) | extra)


def decision(gates):
    states = [gates.get(name, {}).get('status', 'CHECKER_REQUIRED') for name in functional_required(gates)]
    return 'FAIL' if 'FAIL' in states else 'PASS' if all(s == 'PASS' for s in states) else 'CHECKER_REQUIRED'


def current_masked_source_contract(texts):
    """Current compiled path: grant visibility and empty-prefix completion."""
    anchors = {
        'hardware/tb/ara_commit_monitor.sv': (
            'if(wb_valid_i[lane][source])begin',
            'cycle_q,uop_arch_seq_q[id],id,lane,source,',
            'wb_be_i[lane][source],wb_wdata_i[lane][source],NrLanes,VLEN);'),
        'hardware/src/lane/operand_requester.sv': (
            'verify_wb_valid_o={ldu_result_gnt,sldu_result_gnt,masku_result_gnt,mfpu_result_gnt_o,alu_result_gnt_o};',
            'verify_wb_be_o[3]=sldu_result_be;', 'verify_wb_be_o[4]=ldu_result_be;',
            'assignldu_result_final_gnt_o=ldu_result_gnt;'),
        'hardware/src/ara_system.sv': (
            'assignverify_wb_valid[lane]=i_ara.gen_lanes[lane].i_lane.verify_wb_valid_o;',
            '.wb_valid_i(verify_wb_valid)', '.wb_be_i(verify_wb_be)'),
        'hardware/src/vlsu/vldu.sv': (
            "if(vrf_word_byte_cnt_q=='0)beginldu_ex_state_d=WAIT_RESULT_QUEUE;endelseif(!result_queue_full)begin",
            "if(result_queue_cnt_d=='0&&!(|result_queue_valid_d)&&(&result_final_gnt_d))begin",
            'ldu_result_req_o[lane]=result_queue_valid_q[result_queue_read_pnt_q][lane];',
            "pe_resp_d.vinsn_done[vinsn_commit.id]=1'b1;", "load_complete_o=1'b1;"),
        'hardware/src/vlsu/addrgen.sv': (
            "axi_ar_valid_o=1'b0;", 'if((mmu_valid_i&&!mmu_exception_i.valid)||!en_ld_st_translation_i)begin:paddr_valid',
            "is_exception:1'b1", 'addrgen_exception_vstart_d=pe_req_q.vl-(axi_addrgen_q.len>>axi_addrgen_q.vew);'),
    }
    for path, tokens in anchors.items():
        text = re.sub(r'\s+', '', re.sub(r'/\*.*?\*/|//[^\n]*', '', texts[path], flags=re.S))
        require(all(token in text for token in tokens), 'Current compiled source semantics differ: ' + path)
    return dict(accepted_grants_logged_even_when_BE_zero=True, sources=dict(SLDU=3, VLDU=4),
                empty_prefix_does_not_enqueue_dummy_result=True,
                completion_requires_empty_result_queue_and_final_grants=True,
                translation_gated_AR_source_invariant=True, actual_AXI_transactions_observed=False)


def current_masked_native_identity(activity, rows):
    """Original mathematical seed oracle, current exact 16-row no-op shape."""
    import qualify_sv39_masked_unit_fault_terminal_v2 as original
    from ara_verify import vector_commit as vc
    require(activity.instruction == original.p.WORDS['smuf_masked_load'] and
            activity.allocations == activity.completions == 2 and activity.use_vd is True and
            (activity.vd, activity.eew, activity.vl, activity.vstart) == (8, 0, 17, 0), 'Exact masked fault activity required')
    control = [r for r in rows if r['event'] != 'write']
    require([r['event'] for r in control] == ['alloc', 'done', 'alloc', 'done'] and
            [int(r['vl']) for r in control] == [128, 128, 17, 17], 'Exact maintenance/load ownership required')
    require(all(int(r['arch_seq']) == 243 and int(r['vid']) == 0 and int(r['insn'], 16) == activity.instruction and
                (int(r['use_vd']), int(r['vd']), int(r['eew']), int(r['vstart'])) == (1, 8, 0, 0) and
                (int(r['nr_lanes']), int(r['vlen_bits'])) == (4, 1024) for r in rows), 'Current exact owner/shape differs')
    begin, end, load_begin, load_end = [int(r['cycle']) for r in control]
    require(begin <= end < load_begin <= load_end, 'Overlapping maintenance/load ownership')
    writes = activity.writes
    require(len(writes) == len([r for r in rows if r['event'] == 'write']) == 16 and
            all(w.source == 3 and w.arch_seq == 243 and w.vid == 0 and w.instruction == activity.instruction and
                w.eew == 0 and w.be == w.known_be == 255 and begin <= w.cycle <= end for w in writes) and
            {(w.addr, w.lane) for w in writes} == {(addr, lane) for addr in range(32, 36) for lane in range(4)},
            'Exactly 16 known maintenance writes and no VLDU grant required')
    actual = vc._architectural_bytes(writes, 4, 1024)
    expected = {(8, byte): (original.p.word(1, byte // 4, False) >> (8 * (byte % 4))) & 255 for byte in range(128)}
    require(set(actual) == set(expected) and all(actual[k][0] == value for k, value in expected.items()),
            'Every actual maintenance byte must equal independent seed identity')
    return dict(status='CURRENT_COMPILED_MASKED_FAULT_KNOWN_IDENTITY_NO_LOAD_GRANTS',
                arch_seq=243, maintenance_known_bytes=128, load_accepted_bytes=0,
                accepted_VLDU_grant_rows=0, activity_signature=original.signature(activity),
                case_only=True, zero_write_fault_claimed=False,
                maintenance_interval=[begin, end], no_op_load_interval=[load_begin, load_end],
                old_zero_BE_rows_required=False, all_actual_write_bytes_checked=True)


class Audit:
    def __init__(self, index, output):
        require(index in CASES, 'Outside disjoint system scope')
        self.index = index
        self.case = RUNS / f'e{index:04d}'
        self.work = self.case / 'work'
        self.out = output / f'e{index:04d}'
        self.out.mkdir()
        self.pins = {}
        self.stats = {}
        self.gates = {}
        self.identity = None
        self.bind(Path(__file__).resolve())

    def bind(self, path, expected=None):
        path = Path(path).absolute()
        require(path.resolve() == path and not path.is_symlink(), 'Aliased input: ' + str(path))
        st = path.stat()
        stamp = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        if str(path) not in self.pins:
            cached = HASH_CACHE.get(str(path))
            digest = cached[1] if cached and cached[0] == stamp else sha(path)
            after = path.stat()
            require((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) == stamp,
                    'Input changed while hashing: ' + str(path))
            self.pins[str(path)] = digest
            self.stats[str(path)] = stamp
            HASH_CACHE[str(path)] = (stamp, digest)
        else:
            require(self.stats[str(path)] == stamp, 'Input drift: ' + str(path))
        require(expected is None or expected == self.pins[str(path)], 'Input pin mismatch: ' + str(path))
        return path

    def read(self, path, expected=None):
        path = self.bind(path, expected)
        value = json.loads(path.read_text())
        self.bind(path)
        return value

    def old_bind(self, path):
        path = Path(path).absolute()
        expected = self.old['pins'].get(str(path))
        require(expected is not None, 'Original manifest does not authorize reference: ' + str(path))
        return self.bind(path, expected)

    def gate(self, name, fn, numerical=False):
        try:
            value = fn()
            row = dict(status='PASS', result=value)
        except Exception as e:
            # An adapter exception or missing observability is not a DUT failure.
            mismatch = isinstance(e, (ValueError, AssertionError)) and numerical
            row = dict(status='FAIL' if mismatch else 'CHECKER_REQUIRED',
                       reason=f'{type(e).__name__}: {e}', traceback=traceback.format_exc())
        self.gates[name] = row
        save(self.out / (name + '.json'), row)
        return row.get('result')

    def setup(self):
        self.plan = self.read(self.case / 'plan.json')
        require(self.plan['index'] == self.index and self.plan['work'] == str(self.work), 'Current plan identity differs')
        self.old = self.read(self.plan['command_source'], self.plan['pins'][self.plan['command_source']])
        require(self.old['command'] == self.plan['original_command'], 'Original command provenance differs')
        self.bind(self.case / 'input.elf', self.plan['elf_sha256'])
        elf = Path(next(x.split('=', 1)[1] for x in self.plan['original_command'] if x.startswith('+PRELOAD=')))
        self.bind(elf, self.plan['elf_sha256'])
        self.pre_dir = elf.parent
        pp = self.old.get('preflight')
        if isinstance(pp, str):
            pp = Path(pp)
        else:
            names = ('successor-preflight.json', 'preflight-manifest.json', 'preflight.json')
            pp = next(self.pre_dir / n for n in names if str(self.pre_dir / n) in self.old['pins'])
        self.pre = self.read(self.old_bind(pp))
        self.symbols = self.pre['symbols']
        self.spike = self.old_bind(self.pre_dir / 'spike.trace')
        if self.index == 714:
            # Original specialized workflow replaced the CLINT-enabled software
            # reference, not DUT values. Reuse its sealed raw reference only.
            import audit_gap100_trap_ledger as ledger
            successor = self.read(ledger.REFERENCE / 'reference-result.json', ledger.REFERENCE_SEAL)
            require(successor['input_elf_sha256'] == self.plan['elf_sha256'], 'Platform reference ELF differs')
            self.launch_spike = self.spike
            path = Path(successor['new_spike_trace'])
            self.spike = self.bind(path, successor['pins'][str(path)])
        for name in ('commit_trace.csv', 'vector_trace.csv', 'trace_hart_0.log'):
            self.bind(self.work / name)
        with (self.work / 'commit_trace.csv').open() as f:
            self.rows = list(csv.DictReader(f))
        with (self.work / 'vector_trace.csv').open() as f:
            self.vectors = list(csv.DictReader(f))
        self.bind(self.work / 'commit_trace.csv')
        self.bind(self.work / 'vector_trace.csv')
        return dict(preflight=str(pp), reference=str(self.spike), original_results_reused=False)

    def execution(self):
        r = self.read(self.case / 'simulation-exit.json')
        require(r['executed'] is True and type(r['returncode']) is int and r['returncode'] == 0 and
                r['timed_out'] is False and r['cancelled'] is False, 'Current successful execution receipt required')
        require(r['command'] == self.plan['command'] and r['cwd'] == str(self.work) and
                type(r['pid']) is int and r['pid'] > 0 and r['finished'] > r['started'], 'Current command/cwd/pid/time differs')
        image = self.read(BUILD / 'build-image.json')
        source_pins = self.read(BUILD / 'build-source-pins.json')
        for rel in ('hardware/tb/ara_commit_monitor.sv', 'hardware/deps/cva6/core/cva6_rvfi.sv'):
            path = ROOT / rel
            self.bind(path, source_pins[str(path)])
        exe = BUILD / 'sim/simv'
        require(self.plan['command'][0] == str(exe), 'Not the actual current build')
        self.bind(exe, image[str(exe)])
        options = dict(x[1:].split('=', 1) for x in self.plan['command'] if x.startswith('+') and '=' in x)
        require(options['PRELOAD'] == str(self.case / 'input.elf') and
                options['COMMIT_TRACE'] == str(self.work / 'commit_trace.csv') and
                options['VECTOR_TRACE'] == str(self.work / 'vector_trace.csv'), 'Current raw output binding differs')
        self.identity = dict(validated=True, receipt=r, build_image_sha256=self.pins[str(exe)],
                             plan=str(self.case / 'plan.json'), work=str(self.work))
        return self.identity

    def logs(self):
        from ucli_runtime_log_20261015 import iter_runtime_lines
        from ara_verify.contract import check_contract_log, parse_contract_summary
        from ara_verify.runner import FAIL_RE
        sources = {str(p): self.bind(p, self.plan['pins'][str(p)]).read_text()
                   for p in sorted((self.case / 'ucli').glob('*.tcl'))}
        runtime = self.out / 'runtime'
        runtime.mkdir()
        self.log_texts = []
        summaries = []
        for raw in (self.case / 'console.log', self.work / 'run.vcs.log'):
            self.bind(raw)
            with raw.open(errors='replace') as f:
                text = ''.join(iter_runtime_lines(f, sources))
            self.bind(raw)
            (runtime / raw.name).write_text(text)
            require(not FAIL_RE.search(text) and not re.search(r'Fatal:|Error:|Fatal-\[|Error-\[|UCLI_ERROR|_ERROR\b', text),
                    'Runtime simulator/protocol error in ' + str(raw))
            require(text.splitlines().count('Core Test *** SUCCESS ***') == 1, 'Exactly one actual firmware success required')
            counts = [parse_contract_summary(x.strip()) for x in text.splitlines() if '[ARA_CONTRACT]' in x]
            require(len(counts) == 1 and counts[0] is not None and
                    all(counts[0][k] == 0 for k in ('protocol_errors', 'outstanding', 'req_stalled', 'resp_stalled')),
                    'Exact complete clean terminal contract required')
            summaries.append(counts[0])
            if counts[0]['requests']:
                require(not check_contract_log(runtime / raw.name), 'Original contract checker rejected actual runtime log')
            else:
                require(all(value == 0 for value in counts[0].values()), 'Not an exact zero-CVX contract')
            self.log_texts.append(text)
        require(summaries[0] == summaries[1], 'Runtime contract copies differ')
        self.summary = summaries[0]
        self.runtime = runtime
        return dict(summary=self.summary, source_echoes_removed_only_by_exact_frozen_Tcl=True,
                    semantic_acceptance_inferred=False, UVM_final_report_claimed=False)

    def compare(self):
        from ara_verify.spike_trace import compare_commit_prefix
        self.scalar = compare_commit_prefix(self.spike, self.work / 'commit_trace.csv', 0x80000000,
            terminal_tohost_address=self.symbols['tohost'], rvfi_store_data_layout='unshifted',
            **(dict(rtl_exception_log=self.work / 'trace_hart_0.log') if self.index in (732, 735, 772) else {}))
        save(self.out / 'scalar-comparison.json', self.scalar)
        if self.scalar.get('mismatch') is not None:
            self.gates['scalar_numerical_mismatch'] = dict(status='FAIL', reason='Actual current scalar differential mismatch',
                                                         result=self.scalar['mismatch'])
        from ara_verify.spike_trace import parse_spike_commits
        self.reference = parse_spike_commits(self.spike)
        return self.scalar

    def vector(self, **kwargs):
        from ara_verify.vector_commit import compare_vector_commits
        value = compare_vector_commits(self.spike, self.work / 'commit_trace.csv', self.work / 'vector_trace.csv',
                                       0x80000000, **kwargs)
        save(self.out / 'vector-comparison.json', value)
        if value.get('first_mismatch'):
            self.gates['vector_numerical_mismatch'] = dict(status='FAIL', result=value['first_mismatch'])
        return value

    def zero(self):
        import admit_gap99_offline as z
        z.vector_zero(self.work / 'vector_trace.csv')
        return dict(zero_vector_writes=True)

    def architecture(self):
        i, s, q, r, v = self.index, self.symbols, self.pre, self.rows, self.vectors
        def mod(name):
            module = importlib.import_module(name)
            self.bind(Path(module.__file__).resolve())
            return module
        if i == 705:
            m = mod('admit_gap97_offline')
            rows = m.commit_rows(self.work / 'commit_trace.csv')
            arch = m.architecture_audit(rows, m.elf_metadata((self.case / 'input.elf').read_bytes()))
            handshake = m.handshake_audit(rows, arch)
            require(self.summary['requests'] == self.summary['responses'] == handshake['requests'] and
                    self.summary['exceptions'] == self.summary['mmu_request_cycles'] == 0,
                    'Original CSR handshake population differs from terminal contract')
            m.validate_scalar(self.scalar, arch['scalar_retirements'])
            self.zero()
            m.validate_vector(self.vector())
            return arch
        if i == 707:
            m = mod('admit_gap99_offline')
            rows = m.commit_rows(self.work / 'commit_trace.csv')
            arch = m.architecture(rows, m.elf_metadata((self.case / 'input.elf').read_bytes(), s))
            m.common.validate_scalar(self.scalar, len(rows))
            self.zero()
            m.common.validate_vector(self.vector())
            for name in ('console.log', 'run.vcs.log'):
                m.zero_contract(self.runtime / name)
            return arch
        if i == 714:
            m = mod('check_gap100_runtime')
            import audit_gap100_trap_ledger as ledger
            import replay_gap100_platform_matched as platform
            rows = m.commit_rows(self.work / 'commit_trace.csv')
            dut = m.retired_commits(rows)
            ref = platform.from_entry_to_terminal(self.reference, s)
            require(platform.state_scope(ref) == platform.state_scope(dut), 'Platform-matched no-CLINT CSR state scope differs')
            differences = platform.differences.differences(ref, dut)
            require(not differences and m.scalar_qualified(self.scalar, rows), 'Original full GAP100 scalar contract rejected')
            observation = m.software.validate(dut, s)
            from elftools.elf.elffile import ELFFile
            with (self.case / 'input.elf').open('rb') as f:
                symbols = ELFFile(f).get_section_by_name('.symtab')
                matches = symbols.get_symbol_by_name('g100_return')
                require(len(matches or []) == 1, 'Unique compiled return symbol required')
                returns = matches[0]['st_value']
            traps = ledger.audit(rows, (self.work / 'trace_hart_0.log').read_text(), dict(s, g100_return=returns))
            self.zero()
            m.common.validate_vector(self.vector())
            for name in ('console.log', 'run.vcs.log'):
                m.zero.zero_contract(self.runtime / name)
            return dict(observation=observation, traps=traps, all_instruction_differences=differences,
                        platform_reference=str(self.spike), launch_reference=str(self.launch_spike), normalization_performed=False)
        if i == 716:
            m = mod('check_cache_port1_sv39_offline')
            m.validate_scalar(self.scalar)
            arch = m.architecture(m.rows(self.work / 'commit_trace.csv'), s)
            self.zero()
            m.common.validate_vector(self.vector())
            for name in ('console.log', 'run.vcs.log'):
                m.zero.zero_contract(self.runtime / name)
            return arch
        if i == 732:
            m = mod('qualify_store_fault_flush_terminal')
            proof = self.read(self.old_bind(self.pre_dir / 'linked-proof.json'))
            control = m.lifecycle(r, v, s, proof['fault_opcode'], proof['recovery_opcode'])
            signature = m.observed(r, s, self.pre_dir)
            m.scalar_exact(self.scalar, m.common.reference_counts(self.reference, s), s)
            vec = self.vector()
            require(vec['status'] == 'PASS' and vec['compared_bytes'] == 272 and
                    vec['trapped_requests'] == [control['fault_arch_seq']] and
                    vec['compared_instructions'] == sum(bool(c.vector_writes) for c in self.reference) and
                    all(vec[k] == 0 for k in ('skipped_unknown_bytes', 'non_bit_exact_instructions', 'unobservable_instructions')) and
                    not vec['first_mismatch'] and not vec['incomplete_requests'] and not vec['unretired_requests'],
                    'Original full store-fault vector contract rejected')
            require(self.summary['requests'] == self.summary['responses'] == control['requests'] and
                    self.summary['exceptions'] == 1, 'Store-fault terminal request/exception count differs')
            pcs = re.findall(r'^Exception @\s+\d+, PC: ([0-9a-fA-F]+),.*$', (self.work / 'trace_hart_0.log').read_text(), re.M)
            require([int(pc, 16) for pc in pcs] == [s['sff_fault']], 'Exact store-fault tracer exception differs')
            from ara_verify import vector_commit as vc
            lanes, bits, activities = vc._parse_vector_trace(self.work / 'vector_trace.csv')
            starts, retires, rejected = vc._parse_architecture_mapping(self.work / 'commit_trace.csv')
            mapping = vc._map_spike_commits(vc._map_architecture_retires(starts, retires, rejected), self.reference)
            require((lanes, bits) == (4, 1024) and rejected == {control['fault_arch_seq']}, 'Native store-fault geometry differs')
            wanted = {seq: self.reference[n] for seq, n in mapping.items() if self.reference[n].vector_writes}
            require({seq for seq, a in activities.items() if a.writes} == set(wanted), 'Extra/missing native writer')
            for seq, c in wanted.items():
                seen = set()
                for w in activities[seq].writes:
                    require(w.source == 4 and w.be & ~w.known_be == 0, 'Unknown/non-VLDU writer')
                    for byte in range(8):
                        if w.be & (1 << byte):
                            key = w.addr, w.lane, byte
                            require(key not in seen, 'Duplicate accepted native byte')
                            seen.add(key)
                actual = vc._architectural_bytes(activities[seq].writes, 4, 1024)
                require({k: value for k, (value, _) in actual.items()} ==
                        {(reg, byte): (value >> (8 * byte)) & 255 for reg, value in c.vector_writes.items()
                         for byte in range(16 if reg == 4 else 128)}, 'Complete native seed bytes differ')
            return dict(lifecycle=control, signature=signature)
        if i == 734:
            m = mod('qualify_readonly_csr_terminal')
            control = m.lifecycle(r, v, s)
            memory = m.observed(r, s, self.pre_dir)
            m.logs(*self.log_texts, control)
            trap = m.tracer_exact((self.work / 'trace_hart_0.log').read_text(), r, s)
            m.scalar_exact(self.scalar, m.common.reference_counts(self.reference, s), memory)
            m.native_exact(self.vector(), control, self.reference, self.work)
            return dict(lifecycle=control, memory=memory, trap=trap)
        if i == 735:
            return self.masked_fault()
        if i == 738:
            m = mod('qualify_csr_frozen_counter_terminal')
            m.scalar_gate(self.scalar)
            ref = m.primitives.reference_prefix(self.reference, s['tohost'])
            arch = m.architecture(m.primitives.parse_rows(self.work / 'commit_trace.csv'), ref, s,
                m.elf_file_bytes((self.case / 'input.elf').read_bytes(), s['counter_guards'], 16))
            self.zero()
            m.primitives.vector_gate(self.vector())
            for text in self.log_texts:
                m.primitives.log_gate(text)
            return arch
        if i == 742:
            m = mod('postprocess_gap114_traps_v2')
            traps = m.traps_exact(r, s)
            memory = {}
            for row in r:
                if row['event'] == 'retire':
                    store = m.run.shared.scalar_store(row)
                    if store:
                        memory.update({store[0] + n: b for n, b in enumerate(store[1])})
            def value(name, offset=0, size=8):
                return int.from_bytes(bytes(memory[s[name] + offset + n] for n in range(size)), 'little')
            m.run.oracle(value, s)
            m.scalar_exact(self.scalar, q['counts'])
            vec = self.vector()
            require(vec['status'] == 'PASS' and vec['compared_instructions'] == 32 and vec['compared_bytes'] == 4096 and
                    all(vec[k] == 0 for k in ('skipped_unknown_bytes', 'non_bit_exact_instructions', 'unobservable_instructions')) and
                    not vec['incomplete_requests'] and not vec['unretired_requests'] and not vec['first_mismatch'],
                    'Original GAP114 complete vector contract rejected')
            return traps
        if i == 768:
            m = mod('collect_tlb_asid_matrix')
            for text in self.log_texts:
                m.console_gate(text)
            m.pre.architecture.scalar_exact(self.scalar, q['counts'])
            require(m.pre.validate(m.native_reference(r), s) == q['counts'], 'Original native PTE/CSR/guards/96 reads differ')
            self.zero()
            return q['counts']
        if i == 770:
            m = mod('qualify_sv39_alias770_terminal')
            successor = mod('qualify_sv39_alias770_known_tail')
            book = self.read(ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json',
                             '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
            dispatch = self.bind(successor.DISPATCH, book[str(ROOT / 'hardware/src/ara_dispatcher.sv')])
            successor.source_contract(dispatch.read_text())
            control = m.lifecycle(r, v, s)
            observed = m.observed(r, s)
            m.tracer_exact((self.work / 'trace_hart_0.log').read_text(), r, s)
            m.logs_exact(self.log_texts, control)
            m.scalar_exact(self.scalar, self.reference, s)
            successor.scalar_memory_exact(r, self.reference)
            successor.vector_exact(self.vector(), self.reference)
            from ara_verify import vector_commit as vc
            starts, retires, rejected = vc._parse_architecture_mapping(self.work / 'commit_trace.csv')
            require(not rejected, 'Unexpected rejected vector request')
            mapping = vc._map_spike_commits(vc._map_architecture_retires(starts, retires, rejected), self.reference)
            lanes, bits, activities = vc._parse_vector_trace(self.work / 'vector_trace.csv')
            require((lanes, bits) == (4, 1024), 'Native geometry differs')
            native = successor.native_exact(activities, mapping, self.reference)
            return dict(lifecycle=control, observed=observed, native=native)
        if i == 772:
            return self.alternating_fault()
        if i in (773, 793):
            return self.itlb()
        if i == 778:
            m = mod('collect_btb_target_ring_v3')
            m.prior.scalar_exact(self.scalar, dict(q['counts'], ara_trap_events=1))
            gold = m.original.native_gold(r, q)
            control = m.lifecycle(r, v, self.summary)
            ref = m.original.pre.interval(self.reference)
            m.original.vector_gate(self.vector(), ref)
            return dict(gold=gold, lifecycle=control)
        if i == 779:
            m = mod('collect_dtlb_ppn_swap1200_schema')
            native = mod('collect_dtlb_ppn_swap1200')
            ref = self.reference
            require(native.pre.validate(ref, s) == q['counts'], 'Frozen full reference/gold differs')
            memory = native.memory_gate(r, ref)
            require(tuple(memory[k] for k in ('retired', 'compressed', 'uncompressed', 'loads', 'stores', 'total')) ==
                    (191475, 16823, 2248, 8553, 10518, 19071), 'Exact original full memory population differs')
            counts = {k: q['counts'][k] for k in ('matched_instructions', 'matched_scalar_writes',
                      'matched_floating_writes', 'matched_scalar_memory_accesses')}
            native.pre.shared.architecture.scalar_exact(self.scalar, counts)
            native.logs(*self.log_texts)
            self.zero()
            m.vector_zero(self.vector())
            return memory
        if i == 781:
            m = mod('collect_dtlb_permissions780_scalar')
            memory = m.architecture_gate(r, self.reference, s)
            expected = {k: q['counts'][k] for k in ('matched_instructions', 'matched_scalar_writes',
                        'matched_floating_writes', 'matched_scalar_memory_accesses')}
            m.runner.software.p.shared.architecture.scalar_exact(self.scalar, expected)
            require(self.scalar['ara_trap_events'] == 0, 'Scalar trap observability contract differs')
            m.logs(*self.log_texts, s)
            m.zero_schema.vector_zero(self.vector())
            return memory
        if i == 787:
            m = mod('collect_scalar_entropy64')
            ref = m.run.reference_interval(self.reference, s)
            counts = m.architecture.reference_counts(ref, s)
            require(counts == self.old['reference_interval_counts'], 'Frozen full prefix counts differ')
            m.architecture.scalar_exact(self.scalar, counts)
            native = m.native_frame(r, s)
            initial = m.initial_and_dominance(self.case / 'input.elf', r, s)
            control = m.lifecycle(r, v, self.log_texts[0])
            require(m.lifecycle(r, v, self.log_texts[1]) == control, 'Runtime lifecycle copies differ')
            return dict(native=native, initialization=initial, lifecycle=control)
        raise NotImplementedError(i)

    def masked_fault(self):
        import qualify_sv39_masked_unit_fault_terminal_v3 as v3
        from ara_verify import vector_commit as vc
        m, v2 = v3.v2.old, v3.v2
        scope_sources = {}
        for module in (m, v2, v3):
            path = self.bind(Path(module.__file__).resolve())
            text = path.read_text()
            require(not re.search(r'\b(?:axi|vpd|fsdb|waveform)\b', text, re.I),
                    'Original 735 scope changed: physical gate requires source review')
            scope_sources[str(path)] = self.pins[str(path)]
        original_scope = dict(physical_AXI_measurement_required=False,
            source_pins=scope_sources,
            basis='Original collect() checks scalar/RVC, owner/lifecycle, trap CSRs/returns, independent memory/guards and full native vector bytes. v2/v3 replace only the case-specific identity predicate/tuple ownership. No AXI or waveform measurement gate exists.',
            mandatory_predicates=list(MASKED_FUNCTIONAL_PREDICATES),
            only_superseded_physical_shape='Four zero-BE load grant rows replaced by current compiled completed-zero-grant proof; no gold/accepted-byte relaxation.')
        save(self.out / 'original-functional-scope.json', original_scope)
        s = self.symbols
        ref, partial = m.reference_prefix(self.reference, s)
        m.scalar_gate(self.scalar, ref, s, partial)
        memory = m.compressed_audit(self.rows, ref, partial, s)
        gold = m.observed_gold(self.rows, s)
        control = m.lifecycle(self.rows, self.vectors, s)
        require(self.summary['requests'] == self.summary['responses'] == control['requests'] and
                self.summary['exceptions'] == 1, 'Original masked fault request/exception conservation differs')
        exceptions = Counter(int(pc, 16) for pc in re.findall(r'^Exception @\s+\d+, PC: ([0-9a-fA-F]+),',
                             (self.work / 'trace_hart_0.log').read_text(), re.M))
        require(exceptions == Counter((s['smuf_masked_load'], s['smuf_ecall'])), 'Exact masked fault tracer differs')
        for text in self.log_texts:
            m.log_gate(text)
        lanes, bits, activities = vc._parse_vector_trace(self.work / 'vector_trace.csv')
        starts, _, rejected = vc._parse_architecture_mapping(self.work / 'commit_trace.csv')
        require((lanes, bits) == (4, 1024) and rejected == {243}, 'Sole masked fault geometry differs')
        v3.architecture_owner(starts, self.rows, s)
        a = activities[243]
        build_sources = self.read(BUILD / 'build-source-pins.json')
        vldu = ROOT / 'hardware/src/vlsu/vldu.sv'
        self.bind(vldu, build_sources[str(vldu)])
        save(self.out / 'masked-fault-current-native-shape.json', dict(arch_seq=243,
            scalar_qualification_passed=True, compressed_memory=memory, whole_snapshot=gold,
            lifecycle=control, allocations=a.allocations, completions=a.completions,
            write_rows=[asdict(w) for w in a.writes],
            expected_original_shape=dict(write_rows=20, source3_maintenance_rows=16, source4_zero_BE_rows=4),
            actual_write_counts=dict(total=len(a.writes), maintenance=sum(w.source == 3 for w in a.writes),
                                     load=sum(w.source == 4 for w in a.writes)),
            source_hypothesis=dict(confirmed=False, source=str(vldu),
                hypothesis='Current VALID_RESULT_QUEUE skips enqueue when vrf_word_byte_cnt_q is zero; a first-byte fault need not produce old zero-BE grant rows.',
                discriminating_signals=['ldu_ex_state_q', 'vrf_word_byte_cnt_q', 'result_queue_valid_q',
                                        'result_queue_cnt_q', 'ldu_result_req_o', 'ldu_result_gnt_i', 'ldu_result_be_o'],
                alternative='Missing probe/grant visibility versus genuinely absent zero-BE writeback',
                rerun_authorized=False),
            acceptance_inferred=False))
        texts = {}
        for rel in ('hardware/tb/ara_commit_monitor.sv', 'hardware/src/lane/operand_requester.sv',
                    'hardware/src/ara_system.sv', 'hardware/src/vlsu/vldu.sv', 'hardware/src/vlsu/addrgen.sv',
                    'hardware/src/ara.sv', 'hardware/src/lane/lane.sv', 'hardware/src/vlsu/vlsu.sv'):
            path = self.bind(ROOT / rel, build_sources[str(ROOT / rel)])
            texts[rel] = path.read_text()
            self.bind(path)
        source = current_masked_source_contract(texts)
        native_rows = [r for r in self.vectors if int(r['arch_seq']) == 243]
        # Preserve the old exact rejection independently; never manufacture rows.
        try:
            old_native = dict(status='PASS', result=v2.native_identity(activities[243], native_rows))
        except ValueError as error:
            old_native = dict(status='CHECKER_REQUIRED', reason=str(error))
        save(self.out / 'original-native-shape-predicate.json', old_native)
        proof = current_masked_native_identity(activities[243], native_rows)
        proof.update(fault_pc=s['smuf_masked_load'], whole_fault_snapshot=gold)
        fault = self.scalar['aligned_vector_faults'][0]
        require(v2.authorized_fault(activities[243], ref[partial], fault, proof), 'Exact case-only fault identity differs')
        def permit(activity, committed, aligned):
            return v2.authorized_fault(activity, committed, aligned, proof) or vc._known_identity_load_fault(activity, committed, aligned)
        fn = FunctionType(vc.compare_vector_commits.__code__, dict(vc.compare_vector_commits.__globals__,
            _known_identity_load_fault=permit), vc.compare_vector_commits.__name__, vc.compare_vector_commits.__defaults__)
        vec = fn(self.spike, self.work / 'commit_trace.csv', self.work / 'vector_trace.csv', 0x80000000,
                 aligned_vector_faults=self.scalar['aligned_vector_faults'])
        save(self.out / 'vector-comparison.json', vec)
        require(vec['status'] == 'PASS' and vec['compared_instructions'] == 105 and vec['compared_bytes'] == 13321 and
                vec['verified_identity_write_traps'] == [dict(arch_seq=243, compared_bytes=128)] and
                vec['verified_trapped_destination_requests'] == vec['trapped_requests'] == [243] and
                not vec['verified_zero_write_traps'] and not vec['unretired_requests'] and not vec['incomplete_requests'] and
                not vec['first_mismatch'] and all(vec[k] == 0 for k in
                    ('skipped_unknown_bytes', 'non_bit_exact_instructions', 'unobservable_instructions')),
                'Original masked fault full native contract rejected')
        save(self.out / 'current-masked-fault-proof.json', dict(source=source, identity=proof,
            scalar= self.scalar, memory=memory, snapshot=gold, lifecycle=control, vector=vec,
            old_shape_rejection_preserved=True, gold_changed=False, rows_inserted=False))
        self.gates['fault_axi_safety'] = dict(status='NOT_MEASURED', required_for_functional=False,
            reason='Optional physical claim, absent from original mandatory checker: no actual AXI transaction or waveform witness exists. No physical no-illegal-AXI claim is made.',
            original_scope=original_scope,
            evidence=dict(source=source, current_work=str(self.work), VPD_files=[str(p) for p in self.work.glob('*.vpd')],
                FSDB_files=[str(p) for p in self.work.glob('*.fsdb')]),
            needed_rerun=dict(authorized=False, required_for_functional=False,
                rationale='No replay needed for functional acceptance. This profile is relevant only to a separately requested physical AXI claim.',
                cycle_window=[proof['maintenance_interval'][0] - 32, proof['no_op_load_interval'][1] + 32],
                clock_coordinate='ara_commit_monitor.cycle_q',
                signals=['i_vlsu.i_addrgen.axi_ar_valid_o', 'i_vlsu.i_addrgen.axi_ar_ready_i',
                         'i_vlsu.i_addrgen.axi_ar_o', 'i_vlsu.i_addrgen.en_ld_st_translation_i',
                         'i_vlsu.i_addrgen.mmu_valid_i', 'i_vlsu.i_addrgen.mmu_exception_i',
                         'i_vlsu.i_addrgen.axi_addrgen_q', 'i_vlsu.i_vldu.ldu_ex_state_q',
                         'i_vlsu.i_vldu.vrf_word_byte_cnt_q', 'i_vlsu.i_vldu.result_queue_valid_q',
                         'i_vlsu.i_vldu.result_queue_cnt_q', 'i_vlsu.i_vldu.ldu_result_req_o',
                         'i_vlsu.i_vldu.ldu_result_gnt_i', 'i_vlsu.i_vldu.ldu_result_be_o'],
                hypothesis='First-element translation fault skips empty-prefix enqueue and produces no VLDU grant or invalid-page AR.',
                alternative='Unexpected AXI issue before fault despite unchanged architectural destination.'))
        return dict(memory=memory, gold=gold, lifecycle=control, identity_proof=proof,
                    current_source_contract=source, actual_AXI_safety_not_claimed=True,
                    functional_predicates_passed=list(MASKED_FUNCTIONAL_PREDICATES), original_scope=original_scope)

    def alternating_fault(self):
        # Source-bound successor proves mepc writes/returns instead of ignoring them.
        import collect_sv39_fault_alternating771_csr_return as m
        from ara_verify import vector_commit as vc
        old, s = m.old, self.symbols
        ref = m.prefix.terminal_prefix(self.reference, s)
        faults = [c for c in ref if c.pc in (s['fault_load_pc'], s['fault_store_pc'])]
        require(len(faults) == 8, 'Exact eight faults required')
        control = old.lifecycle(self.rows, self.vectors, [faults[0].instruction, faults[1].instruction])
        scalar = self.scalar
        require(scalar['status'] == 'TERMINAL_TOHOST_MATCH' and scalar['mismatch'] is None and
                scalar['skipped_unobservable_register_values'] == 0 and scalar['stopped_at_unobservable'] is None and
                scalar['matched_instructions'] == len(ref) - 8, 'Original full scalar/GPR fault contract rejected')
        aligned = scalar['aligned_vector_faults']
        require(len(aligned) == 8, 'Eight aligned faults required')
        handler = m.handler_replay(self.rows, ref, s)
        for i, (f, c) in enumerate(zip(aligned, faults)):
            require(f['pc'] == '0x%016x' % c.pc and f['instruction'] == '0x%08x' % c.instruction and
                    f['matched_fault_csrs'] == {'0x341': c.pc, '0x342': 15 if i & 1 else 13,
                        '0x343': old.p.ADDRESSES[(i // 2) & 1]} and f['fault_handler_returned'] and
                    f['invalidated_fault_csrs'] == ['0x341'], 'Exact fault CSR/PC/tval/return differs')
        memory = old.memory.scalar_memory_exact(self.rows, [c for c in ref if c not in faults])
        lanes, bits, activities = vc._parse_vector_trace(self.work / 'vector_trace.csv')
        require((lanes, bits) == (4, 1024), 'Native geometry differs')
        allowed = set()
        signature = lambda a: json.dumps(asdict(a), sort_keys=True)
        for seq in control['rejected']:
            a = activities[seq]
            accepted = [w for w in a.writes if w.be]
            require(a.allocations == a.completions, 'Fault completion differs')
            if accepted:
                require(all(w.source == 3 and w.be == w.known_be == 255 for w in accepted), 'Only known maintenance allowed')
                actual = vc._architectural_bytes(accepted, 4, 1024)
                reg = 16 if a.instruction == faults[0].instruction else 8
                require(sum(bin(w.be).count('1') for w in accepted) == 128 and
                        set(actual) == {(reg, b) for b in range(128)} and all(x[0] == 0x5a for x in actual.values()),
                        'Entire known prestate must be unchanged')
                allowed.add(signature(a))
        def permit(a, c, f):
            return (signature(a) in allowed and c.pc == s['fault_load_pc'] and f in aligned and
                    not c.vector_writes and not c.memory_accesses and c.vector_sew == 64 and
                    c.vector_vl == 1 and c.vector_vstart == 0 and f['matched_fault_csrs'].get('0x342') == 13)
        fn = FunctionType(vc.compare_vector_commits.__code__, dict(vc.compare_vector_commits.__globals__,
            _known_identity_load_fault=permit), vc.compare_vector_commits.__name__, vc.compare_vector_commits.__defaults__)
        vec = fn(self.spike, self.work / 'commit_trace.csv', self.work / 'vector_trace.csv', 0x80000000, aligned_vector_faults=aligned)
        save(self.out / 'vector-comparison.json', vec)
        require(vec['status'] == 'PASS' and vec['compared_instructions'] == 5 and vec['trapped_requests'] == control['rejected'] and
                not vec['first_mismatch'] and not vec['incomplete_requests'] and not vec['unretired_requests'] and
                all(vec[k] == 0 for k in ('skipped_unknown_bytes', 'non_bit_exact_instructions', 'unobservable_instructions')),
                'Original complete native fault vector contract rejected')
        require(self.summary['requests'] == self.summary['responses'] == control['requests'] and self.summary['exceptions'] == 8,
                'Original protocol fault conservation differs')
        observed = Counter(int(pc, 16) for pc in re.findall(r'^Exception @\s+\d+, PC: ([0-9a-fA-F]+),',
                           (self.work / 'trace_hart_0.log').read_text(), re.M))
        require(observed == Counter({s['fault_load_pc']: 4, s['fault_store_pc']: 4, s['fault_s_ecall']: 4}), 'Only twelve expected exceptions')
        return dict(handler=handler, memory=memory, lifecycle=control)

    def itlb(self):
        if self.index == 773:
            import collect_itlb_asid_exec_bulk_csr as m
            core = m.core
            ref, _ = core.checked_reference(self.spike, self.symbols)
            core.exact_scalar(self.scalar, self.pre['counts'])
            control = m.csr_lifecycle(self.rows, self.symbols)
            retired = [r for r in self.rows if r['event'] == 'retire']
            traps = core.support.old.trap_contract(retired, self.symbols)
            nontrap = [dict(r, order=str(i)) for i, r in enumerate(r for r in retired if not int(r['trap']))]
            cs = core.reference.native_reference(nontrap)
            require(core.bulk.reference_interval(cs) == cs, 'Exact native entry-terminal interval differs')
            require(len(cs) == len(ref), 'Full native reference prefix differs')
            for i, (a, b) in enumerate(zip(cs, ref)):
                require((a.pc, a.instruction, a.gpr_writes, a.memory_accesses) ==
                        (b.pc, b.instruction, b.gpr_writes, b.memory_accesses), 'Full native scalar divergence at ' + str(i))
            core.pre.validate(core.pre.with_ecalls(cs, self.symbols), self.symbols)
            dominance = core.code_write_dominance(cs, self.symbols)
        else:
            import collect_itlb_ppn_aba_v2 as successor
            m = successor.old
            ref = m.pre.reference(self.spike, self.symbols)
            m.original.exact_scalar(self.scalar, self.pre['counts'])
            control = m.csr_lifecycle(self.rows, ref)
            for text in self.log_texts:
                successor.console_gate(text, self.rows, ref, self.vectors)
            retired = [r for r in self.rows if r['event'] == 'retire']
            fn = FunctionType(m.original.trap_contract.__code__, dict(m.original.trap_contract.__globals__,
                              pre=SimpleNamespace(address=m.pre.address)))
            traps = fn(retired, self.symbols)
            nontrap = [dict(r, order=str(i)) for i, r in enumerate(r for r in retired if not int(r['trap']))]
            cs = m.original.reference.native_reference(nontrap)
            require(len(cs) == len(ref) and m.bulk_interval(cs) == cs, 'Full native prefix differs')
            for i, (a, b) in enumerate(zip(cs, ref)):
                require((a.pc, a.instruction, a.gpr_writes, a.memory_accesses) ==
                        (b.pc, b.instruction, b.gpr_writes, b.memory_accesses), 'Full native scalar divergence at ' + str(i))
            expanded = []
            index = 0
            for c in cs:
                if c.pc == self.symbols['itm_handler']:
                    p, e = divmod(index, 16)
                    index += 1
                    expanded.append(m.pre.architecture.spike_trace.SpikeCommit(pc=m.pre.address(p, e) + 8,
                        instruction=0x73, gpr_writes={}, fpr_writes={}, vector_writes={}, csr_writes={}, memory_accesses=()))
                expanded.append(c)
            require(index == 48, 'Exactly 48 previously verified traps required')
            m.pre.validate(expanded, self.symbols)
            dominance = dict(physical_A_B_code_distinguished=True)
        self.zero()
        return dict(lifecycle=control, traps=traps, initialization=dominance)

    def run(self):
        if self.gate('source_binding', self.setup) is not None:
            self.gate('execution', self.execution)
            self.gate('runtime_logs', self.logs)
            self.gate('scalar_comparator', self.compare)
            if hasattr(self, 'scalar') and hasattr(self, 'summary'):
                self.gate('original_architecture', self.architecture)
            else:
                self.gates['original_architecture'] = dict(status='CHECKER_REQUIRED', reason='Prerequisite raw comparator/log evidence unavailable')
        # Bind the actual transitive local checker implementations, not old PASS reports.
        for module in tuple(sys.modules.values()):
            p = getattr(module, '__file__', None)
            if p and p.endswith('.py') and Path(p).resolve().is_relative_to(ROOT / 'verification'):
                self.bind(Path(p).resolve())
        self.bind(Path(__file__).resolve())
        self.bind(Path(__file__).with_name('test_audit_pending_system_20261016.py'))
        for path in tuple(self.pins):
            self.bind(path)
        required = functional_required(self.gates)
        for name, row in self.gates.items():
            row['required_for_functional'] = name in required
        status = decision(self.gates)
        reasons = [name + ': ' + row['reason'] for name, row in self.gates.items()
                   if name in required and row['status'] != 'PASS' and 'reason' in row]
        report = self.out / 'audit.json'
        result = dict(index=self.index, status=status, report=str(report), work=str(self.work),
            architectural_status=self.gates.get('original_architecture', {}).get('status', 'CHECKER_REQUIRED'),
            functional_required=required,
            optional_physical_claims={name: row for name, row in self.gates.items() if name not in required},
            original_oracle=ORACLES[self.index],
            planpath=str(self.case / 'plan.json'), root=str(ROOT), actual_execution_identity=self.identity,
            input_pins=self.pins, gates=self.gates, reason='; '.join(reasons) if reasons else 'All mandatory functional predicates passed on actual current outputs; no optional physical claims inferred',
            acceptance_scope='ARCHITECTURE_ONLY', microstructure_witness=dict(status='NOT_CLAIMED',
                reason='No waveform/slot/refill/AXI timing or coverage-gain acceptance inferred from architectural acceptance'),
            coverage_admitted=False, old_PASS_reused=False, simulation_started=False, RTL_changed=False,
            needed_rerun=None if status == 'PASS' else ('Raw scalar/vector/tracer evidence is complete. '
                'For e0735, resolve only the failed mandatory gate reported above offline first. Optional AXI measurement '
                'is not a functional prerequisite and does not justify a rerun.' if self.index == 735 else
                'No rerun authorized. Resolve reported adapter/source/observability holds offline first; any missing raw evidence '
                'needs the original focused profile, after source analysis.'))
        save(report, result)
        print(f'e{self.index:04d} {status}: {result["reason"]}', flush=True)
        return dict(index=self.index, status=status, architectural_status=result['architectural_status'],
                    report=str(report), reason=result['reason'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--cases', type=int, nargs='+', default=list(CASES))
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.resolve() == output and output.is_relative_to(ROOT / 'verification/out') and not output.exists(), 'Fresh output inside workspace required')
    require(len(args.cases) == len(set(args.cases)) and set(args.cases) <= set(CASES), 'Assigned unique cases only')
    output.mkdir()
    guard_writes(output)
    cases = [Audit(i, output).run() for i in args.cases]
    save(output / 'audit.json', dict(cases=cases, counts=dict(Counter(c['status'] for c in cases)),
        scope=list(args.cases), simulation_started=False, shared_aggregator_modified=False))


if __name__ == '__main__':
    main()

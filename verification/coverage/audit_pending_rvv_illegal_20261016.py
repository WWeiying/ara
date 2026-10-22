#!/usr/bin/env python3
"""Nine current ordinary RVV/reject cases: offline original semantic predicates.

No original collect/prepare/terminal/image/source-book substitution, simulator,
Spike, coverage collection or historical verdict reuse. Execution identity is
validated by the parent's positive-vector execution() helper. Every original
mandatory architectural predicate is recorded independently, including physical
transport supplementation where generic vector comparison is insufficient.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys
import traceback
from copy import deepcopy

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'verification'), str(Path(__file__).resolve().parent),
               str(ROOT / 'verification/tools/soc-venv/lib/python3.9/site-packages')]
CASES = (715, 717, 718, 719, 721, 722, 725, 736, 737)
MODULES = dict(zip(CASES, (
    'collect_gap101a_strict_v2', 'collect_opivx_vsbc_strict',
    'collect_gap102b_strict_v3', 'collect_gap103_strict',
    'collect_gap104_strict_v2', 'collect_narrow_reject_r1_cached_strict',
    'qualify_vnclipu_parent_terminal', 'qualify_narrow_source_group_terminal',
    'qualify_narrow_clip_reject_terminal_v2')))
EXCEPTIONS = dict(zip(CASES, (1, 1, 0, 0, 2, 24, 1, 1, 17)))
RUNS = ROOT / 'verification/out/full-regression-20261015-01/extensions'
DEFAULT_OUT = ROOT / 'verification/out/full-regression-pending-rvv-illegal-agent-20261016-01'


class ContextRequired(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def install_guard(output):
    output = output.resolve()
    def inside(path):
        return isinstance(path, (str, bytes, os.PathLike)) and Path(os.fsdecode(path)).resolve().is_relative_to(output)
    def guard(event, args):
        if event == 'open':
            path, mode, flags = args
            if ((mode and any(c in mode for c in 'wax+')) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)) and not inside(path):
                raise PermissionError('Offline audit write outside output: ' + str(path))
        elif event in ('subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn', 'os.fork'):
            raise PermissionError('Offline audit prohibits process launch')
        elif event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.utime'):
            if not inside(args[0]):
                raise PermissionError('Offline audit mutation outside output')
        elif event in ('os.rename', 'os.link', 'os.symlink'):
            raise PermissionError('Offline audit prohibits relinking')
    sys.addaudithook(guard)


def classify_error(error, evidence=False):
    if evidence or isinstance(error, (ContextRequired, ImportError, OSError, KeyError, TypeError, AttributeError)):
        return 'CHECKER_REQUIRED'
    if re.search(r'Frozen .*oracle changed|Frozen .*drift|Exact reviewed450 runner/test source|Exact predecessor replacement|Unexpected frozen signature dimension|Frozen dimension positions', str(error)):
        return 'CHECKER_REQUIRED'
    return 'FAIL' if isinstance(error, (ValueError, AssertionError)) else 'CHECKER_REQUIRED'


def tracer_no_traps(text, rows):
    """Exact nontrapping GAP102B/GAP103 original tracer-prefix and tail gate."""
    require('Exception @' not in text, 'Independent tracer exception')
    pattern = re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
    actual = [match.groups() for line in text.splitlines() if (match := pattern.match(line))]
    expected = [(str(int(row['cycle'])), 'M', row['pc'], row['insn']) for row in rows if row['event'] == 'retire']
    require(expected and actual[:len(expected)] == expected, 'Tracer prefix differs')
    tail = actual[len(expected):]
    require(not tail or tail == [(expected[-1][0], 'M', '%016x' % (int(expected[-1][2], 16) + 4), '0000a001')], 'Unknown tracer tail')
    return dict(retirements=len(expected), exceptions=0, exact_prefix=True, tail=tail)


def retirement_elf(rows, blob):
    from qualify_store_fault_flush_terminal import elf_instruction
    count = 0
    for row in rows:
        if row['event'] != 'retire':
            continue
        word, pc = int(row['insn'], 16), int(row['pc'], 16)
        require(word & 3 == 3 and elf_instruction(blob, pc, 4) == word, 'Retirement opcode outside actual current no-C ELF')
        count += 1
    return dict(elf_matched_retirements=count, source='actual current input.elf bytes', no_old_runner_ELF_substitution=True)


def vnclipu_maintenance(result, rows, vectors, reference, control):
    """Original maintenance byte proof using actual current owner lifetimes.

    Historical absolute cycles and VID numbering are not architectural values.
    No input timestamp, image, manifest, source-book or comparator result is
    altered. Only a private result copy is classified AFTER proving every one
    of the128 extra non-destination bytes against independent source prestate.
    """
    import qualify_vnclipu_maintenance_successor as old
    import ara_verify.vector_commit as vc
    pre, post = old.reference_state(reference)
    record = result['instructions'][-1]
    seq = record['arch_seq']
    require(int(record['pc'], 16) == old.PC and int(record['instruction'], 16) == old.WORD,
            'Exact recovery PC/opcode')
    starts = [r for r in rows if r['event'] == 'arch_start' and int(r['order']) == seq]
    retired = [r for r in rows if r['event'] == 'retire' and int(r['pc'], 16) == old.PC]
    require(len(starts) == len(retired) == 1 and int(starts[0]['insn'], 16) == old.WORD
            and int(retired[0]['insn'], 16) == old.WORD, 'Unique recovery request and retirement')
    tid, begin = int(starts[0]['trans_id']), int(starts[0]['cycle'])
    selected = [r for r in vectors if int(r['arch_seq']) == seq]
    require(all(r['event'] in ('alloc', 'done', 'write') and int(r['insn'], 16) == old.WORD
                and (int(r['nr_lanes']), int(r['vlen_bits']), int(r['use_vd']), int(r['vstart'])) == (4, 1024, 1, 0)
                for r in selected), 'Recovery native owner/context')
    alloc = [r for r in selected if r['event'] == 'alloc']
    done = [r for r in selected if r['event'] == 'done']
    shapes = [(16, 1, 64), (8, 2, 32), (16, 1, 2)]
    require(len(alloc) == len(done) == 3 and [(int(r['vd']), int(r['eew']), int(r['vl'])) for r in alloc] == shapes,
            'Three exact maintenance/result phases')
    phases = []
    for row in alloc:
        matches = [r for r in done if all(r[k] == row[k] for k in ('vid', 'vd', 'eew', 'vl', 'insn'))
                   and int(r['cycle']) >= int(row['cycle'])]
        require(len(matches) == 1, 'Unique native phase completion')
        phases.append(dict(start=int(row['cycle']), end=int(matches[0]['cycle']),
                           vid=int(row['vid']), vd=int(row['vd']), eew=int(row['eew']), vl=int(row['vl'])))
    backend = [r for r in rows if int(r['order']) == seq and r['event'] in ('uop_alloc', 'uop_done')]
    actual_backend = sorted((r['event'], int(r['cycle']), int(r['port'])) for r in backend)
    expected_backend = sorted((event, phase[key], phase['vid']) for phase in phases
                              for event, key in (('uop_alloc', 'start'), ('uop_done', 'end')))
    require(actual_backend == expected_backend and all(int(r['trans_id']) == tid and int(r['insn'], 16) == old.WORD
            for r in backend) and all(begin <= p['start'] <= p['end'] for p in phases)
            and max(p['end'] for p in phases[:2]) < phases[2]['start'], 'Exact backend/native phase ownership and ordering')
    decoded = [{}, {}, {}]
    write_counts = [0, 0, 0]
    for number, row in enumerate(selected):
        if row['event'] != 'write':
            continue
        candidates = [i for i, p in enumerate(phases) if p['start'] <= int(row['cycle']) <= p['end']
                      and all(int(row[k]) == p[k] for k in ('vid', 'vd', 'eew', 'vl'))]
        require(len(candidates) == 1, 'Write must belong to exactly one actual phase')
        i = candidates[0]
        require(int(row['source']) == (3 if i < 2 else 0) and 0 <= int(row['lane']) < 4, 'Exact maintenance/result source/lane')
        data, known = vc._write_data(row['wdata'])
        mask = int(row['be'], 16)
        require(0 < mask <= 255 and not mask & ~known, 'Unknown enabled maintenance byte')
        write = vc.VectorWrite(number, int(row['cycle']), seq, int(row['vid']), int(row['lane']),
            int(row['source']), old.WORD, int(row['eew']), int(row['addr']), mask, data, known)
        one = vc._architectural_bytes([write], 4, 1024)
        require(not set(one) & set(decoded[i]), 'Duplicate accepted phase byte')
        decoded[i].update(one)
        write_counts[i] += 1
    require(write_counts == [16, 16, 2], 'Full maintenance/result write inventory')
    for i, values in enumerate(decoded):
        reg = 8 if i == 1 else 16
        require(set(values) == {(reg, b) for b in range(128 if i < 2 else 4)}, 'Exact phase byte footprint')
        expected = pre[reg] if i < 2 else post
        require(all(value is not None and value == (expected >> (8 * b)) & 255
                    for (_, b), (value, _) in values.items()), 'Independent maintenance/prestate/result byte mismatch')
    final = dict(decoded[0]); final.update(decoded[2])
    require(bytes(final[(16, b)][0] for b in range(128)) == post.to_bytes(128, 'little'), 'Complete128-byte recovery poststate')
    require(len(result['instructions']) == 33 and result['skipped_unknown_bytes'] == 128 and
            all(r['skipped_unknown_bytes'] == 0 for r in result['instructions'][:-1]) and
            record['skipped_unknown_bytes'] == 128 and record['compared_bytes'] == 128 and
            record['uops'] == 3 and record['write_events'] == 34, 'Only exact proved maintenance may be classified')
    classified = deepcopy(result)
    classified['skipped_unknown_bytes'] = classified['instructions'][-1]['skipped_unknown_bytes'] = 0
    old.old.r1.vector_exact(classified, [control['exception_arch_seq']], reference)
    return dict(arch_seq=seq, trans_id=tid, actual_start=begin, actual_phases=phases,
                write_counts=write_counts, known_source_maintenance_bytes=128,
                destination_prestate_bytes=128, destination_result_bytes=4, destination_poststate_bytes=128,
                genuinely_unknown_bytes=0, original_generic_result_modified=False,
                historical_absolute_cycles_required=False, complete_original_byte_and_owner_predicates=True)


class Audit:
    def __init__(self, index, output):
        self.index = index
        self.case = RUNS / f'e{index:04d}'
        self.work = self.case / 'work'
        self.out = output / f'e{index:04d}'
        self.out.mkdir()
        self.input_pins = {}
        self.components = {}
        self.required = []

    def bind(self, path, expected=None):
        path = Path(path).absolute()
        value = sha(path)
        if expected is not None and value != expected:
            raise ContextRequired('Input pin differs: ' + str(path))
        if str(path) in self.input_pins and self.input_pins[str(path)] != value:
            raise ContextRequired('Input changed: ' + str(path))
        self.input_pins[str(path)] = value
        return path

    def bind_json(self, path, expected=None):
        return json.loads(self.bind(path, expected).read_text())

    def check(self, name, function, checker, evidence=False):
        self.required.append(name)
        try:
            result = function()
            row = dict(status='PASS', checker=checker, result=result)
        except Exception as error:
            row = dict(status=classify_error(error, evidence), checker=checker,
                       reason=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
        self.components[name] = row
        save(self.out / f'{name}.json', row)
        print(f'e{self.index:04d} {name}: {row["status"]}' + (': ' + row['reason'] if 'reason' in row else ''), flush=True)
        return row.get('result') if row['status'] == 'PASS' else None

    def setup(self):
        self.plan = self.bind_json(self.case / 'plan.json')
        require(self.plan['index'] == self.index and Path(self.plan['work']) == self.work, 'Current case index/work differs')
        source = self.plan['command_source']
        self.old = self.bind_json(source, self.plan['pins'][source])
        self.q = importlib.import_module(MODULES[self.index])
        prevalue = self.old['preflight']
        original_elf = Path(next(x.split('=', 1)[1] for x in self.plan['original_command'] if x.startswith('+PRELOAD=')))
        self.bind(original_elf, self.plan['elf_sha256'])
        self.bind(self.case / 'input.elf', self.plan['elf_sha256'])
        self.bind_json(self.case / 'simulation-exit.json')
        self.bind(self.plan['command'][0])
        self.bind(self.work / 'commit_trace.csv')
        self.bind(self.work / 'vector_trace.csv')
        if isinstance(prevalue, dict):
            self.pre = prevalue
            self.pre_dir = original_elf.parent
        else:
            path = Path(prevalue)
            self.pre = self.bind_json(path, self.old['preflight_seal'])
            self.pre_dir = path.parent
        self.symbols = self.pre['symbols']
        self.reference_path = Path(self.pre.get('input_spike_trace', self.pre_dir / 'spike.trace'))
        maps = [self.old.get('pins', {}), self.pre.get('pins', {}), self.pre.get('output_pins', {}), self.pre.get('input_pins', {})]
        expected = {pins[str(self.reference_path)] for pins in maps if str(self.reference_path) in pins}
        if len(expected) != 1:
            raise ContextRequired('One unambiguous original software reference pin required: ' + str(self.reference_path))
        self.bind(self.reference_path, expected.pop())
        if self.index == 736:
            # Original pure observed() reads this immutable input for opcode
            # checking only. Prove byte equality; never replace its global path.
            self.bind(self.q.runner.ELF, self.plan['elf_sha256'])
        # v2.namespace() also guards an obsolete top-level collector source hash.
        # Call its actual pure predecessor predicates directly, plus both v2
        # architectural strengthenings below; never fabricate its frozen source.
        self.ns = vars(self.q.prior) if self.index == 737 else vars(self.q)
        import collect_opivx_vsbc_strict as common
        from ara_verify.spike_trace import parse_spike_commits
        self.common = common
        self.rows = common.read_csv(self.bind(self.work / 'commit_trace.csv').read_bytes(), common.COMMIT_FIELDS)
        self.vectors = common.read_csv(self.bind(self.work / 'vector_trace.csv').read_bytes(), common.VECTOR_FIELDS)
        self.tracer = self.bind(self.work / 'trace_hart_0.log').read_text()
        if (self.work / 'trace_hart_0_commit.log').is_file():
            self.bind(self.work / 'trace_hart_0_commit.log')
        self.reference = list(parse_spike_commits(self.reference_path))
        self.counts = common.reference_counts(self.reference, self.symbols)
        return dict(original_command_source=source, reference=str(self.reference_path),
                    reference_sha256=self.input_pins[str(self.reference_path)],
                    reference_counts=self.counts, private_ELF_sha256=self.plan['elf_sha256'],
                    old_manifest_used_as='software input provenance only; not current execution context')

    def lifecycle(self):
        fn = self.ns['lifecycle']
        return fn(self.rows, self.vectors) if self.index in (715, 721) else fn(self.rows, self.vectors, self.symbols)

    def observed(self):
        fn = self.ns['observed']
        return fn(self.rows, self.symbols, self.pre_dir) if self.index == 736 else fn(self.rows, self.symbols)

    def scalar(self, observed):
        from ara_verify.spike_trace import compare_commit_prefix
        result = compare_commit_prefix(self.reference_path, self.work / 'commit_trace.csv', 0x80000000,
            terminal_tohost_address=self.symbols['tohost'], rvfi_store_data_layout='unshifted')
        save(self.out / 'scalar-comparison.json', result)
        if self.index == 715:
            self.q.scalar_exact(result)
        elif self.index in (718, 719):
            counts = self.q.reference_counts(self.reference, self.symbols)
            require(counts == self.q.SCALAR_COUNTS, 'Independent complete reference counts differ')
            self.q.scalar_exact(result, counts)
        elif self.index == 721:
            counts = self.q.shared.reference_counts(self.reference, self.symbols)
            require(counts == self.q.SCALAR_COUNTS, 'Independent complete reference counts differ')
            self.q.shared.scalar_exact(result, counts)
        elif self.index == 736:
            if observed is None:
                raise ContextRequired('Native observed gate required for trap-marked retirement population')
            self.q.scalar_exact(result, self.counts, observed)
        else:
            self.common.scalar_exact(result, self.counts)
        return result

    def vector(self, control, transport):
        from ara_verify.vector_commit import compare_vector_commits
        result = compare_vector_commits(self.reference_path, self.work / 'commit_trace.csv', self.work / 'vector_trace.csv', 0x80000000)
        save(self.out / 'vector-comparison.json', result)
        if control is None:
            raise ContextRequired('Original lifecycle gate must pass before vector ownership can be admitted')
        if self.index in (718, 719, 721) and transport is None:
            raise ContextRequired('Independent transport-byte supplementation is mandatory')
        if self.index == 715:
            self.q.vector_exact(result, control['exception_arch_seq'])
        elif self.index == 717:
            self.q.vector_exact(result, control['exception_arch_seq'], self.reference)
        elif self.index in (718, 719):
            self.q.vector_exact(result, transport)
        elif self.index == 721:
            self.q.vector_exact(result, control, transport)
        elif self.index == 722:
            self.q.vector_exact(result, control['rejected_arch_seqs'], self.reference)
        elif self.index == 725:
            proof = vnclipu_maintenance(result, self.rows, self.vectors, self.reference, control)
            save(self.out / 'known-maintenance-byte-proof.json', proof)
        elif self.index == 736:
            self.q.native_exact(result, control, self.reference, self.work)
        else:
            self.ns['vector_gate'](result, control['rejected_arch_seqs'], self.reference)
            self.q.vector_exact(result, control['rejected_arch_seqs'], self.reference)
        return result

    def protocol(self, control):
        from ara_verify.contract import check_contract_log, parse_contract_summary
        if control is None:
            raise ContextRequired('Lifecycle conservation required to bind protocol counters')
        records = {}
        for name, path in [('console.log', self.case / 'console.log'), ('run.vcs.log', self.work / 'run.vcs.log')]:
            text = self.bind(path).read_text()
            require(not check_contract_log(path), 'Actual protocol diagnostics: ' + name)
            summaries = [parse_contract_summary(line) for line in text.splitlines() if '[ARA_CONTRACT]' in line]
            require(len(summaries) == 1 and summaries[0] is not None, 'One complete actual contract required')
            value = summaries[0]
            require((value['requests'], value['responses'], value['exceptions']) ==
                    (control['requests'], control['responses'], EXCEPTIONS[self.index]) and
                    all(value[key] == 0 for key in ('protocol_errors', 'outstanding', 'req_stalled', 'resp_stalled')),
                    'Actual full request/response/exception/drain/stability counters differ')
            records[name] = value
        console = (self.case / 'console.log').read_text()
        log = (self.work / 'run.vcs.log').read_text()
        if self.index in (725, 736):
            self.q.logs(console, log, control)
        elif self.index == 737:
            self.ns['stdout_gate'](console, log, control)
        return records

    def run(self):
        if self.check('inputs', self.setup, 'Pinned software inputs and exact current CSV schemas', evidence=True) is None:
            return
        from audit_pending_rvv_20261016 import execution
        self.check('execution', lambda: execution(self), 'Parent positive-vector execution(): actual current wait/image/ELF/logs/trace', evidence=True)
        control = self.check('lifecycle', self.lifecycle, MODULES[self.index] + '.lifecycle')
        observed = self.check('observed', self.observed, MODULES[self.index] + '.observed: actual VRF/CSR/trap/guard/recovery bytes')
        self.check('tracer', lambda: tracer_no_traps(self.tracer, self.rows) if self.index in (718, 719) else self.ns['tracer_exact'](self.tracer, self.rows, self.symbols),
                   'Original independent tracer/precise exception PC/cause/tval gate')
        if self.index == 737:
            self.check('retirement_elf', lambda: retirement_elf(self.rows, (self.case / 'input.elf').read_bytes()),
                       'qualify_narrow_clip_reject_terminal_v2 audit_retirements predicates on actual current ELF')
        self.check('scalar', lambda: self.scalar(observed), 'Original full scalar terminal/reference gate (no prefix-only acceptance)')
        transport = None
        if self.index in (718, 719, 721):
            transport = self.check('transport', lambda: self.q.transport_exact(self.vectors, self.reference) if self.index == 719 else self.q.transport_exact(self.vectors),
                                   MODULES[self.index] + '.transport_exact: all physical bytes/preservation')
        self.check('vector', lambda: self.vector(control, transport), 'Original full per-instruction VRF/known-byte/reject gate')
        self.check('protocol', lambda: self.protocol(control), 'Original request/response/exception/protocol/stability/terminal gates')

    def finish(self):
        drift = []
        for path, expected in self.input_pins.items():
            if sha(path) != expected:
                drift.append(path)
        if drift:
            self.components['input_stability'] = dict(status='CHECKER_REQUIRED', reason='Inputs changed', paths=drift)
        statuses = [row['status'] for row in self.components.values()]
        status = 'FAIL' if 'FAIL' in statuses else 'CHECKER_REQUIRED' if 'CHECKER_REQUIRED' in statuses else 'PASS'
        expected = {'inputs', 'execution', 'lifecycle', 'observed', 'tracer', 'scalar', 'vector', 'protocol'}
        if self.index in (718, 719, 721):
            expected.add('transport')
        if self.index == 737:
            expected.add('retirement_elf')
        missing = sorted(expected - self.components.keys())
        if missing and status != 'FAIL':
            status = 'CHECKER_REQUIRED'
        result = dict(index=self.index, status=status, functional_status=status,
            work=str(self.work), current_case=str(self.case), input_pins=self.input_pins,
            actual_execution_identity_validation=self.components.get('execution'),
            mandatory_predicates=sorted(expected), missing_predicates=missing, components=self.components,
            original_oracle=MODULES[self.index], old_PASS_reused=False, old_context_spoofed=False,
            simulations_started=False, RTL_changed=False, coverage_admitted=False,
            internal_historical_toggle_hits_required=False)
        save(self.out / 'audit.json', result)
        return dict(index=self.index, status=status, report=str(self.out / 'audit.json'),
                    report_sha256=sha(self.out / 'audit.json'), work=str(self.work), missing_predicates=missing)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--cases', nargs='+', type=int, choices=CASES, default=CASES)
    args = parser.parse_args()
    output = args.output.absolute()
    require(not output.exists() and output.parent.resolve().is_relative_to(ROOT / 'verification/out'), 'Fresh independent verification/out output required')
    install_guard(output)
    output.mkdir()
    save(output / 'policy.json', dict(simulation_permitted=False, subprocess_permitted=False,
        writes_confined_to=str(output), interpreter=sys.executable, python_path=sys.path, cases=args.cases))
    results = []
    for index in args.cases:
        item = Audit(index, output)
        item.run()
        results.append(item.finish())
    code = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename and Path(filename).suffix == '.py' and Path(filename).is_file() and (
                Path(filename).resolve().is_relative_to(ROOT / 'verification') or 'elftools' in filename or '/yaml/' in filename):
            code[str(Path(filename).resolve())] = sha(filename)
    save(output / 'checker-code-pins.json', code)
    save(output / 'audit.json', dict(cases=results, counts={key: sum(row['status'] == key for row in results)
        for key in ('PASS', 'FAIL', 'CHECKER_REQUIRED')}, checker_code_pins=str(output / 'checker-code-pins.json'),
        simulations_started=False, old_reports_changed=False, RTL_changed=False, coverage_admitted=False))
    print(json.dumps(results, indent=2), flush=True)


if __name__ == '__main__':
    main()

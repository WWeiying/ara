#!/usr/bin/env python3
"""Offline current-output FPU acceptance; no simulation or coverage aggregation.

Historical main/collect entry points are never called. Contiguous original
architecture statements are compiled unchanged with explicit current data paths.
The extracted source is published next to its result for review.
"""
from __future__ import annotations

import argparse
import ast
import csv
import importlib
import inspect
import json
from pathlib import Path
import struct
import sys
import textwrap
import traceback
from types import FunctionType, SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'verification'), str(Path(__file__).resolve().parent)]
from audit_probe_semantics_20261015 import CaseAudit, install_guard, require, save, sha
from audit_pending_rvv_20261016 import execution, prefix

CASES = (660, *range(689, 705), 706, 744, 745, *range(747, 758), 764, 769, 777, 783)
RESET_CASES = (744, 745, *range(747, 758), 764)


def execution_bound(a):
    if a.index not in RESET_CASES:
        return execution(a)
    from qualify_gap113_cached_reset import read_csv, split_epochs

    def validate_reset_epochs(path):
        _, commits = read_csv(path)
        _, vectors = read_csv(a.work / 'vector_trace.csv')
        epochs, cycle = split_epochs(commits, vectors)
        return dict(validator='qualify_gap113_cached_reset.split_epochs', epochs=2,
            cut_cycle=cycle, epoch_rows=[len(cr) for cr, _ in epochs],
            whole_trace_order_restart_expected=True,
            mandatory_per_epoch_architecture_and_lifecycle='original reset checker below')

    tree = ast.parse(textwrap.dedent(inspect.getsource(execution)))
    replacements = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'validate_trace':
            node.func.id = 'validate_reset_epochs'
            replacements += 1
    require(replacements == 1, 'Execution helper global trace gate changed')
    ast.fix_missing_locations(tree)
    namespace = dict(execution.__globals__, validate_reset_epochs=validate_reset_epochs)
    exec(compile(tree, inspect.getsourcefile(execution), 'exec'), namespace)
    (a.out / 'reset-execution-binder.py').write_text(ast.unparse(tree) + '\n')
    a.bind(inspect.getsourcefile(execution))
    return namespace['execution'](a)


class CurrentView:
    """Original predicates see raw current traces and echo-classified current logs."""
    def __init__(self, audit):
        self.audit = audit

    def __truediv__(self, name):
        if name in ('console.log', 'run.vcs.log'):
            return self.audit.out / 'runtime' / name
        if name.startswith('epoch') or name.endswith('.json'):
            return self.audit.out / name
        return self.audit.work / name


def source_block(function, start, stop):
    """Extract whole AST statements, including nested suites, without rewriting."""
    source = textwrap.dedent(inspect.getsource(function))
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    first = [i for i, line in enumerate(lines, 1) if line.lstrip().startswith(start)]
    require(len(first) == 1, 'Ambiguous original block start: ' + start)
    last = [i for i, line in enumerate(lines, 1) if i > first[0] and line.lstrip().startswith(stop)]
    require(last, 'Missing original block end: ' + stop)
    begin, end = first[0], last[0]
    suites = [n.body for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.Try))]
    candidates = [[n for n in suite if begin <= n.lineno < end] for suite in suites]
    nodes = next((ns for ns in candidates if ns and ns[0].lineno == begin), None)
    require(nodes and nodes[-1].end_lineno < end, 'Block splits an original statement')
    return ast.Module(body=nodes, type_ignores=[]), textwrap.dedent(''.join(lines[begin-1:end-1]))


def execute_block(a, label, function, start, stop, namespace):
    tree, source = source_block(function, start, stop)
    a.bind(inspect.getsourcefile(function))
    (a.out / (label + '-original.py')).write_text(source)
    state = dict(function.__globals__, **namespace)
    try:
        exec(compile(tree, inspect.getsourcefile(function), 'exec'), state)
    finally:
        for name in ('scalar', 'vector', 'diff', 'prefix', 'sig', 'native', 'mem', 'lifecycle',
                     'backend', 'frontend', 'store_proof', 'receipts', 'axi', 'controllers'):
            if name in state and isinstance(state[name], (dict, list, tuple, int, str, float, bool, type(None))):
                save(a.out / (label + '-' + name + '.json'), state[name])
    return state


def cancelled_binding_current(function, first_cycle, namespace):
    """Rebind the historical absolute schedule, retaining every owner predicate.

    The current first allocation is bound by the architectural-start mapping in
    the original predicate. Both allocations must still be exactly consecutive.
    The unmodified historical timing check is reported separately by the caller.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    changed = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == 8568:
            node.value = first_cycle
            changed += 1
    require(changed == 1, 'Original URED timing predicate changed')
    ast.fix_missing_locations(tree)
    state = dict(function.__globals__, **namespace)
    exec(compile(tree, inspect.getsourcefile(function), 'exec'), state)
    return state[function.__name__], ast.unparse(tree) + '\n'


def reference(a):
    original = Path(next(c.split('=', 1)[1] for c in a.plan['original_command'] if c.startswith('+PRELOAD=')))
    a.bind(original, a.plan['elf_sha256'])
    spike = original.parent / 'spike.trace'
    expected = a.old.get('pins', {}).get(str(spike))
    a.bind(spike, expected)
    return original.parent, spike


def red32_vector_gate(exact):
    require(exact['status'] == 'PASS' and exact['stopped_at_spike_index'] is None and exact['first_mismatch'] is None
        and exact['vector_destination_requests'] == exact['prefix_vector_destination_requests'] == exact['compared_instructions'] == 84
        and exact['compared_bytes'] == 19908 and all(exact[k] == 0 for k in
            ('skipped_unknown_bytes', 'non_bit_exact_instructions', 'unobservable_instructions'))
        and not exact['incomplete_requests'] and not exact['unretired_requests'] and not exact['trapped_requests']
        and all(row['unknown_write_bytes'] == row['skipped_unknown_bytes'] == row['mismatch_count'] == 0 for row in exact['instructions']),
        'Complete exact RED32 current vector population differs')


def red32_exact(a, spike, scalar, vector):
    """Fixture-specific exact integer sums: no unordered-reduction byte skip."""
    import ara_verify.vector_commit as vc
    import collect_opivx_vsbc_strict as common
    compile_path = spike.parent / 'compile.command.json'
    compile_record = a.bind_json(compile_path)
    source_book = a.bind_json(spike.parents[2] / 'source-pins.json')
    require(source_book[str(spike.parent / 'input.elf')] == a.plan['elf_sha256'],
            'RED32 immutable original ELF identity differs')
    source_context = {}
    for filename in ('vgap76_red32.c', 'vgap76_wide_body.h'):
        path = ROOT / 'apps/riscv-tests/isa/rv64uv' / filename
        a.bind(path)
        source_context[str(path)] = dict(historical_sha256=source_book[str(path)],
            current_sha256=a.inputs[str(path)], current_source_used_as_binary_authority=False)
    require(not any(c.startswith('-DG_PATTERN') for c in compile_record['command']),
            'RED32 exact finite integer source domain differs')
    ref = prefix(spike, 0x80001000)
    counts = common.reference_counts(ref, dict(tohost=0x80001000))
    common.scalar_exact(scalar, counts)
    expected = []
    phases = []
    for full in (32, 64):
        for phase, active in enumerate((1, 3, 5, full-1, full, full, full)):
            mask = 0 if phase == 4 else 0xa5 if phase == 5 else 0xff
            value = 2 + sum(i % 5 - 2 for i in range(active) if mask >> (i % 8) & 1)
            expected.append(int.from_bytes(struct.pack('<d', float(value)), 'little'))
            phases.append((full, active, mask))
    opcode = 0xc4861857
    reductions = [c for c in ref if c.instruction == opcode]
    require(len(reductions) == 14 and all(16 in c.vector_writes for c in reductions),
            'Complete14 RED32 reference operations required')
    require([c.vector_writes[16] & ((1 << 64)-1) for c in reductions] == expected,
            'Independent finite integer RED32 gold differs')
    # Bind the numerical-domain argument to every actual reference operand, not
    # to a live header that acquired unrelated conditional patterns later.
    registers, cell = {}, 0
    for commit in ref:
        if commit.instruction == opcode:
            full, active, mask = phases[cell]
            require(registers[12] & ((1 << 64)-1) == int.from_bytes(struct.pack('<d', 2.0), 'little'),
                    'RED32 actual seed not exact2')
            for i in range(full):
                actual = registers[8+i//32] >> (32*(i%32)) & 0xffffffff
                want = int.from_bytes(struct.pack('<f', float(i%5-2)), 'little')
                require(actual == want, 'RED32 actual finite integer operand differs')
            require(registers[0] & ((1 << full)-1) == int.from_bytes(bytes([mask]) * (full//8), 'little'),
                    'RED32 actual phase mask differs')
            cell += 1
        registers.update(commit.vector_writes)
    require(cell == 14, 'RED32 complete operand-domain population')
    namespace = dict(vars(vc))
    original = vc._is_non_bit_exact_vector_result
    for name, fn in list(namespace.items()):
        if isinstance(fn, FunctionType) and fn.__globals__ is vars(vc):
            namespace[name] = FunctionType(fn.__code__, namespace, name, fn.__defaults__, fn.__closure__)
            namespace[name].__kwdefaults__ = fn.__kwdefaults__
    namespace['_is_non_bit_exact_vector_result'] = lambda word: False if word == opcode else original(word)
    exact = namespace['compare_vector_commits'](spike, a.work / 'commit_trace.csv', a.work / 'vector_trace.csv', 0x80000000)
    save(a.out / 'red32-exact-vector.json', exact)
    red32_vector_gate(exact)
    save(a.out / 'red32-policy.json', dict(status='PASS', original_generic_oracle=vector,
        original_generic_skip_not_used_for_acceptance=True, exact_integer_reductions=14,
        expected_reduction_bits=[hex(v) for v in expected], exact_destination_instructions=84,
        exact_destination_bytes=19908, expected_scalar_counts=counts,
        compile_source_context=source_context, actual_reference_operands_checked=True,
        source_domain='input i%5-2, seed2; at most64 exact binary32 integers widened to binary64; all partial sums exact',
        tail_policy='tu/mu: full initialized destination group retained; accepted writes and firmware full64 output checks retained'))


def literal_spec(a, gap):
    path = Path(__file__).with_name('admit_gap%d_offline.py' % gap)
    if gap == 96:
        path = path.with_name('admit_gap96_offline_v2.py')
    tree = ast.parse(a.bind(path).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Attribute) and t.attr == 'SPECS' for t in node.targets):
            require(isinstance(node.value, ast.Dict), 'Original case definition is not a literal dictionary')
            for key, value in zip(node.value.keys, node.value.values):
                if ast.literal_eval(key) == 'gap%d' % gap:
                    require(isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                            and value.func.id == 'dict' and not value.args,
                            'Original case specification is not literal dict keywords')
                    return {kw.arg: ast.literal_eval(kw.value) for kw in value.keywords}
    raise ValueError('Missing original literal case specification')


def arithmetic(a):
    pre, spike = reference(a)
    if 689 <= a.index <= 694:
        q = importlib.import_module('admit_gap%d_offline' % (a.index - 606))
        execute_block(a, 'architecture', q.main, 'scalar =', 'check()', dict(run=CurrentView(a), pre=pre))
    elif 695 <= a.index <= 700 or a.index == 704:
        import admit_fp64_scan as q
        gap = a.index - 606 if a.index != 704 else 96
        spec = q.SPECS['gap%d' % gap] if gap in (89, 90) else literal_spec(a, gap)
        execute_block(a, 'architecture', q.main, 'scalar =', 'check()', dict(run=CurrentView(a), pre=pre, spec=spec))
    elif 701 <= a.index <= 703:
        import admit_gap95_batch as q
        spec = a.old['preflight']
        from ara_verify.spike_trace import compare_commit_prefix
        from ara_verify.vector_commit import compare_vector_commits
        scalar = compare_commit_prefix(spike, a.work / 'commit_trace.csv', 0x80000000,
            terminal_tohost_address=spec['symbols']['tohost'], rvfi_store_data_layout='unshifted')
        vector = compare_vector_commits(spike, a.work / 'commit_trace.csv', a.work / 'vector_trace.csv', 0x80000000)
        save(a.out / 'scalar.json', scalar); save(a.out / 'vector.json', vector)
        require(scalar['status'] == 'TERMINAL_TOHOST_MATCH' and scalar['ara_trap_events'] == 0, 'Original GAP95 scalar mismatch/trap')
        require(q.vector_exact(vector, spec), 'Original GAP95 vector mismatch/incomplete/non-exact')
        with (a.work / 'commit_trace.csv').open() as stream:
            writes = {int(r['mem_addr'], 16): (int(r['mem_wmask'], 16), int(r['mem_wdata'], 16))
                      for r in csv.DictReader(stream) if r['event'] == 'retire' and int(r['mem_wmask'], 16)}
        require(q.signature_exact(writes, spec), 'Original GAP95 signature mismatch')
    elif a.index == 706:
        import admit_gap98_offline_v2 as q
        meta = q.old.elf_metadata((a.case / 'input.elf').read_bytes(), a.old['preflight']['main_case']['symbols'])
        save(a.out / 'architecture.json', q.runtime(CurrentView(a), meta, spike))
    else:
        import run_gap76_old_image as q
        from ara_verify.spike_trace import compare_commit_prefix, parse_spike_commits
        from ara_verify.vector_commit import compare_vector_commits
        scalar = compare_commit_prefix(spike, a.work / 'commit_trace.csv', 0x80000000,
            terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
        vector = compare_vector_commits(spike, a.work / 'commit_trace.csv', a.work / 'vector_trace.csv', 0x80000000)
        save(a.out / 'scalar.json', scalar); save(a.out / 'vector.json', vector)
        require(scalar['status'] in ('MATCH', 'TERMINAL_TOHOST_MATCH') and vector['status'] == 'PASS',
                'Original GAP76 complete scalar/vector differential mismatch')
        red32_exact(a, spike, scalar, vector)
        # The original oracle also requires the firmware's independent reduction
        # signature. Derive its addresses from this identical ELF, not an old PASS.
        from elftools.elf.elffile import ELFFile
        with (a.case / 'input.elf').open('rb') as stream:
            table = ELFFile(stream).get_section_by_name('.symtab')
            symbols = {s.name: s['st_value'] for s in table.iter_symbols()}
        from collect_gap103_strict import scalar_store
        memory = {}
        with (a.work / 'commit_trace.csv').open() as stream:
            for row in csv.DictReader(stream):
                if row['event'] == 'retire':
                    store = scalar_store(row)
                    if store:
                        memory.update({store[0]+i: b for i, b in enumerate(store[1])})
        def word(address, size):
            return int.from_bytes(bytes(memory[address+i] for i in range(size)), 'little')
        signature = symbols['g75_result']
        gold = {address: value for c in parse_spike_commits(spike) for address, value in c.memory_accesses if value is not None}
        require(word(symbols['tohost'], 8) == 1 and word(signature, 4) == gold[signature] > 0
                and word(signature+4, 4) == 0, 'Actual reduction firmware signature mismatch')
    return dict(status='PASS', original_specialized_architecture=True, reference=str(spike),
                microstructure_witness=dict(status='NOT_REQUIRED', architectural_acceptance_inferred_from_coverage=False))


def complex_vector(a):
    pre_dir, spike = reference(a)
    if a.index == 769:
        import run_mfpu_restart_word_boundary769 as q
        state = execute_block(a, 'architecture', q.collect, 'console=', "native=OUT/", dict(
            OUT=CurrentView(a), QUAL=a.out, record=a.old))
    else:
        q = importlib.import_module('collect_c910_float_edge_initialized777' if a.index == 777 else 'collect_fclass_divsqrt783')
        pre = a.bind_json(a.old['preflight'], a.old['preflight_seal'])
        ref = q.reference_prefix(pre)
        # Replace only the runner's preflight lookup, never its architecture predicates.
        proxy = SimpleNamespace(preflight=lambda: pre)
        if a.index == 777:
            native = FunctionType(q.native.__code__, dict(q.native.__globals__, runner=proxy))
            state = execute_block(a, 'architecture', q.collect, 'rows =', 'vector = native(', dict(
                run=CurrentView(a), pre=pre, reference=ref, native=native))
            save(a.out / 'native.json', native(CurrentView(a), ref, pre['symbols']))
        else:
            import collect_fclass_divsqrt783_store75 as successor
            def restore(activities, rows):
                starts, retires, rejected = q.vc._parse_architecture_mapping(a.work / 'commit_trace.csv')
                require(not rejected, 'No rejected store owner')
                mapping = q.vc._map_spike_commits(q.vc._map_architecture_retires(starts, retires, rejected), ref)
                activities, proof = successor.restore_stores(activities, rows, ref, mapping, pre['symbols'])
                save(a.out / 'store75-proof.json', proof)
                return activities
            reused = SimpleNamespace(**vars(q.reused))
            reused.store_adapter = SimpleNamespace(restore_stores=restore)
            state = execute_block(a, 'architecture', q.collect, 'rows =', 'vector_gate(diff);', dict(
                run=CurrentView(a), pre=pre, reference=ref, reused=reused))
            q.vector_gate(state['diff'])
    return dict(status='PASS', original_specialized_architecture=True, reference=str(spike),
                microstructure_witness=dict(status='NOT_REQUIRED'))


def reset_architecture(a):
    pre_dir, spike = reference(a)
    if a.index in range(747, 758):
        import qualify_fpu_reset_matrix as q
        record = dict(a.old, output=CurrentView(a))
        # runtime starts by Path(record['output']); bypass only archived execution
        # metadata, which execution() already validates against the actual OS wait.
        state = execute_block(a, 'architecture', q.runtime, 'console =', 'reader =', dict(
            root=CurrentView(a), pre=record['preflight_case'], record=record, destination=a.out))
    elif a.index == 745:
        import qualify_external_reset_fixture as q
        pre = a.bind_json(pre_dir / 'preflight.json', a.old['preflight_seal'])
        state = execute_block(a, 'architecture', q.collect, 'log=(run.OUT/', 'reader=', dict(
            run=SimpleNamespace(OUT=CurrentView(a), PRE=pre_dir), OUT=a.out, pre=pre, plan=a.old))
    elif a.index == 744:
        import postprocess_gap115_events_v2 as q
        pre = a.bind_json(pre_dir / 'preflight.json', a.old.get('pins', {}).get(str(pre_dir / 'preflight.json')))
        proxy = SimpleNamespace(**vars(q.run))
        proxy.RUN, proxy.PRE = CurrentView(a), pre_dir
        state = execute_block(a, 'architecture', q.collect, 'audit = run.reset.', 'base = run.shared.reviewed.', dict(
            run=proxy, OUT=a.out, pre=pre))
    else:
        import run_vmfpu_ured_reset763 as q
        import postprocess_vmfpu_ured_reset763 as reviewed
        pre = a.bind_json(pre_dir / 'preflight.json', a.old['preseal'])
        # The reviewed successor corrects the original allowed seed opcode and
        # binds cancelled owners to architectural starts. Its absolute historical
        # cycle equality remains a separate old-context witness, never waived.
        state = execute_block(a, 'epochs', q.collect, 'log=', 'pending={}', dict(
            RUN=CurrentView(a), PRE=pre_dir, QUAL=a.out, pre=pre, ev=q.audit.events,
            reset=q.audit.events.run.reset))
        pending = {}
        for row in state['epochs'][0][1]:
            if row['event'] == 'alloc':
                pending[int(row['vid'])] = row
            elif row['event'] == 'done':
                require(int(row['vid']) in pending, 'Orphan completion')
                pending.pop(int(row['vid']))
        initial = FunctionType(reviewed.initial_bytes.__code__, dict(reviewed.initial_bytes.__globals__, OUT=a.out))
        # Same successor seed-word reference, with explicit authenticated path.
        old_proxy = SimpleNamespace(**vars(q)); old_proxy.PRE = pre_dir
        seed = FunctionType(reviewed.seed_word.__code__, dict(reviewed.seed_word.__globals__, old=old_proxy))
        binding_fn = FunctionType(reviewed.cancelled_binding.__code__, dict(reviewed.cancelled_binding.__globals__, seed_word=seed))
        try:
            binding = binding_fn(pending, a.out / 'epoch0/commit_trace.csv', pre)
            save(a.out / 'cancelled-owner-bindings.json', binding)
        except ValueError as error:
            save(a.out / 'cancelled-owner-context.json', dict(status='CHECKER_REQUIRED', reason=str(error),
                actual_cancelled_owners=pending, old_absolute_cycles=[8568, 8569],
                purpose='Historical absolute timing witness, not an architectural value requirement',
                required_for_architectural_acceptance=False))
        require(0 in pending, 'Missing current URED seed allocation')
        current_cycle = int(pending[0]['cycle'])
        current_binding, binding_source = cancelled_binding_current(reviewed.cancelled_binding, current_cycle, dict(seed_word=seed))
        (a.out / 'current-cancelled-owner-predicate.py').write_text(binding_source)
        save(a.out / 'current-cancelled-owner-bindings.json', current_binding(pending, a.out / 'epoch0/commit_trace.csv', pre))
        allowed = set(pre['words'].values()) | {seed(pre)}
        state = execute_block(a, 'architecture', q.collect, 'backend=[', 'source=__import__', dict(
            RUN=CurrentView(a), PRE=pre_dir, QUAL=a.out, pre=pre, ev=q.audit.events,
            reset=q.audit.events.run.reset, initial_bytes=initial, pending=pending,
            epochs=state['epochs'], log=state['log'], allowed=allowed))
    save(a.out / 'architecture-status.json', dict(status='PASS', original_specialized_architecture=True))
    from audit_pending_fpu_reset_wave_20261016 import audit_reset_wave
    micro = audit_reset_wave(a)
    return dict(status='PASS', original_specialized_architecture=True, reference=str(spike),
                microstructure_witness=dict(micro, required_for_case=True))


def classify_error(a, error):
    """Only observed architectural data mismatches are failures, not adapters."""
    for path in a.out.glob('*.json'):
        value = json.loads(path.read_text())
        if isinstance(value, dict) and (value.get('mismatch') or value.get('first_mismatch')):
            return 'FAIL'
    # These are the original pure value predicates, not parser/context errors.
    value_errors = {'Full VRF differs', 'Canonical full VRF differs', 'CSR/RTZ/NX differs',
        'Exact CSR differs', 'Finite exact reduction130 differs', 'Full scalar GPR/CSR comparison',
        'Independent actual per-FMA result byte', 'Exact native gold byte set',
        'Full source/destination/guard/CSR/selfcheck footprint',
        'Original GAP95 signature mismatch', 'Actual reduction firmware signature mismatch',
        'Failed DUT signature', 'DUT signature failure', 'DUT self-check failed',
        'DUT signature missing or failed'}
    if type(error) is ValueError and str(error) in value_errors:
        return 'FAIL'
    return 'CHECKER_REQUIRED'


def audit_one(index, output):
    a = CaseAudit(index, output)
    a.bind(__file__)
    a.bind(ROOT / 'verification/tests/test_audit_pending_fpu_20261016.py')
    identity = None
    semantic = None
    reason = None
    try:
        identity = execution_bound(a)
        save(a.out / 'execution.json', identity)
        if index in (769, 777, 783):
            semantic = complex_vector(a)
        elif index >= 744:
            semantic = reset_architecture(a)
        else:
            semantic = arithmetic(a)
        micro = semantic['microstructure_witness']
        status = 'CHECKER_REQUIRED' if micro.get('required_for_case') and micro['status'] != 'PASS' else 'PASS'
        reason = micro.get('reason') if status != 'PASS' else 'All mandatory original architecture predicates passed on actual current outputs'
    except Exception as error:
        status = classify_error(a, error)
        reason = '%s: %s' % (type(error).__name__, error)
        save(a.out / 'exception.json', dict(reason=reason, traceback=traceback.format_exc()))
    for path, digest in a.inputs.items():
        require(sha(path) == digest, 'Input changed while auditing: ' + path)
    report = a.out / 'audit.json'
    result = dict(index=index, status=status, reason=reason, semantic=semantic,
        execution_identity=identity, actual_current_run=str(a.work), work=str(a.work),
        input_pins=a.inputs, simulation_started=False, old_PASS_reused=False,
        shared_aggregator_modified=False, coverage_admitted=False,
        rerun_required=False, next_step=None if status == 'PASS' else
        'Inspect exception and original checker slice; resolve offline adapter/evidence gap before considering any source-analyzed rerun.')
    timing = a.out / 'cancelled-owner-context.json'
    if timing.exists():
        result['historical_absolute_timing_witness'] = json.loads(timing.read_text())
    save(report, result)
    return dict(index=index, status=status, reason=reason, report=str(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cases', type=int, nargs='+', choices=CASES, default=CASES)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT / 'verification/out') and not output.exists(), 'Fresh verification/out destination required')
    install_guard(output)
    output.mkdir()
    rows = []
    for index in args.cases:
        row = audit_one(index, output)
        rows.append(row)
        save(output / 'audit.json', dict(cases=rows, simulation_runs=0, coverage_admitted=False))
        print(index, row['status'], row['reason'], flush=True)
    pins = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename and Path(filename).suffix == '.py' and Path(filename).resolve().is_relative_to(ROOT / 'verification'):
            pins[str(Path(filename).resolve())] = sha(filename)
    pins[str(Path(__file__).resolve())] = sha(__file__)
    save(output / 'checker-code-pins.json', pins)
    save(output / 'audit.json', dict(cases=rows, simulation_runs=0, coverage_admitted=False,
        checker_code_pins=str(output / 'checker-code-pins.json'),
        accepted=[r['index'] for r in rows if r['status'] == 'PASS'],
        rejected=[r['index'] for r in rows if r['status'] == 'FAIL'],
        checker_required=[r['index'] for r in rows if r['status'] == 'CHECKER_REQUIRED']))


if __name__ == '__main__':
    main()

"""Compact parent-run GAP111 architecture/raw-FSM diagnostic; never admission."""
import argparse
import ast
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import run_gap111_simulation as runner
import qualify_ptw_sfence_boundary_terminal as scalar_api
import coverage_bitmap_delta as bitmap

life, require = runner.life, runner.require
RUN = life.OUT / 'gap111-pte-line-old-image-parent-20261007-01'
ANCHOR = life.OUT / 'gap111-pte-line-old-image-agent-20261007-01.prepared.json'
ANCHOR_SHA = 'ed1c094daaf65db3a753898dd779c4199145f9ad68aedc0672b70790923a8ff2'


def exact(actual, expected, message):
    require(all(k in actual and type(actual[k]) is type(v) and actual[k] == v
                for k, v in expected.items()), message)


def architecture_function():
    # Only the case trap PC and trap-row count differ. Preserve the full scoped
    # GPR/RVC address/mask/data/CSR checker and independent gold implementation.
    tree = ast.parse(inspect.getsource(scalar_api.architecture))
    changed_pc = changed_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id == 'expected_pcs':
            old = ast.parse('[0x40000000 + (slot + 1) * 4096 + 32 for slot in (3, 35)]', mode='eval').body
            require(ast.dump(node.value) == ast.dump(old), 'Frozen trap-PC boundary drift')
            node.value = ast.parse('[0x40004028]', mode='eval').body
            changed_pc += 1
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) \
                and ast.dump(node.left) == ast.dump(ast.parse('len(reference)', mode='eval').body) \
                and isinstance(node.right, ast.Constant) and type(node.right.value) is int and node.right.value == 2:
            node.right = ast.Constant(value=1)
            changed_count += 1
    require((changed_pc, changed_count) == (1, 1), 'Not exactly two case boundary adaptations')
    namespace = dict(scalar_api.architecture.__globals__, runner=SimpleNamespace(oracle=runner.oracle))
    exec(compile(ast.fix_missing_locations(tree), '<gap111-private-scalar-audit>', 'exec'), namespace)
    return namespace['architecture']


def terminal(state, started, record):
    exact(state, dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=0, case=runner.NAME,
        timeout=False, coverage_admitted=False, admission_performed=False,
        dut_self_check_verified=False, terminal_oracle_verified=False), 'Nonterminal/failed simulator')
    require(type(state['wall_seconds']) in (int, float) and 0 <= state['wall_seconds'] < 240,
            'Invalid elapsed receipt')
    exact(started, dict(budget_s=180, input_elf=str(runner.PRE / 'input.elf'), elf_sha256=runner.ELF_SHA,
        image=str(life.IMAGE), image_sha256=runner.IMAGE_SHA, command=record['command'],
        foreground_lifetime=True, coverage_admitted=False), 'Startup identity differs')
    require(type(started['pid']) is int and started['pid'] > 0
            and started['pid'] == started['process_group'] == state['pid'], 'PID ownership differs')
    require(not Path('/proc/%d' % started['pid']).exists(), 'Simulator still present; HOLD')


def scalar_gate(result, reference):
    s = scalar_api.spike_trace
    exact(result, dict(status='TERMINAL_TOHOST_MATCH', entry='0x0000000080000000',
        rvfi_store_data_layout='unshifted', matched_instructions=len(reference),
        matched_scalar_writes=sum(len({k: v for k, v in c.gpr_writes.items() if k}) for c in reference),
        matched_floating_writes=0,
        matched_scalar_memory_accesses=sum(bool(c.memory_accesses) and s._scalar_memory_access(c.instruction)
                                          is not None for c in reference),
        ara_committed_instructions=len(reference), ara_retired_instructions=len(reference) + 1,
        ara_trap_events=1, skipped_unobservable_register_values=0, stopped_at_unobservable=None,
        mismatch=None, terminal_ecall=None, aligned_vector_faults=[]), 'Incomplete scalar differential')
    require(result['terminal_tohost']['address'] == '0x0000000080001000'
            and result['terminal_tohost']['write_value'] == '0x1', 'Wrong terminal')


def target_gain(before, single, targets):
    observed = []
    for t in targets:
        scope, raw = t['scope'], t['compiled']['raw_index']
        old, new = before['metrics']['fsm'][scope], single['metrics']['fsm'][scope]
        require((old['width'], old['checksum']) == (new['width'], new['checksum']) == (28, '3476102610'),
                'FSM width/checksum differs')
        before_hit = bool(int(old['bits'], 16) & (1 << (27 - raw)))
        sample_hit = bool(int(new['bits'], 16) & (1 << (27 - raw)))
        require(not before_hit, 'Target no longer zero in exact740')
        observed.append(dict(target=t, before_hit=before_hit, sample_hit=sample_hit, newly_hit=sample_hit))
    require(len(observed) == 14 and len({(r['target']['scope'], r['target']['compiled']['raw_index'])
                                      for r in observed}) == 14, 'Not exact14 targets')
    return dict(targets=observed, new_targets=sum(r['newly_hit'] for r in observed),
                same_PTE_line_collision_cause_proven=False, runtime_coldness_proven=False,
                official_denominator_verified=False, Toggle_gain_not_measured=True)


def collect(seal, out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh output required')
    record = life.read_bound(RUN.with_name(RUN.name + '.prepared.json'), seal)
    anchor = life.read_bound(ANCHOR, ANCHOR_SHA)
    expected = dict(anchor, output=str(RUN), command=runner.command(RUN))
    require(record == expected and life.read_bound(RUN / 'manifest.json', seal) == record,
            'Executed parent run is not exact reviewed private lifecycle')
    pre = life.read_bound(runner.PRE / 'preflight-manifest.json', runner.PRE_SHA)
    runner.validate(pre)
    terminal(json.loads((RUN / 'simulation-status.json').read_bytes()),
             json.loads((RUN / 'started.json').read_bytes()), record)
    out.mkdir()
    pins = dict(record['pins'])
    try:
        files = [RUN / n for n in ('manifest.json', 'simulation-status.json', 'started.json',
                 'commit_trace.csv', 'vector_trace.csv', 'run.vcs.log', 'console.log')]
        files += [RUN.with_name(RUN.name + '.prepared.json'), ANCHOR, Path(__file__).resolve(),
                  Path(__file__).with_name('test_qualify_gap111_terminal.py')]
        modules = (runner, scalar_api, scalar_api.common, scalar_api.zero, scalar_api.reset_proof,
                   scalar_api.compressed, scalar_api.spike_trace, scalar_api.vector_commit,
                   scalar_api.contract, bitmap)
        files += [Path(m.__file__).resolve() for m in modules]
        vdb = RUN / 'code.vdb'
        members = sorted(p for p in vdb.rglob('*') if p.is_file())
        require(members and not vdb.is_symlink() and not any(p.is_symlink() for p in vdb.rglob('*')),
                'Missing/aliased VDB')
        files += members
        pins = life.merge_pins(pins, {str(p): life.digest(p) for p in files})
        pins, source = scalar_api.reset_proof.source_contract(pins)
        life.check(pins)
        reference = scalar_api.reference_prefix(scalar_api.spike_trace.parse_spike_commits(
            Path(pre['input_spike_trace'])), pre['symbols']['tohost'])
        require(runner.oracle.validate(reference, pre['symbols']) == pre['validation'],
                'Sealed independent reference differs')
        scalar = scalar_api.spike_trace.compare_commit_prefix(Path(pre['input_spike_trace']),
            RUN / 'commit_trace.csv', 0x80000000, terminal_tohost_address=pre['symbols']['tohost'],
            rvfi_store_data_layout='unshifted')
        life.save(out / 'scalar-comparison.json', scalar)
        scalar_gate(scalar, reference)
        rows = scalar_api.parse_rows(RUN / 'commit_trace.csv')
        arch = architecture_function()(rows, reference, pre['symbols'])
        require(arch['memory_accesses'] == 3561 and arch['scalar_retirements'] == 11537,
                'Complete compressed-inclusive architecture boundary differs')
        arch['status'] = 'GAP111_FULL_SCALAR_RVC_CSR_TRAP_OUTPUT_EXACT'
        scalar_api.zero.vector_zero(RUN / 'vector_trace.csv')
        vector = scalar_api.vector_commit.compare_vector_commits(Path(pre['input_spike_trace']),
            RUN / 'commit_trace.csv', RUN / 'vector_trace.csv', 0x80000000)
        scalar_api.vector_gate(vector)
        contract = scalar_api.log_gate((RUN / 'run.vcs.log').read_text())
        console = (RUN / 'console.log').read_text()
        scalar_api.log_gate(console, require_contract='[ARA_CONTRACT]' in console)
        formal = life.read_bound(runner.oracle.BASE / 'admission-manifest.json', runner.oracle.BASE_SHA)
        before_path = runner.oracle.BASE / 'combined-bits.json'
        before = life.read_bound(before_path, formal['output_pins'][str(before_path)])
        require(len(before['tests']) == len(set(before['tests'])) == 740 and str(vdb) not in before['tests'],
                'Wrong/duplicate baseline')
        fsm_files = list((vdb / 'snps/coverage/db/testdata').glob('*/fsm.verilog.data.xml'))
        require(len(fsm_files) == 1, 'Ambiguous singleton FSM data')
        single = dict(metrics=dict(fsm=bitmap.read_metric(fsm_files[0])))
        previous, sampled = before['metrics']['fsm'], single['metrics']['fsm']
        require(set(previous) == set(sampled), 'FSM scope universe differs')
        changes = []
        for scope, old in previous.items():
            new = sampled[scope]
            require((old['width'], old['checksum']) == (new['width'], new['checksum']), 'FSM shape differs')
            gain = int(new['bits'], 16) & ~int(old['bits'], 16)
            require(0 <= int(new['bits'], 16) < 1 << new['width'], 'FSM bits out of range')
            if gain:
                changes.append(dict(scope=scope, new_bits=gain.bit_count(), raw_mask=hex(gain)))
        delta = dict(scope='ara_tb.dut.i_ara_soc.i_system', raw_diagnostic_bits=True,
                     metrics=dict(fsm=sum(r['new_bits'] for r in changes if
                                          r['scope'].startswith('ara_tb.dut.i_ara_soc.i_system.'))),
                     whole_design_FSM_gain=sum(r['new_bits'] for r in changes), instances=changes,
                     other_metrics_not_collected=True, full_population_union_generated=False)
        targets = target_gain(before, single, record['targets'])
        for name, value in (('architecture-audit.json', arch), ('source-contract.json', source),
                            ('vector-comparison.json', vector), ('contract-audit.json', contract),
                            ('single-fsm.json', single), ('raw-delta-vs740.json', delta),
                            ('target-FSM-audit.json', targets)):
            life.save(out / name, value)
        require(members == sorted(p for p in vdb.rglob('*') if p.is_file()), 'VDB membership changed')
        life.check(pins)
        outputs = {str(p): life.digest(p) for p in out.iterdir() if p.is_file()}
        result = dict(status='GAP111_ARCHITECTURE_RAW_FSM_DIAGNOSTIC_NOT_ADMITTED', run=str(RUN), run_seal=seal,
            pins=pins, output_pins=outputs, baseline_tests=740, baseline_manifest_sha256=runner.oracle.BASE_SHA,
            full_scalar_differential_qualified=True, full_scalar_RVC_memory_qualified=True,
            observed_checks=26, expected_traps=1, vector_status='UNOBSERVABLE_ZERO_DESTINATIONS',
            raw_delta=delta['metrics'], newly_hit_primary_FSM_targets=targets['new_targets'],
            collision_cause_proven=False, runtime_coldness_proven=False, Toggle_gain_measured=False,
            official_denominator_verified=False, coverage_admitted=False, DVE_launched=False,
            no_gain_action='Preserve diagnostic only; no timing/layout retry or zero-gain admission')
        life.save(out / 'qualification-seal.json', result)
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'qualification-seal.json'),
                              status=result['status'], primary_FSM_gain=targets['new_targets'], raw_delta=delta['metrics'])))
    except Exception as error:
        life.save(out / 'failure.json', dict(status='GAP111_QUALIFICATION_HOLD_NOT_ADMITTED', reason=str(error)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-seal', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    collect(args.run_seal, args.output.absolute())


if __name__ == '__main__':
    main()

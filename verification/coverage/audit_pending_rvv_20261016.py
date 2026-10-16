#!/usr/bin/env python3
"""Rebind nine original RVV semantic oracles to the completed current-image runs.

Only pure architecture/lifecycle functions are called. Historical simulation,
admission and bitmap-gain functions are deliberately not invoked.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import importlib
import json
from pathlib import Path
import sys
import traceback
from types import FunctionType

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'verification'), str(Path(__file__).resolve().parent),
               str(ROOT / 'hardware/fpga/ara_dsa_vcu118/software/vendor/pyelftools-0.32-py3-none-any.whl')]
from audit_probe_semantics_20261015 import CaseAudit, BUILD, read, require, save, sha

CASES = (730, 739, 743, 762, 767, 774, 775, 796, 797)


def current_gather_source_proof(a):
    """Authenticate the current build, not the old checker's source-book epoch."""
    import collect_gather_war797_successor as q
    a.bind(q.g.__file__, q.ORIGINAL_SHA)
    book = a.bind_json(BUILD / 'build-source-pins.json')
    code = {}
    for relative in ('hardware/src/ara_sequencer.sv', 'hardware/src/lane/operand_requester.sv',
                     'hardware/src/ara_system.sv', 'hardware/tb/ara_commit_monitor.sv'):
        path = ROOT / relative
        code[relative] = a.bind(path, book[str(path)]).read_text()
    requester = code['hardware/src/lane/operand_requester.sv']
    require('verify_wb_id_o[2]    = masku_result_id;' in requester and
            'verify_wb_wdata_o[2] = masku_result_wdata;' in requester and
            'ldu_result_gnt, sldu_result_gnt, masku_result_gnt,' in requester,
            'Current accepted-write MASKU producer mapping differs')
    require('[VRGATHER:VCOMPRESS]:\n        for (int i = 0; i < NrVFUs; i++)\n'
            "          if (i == VFU_Alu || i == VFU_MaskUnit) target_vfus[i] = 1'b1;"
            in code['hardware/src/ara_sequencer.sv'], 'Current Gather route differs')
    require('assign verify_wb_valid[lane] = i_ara.gen_lanes[lane].i_lane.verify_wb_valid_o;'
            in code['hardware/src/ara_system.sv'] and
            'for (int unsigned source = 0; source < 5; source++)' in code['hardware/tb/ara_commit_monitor.sv'] and
            'cycle_q, uop_arch_seq_q[id], id, lane, source,' in code['hardware/tb/ara_commit_monitor.sv'],
            'Current final-accepted write monitor mapping differs')
    return dict(actual_current_build=True, gather_producer=2, identity_transport_producer=3,
                old_source_hash_gate_reused=False, numerical_predicates_unchanged=True)


def execution(a):
    from ucli_runtime_log_20261015 import iter_runtime_lines
    from replay_historical_extensions_20261015 import RAW_FAIL
    from ara_verify.runner import FAIL_RE, SUCCESS_RE
    from ara_verify.contract import check_contract_log
    from ara_verify.trace import validate_trace
    receipt = a.bind_json(a.case / 'simulation-exit.json')
    require(receipt['executed'] is True and type(receipt['returncode']) is int and
            receipt['returncode'] == 0 and receipt['timed_out'] is False and
            receipt['cancelled'] is False, 'Successful actual OS wait required')
    require(receipt['command'] == a.plan['command'] and receipt['cwd'] == str(a.work)
            and receipt['pid'] > 0 and receipt['finished'] > receipt['started'], 'Execution binding differs')
    image = a.bind_json(BUILD / 'build-image.json')
    require(a.plan['command'][0] == str(BUILD / 'sim/simv'), 'Wrong image path')
    a.bind(a.plan['command'][0], image[a.plan['command'][0]])
    a.bind(a.case / 'input.elf', a.plan['elf_sha256'])
    sources = {str(p): a.bind(p, a.plan['pins'][str(p)]).read_text()
               for p in (a.case / 'ucli').glob('*.tcl')}
    runtime = a.out / 'runtime'
    runtime.mkdir()
    for name, path in [('console.log', a.case / 'console.log'), ('run.vcs.log', a.work / 'run.vcs.log')]:
        with a.bind(path).open(errors='replace') as stream:
            text = ''.join(iter_runtime_lines(stream, sources)) if sources else stream.read()
        require(not RAW_FAIL.search(text) and not FAIL_RE.search(text), 'Runtime diagnostic: ' + name)
        require(len(SUCCESS_RE.findall(text)) == 1, 'One actual firmware success required')
        target = runtime / name
        target.write_text(text)
        require(not check_contract_log(target), 'Protocol contract errors')
    for name in ('commit_trace.csv', 'vector_trace.csv'):
        a.bind(a.work / name)
    return dict(actual_wait=receipt, trace=validate_trace(a.work / 'commit_trace.csv'),
                current_image_sha256=image[a.plan['command'][0]], original_PASS_reused=False)


def prefix(reference, tohost):
    from ara_verify.spike_trace import parse_spike_commits
    result = []
    for c in parse_spike_commits(reference):
        if not result and c.pc != 0x80000000:
            continue
        result.append(c)
        if c.memory_accesses == ((tohost, 1),):
            break
    require(result and result[-1].memory_accesses == ((tohost, 1),), 'Independent reference terminal missing')
    return result


def run_semantics(a):
    import collect_opivx_vsbc_strict as common
    from ara_verify.spike_trace import compare_commit_prefix
    from ara_verify.vector_commit import compare_vector_commits

    prevalue = a.old['preflight']
    if isinstance(prevalue, dict):
        pre = prevalue
        original = Path(next(x.split('=', 1)[1] for x in a.plan['original_command'] if x.startswith('+PRELOAD=')))
        pre_dir = original.parent
    else:
        path = Path(prevalue)
        if path.is_dir():
            pre_dir = path
            pre = {}
        else:
            pre_dir = path.parent
            pre = a.bind_json(path, a.old['preflight_seal'])
    symbols = pre.get('symbols')
    if symbols is None:
        symbols = a.bind_json(pre_dir / 'symbols.json')
    reference = Path(pre.get('reference', pre.get('input_spike_trace', pre_dir / 'spike.trace')))
    if not reference.is_file():
        reference = pre_dir / 'spike.log'
    expected = pre.get('pins', pre.get('input_pins', {})).get(str(reference),
                 a.old.get('pins', {}).get(str(reference)))
    a.bind(reference, expected)
    original = Path(next(x.split('=', 1)[1] for x in a.plan['original_command'] if x.startswith('+PRELOAD=')))
    a.bind(original, a.plan['elf_sha256'])
    ref = prefix(reference, symbols['tohost'])
    rows = common.read_csv((a.work / 'commit_trace.csv').read_bytes(), common.COMMIT_FIELDS)
    vectors = common.read_csv((a.work / 'vector_trace.csv').read_bytes(), common.VECTOR_FIELDS)
    scalar = compare_commit_prefix(reference, a.work / 'commit_trace.csv', 0x80000000,
                                  terminal_tohost_address=symbols['tohost'], rvfi_store_data_layout='unshifted')
    save(a.out / 'scalar-comparison.json', scalar)
    common.scalar_exact(scalar, common.reference_counts(ref, symbols))
    if a.index == 730:
        import qualify_pure_war_parent_terminal as q
        control = q.lifecycle(rows, vectors, symbols)
        signature = q.observed(rows, symbols)
        vector = compare_vector_commits(reference, a.work / 'commit_trace.csv', a.work / 'vector_trace.csv', 0x80000000)
        q.vector_exact(vector, ref)
        vc = q.common.vc if hasattr(q.common, 'vc') else importlib.import_module('ara_verify.vector_commit')
        _, _, activities = vc._parse_vector_trace(a.work / 'vector_trace.csv')
        starts, retires, rejected = vc._parse_architecture_mapping(a.work / 'commit_trace.csv')
        mapping = vc._map_spike_commits(vc._map_architecture_retires(starts, retires, rejected), ref)
        native = q.native_exact(activities, mapping, ref)
    elif a.index == 739:
        import qualify_queue_mask_source_lifetime_terminal as q
        control = q.lifecycle(rows, vectors)
        signature = q.observed(rows, symbols)
        native = q.native(a.work, ref, symbols)
        vector = None  # Original exact native-state/set-valued mask oracle replaces a bit-exact tail comparison.
    elif a.index == 743:
        import collect_rvv_lmul8_payload_walk as q
        control = q.lifecycle(rows, vectors)
        signature = q.footprint(rows, symbols, original.read_bytes())
        vector = compare_vector_commits(reference, a.work / 'commit_trace.csv', a.work / 'vector_trace.csv', 0x80000000)
        require(vector['status'] == 'PASS' and vector['skipped_unknown_bytes'] == 0 and
                vector['compared_instructions'] >= 24 and vector['compared_bytes'] > 0, 'Complete strict vector comparison')
        native = dict(original_gate='collect_rvv_lmul8_payload_walk', complete_vector_diff=True)
    elif a.index == 762:
        import qualify_operand_mask_data_02_defined as q
        _, parsed, terminal = q.q.prefix((a.work / 'commit_trace.csv').read_bytes())
        require(len(parsed) == len(rows), 'No truncated current execution accepted')
        whole, memory, reads = q.q.full_scalar(parsed, ref, symbols)
        signature = q.q.independent_actual(memory, reads, symbols)
        control = q.q.lifecycle(parsed, vectors)
        vector = compare_vector_commits(reference, a.work / 'commit_trace.csv', a.work / 'vector_trace.csv', 0x80000000)
        native = q.policy_audit(a.work / 'commit_trace.csv', a.work / 'vector_trace.csv', vector)
    elif a.index == 767:
        import run_stride_metadata767 as q
        control = q.lifecycle(rows, vectors)
        signature = q.observed(rows, symbols)
        vector = compare_vector_commits(reference, a.work / 'commit_trace.csv', a.work / 'vector_trace.csv', 0x80000000)
        q.vector_gate(vector, ref)
        native = dict(actual_VL1_strided_operations=control['actual_VL1_strided_operations'])
    else:
        modules = {774: 'collect_vmacc_c_fifo773', 775: 'collect_vfirst_long_mask',
                   796: 'collect_vsmul_saturation796', 797: 'gather_war797'}
        q = importlib.import_module(modules[a.index])
        control_module = q.mature.control if a.index == 797 else q.control
        control = control_module.lifecycle(rows, vectors)
        if a.index in (796, 797):
            signature = q.footprint(rows, symbols, ref)
        else:
            signature = q.footprint(rows, symbols)
        if a.index == 774:
            vector, native = q.native(a.work, ref)
        elif a.index == 775:
            native = q.native(a.work, ref, symbols)
            vector = None
        elif a.index == 796:
            native = q.native(a.work, ref, symbols, pre)
            vector = None
        else:
            from collect_gather_war797_successor import corrected_native
            # Replace only the source-epoch verifier with an explicit current-build
            # proof. The previously reviewed native algorithm and fixes are kept.
            proof = current_gather_source_proof(a)
            rebound = FunctionType(corrected_native.__code__,
                dict(corrected_native.__globals__, source_pins=lambda: proof))
            native = rebound()(a.work, ref, symbols, pre)
            save(a.out / 'current-monitor-proof.json', proof)
            vector = None
        memory_module = q.mature.memory if a.index == 797 else q.memory
        memory_proof = memory_module.scalar_memory_exact(rows, ref)
        save(a.out / 'scalar-memory.json', memory_proof)
    for name, value in [('lifecycle', control), ('footprint', signature), ('native', native), ('vector-comparison', vector)]:
        save(a.out / (name + '.json'), value)
    return dict(reference=str(reference), reference_retirements=len(ref), full_scalar=True,
                original_specialized_native_oracle=True, coverage_gain_claimed=False)


def audit_case(index, output):
    a = CaseAudit(index, output)
    adapter_sha = sha(__file__)
    try:
        common = execution(a)
        save(a.out / 'execution.json', common)
        semantic = run_semantics(a)
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).is_file() and Path(path).resolve().is_relative_to(ROOT / 'verification'):
                a.bind(Path(path).resolve())
        a.bind(__file__, adapter_sha)
        for path, digest in a.inputs.items():
            require(sha(path) == digest, 'Evidence changed during audit: ' + path)
        status, reason = 'PASS', None
    except Exception as error:
        status = 'CHECKER_REQUIRED'
        reason = f'{type(error).__name__}: {error}'
        semantic = dict(traceback=traceback.format_exc())
    result = dict(index=index, status=status, reason=reason, semantic=semantic,
                  input_pins=a.inputs, actual_current_run=str(a.work), simulation_started=False,
                  old_PASS_reused=False, coverage_admitted=False)
    save(a.out / 'audit.json', result)
    return dict(index=index, status=status, reason=reason, report=str(a.out / 'audit.json'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cases', type=int, nargs='+', choices=CASES, default=CASES)
    parser.add_argument('--jobs', type=int, default=3, choices=range(1, 5))
    args = parser.parse_args()
    require(len(set(args.cases)) == len(args.cases), 'Duplicate requested case')
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(audit_case, index, args.output) for index in args.cases]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            save(args.output / 'audit.json', dict(cases=sorted(results, key=lambda r: r['index'])))
            print(result['index'], result['status'], result['reason'], flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Prepare a frozen compute-only seed gate; execution needs separate review.

No service is launched here. After review, a long-lived independent service may
own --execute-reviewed directly. Its fresh worker/ evidence never overwrites
the immutable preparation receipt. This is not a performance or ISA gate.
"""
import argparse
import ast
from collections import defaultdict
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
QBS = ROOT / 'verification/qbs'
RUNS = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
OUT = RUNS / 'e2e_balanced_seed_20261106_01'
PARENT = RUNS / 'e2e_balanced_compute_20261106_01'
PARENT_SHA = 'a7ccf4376c736101c76659330999b633eed9985c943bc5cd5516bbc465a88b0d'
EDGES = RUNS / 'e2e_mixed_scale_edges_20261106_01'
EDGES_SHA = '7bede0e75550725d6755f680e7d296ed7c913b6c49d5fca60f2fd3d65357440a'
RAW36 = EDGES / 'original-generator-default.txt'
RAW36_SHA = '0df880f9f7d4e08ac1a3549caa913430254fd35eecabd38d7fad428a7ad0947f'
TB = QBS / 'qbs_compute_engine_tb.sv'
CONTINUATION = QBS / 'run_compute_continuation.py'
TB_SHA = '4f015ccd233d78fe07607af1a5a9bf3a10a96709126d906522235f75fc49b476'
CONTINUATION_SHA = '3e91143342eb722678e1195119804edadae685cd66b7dd90b23c0f416a3b2a0c'
FROZEN_C = {
    QBS / 'qbs_command_vectors.c': 'da2ac980cdcc9ec97cdc06d72511b4a708f0bc9ff5ca3226027411551be34c2e',
    QBS / 'qbs_ref.c': 'adf815ed88e50d3f9d23dbb8fab2baa959d8d5aaebcd6f15cbd7a347678f423a',
    QBS / 'qbs_ref.h': 'bee076dc0d1ee7a154ed3dc837a1bcd1d77bd57fec8c3099e13eb0e58d733928',
    ROOT / 'apps/common/qbs_abi.h': '691fcc9c0a674193c5f4879e43e9fb72404e822a39dd6037444ae75a2387dada',
}
OWNED = ('balanced_seed_gate.py', 'test_balanced_seed_gate.py')
COUNTERS = ('tiles', 'weight', 'activation', 'pairs', 'capacity', 'dot', 'uops', 'updates')
PREPARED = 'BALANCED_SEED_INPUTS_PREPARED_NOT_EXECUTED'
SUCCESS = 'BALANCED_NONZERO_SEED_CONTINUATION_CANCEL_RECOVERY_FUNCTIONAL_PASS'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    return sha(Path(path).read_bytes())


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def inherited_bench(template, helper):
    """Execute the original bench_source body, not its imports/main/EDA driver."""
    require(sha(template.encode()) == TB_SHA and sha(helper.encode()) == CONTINUATION_SHA,
            'Exact original continuation helper and compute TB required')
    tree = ast.parse(helper)
    declarations = [node for node in tree.body if isinstance(node, ast.Assign) and
                    any(isinstance(target, ast.Name) and target.id == 'DECLARATIONS' for target in node.targets)]
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'bench_source']
    require(len(declarations) == len(functions) == 1, 'Original continuation definitions ambiguous')
    namespace = {'DECLARATIONS': ast.literal_eval(declarations[0].value)}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(CONTINUATION), 'exec'), namespace)
    return namespace['bench_source'](template)


OBSERVATIONS = '''
  int bsg_case=-1,bsg_k=0,bsg_m=0,bsg_n=0,bsg_kb=0;
  int bsg_requests[128],bsg_fmas[128],bsg_seeds[128];
  int bsg_checkpoints=0,bsg_nonzero=0;
  bit bsg_normal=0;
  function automatic bit bsg_active(input int acc);
    return acc/(bsg_m>4?16:32)<bsg_m && acc%(bsg_m>4?16:32)<bsg_n;
  endfunction
  task automatic bsg_checkpoint;
    int nz;
    nz=0;
    for(int acc=0;acc<128;acc++) if(bsg_active(acc)) begin
      if($isunknown(checkpoint[acc]) || checkpoint[acc][30:23]==8'hff)
        $fatal(1,"BSG_BAD_CHECKPOINT");
      if(checkpoint[acc][30:0]!=0) nz++;
      bsg_checkpoints++;
      $display("BSG_CHECKPOINT case=%0d k=%0d acc=%0d bits=%08h",bsg_case,bsg_k+1,acc,checkpoint[acc]);
    end
    bsg_nonzero+=nz;
    if(bsg_m==4 && nz==0) $fatal(1,"BSG_ZERO_M4_CHECKPOINT");
  endtask

  always @(posedge clk) begin : bsg_monitor
    int acc,k,slot,row_copy;
    logic [7:0] mask_copy;
    logic [31:0] data_copy[8];
    if(rst_n && bsg_normal) begin
      if($isunknown({command_ready,weight_ready,activation_ready,result_valid,busy,
          fault_done,result_fflags,tiles_computed,weight_bytes,activation_bytes,
          useful_pairs,pair_capacity,dot_active_cycles,fp_uops,accumulator_updates,
          seed_valid,seed_ready,seed_done,dut.fp_request_ready,dut.integer_result_valid,
          dut.integer_busy,dut.fp_busy,dut.i_fp_accumulator.fp_fire,
          dut.i_fp_accumulator.request_valid_i,dut.i_fp_accumulator.request_ready_o}))
        $fatal(1,"BSG_UNKNOWN_CONTROL");
      if(dut.i_fp_accumulator.request_valid_i && dut.i_fp_accumulator.request_ready_o) begin
        if($isunknown({dut.i_fp_accumulator.request_accumulator_index_i,
                       dut.i_fp_accumulator.request_first_block_i})) $fatal(1,"BSG_UNKNOWN_REQUEST");
        acc=int'(dut.i_fp_accumulator.request_accumulator_index_i);
        if(!bsg_active(acc) || bsg_requests[acc]>=bsg_kb ||
            dut.i_fp_accumulator.request_first_block_i !== (bsg_requests[acc]==0) ||
            (split_k && bsg_requests[acc]!=bsg_k)) $fatal(1,"BSG_FIRST_BLOCK_OR_OWNER");
        $display("BSG_REQUEST case=%0d acc=%0d k=%0d first=%0d",bsg_case,acc,bsg_requests[acc],
          dut.i_fp_accumulator.request_first_block_i);
        bsg_requests[acc]++;
      end
      if(dut.i_fp_accumulator.fp_fire) begin
        slot=int'(dut.i_fp_accumulator.fp_tag_in);
        if($isunknown({dut.i_fp_accumulator.fp_tag_in,
                       dut.i_fp_accumulator.entry_state_q[slot],
                       dut.i_fp_accumulator.entry_accumulator_index_q[slot]})) $fatal(1,"BSG_UNKNOWN_FMA");
        if(int'(dut.i_fp_accumulator.entry_state_q[slot]) inside {4,5}) begin
          acc=int'(dut.i_fp_accumulator.entry_accumulator_index_q[slot]);
          k=bsg_fmas[acc]-(int'(dut.i_fp_accumulator.entry_state_q[slot])==5?1:0);
          if(!bsg_active(acc) || k<0 || k>=bsg_kb ||
              $isunknown(dut.i_fp_accumulator.fp_operands)) $fatal(1,"BSG_FMA_OWNER");
          if(int'(dut.i_fp_accumulator.entry_state_q[slot])==4) begin
            if(split_k && k>0 && dut.i_fp_accumulator.fp_operands[2] !== checkpoint[acc])
              $fatal(1,"BSG_RESTORED_ADDEND_CHANGED");
            bsg_fmas[acc]++;
          end
          $display("BSG_ACCUM case=%0d acc=%0d k=%0d state=%0d a=%08h b=%08h c=%08h",
            bsg_case,acc,k,int'(dut.i_fp_accumulator.entry_state_q[slot]),
            dut.i_fp_accumulator.fp_operands[0],dut.i_fp_accumulator.fp_operands[1],
            dut.i_fp_accumulator.fp_operands[2]);
        end
      end
      if(seed_valid && seed_ready) begin
        row_copy=int'(seed_row);mask_copy=seed_mask;data_copy=seed_data;
        if(!split_k || bsg_k==0 || $isunknown({seed_row,seed_mask}) || seed_mask==0 ||
            dut.i_fp_accumulator.raw_seed_fire !== 1'b1)
          $fatal(1,"BSG_UNEXPECTED_SEED");
        for(int bank=0;bank<8;bank++) if(mask_copy[bank]) begin
          acc=row_copy*8+bank;
          if(!bsg_active(acc) || data_copy[bank] !== checkpoint[acc]) $fatal(1,"BSG_SEED_PAYLOAD_CHANGED");
          bsg_seeds[acc]++;
        end
        #1;
        for(int bank=0;bank<8;bank++) if(mask_copy[bank]) begin
          acc=row_copy*8+bank;
          if(dut.i_fp_accumulator.accumulator_valid_q[acc] !== 1'b1 ||
              dut.i_fp_accumulator.accumulator_data_q[bank][row_copy] !== data_copy[bank])
            $fatal(1,"BSG_SEED_NOT_WRITTEN");
          $display("BSG_SEED case=%0d k=%0d acc=%0d bits=%08h",bsg_case,bsg_k,acc,data_copy[bank]);
        end
      end
    end
  end
  initial begin #200000000;$fatal(1,"BSG_WATCHDOG");end
'''


def bench_source(template, helper):
    parent = inherited_bench(template, helper)
    text, edits = parent, []
    def edit(label, before, after):
        nonlocal text
        require(text.count(before) == 1, 'Seed fixture exact anchor: ' + label)
        text = text.replace(before, after, 1)
        edits.append(dict(label=label, before=before, after=after))
    edit('module', 'module qbs_compute_continue_tb;', 'module qbs_balanced_seed_tb;')
    edit('endmodule', 'endmodule : qbs_compute_continue_tb', 'endmodule : qbs_balanced_seed_tb')
    edit('candidate-and-observers', "  qbs_compute_engine #(.SeedRestoreEnable(1'b1)) dut (",
         OBSERVATIONS + "\n  qbs_compute_engine_balanced #(.SeedRestoreEnable(1'b1),\n"
         "      .WideWeightIngress(1'b0), .WideMatrixDot(1'b1), .BalancedMatrixDot(1'b1)) dut (")
    edit('checkpoint-proof', '    @(negedge clk); result_consumed = 1;',
         '    bsg_checkpoint();\n    @(negedge clk); result_consumed = 1;')
    edit('logical-k', '    command_seed = 1; command_k_blocks = 1; command_valid = 1;',
         '    bsg_k++;\n    command_seed = 1; command_k_blocks = 1; command_valid = 1;')
    edit('cancel-relocation', '    seed_fault_or_reset(0);\n    seed_fault_or_reset(1);',
         '    // Seed cancellations run before cases 0/1 for numerical recovery proof.')
    edit('cancel-before-recovery', '      while (!command_ready) @(posedge clk);',
         '      if(ordinal==0) seed_fault_or_reset(0);\n'
         '      if(ordinal==1) seed_fault_or_reset(1);\n'
         '      while (!command_ready) @(posedge clk);')
    edit('case-monitor-initialization', '      command_valid = 1\'b1;',
         '''      bsg_case=case_id;bsg_k=0;bsg_m=m;bsg_n=n;bsg_kb=k_blocks;
      bsg_checkpoints=0;bsg_nonzero=0;
      for(int acc=0;acc<128;acc++) begin bsg_requests[acc]=0;bsg_fmas[acc]=0;bsg_seeds[acc]=0;end
      bsg_normal=1;
      command_valid = 1'b1;''')
    edit('raw-output-after-read', '          #1;\n          if (result_read_valid',
         '          #1;\n          $display("BSG_OUTPUT case=%0d acc=%0d bits=%08h",case_id,index,result_read_data);\n'
         '          if (result_read_valid')
    summary = '''      for(int acc=0;acc<128;acc++) if(bsg_active(acc)) begin
        if(bsg_requests[acc]!=k_blocks || bsg_fmas[acc]!=k_blocks ||
            bsg_seeds[acc]!=(split_k?k_blocks-1:0)) $fatal(1,"BSG_MISSING_ACCUMULATOR_WORK");
      end
      $display("BSG_CASE case=%0d profile=%0d m=%0d n=%0d kb=%0d flags=%0d tiles=%0d weight=%0d activation=%0d pairs=%0d capacity=%0d dot=%0d uops=%0d updates=%0d checkpoints=%0d nonzero=%0d recovery=%0d",
        case_id,profile,m,n,k_blocks,result_fflags|prefix_flags,
        tiles_computed+prefix_counters[0],weight_bytes+prefix_counters[1],activation_bytes+prefix_counters[2],
        useful_pairs+prefix_counters[3],pair_capacity+prefix_counters[4],dot_active_cycles+prefix_counters[5],
        fp_uops+prefix_counters[6],accumulator_updates+prefix_counters[7],bsg_checkpoints,bsg_nonzero,
        case_id==0?1:case_id==1?2:0);
'''
    edit('raw-work-and-coverage', '      total_errors += case_errors;', summary + '      total_errors += case_errors;')
    edit('stop-normal-monitor', "      result_consumed = 1'b0;", "      result_consumed = 1'b0;\n      bsg_normal=0;")
    edit('configuration', '    for (integer ordinal = 0; ordinal < case_count; ordinal++) begin',
         '    $display("BSG_CONFIG ingress=128 matrix=1 balanced=1 seed_restore=1 split=%0d",split_k);\n'
         '    for (integer ordinal = 0; ordinal < case_count; ordinal++) begin')
    edit('strict-eof', '    $fclose(fd);',
         '    rc=$fscanf(fd,"%s",token);if(rc!=-1) $fatal(1,"BSG_TRAILING_VECTOR");\n    $fclose(fd);')
    restored = text
    for change in reversed(edits):
        require(restored.count(change['after']) == 1, 'Seed fixture inverse anchor')
        restored = restored.replace(change['after'], change['before'], 1)
    require(restored == parent, 'Seed fixture must restore the exact original continuation transform')
    return text, dict(original_tb_sha256=TB_SHA, original_helper_sha256=CONTINUATION_SHA,
        inherited_bench_sha256=sha(parent.encode()), generated_sha256=sha(text.encode()), edits=edits,
        original_bench_source_reused=True, original_cancel_task_body_preserved=True,
        original_continuation_statements_retained=True,
        inverse_restores_inherited_bench=True, physical_weight_bits=128, performance_measured=False,
        cancellation_recovery='Original cancel fault before case0; original reset before case1',
        nonzero_checkpoint_and_actual_seed_writeback_required=True,
        continued_first_block_false_and_fma_addend_required=True)


def vectors(text):
    from run_wide_compute import BLOCKS, parse_vectors
    shapes = parse_vectors(text, matrix=False)
    require(len(shapes) == 36 and {s['profile'] for s in shapes} == set(range(1, 10)), 'Original 36/nine-profile suite')
    converted, owner = [], None
    for line in text.splitlines():
        if line.startswith('CMD '):
            owner = int(line.split()[1])
        elif line.startswith('C '):
            s = shapes[owner]
            block = BLOCKS[s['profile']][1]
            waves = [s['m']] if s['m'] <= 4 else [4, s['m'] - 4]
            issues = sum(block // (8 if wave == 1 or block == 256 and wave >= 3 else
                                   4 if wave == 2 else 2) for wave in waves)
            c = list(s['counters'])
            c[4] = s['n'] * s['kb'] * issues * 32
            c[5] = ((s['n'] + 3) // 4) * s['kb'] * issues
            s['counters'] = c
            line = 'C ' + ' '.join(map(str, c))
        converted.append(line)
    return '\n'.join(converted) + '\n', shapes


def fields(line, hex_fields=()):
    result = {}
    for word in line.split()[1:]:
        key, sep, value = word.partition('=')
        require(sep and key not in result and re.fullmatch('[0-9a-fA-F]{8}' if key in hex_fields else '[0-9]+', value),
                'Malformed/duplicate seed record')
        result[key] = int(value, 16 if key in hex_fields else 10)
    return result


def check_log(text, shapes, split):
    require(split in (0, 1) and len(shapes) == 36, 'Seed gate mode/shape inventory')
    normalized = []
    for shape in shapes:
        output = {}
        for key, value in shape['outputs'].items():
            require(type(key) is int or isinstance(key, str) and key == str(int(key)), 'Noncanonical output owner')
            require(int(key) not in output, 'Duplicate normalized output owner')
            output[int(key)] = value
        normalized.append({**shape, 'outputs': output})
    shapes = normalized
    require(not re.search(r'Fatal:|Error[-:]|Assertion.*failed|UVM_(?:FATAL|ERROR)', text), 'RTL/error diagnostic')
    lines = text.splitlines()
    require(lines.count(f'BSG_CONFIG ingress=128 matrix=1 balanced=1 seed_restore=1 split={split}') == 1,
            'Wrong actual elaboration/mode')
    expected_cases = [(s['case'], s['profile'], s['m'], s['n'], s['kb'], s['wl'], s['al']) for s in shapes]
    got = re.findall(r'^QBS command case (\d+) PASS profile=(\d+) M=(\d+) N=(\d+) Kb=(\d+) layouts=(\d+)/(\d+)$', text, re.M)
    require([tuple(map(int, row)) for row in got] == expected_cases, 'Missing/wrong numerical verdict')
    require(lines.count('QBS command engine PASS: 36 functional cases') == 1 and
            lines.count('QBS command fault discard PASS') == 1 and
            lines.count('QBS_SEED_CANCEL_PASS reset=0') == lines.count('QBS_SEED_CANCEL_PASS reset=1') == 1,
            'Missing inherited suite/cancel terminal')
    faults = re.findall(r'^QBS pipeline fault stage ([0-3]) PASS drain_cycles=(\d+)$', text, re.M)
    require([int(row[0]) for row in faults] == list(range(4)) and all(0 < int(row[1]) <= 1024 for row in faults),
            'Inherited fault inventory')
    prefixes = sum(s['kb'] - 1 for s in shapes) if split else 0
    require(lines.count(f'QBS_CONTINUATION_ACCEPT split={split} prefixes={prefixes}') == 1, 'Prefix completion count')
    records = defaultdict(list)
    timeline = {}
    for position, line in enumerate(lines):
        if line.startswith('BSG_'):
            tag = line.split()[0]
            require(tag in ('BSG_CONFIG', 'BSG_CHECKPOINT', 'BSG_SEED', 'BSG_REQUEST', 'BSG_ACCUM', 'BSG_OUTPUT', 'BSG_CASE'),
                    'Unknown seed evidence record')
            row = fields(line, ('a', 'b', 'c') if tag == 'BSG_ACCUM' else ('bits',) if
                         tag in ('BSG_CHECKPOINT', 'BSG_SEED', 'BSG_OUTPUT') else ())
            records[tag].append(row)
            if tag != 'BSG_CONFIG':
                identity = tag, row.get('case'), row.get('acc', -1), row.get('k', -1), row.get('state', -1)
                require(identity not in timeline, 'Duplicate seed evidence event')
                timeline[identity] = position
    require(records['BSG_CONFIG'] == [dict(ingress=128, matrix=1, balanced=1, seed_restore=1, split=split)], 'Config schema')
    require([r['case'] for r in records['BSG_CASE']] == list(range(36)), 'Per-case coverage')
    for reset, case in ((0, 0), (1, 1)):
        cancel = lines.index(f'QBS_SEED_CANCEL_PASS reset={reset}')
        finish = next(i for i, line in enumerate(lines) if line.startswith(f'BSG_CASE case={case} '))
        require(cancel < finish, 'No numerical work after seed cancellation')
        first_request = min(pos for identity, pos in timeline.items()
                            if identity[0] == 'BSG_REQUEST' and identity[1] == case)
        require(cancel < first_request, 'Seed cancellation must precede numerical recovery requests')
        if case == 1:
            require(next(i for i, line in enumerate(lines) if line.startswith('BSG_CASE case=0 ')) < cancel,
                    'Reset masks the preceding fault recovery')
    requests, fmas, checkpoints, seeds, outputs = {}, {}, {}, {}, {}
    for tag, destination, keys in (
            ('BSG_REQUEST', requests, {'case', 'acc', 'k', 'first'}),
            ('BSG_ACCUM', fmas, {'case', 'acc', 'k', 'state', 'a', 'b', 'c'}),
            ('BSG_CHECKPOINT', checkpoints, {'case', 'acc', 'k', 'bits'}),
            ('BSG_SEED', seeds, {'case', 'acc', 'k', 'bits'}),
            ('BSG_OUTPUT', outputs, {'case', 'acc', 'bits'})):
        for row in records[tag]:
            require(set(row) == keys and 0 <= row['case'] < 36 and row['acc'] in shapes[row['case']]['outputs'],
                    'Record fields/accumulator owner')
            key = row['case'], row['acc']
            destination.setdefault(key, []).append(row)
    m4_nonzero = 0
    for shape, summary in zip(shapes, records['BSG_CASE']):
        cid = shape['case']
        expected = dict(case=cid, profile=shape['profile'], m=shape['m'], n=shape['n'], kb=shape['kb'],
                        flags=shape['flags'], **dict(zip(COUNTERS, shape['counters'])),
                        checkpoints=len(shape['outputs']) * (shape['kb'] - 1) * split,
                        recovery=1 if cid == 0 else 2 if cid == 1 else 0)
        require(set(summary) == set(expected) | {'nonzero'} and all(summary[k] == v for k, v in expected.items()),
                'Observed per-case C flags/work/coverage differs')
        nonzero = 0
        for acc, golden in shape['outputs'].items():
            key = cid, acc
            require(requests.get(key) == [dict(case=cid, acc=acc, k=k, first=int(k == 0)) for k in range(shape['kb'])],
                    'Missing continuation request/first_block false')
            expected_order = [(k, state) for k in range(shape['kb']) for state in
                              ((4, 5) if shape['profile'] in (1, 4, 7) else (4,))]
            require([(r['k'], r['state']) for r in fmas.get(key, [])] == expected_order, 'FMA K/order inventory')
            for k in range(shape['kb']):
                require(timeline['BSG_REQUEST', cid, acc, k, -1] < timeline['BSG_ACCUM', cid, acc, k, 4],
                        'FMA precedes its request')
            require(outputs.get(key) == [dict(case=cid, acc=acc, bits=golden)], 'Raw output differs from independent C oracle')
            cp = checkpoints.get(key, [])
            require([r['k'] for r in cp] == list(range(1, shape['kb'])) * split and seeds.get(key, []) == cp,
                    'Checkpoint/actual seed write inventory or payload differs')
            for row in cp:
                require(row['bits'] & 0x7f800000 != 0x7f800000, 'Nonfinite checkpoint')
                nonzero += bool(row['bits'] & 0x7fffffff)
                event = next(r for r in fmas[key] if r['k'] == row['k'] and r['state'] == 4)
                require(event['c'] == row['bits'], 'Restored seed not used as FMA addend')
                k = row['k']
                previous = 5 if shape['profile'] in (1, 4, 7) else 4
                require(timeline['BSG_ACCUM', cid, acc, k - 1, previous] <
                        timeline['BSG_CHECKPOINT', cid, acc, k, -1] <
                        timeline['BSG_SEED', cid, acc, k, -1] <
                        timeline['BSG_REQUEST', cid, acc, k, -1], 'Checkpoint/seed/request temporal order')
        require(summary['nonzero'] == nonzero, 'Nonzero checkpoint tally differs')
        if split and shape['m'] == 4 and shape['kb'] > 1:
            for k in range(1, shape['kb']):
                require(any(row['bits'] & 0x7fffffff for key, rows in checkpoints.items() if key[0] == cid
                            for row in rows if row['k'] == k), 'Zero-only M4 seed proof')
            m4_nonzero += nonzero
    expected_owners = {(s['case'], acc) for s in shapes for acc in s['outputs']}
    require(set(requests) == set(fmas) == set(outputs) == expected_owners, 'Missing/extra accumulator work')
    require(not split or m4_nonzero > 0, 'Missing genuine nonzero M4 continuation')
    return dict(cases=36, prefixes=prefixes, m4_nonzero_checkpoint_words=m4_nonzero,
                seed_words=sum(len(v) for v in seeds.values()), requests=sum(len(v) for v in requests.values()),
                outputs=sum(len(v) for v in outputs.values()), fma_events=fmas)


def check_pair(unsplit, split, shapes):
    a, b = check_log(unsplit, shapes, 0), check_log(split, shapes, 1)
    require(a['fma_events'] == b['fma_events'], 'Seed restore changes actual per-accumulator FMA operands/K order')
    for value in (a, b):
        del value['fma_events']
    return dict(state=SUCCESS, unsplit=a, split=b, independent_c_golden_unchanged=True,
                identical_per_accumulator_fma_operands=True, target_executed=True,
                performance_measured=False, isa_or_lane_path_tested=False)


def ownership():
    path = RUNS / 'e2e_qwen3_f16_phase_vcs_20261106_01/source-pins.json'
    data = path.read_bytes()
    inventory = json.loads(data)
    require(not {str(HERE / name) for name in OWNED}.intersection(inventory), 'Owned helper already consumed')
    return dict(path=str(path), sha256=sha(data), entries=len(inventory),
                inherited_documentation={k: v for k, v in inventory.items() if k.endswith(('.md', '.markdown'))})


def prepare(output=OUT):
    out = Path(output).absolute()
    require(out == OUT and out.resolve() == out, 'Assigned fresh preparation output only')
    observed = ownership()
    out.mkdir(exist_ok=False)
    pins = {}
    def pin(path, expected=None):
        path = Path(path).resolve(strict=True)
        actual = digest(path)
        require(expected is None or actual == expected, 'Input hash mismatch: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == actual, 'Input drift: ' + str(path))
        pins[str(path)] = actual
    result = dict(state='BALANCED_SEED_PREPARATION_FAIL', target_executed=False, rtl_compiled=False,
                  performance_measured=False, production_source_changed=False)
    try:
        pin(PARENT / 'result.json', PARENT_SHA)
        parent = read(PARENT / 'result.json')
        require(parent['state'] == 'BALANCED_COMPUTE_ORDER_FLAGS_WORK_DISABLED_AND_FAULTS_PASS' and
                parent['post_pins_match'] and parent['child_pid'] is None, 'Accepted balanced component required')
        pin(PARENT / 'source-pins.json', parent['source_pins_sha256'])
        inherited = read(PARENT / 'source-pins.json')
        pin(PARENT / 'commands.json', parent['artifacts'][str(PARENT / 'commands.json')])
        pin(EDGES / 'result.json', EDGES_SHA)
        oracle = read(EDGES / 'result.json')
        pin(EDGES / 'source-pins.json', oracle['source_pins_sha256'])
        require(oracle['state'] == 'MIXED_SCALE_EDGE_HOST_ORACLES_PREPARED_NOT_RTL_VERIFIED' and
                oracle['original_default_and_context_byte_identical'], 'Original C oracle acceptance')
        pin(RAW36, RAW36_SHA)
        require(oracle['artifacts'][str(RAW36)] == RAW36_SHA, 'Original 36 artifact binding')
        for path, expected in {TB: TB_SHA, CONTINUATION: CONTINUATION_SHA, **FROZEN_C}.items():
            pin(path, expected)
        for name in OWNED:
            pin(HERE / name)
            shutil.copyfile(HERE / name, out / name)
        pin(HERE / 'run_wide_compute.py', inherited[str(HERE / 'run_wide_compute.py')])
        pin(sys.executable)
        bench, report = bench_source(TB.read_text(), CONTINUATION.read_text())
        tb = out / 'qbs_balanced_seed_tb.sv'
        tb.write_text(bench); pin(tb)
        text, shapes = vectors(RAW36.read_text())
        vector = out / 'vectors-balanced.txt'
        vector.write_text(text); pin(vector)
        source = out / 'source'; source.mkdir()
        rows = [r for r in read(PARENT / 'commands.json') if r['label'] == 'compile-enabled']
        require(len(rows) == 1 and rows[0]['returncode'] == 0, 'Accepted compile recipe')
        original = rows[0]['argv']
        selected = [Path(arg) for arg in original if arg.endswith('.sv') and Path(arg).parent == PARENT / 'source']
        require(len(selected) == len(set(selected)) and {p.name for p in selected} >= {
            'qbs_compute_engine_balanced.sv', 'qbs_fp_accumulator_balanced.sv', 'qbs_profile_engine_int_balanced.sv',
            'qbs_profile_decoder_balanced.sv', 'qbs_dot_array_balanced.sv', 'qbs_fp16_f32_scale.sv', 'qbs_mixed_scale.sv'},
            'Balanced source graph incomplete')
        mapping = {}
        for path in selected:
            pin(path, inherited[str(path)])
            target = source / path.name
            shutil.copyfile(path, target); pin(target)
            mapping[str(path)] = str(target)
        for name, expected in inherited.items():
            path = Path(name)
            if path.is_relative_to(PARENT / 'source/include'):
                pin(path, expected)
                target = source / path.relative_to(PARENT / 'source')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target); pin(target)
        old_top = str(PARENT / 'source/clone/qbs_balanced_compute_tb.sv')
        require(original.count(old_top) == 1, 'Accepted top identity')
        mapping[old_top] = str(tb)
        mapping['+incdir+' + str(PARENT / 'source/include')] = '+incdir+' + str(source / 'include')
        mapping['qbs_balanced_compute_tb'] = 'qbs_balanced_seed_tb'
        planned = []
        for arg in original:
            if arg in ('-pvalue+qbs_balanced_compute_tb.Wide=1', '-pvalue+qbs_balanced_compute_tb.Balanced=1'):
                continue
            if arg.startswith('-Mdir='):
                arg = '-Mdir=' + str(out / 'worker/csrc')
            if arg == str(PARENT / 'enabled/simv'):
                arg = str(out / 'worker/simv')
            planned.append(mapping.get(arg, arg))
        require('-assert' in planned and 'svaext' in planned and
                not any(arg.startswith('-pvalue') for arg in planned), 'Unexpected elaboration controls')
        pin(planned[0], inherited[str(Path(planned[0]).resolve())])
        vcs1 = Path(planned[0]).resolve().parent.parent / 'linux64/bin/vcs1'
        pin(vcs1, inherited[str(vcs1.resolve())])
        # All local numerical parsing dependencies are explicit and inherited.
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).resolve().parent == HERE and Path(path).name not in OWNED:
                pin(path, inherited[str(Path(path).resolve())])
        tests = __import__('test_balanced_seed_gate')
        log = io.StringIO()
        tested = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
        (out / 'unit-tests.log').write_text(log.getvalue())
        require(tested.wasSuccessful(), 'Host source/admission/replay tests failed')
        write(out / 'transform.json', report)
        write(out / 'ownership.json', observed)
        write(out / 'compile-command.json', dict(argv=planned, cwd=str(out / 'worker'), timeout_seconds=600))
        write(out / 'runtime-commands.json', [dict(argv=[str(out / 'worker/simv'), '-no_save',
              '+QBS_COMMAND_VECTOR_FILE=' + str(vector), *(['+SPLIT_K'] if mode else [])],
              label='split' + str(mode), timeout_seconds=300) for mode in (0, 1)])
        write(out / 'shapes.json', shapes)
        for path, expected in pins.items():
            require(digest(path) == expected, 'Post-preparation input drift: ' + path)
        write(out / 'source-pins.json', pins)
        result.update(state=PREPARED, parent_result_sha256=PARENT_SHA, cases=36,
                      expected_split_prefixes=sum(s['kb'] - 1 for s in shapes),
                      expected_m4_split_prefixes=sum(s['kb'] - 1 for s in shapes if s['m'] == 4),
                      physical_weight_bits=128, wide_matrix_dot=True, balanced_matrix_dot=True,
                      seed_restore_enable=True, only_vector_capacity_dot_changed=True,
                      original_c_oracle_reused=True, host_tests=tested.testsRun,
                      source_pins_sha256=digest(out / 'source-pins.json'),
                      artifacts={str(p): digest(p) for p in out.rglob('*') if p.is_file()},
                      limits=['Prepared only; no VCS launched', 'Compute-only, not ISA/VRF lane/controller/SoC acceptance',
                              'Functional-only transport128 gate, not a throughput experiment'])
        write(out / 'result.json', result)
        return result
    except BaseException as exc:
        result['error'] = repr(exc)
        write(out / 'result.json', result)
        raise


def execute(prepared, expected):
    prepared = Path(prepared).absolute()
    require(prepared == OUT and re.fullmatch('[0-9a-f]{64}', expected or '') and
            digest(prepared / 'result.json') == expected, 'Explicit exact preparation receipt required')
    report = read(prepared / 'result.json')
    require(report['state'] == PREPARED and not report['target_executed'] and not report['rtl_compiled'], 'Prepared-only input required')
    pins = read(prepared / 'source-pins.json')
    require(digest(prepared / 'source-pins.json') == report['source_pins_sha256'], 'Preparation pins binding')
    pins.update(report['artifacts'])
    pins[str(prepared / 'result.json')] = expected
    def verify():
        for path, value in pins.items():
            require(digest(path) == value, 'Consumed input/image drift: ' + path)
    verify()
    worker = prepared / 'worker'; worker.mkdir(exist_ok=False)
    commands = []
    result = dict(state='BALANCED_SEED_GATE_FAIL', child_pid=None, performance_measured=False,
                  target_executed=False, rtl_compiled=False,
                  prepared_result_sha256=expected, production_source_changed=False)
    env = {key: value for key, value in os.environ.items() if key not in (
        'LD_PRELOAD', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'COMPILER_PATH', 'GCC_EXEC_PREFIX', 'LIBRARY_PATH')}
    env.update(PATH='/usr/bin:/bin', LC_ALL='C', HOME=str(worker), PYTHONDONTWRITEBYTECODE='1')
    def command(row, label):
        verify()
        argv = row['argv']
        record = {**row, 'label': label, 'returncode': None}
        commands.append(record)
        with (worker / (label + '.log')).open('xb') as log:
            child = subprocess.Popen(argv, cwd=worker, stdout=log, stderr=subprocess.STDOUT,
                env=env, start_new_session=True)
            result.update(state=label, child_pid=child.pid)
            if label.startswith('split'):
                result['target_executed'] = True
            (worker / 'status.json').write_text(json.dumps(result, indent=2) + '\n')
            try:
                code = child.wait(timeout=row['timeout_seconds'])
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL); child.wait(); raise
            finally:
                result['child_pid'] = None
        record['returncode'] = code
        text = (worker / (label + '.log')).read_text()
        require(code == 0 and not re.search(r'Fatal:|Error[-:]|Assertion.*failed|UVM_(?:FATAL|ERROR)', text),
                'First failure preserved: ' + label)
        verify()
        return text
    try:
        command(read(prepared / 'compile-command.json'), 'compile')
        result['rtl_compiled'] = True
        image = worker / 'simv'
        libraries = list(worker.rglob('*.so'))
        require(image.is_file() and libraries, 'Actual VCS image/libraries missing')
        for path in (image, *libraries):
            pins[str(path)] = digest(path)
        texts = [command(row, row['label']) for row in read(prepared / 'runtime-commands.json')]
        shapes = read(prepared / 'shapes.json')
        _, regenerated = vectors(RAW36.read_text())
        require(json.loads(json.dumps(regenerated)) == shapes, 'Prepared shapes differ from independent C vectors')
        measured = check_pair(*texts, shapes)
        write(worker / 'measured.json', measured)
        verify()
        result.update(state=SUCCESS, measured=measured, post_pins_match=True, target_executed=True,
                      rtl_compiled=True, independent_c_golden_unchanged=True)
    except BaseException as exc:
        result.update(state='BALANCED_SEED_GATE_FAIL', error=repr(exc), first_failure_preserved=True)
    finally:
        try:
            verify()
            result['post_pins_match'] = True
        except Exception as exc:
            result.update(state='BALANCED_SEED_GATE_FAIL', post_pins_match=False, pin_error=repr(exc))
        write(worker / 'commands.json', commands)
        write(worker / 'source-pins.json', pins)
        result['source_pins_sha256'] = digest(worker / 'source-pins.json')
        result['artifacts'] = {str(p): digest(p) for p in worker.iterdir() if p.is_file() and p.name != 'status.json'}
        write(worker / 'result.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--execute-reviewed', action='store_true')
    parser.add_argument('--prepared-sha256')
    args = parser.parse_args()
    record = execute(args.output, args.prepared_sha256) if args.execute_reviewed else prepare(args.output)
    print(json.dumps(dict(state=record['state'], output=str(args.output))))
    sys.exit(0 if record['state'] in (PREPARED, SUCCESS) else 1)

#!/usr/bin/env python3
"""Add source-bound memory-owner presence to the unchanged sealed data checker."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'unmasked_strided_alignment_soc_m9_prepare01'
sys.path.insert(0, str(BASE))
_spec = importlib.util.spec_from_file_location('sealed_m9_dut_check', BASE / 'dut_check.py')
old = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(old)
need = old.c.need


def memory(insn):
    return insn & 127 in (7, 39) and (insn >> 12) & 7 in (0, 5, 6, 7)


def recipe(spec):
    s = spec['symbols']
    code = {int(k): v for k, v in spec['code'].items()}
    seeds = sorted(pc for pc, op in code.items()
                   if s['mt_test_entry'] <= pc < s['mt_target'] and memory(op))
    need(len(seeds) == 2, 'Exactly two original seed loads')
    sites = [('seed_v24', seeds[0], 16, 0), ('seed_v8', seeds[1], 16, 0),
             ('target_first', s['mt_target'], 2, 0),
             ('fault_snapshot', s['mt_fault_snapshot'], 16, 0),
             ('target_retry', s['mt_target'], 2, 1),
             ('result_snapshot', s['mt_result_snapshot'], 16, 0),
             ('successor_load', s['mt_successor_load'], 2, 0),
             ('successor_store', s['mt_successor_store'], 2, 0),
             ('next_snapshot', s['mt_next_snapshot'], 16, 0)]
    need({pc for pc, op in code.items() if memory(op)} == {x[1] for x in sites},
         'Unexpected memory code outside original helper sites')
    result = []
    for name, pc, vl, start in sites:
        op = code[pc]
        need(memory(op) and (op >> 12) & 7 == 7 and (op >> 25) & 1 == 1
             and op >> 28 == 0, 'Original unmasked e64 NF1 memory encoding')
        need((op >> 26) & 3 == (2 if name.startswith('target_') else 0),
             'Original strided target / unit helper')
        result.append(dict(site=name, pc=pc, insn=op, vl=vl, vstart=start))
    need(code[seeds[0]] == 0x020e7c07 and code[seeds[1]] == 0x020e7407,
         'Original v24/v8 seed loads')
    return result


class MemoryOwners:
    """VID and transaction IDs may be reused only after their actual completion."""
    def __init__(self, spec):
        self.expected = recipe(spec)
        self.symbols = spec['symbols']
        self.arch = {}
        self.owners = []
        self.active = {}
        self.requests = {}
        self.request_count = 0
        self.retired = []
        self.vl = self.vtype = self.start = None
        self.fault_context = None

    def row(self, r, regs):
        event, op = r['event'], int(r['insn'], 16)
        seq, tid, vid, cycle = (int(r[k]) for k in ('order', 'trans_id', 'port', 'cycle'))
        if event == 'arch_start':
            need(seq == len(self.arch), 'Architecture sequence discontinuity')
            a = dict(seq=seq, trans_id=tid, insn=op, cycle=cycle, allocations=[], completions=[])
            self.arch[seq] = a
            if memory(op):
                i = len(self.owners)
                need(i < len(self.expected) and op == self.expected[i]['insn'],
                     'Source memory dispatch order/encoding')
                a.update(self.expected[i], trap=None, request_cycle=None)
                self.owners.append(a)
        elif event == 'uop_alloc':
            a = self.arch.get(seq)
            need(a is not None and (op, tid) == (a['insn'], a['trans_id']),
                 'Allocation owner/insn/transaction mismatch')
            need(0 <= vid < 8 and vid not in self.active, 'Live VID reused / invalid VID')
            self.active[vid] = (seq, op, tid, cycle)
            a['allocations'].append(dict(vid=vid, cycle=cycle))
        elif event == 'uop_done':
            prior = self.active.get(vid)
            need(prior is not None and prior[:3] == (seq, op, tid),
                 'Completion owner/insn/transaction mismatch')
            need(cycle >= prior[3], 'Completion before allocation')
            del self.active[vid]
            self.arch[seq]['completions'].append(dict(vid=vid, allocated=prior[3], cycle=cycle))
        elif event == 'cvx_req' and memory(op):
            need(self.request_count < len(self.owners) and tid not in self.requests,
                 'Unowned/duplicate memory request')
            a = self.owners[self.request_count]
            need((op, tid) == (a['insn'], a['trans_id']), 'Memory request identity')
            a['request_cycle'] = cycle
            self.requests[tid] = a
            self.request_count += 1
        elif event == 'cvx_resp' and tid in self.requests:
            a = self.requests.pop(tid)
            trap = int(r['trap'])
            need(trap == int(a['site'] == 'target_first'), 'Memory response fault qualification')
            a['trap'] = trap
            a['response_cycle'] = cycle
        elif event == 'retire':
            pc = int(r['pc'], 16)
            trap = int(r['trap'])
            rd, value = int(r['rd']), int(r['rd_wdata'], 16)
            if pc == self.symbols['mt_handler'] and self.fault_context is None:
                need(len(self.retired) == 2 and (self.vl, self.vtype, self.start) == (2, 24, 0),
                     'First fault actual nonempty setup')
                self.fault_context = dict(vl=self.vl, vtype=self.vtype, vstart=self.start,
                                          handler_cycle=cycle)
            if not trap and op & 127 == 0x57 and (op >> 12) & 7 == 7:
                # This fixture uses vsetvli with nonzero rd before every memory site.
                self.vl = value if rd else None
                self.vtype = (op >> 20) & 0x7ff if op >> 31 == 0 else None
                self.start = 0
            if not trap and op & 127 == 0x73 and op >> 20 == 8:
                f, src = (op >> 12) & 7, (op >> 15) & 31
                if f in (1, 5):
                    self.start = src if f == 5 else regs.get(src)
                elif f in (2, 3, 6, 7):
                    operand = src if f >= 6 else regs.get(src)
                    previous = value if rd else self.start
                    if src == 0:
                        self.start = previous
                    elif operand is None or previous is None:
                        self.start = None
                    else:
                        self.start = previous | operand if f in (2, 6) else previous & ~operand
            if memory(op):
                want = [x for x in self.expected if x['site'] != 'target_first']
                i = len(self.retired)
                need(not trap and i < len(want) and (pc, op) == (want[i]['pc'], want[i]['insn']),
                     'Actual memory retire PC/order/encoding')
                need((self.vl, self.vtype, self.start) == (want[i]['vl'], 24, want[i]['vstart'])
                     and self.vl > self.start, 'Actual nonempty helper VL/vtype/vstart')
                self.retired.append(dict(pc=pc, insn=op, cycle=cycle, vl=self.vl,
                                         vtype=self.vtype, vstart=self.start))
                self.start = 0

    def finish(self):
        need(not self.active and not self.requests, 'Pending backend/memory owner')
        need(len(self.owners) == self.request_count == len(self.expected), 'Missing memory dispatch')
        need(len(self.retired) == len(self.expected)-1 and self.fault_context is not None,
             'Missing actual memory retire/setup context')
        j = 0
        for a in self.owners:
            need(a['allocations'] and len(a['allocations']) == len(a['completions']),
                 'Missing completed memory owner: ' + a['site'])
            need(a['request_cycle'] is not None and a['trap'] == int(a['site'] == 'target_first'),
                 'Incomplete memory response: ' + a['site'])
            if a['site'] != 'target_first':
                retired = self.retired[j]
                need(a['cycle'] <= retired['cycle'], 'Memory retired before architecture owner')
                a['retire_context'] = retired
                j += 1
            else:
                need(a['response_cycle'] <= self.fault_context['handler_cycle'], 'Handler before fault response')
                a['setup_context'] = self.fault_context
        return dict(memory_owner_count=len(self.owners), memory_owners=self.owners,
                    helper_owner_count=sum(not a['site'].startswith('target_') for a in self.owners),
                    memory_allocations=sum(len(a['allocations']) for a in self.owners))


class Checker(old.Checker):
    def __init__(self, spec, st, sv):
        super().__init__(spec, st, sv)
        self.memory_owners = MemoryOwners(spec)

    def row(self, row):
        # Both checkers see the same unmodified row; the source operand state is pre-retire.
        self.memory_owners.row(row, self.o.regs)
        super().row(row)

    def finish(self):
        owners = self.memory_owners.finish()
        result = super().finish()
        result.update(owners)
        result['lifecycle_successor'] = 'source-bound-nonempty-memory-owners01'
        return result


def analyze(path, spec, st, sv):
    checker = Checker(spec, st, sv)
    with Path(path).open(newline='') as f:
        reader = csv.DictReader(f)
        need(reader.fieldnames == old.c.FIELDS, 'CSV header')
        for row in reader:
            checker.row(row)
    return checker.finish()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('member', choices=['load_m', 'store_m', 'load_sv39', 'store_sv39'])
    ap.add_argument('csv', type=Path)
    ap.add_argument('spec', type=Path)
    ap.add_argument('out', type=Path)
    args = ap.parse_args()
    result = analyze(args.csv, json.loads(args.spec.read_text()),
                     args.member.startswith('store'), args.member.endswith('sv39'))
    with args.out.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps(result, indent=2))

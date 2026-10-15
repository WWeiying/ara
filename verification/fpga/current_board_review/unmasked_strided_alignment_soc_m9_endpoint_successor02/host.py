#!/usr/bin/env python3
"""Actual SoC first-write prefixes and existing Spike traces; no simulator."""
import ast
import copy
import csv
import inspect
import json
from pathlib import Path
import re
import textwrap
import checker as n

RUN = n.HERE.parent/'unmasked_strided_alignment_soc_m9_worker_successor01/prepared01'


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def unchanged_step():
    old = ast.parse(textwrap.dedent(inspect.getsource(n.c.Observer.step)))
    new = ast.parse(textwrap.dedent(inspect.getsource(n.Observer.step)))

    class Normalize(ast.NodeTransformer):
        def visit_Attribute(self, node):
            if isinstance(node.value, ast.Name) and node.value.id == 'c':
                return ast.copy_location(ast.Name(id=node.attr, ctx=node.ctx), node)
            return self.generic_visit(node)

        def visit_If(self, node):
            if ast.unparse(node.test) == "a in (self.s['tohost'], 3489660928)":
                return ast.parse('self.record_exit(pc,insn,a,v,n)').body[0]
            return self.generic_visit(node)

    assert ast.dump(Normalize().visit(old), include_attributes=False) == ast.dump(
        Normalize().visit(new), include_attributes=False), 'Non-endpoint original step changed'


def main():
    out = n.HERE/'host01'
    out.mkdir(exist_ok=False)
    unchanged_step()
    negatives, bindings, prefixes, bridges = [], [], [], []

    def reject(name, fn):
        try:
            fn()
        except (ValueError, KeyError):
            negatives.append(name)
            return
        raise AssertionError('Accepted negative '+name)

    for member in ('load_m', 'store_m', 'load_sv39', 'store_sv39'):
        for backend in ('dut', 'spike'):
            spec, e = n.bind(member, backend)
            bindings.append(e)
            o = n.Observer(spec, member.startswith('store'), member.endswith('sv39'), e)
            if backend == 'dut':
                assert 'tohost' not in o.s
            valid = (e['store_pc'], e['store_insn'], e['address'], e['value'], 8)
            for field, replacement in ((0, e['store_pc']+4), (1, 0x13), (2, e['address']+8),
                                       (3, 1-e['value']), (4, 4)):
                bad = list(valid)
                bad[field] = replacement
                reject(member+backend+'exit_field'+str(field), lambda: o.record_exit(*bad))
            reject(member+backend+'missing_exit', lambda: o.finish(backend))
            o.record_exit(*valid)
            reject(member+backend+'duplicate_exit', lambda: o.record_exit(*valid))
            if backend == 'spike':
                reject(member+'spike_CTRL', lambda: o.record_exit(e['store_pc'], e['store_insn'], 0xd0000000, 0, 8))

    for member in ('load_m', 'store_m'):
        spec, endpoint = n.bind(member, 'dut')
        new = n.instance(member)
        old = n.previous.Checker(spec, member.startswith('store'), False)
        path = RUN/'alignment4/tests'/('strided_alignment_'+member)/'commit_trace.csv'
        with path.open() as f:
            for lineno, row in enumerate(csv.DictReader(f), 2):
                new.row(row)
                try:
                    old.row(row)
                except KeyError as e:
                    assert e.args == ('tohost',) and row['event'] == 'retire' and int(row['mem_wmask'], 16)
                    prefixes.append(dict(member=member, line=lineno, row=row,
                                         old_error=repr(e), new_prefix_pass=True, tohost_added=False))
                    break
            else:
                raise AssertionError('Expected actual old-prefix rejection absent')

        # Reuse the existing golden trace once. Its native HTIF endpoint is not
        # substituted with CTRL, and there are no invented CVX/uop events.
        ref = n.BASE/('reference_'+member+'01')
        spec, endpoint = n.bind(member, 'spike')
        good = n.instance(member, 'spike')
        missing = n.instance(member, 'spike')
        partial, order = 0, 0
        raw_pins = json.loads((ref/'READY.json').read_text())['outputs']
        assert n.sha(ref/'spike.trace') == raw_pins['spike.trace']
        for line in (ref/'spike.trace').open():
            match = re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$', line)
            if not match:
                continue
            pc, insn, tail = int(match[2], 16), int(match[3], 16), match[4]
            if pc == spec['symbols']['mt_target'] and not partial:
                partial += 1
                continue
            gp = [(int(r), int(v, 16)) for r, v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)', tail)]
            assert len(gp) <= 1
            row = dict.fromkeys(n.c.FIELDS, '0')
            row.update(event='retire', cycle=str(order), order=str(order), pc=f'{pc:x}', insn=f'{insn:x}')
            if gp:
                row.update(rd=str(gp[0][0]), rd_wdata=f'{gp[0][1]:x}')
            d = n.c.memory_op(insn)
            if d is not None:
                accesses = [(int(a, 16), int(v, 16) if v else None)
                            for a, v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?', tail)]
                assert len(accesses) == 1
                a, value = accesses[0]
                row['mem_addr'] = f'{a:x}'
                row['mem_wmask' if d['kind']=='write' else 'mem_rmask'] = f'{((1<<d["size"])-1)<<(a%8):x}'
                if value is not None:
                    row['mem_wdata'] = f'{value:x}'
            good.row(row)
            bad = dict(row)
            if pc == endpoint['store_pc']:
                bad['mem_wmask'] = '0'
            missing.row(bad)
            order += 1
        assert partial == 1
        result = good.o.finish('spike')
        assert missing.o.calls == result['checks']
        reject(member+'full_bridge_missing_HTIF', lambda: missing.o.finish('spike'))
        bridges.append(dict(member=member, scalar_rows=order, result=result, cvx_proven=False,
                            full_data_oracle=True, native_HTIF=True, no_reference_execution=True))
        assert n.sha(ref/'spike.trace') == raw_pins['spike.trace']

    result = dict(status='HOST_ENDPOINT_PASS_NOT_DUT', negative_count=len(negatives), negatives=negatives,
                  source_step_AST_identical_except_explicit_endpoint=True, bindings=bindings,
                  actual_soc_prefixes=prefixes, existing_reference_bridges=bridges,
                  checker_sha256=n.sha(n.HERE/'checker.py'), host_sha256=n.sha(__file__))
    save(out/'result.json', result)
    print(json.dumps(dict(status=result['status'], negatives=len(negatives), actual_soc_prefixes=len(prefixes), bridges=len(bridges))))


if __name__ == '__main__':
    main()

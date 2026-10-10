import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import collect_c910_float_edge777 as q


class NativeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = q.runner.preflight(); cls.reference = q.reference_prefix(cls.pre); cls.symbols = cls.pre['symbols']
        roles = {cls.symbols['edge_' + op + str(width)]: (op, width) for width in (16, 32, 64)
                 for op in ('load_a', 'load_b', 'div', 'store')}
        cls.mapping, cls.activities = {}, {}; counters = {op: 0 for op in ('load_a', 'load_b', 'div', 'store')}
        for i, commit in enumerate(cls.reference):
            if commit.pc not in roles: continue
            op, width = roles[commit.pc]; phase = counters[op]; counters[op] += 1; seq = len(cls.mapping)
            cls.mapping[seq] = i; eew = {16: 1, 32: 2, 64: 3}[width]; writes = []
            reg = {'load_a': 8, 'load_b': 16, 'div': 24, 'store': 0}[op]
            if op != 'store':
                value = q.p.gold(width, phase % 8, phase // 8 % 2)[{'load_a': 0, 'load_b': 1, 'div': 2}[op]]
                for lane in range(4):
                    writes.append(q.vc.VectorWrite(row=seq * 4 + lane, cycle=seq * 2, arch_seq=seq, vid=seq % 8,
                        lane=lane, source=1 if op == 'div' else 4, instruction=commit.instruction, eew=eew,
                        addr=reg * 4, be=255, data=q.p.word(value, width), known_be=255))
            cls.activities[seq] = q.vc.ArchActivity(instruction=commit.instruction, allocations=1, completions=1,
                use_vd=op != 'store', vd=reg, eew=eew, vl=256 // width, vstart=0, writes=writes)
        cls.rows = []
        for i, commit in enumerate(cls.reference):
            values = commit.gpr_writes; rd = next(iter(values), 0); address = 0; rm = wm = data = 0
            access = q.common.scalar_memory(commit.instruction)
            if access:
                kind, width = access
                if commit.memory_accesses:
                    address, value = commit.memory_accesses[0]; mask = ((1 << width) - 1) << (address & 7)
                    if kind == 'read': rm = mask
                    else: wm, data = mask, value
            cls.rows.append(dict(event='retire', order=str(i), pc=f'{commit.pc:016x}', insn=f'{commit.instruction:08x}',
                trap='0', rd=str(rd), rd_wdata=f'{values.get(rd, 0):016x}', mem_addr=f'{address:016x}',
                mem_rmask=f'{rm:02x}', mem_wmask=f'{wm:02x}', mem_wdata=f'{data:016x}'))

    def native(self, activities=None):
        return q.native_state(self.reference, self.activities if activities is None else activities, self.mapping, self.symbols)

    def test_real_reference_gold_footprint_and_all48_flags(self):
        proof = q.footprint(self.rows, self.symbols, self.reference)
        self.assertEqual((proof['checks'], proof['required_read_bytes']), (1440, 11520))
        self.assertEqual(len(proof['per_division_fcsr']), 48)

    def test_real_reference_all_native_defined_bytes(self):
        proof = self.native(); self.assertEqual(proof['defined_bytes'], 4608)
        self.assertEqual(proof['operations']['div'], 48)

    def test_every_div_context_rejected_if_changed(self):
        for attr, value in [('vl', 15), ('vstart', 1), ('eew', 3), ('use_vd', False), ('vd', 25), ('completions', 0), ('instruction', 0)]:
            activities = copy.deepcopy(self.activities); seq = next(s for s, i in self.mapping.items() if self.reference[i].pc == self.symbols['edge_div16'])
            setattr(activities[seq], attr, value)
            with self.assertRaises(ValueError, msg=attr): self.native(activities)

    def test_native_missing_unknown_wrong_result_or_extra_byte_rejected(self):
        from dataclasses import replace
        for case in ('missing', 'unknown', 'wrong', 'extra', 'source', 'duplicate'):
            activities = copy.deepcopy(self.activities); a = activities[2]
            if case == 'missing': a.writes.pop()
            elif case == 'unknown': a.writes[0] = replace(a.writes[0], known_be=254)
            elif case == 'wrong': a.writes[0] = replace(a.writes[0], data=a.writes[0].data ^ 1)
            elif case == 'extra': a.writes.append(replace(a.writes[0], addr=a.writes[0].addr + 1))
            elif case == 'source': a.writes[0] = replace(a.writes[0], source=0)
            else: a.writes.append(a.writes[0])
            with self.assertRaises(ValueError, msg=case): self.native(activities)

    def test_missing_backend_rejected(self):
        activities = copy.deepcopy(self.activities); del activities[2]
        with self.assertRaises(ValueError): self.native(activities)

    def test_store_write_rejected(self):
        activities = copy.deepcopy(self.activities); activities[3].writes = activities[2].writes
        with self.assertRaises(ValueError): self.native(activities)

    def test_signature_or_flag_corruption_rejected(self):
        first_div = next(i for i, c in enumerate(self.reference) if c.pc == self.symbols['edge_div16'])
        indices = [next(i for i, c in enumerate(self.reference) if i > first_div and c.gpr_writes and
            c.instruction & 127 == 0x73 and c.instruction >> 20 == 3 and c.instruction >> 12 & 7 == 2),
            max(i for i, row in enumerate(self.rows) if int(row['mem_addr'], 16) == self.symbols['edge_dst'])]
        for index in indices:
            rows = copy.deepcopy(self.rows); key = 'rd_wdata' if int(rows[index]['mem_rmask'], 16) or self.reference[index].instruction & 127 == 0x73 else 'mem_wdata'
            rows[index][key] = f'{int(rows[index][key], 16) ^ 1:016x}'
            with self.assertRaises(ValueError): q.footprint(rows, self.symbols, self.reference)

    def test_actual_scalar_comparison_no_skip(self):
        import csv
        with TemporaryDirectory() as d:
            path = Path(d) / 'commit.csv'
            fields = q.common.COMMIT_FIELDS
            with path.open('w') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
                writer.writerows({**{key: '0' for key in fields}, **row} for row in self.rows)
            result = q.common.spike_trace.compare_commit_prefix(Path(self.pre['reference']), path, 0x80000000,
                terminal_tohost_address=self.symbols['tohost'], rvfi_store_data_layout='unshifted')
            q.common.scalar_exact(result, q.common.reference_counts(self.reference, self.symbols))

    def test_terminal_missing_rejected(self):
        with TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError): q.terminal(Path(d), {})

    def test_real_cache_all744_pins(self):
        cache, pins = q.checked_cache()
        self.assertEqual(len(cache['input_pins']), 744)
        self.assertTrue(all(pins[path] == sha for path, sha in cache['input_pins'].items()))

    def test_cache_input_drift_rejected(self):
        from unittest.mock import patch
        with TemporaryDirectory() as d:
            path = Path(d) / 'input'; path.write_text('original')
            cache = {'input_pins': {str(path): q.life.digest(path)}}
            path.write_text('changed')
            with patch.object(q.life, 'read_bound', return_value=cache):
                with self.assertRaises(ValueError): q.checked_cache()

    def test_actual_coverage_metadata_and_negative_identity(self):
        from unittest.mock import patch
        run = q.life.OUT / 'c910-float-edge-vcs777-parent-20261007-01'
        folder = run / 'code.vdb/snps/coverage/db/testdata' / q.runner.NAME
        manifest = {'command': q.runner.command(run)}
        design = q.toggle.xml(folder / 'vcmArguments.xml').get('compvdbpath')
        self.assertEqual(len(q.coverage_identity(folder, run, manifest, Path(design))), 7)
        xml = q.toggle.xml
        for case in ('seed', 'compile', 'metric'):
            def changed(path):
                tree = copy.deepcopy(xml(path))
                if case == 'seed' and path.name == 'siminfo.xml': tree.find('srctest').set('seed', '2')
                if case == 'compile' and path.name == 'vcmArguments.xml': tree.set('compvdbpath', '/foreign')
                if case == 'metric' and path.name == 'vcmArguments.xml':
                    next(x for x in tree.iter('vcm_arg_data') if x.get('vcm_opt')).set('vcm_opt', '-cm line')
                return tree
            with patch.object(q.toggle, 'xml', side_effect=changed):
                with self.assertRaises(ValueError, msg=case): q.coverage_identity(folder, run, manifest, Path(design))


if __name__ == '__main__': unittest.main()

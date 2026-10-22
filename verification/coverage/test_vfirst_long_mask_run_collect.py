"""Real frozen-reference fixtures, negative qualification and no-EDA lifecycle tests."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import collect_vfirst_long_mask as q


def writes(value, seq, instruction):
    result = []
    for word in range(4):
        for lane in range(4):
            data = sum((value >> (8 * (word * 32 + q.vc._deshuffle_byte(lane * 8 + b, 4, 0))) & 255)
                       << (8 * b) for b in range(8))
            result.append(q.vc.VectorWrite(row=len(result), cycle=100 * seq + len(result), arch_seq=seq,
                vid=seq % 8, lane=lane, source=4, instruction=instruction, eew=0, addr=word,
                be=255, data=data, known_be=255))
    return result


class RealReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = q.runner.preflight(); cls.reference = q.reference_prefix(cls.pre)
        cls.rows = []
        for i, c in enumerate(cls.reference):
            values = {r: v for r, v in c.gpr_writes.items() if r}; rd = next(iter(values), 0)
            address = rm = wm = data = 0; access = q.common.scalar_memory(c.instruction)
            if access is not None:
                kind, width = access; address, value = c.memory_accesses[0]
                mask = ((1 << width) - 1) << (address & 7)
                if kind == 'read': rm = mask
                else: wm, data = mask, value
            cls.rows.append(dict(event='retire', order=str(i), pc=hex(c.pc), insn=hex(c.instruction),
                trap='0', rd=str(rd), rd_wdata=hex(values.get(rd, 0)), mem_addr=hex(address),
                mem_rmask=hex(rm), mem_wmask=hex(wm), mem_wdata=hex(data)))
        symbols = cls.pre['symbols']; pcs = {symbols[n] for n in ('vfirst_mask_load', 'vfirst_scalar_op', 'vfirst_whole_readback')}
        cls.mapping = {seq: i for seq, i in enumerate(i for i, c in enumerate(cls.reference) if c.pc in pcs)}
        cls.activities = {}
        for seq, i in cls.mapping.items():
            c = cls.reference[i]; ws = writes(c.vector_writes[0], seq, c.instruction) if c.vector_writes else []
            cls.activities[seq] = q.vc.ArchActivity(instruction=c.instruction, allocations=1, completions=1,
                use_vd=bool(ws), vd=c.instruction >> 7 & 31, eew=0,
                vl=128 if ws else 1024, vstart=0, writes=ws)

    def native(self, activities=None, mapping=None):
        return q.native_state(self.reference, self.activities if activities is None else activities,
                              self.mapping if mapping is None else mapping, self.pre['symbols'])

    def test_real_reference_complete_signature(self):
        result = q.footprint(self.rows, self.pre['symbols'])
        self.assertEqual(result['checks'], 384); self.assertEqual(result['required_read_bytes'], 3072)
        self.assertEqual(len(self.reference), 9918)

    def test_real_reference_full_scalar_memory(self):
        result = q.memory.scalar_memory_exact(self.rows, self.reference)
        self.assertEqual(result['unmodeled_memory_effects'], 0)
        self.assertGreater(result['compressed_memory_accesses'], 0)

    def test_real_reference_native_complete_masks(self):
        result = self.native()
        self.assertEqual(result['compared_bytes'], 1024)
        self.assertEqual(result['mask_loads'], result['vfirst_without_VRF_write'])

    def test_actual_scalar_diff_engine_no_skip(self):
        # CSV is a controlled reference fixture, not processor PASS evidence.
        import csv
        with tempfile.TemporaryDirectory(dir=q.life.OUT) as tmp:
            path = Path(tmp) / 'reference-fixture.csv'
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=q.common.COMMIT_FIELDS)
                writer.writeheader()
                for i, row in enumerate(self.rows):
                    row = dict(row)
                    for key in ('pc', 'rd_wdata', 'mem_addr', 'mem_wdata'):
                        row[key] = '%016x' % int(row[key], 16)
                    row['insn'] = '%08x' % int(row['insn'], 16)
                    for key in ('mem_rmask', 'mem_wmask'): row[key] = '%02x' % int(row[key], 16)
                    writer.writerow(dict(cycle=str(i), port='0', trans_id='0', **row))
            result = q.common.spike_trace.compare_commit_prefix(Path(self.pre['reference']), path, 0x80000000,
                terminal_tohost_address=self.pre['symbols']['tohost'], rvfi_store_data_layout='unshifted')
            q.common.scalar_exact(result, q.common.reference_counts(self.reference, self.pre['symbols']))

    def test_missing_retirement(self):
        with self.assertRaises(ValueError): q.footprint(self.rows[:-1], self.pre['symbols'])

    def test_bad_scalar_result(self):
        rows = copy.deepcopy(self.rows)
        next(r for r in rows if int(r['pc'], 16) == self.pre['symbols']['vfirst_scalar_op'])['rd_wdata'] = '0'
        with self.assertRaises(ValueError): q.footprint(rows, self.pre['symbols'])

    def test_missing_source_readback(self):
        rows = copy.deepcopy(self.rows); address = self.pre['symbols']['vfirst_source']
        for r in rows:
            if int(r['mem_addr'], 16) == address and int(r['mem_rmask'], 16): r['rd'] = '0'
        with self.assertRaises(ValueError): q.footprint(rows, self.pre['symbols'])

    def test_wrong_guard(self):
        rows = copy.deepcopy(self.rows); address = self.pre['symbols']['vfirst_snapshot']
        row = next(r for r in reversed(rows) if int(r['mem_addr'], 16) == address and int(r['mem_rmask'], 16))
        row['rd_wdata'] = hex(int(row['rd_wdata'], 16) ^ 1)
        with self.assertRaises(ValueError): q.footprint(rows, self.pre['symbols'])

    def test_wrong_CSR(self):
        rows = copy.deepcopy(self.rows); address = self.pre['symbols']['vfirst_ledger'] + 32
        row = next(r for r in reversed(rows) if int(r['mem_addr'], 16) == address and int(r['mem_rmask'], 16))
        row['rd_wdata'] = '0'
        with self.assertRaises(ValueError): q.footprint(rows, self.pre['symbols'])

    def test_trap_rejected(self):
        rows = copy.deepcopy(self.rows); rows[100]['trap'] = '1'
        with self.assertRaises(ValueError): q.footprint(rows, self.pre['symbols'])

    def mutate_write(self, **change):
        activities = copy.deepcopy(self.activities)
        a = next(a for a in activities.values() if a.writes)
        a.writes[0] = q.vc.VectorWrite(**dict(a.writes[0].__dict__, **change))
        return activities

    def test_wrong_native_owner(self):
        with self.assertRaises(ValueError): self.native(self.mutate_write(arch_seq=999))

    def test_unknown_native_byte(self):
        with self.assertRaises(ValueError): self.native(self.mutate_write(known_be=0))

    def test_wrong_native_source(self):
        with self.assertRaises(ValueError): self.native(self.mutate_write(source=2))

    def test_wrong_native_EEW(self):
        with self.assertRaises(ValueError): self.native(self.mutate_write(eew=1))

    def test_missing_mask_byte(self):
        with self.assertRaises(ValueError): self.native(self.mutate_write(be=254))

    def test_extra_register_write(self):
        with self.assertRaises(ValueError): self.native(self.mutate_write(addr=4))

    def test_wrong_mask_data(self):
        with self.assertRaises(ValueError): self.native(self.mutate_write(data=1))

    def test_duplicate_native_write(self):
        activities = copy.deepcopy(self.activities); a = next(a for a in activities.values() if a.writes)
        a.writes.append(a.writes[0])
        with self.assertRaises(ValueError): self.native(activities)

    def test_vfirst_forbidden_VRF_write(self):
        activities = copy.deepcopy(self.activities)
        seq = next(s for s, i in self.mapping.items() if self.reference[i].pc == self.pre['symbols']['vfirst_scalar_op'])
        activities[seq].writes = writes(0, seq, activities[seq].instruction)
        with self.assertRaises(ValueError): self.native(activities)

    def test_no_vfirst_backend(self):
        activities = copy.deepcopy(self.activities)
        seq = next(s for s, i in self.mapping.items() if self.reference[i].pc == self.pre['symbols']['vfirst_scalar_op'])
        activities.pop(seq)
        with self.assertRaises(ValueError): self.native(activities)

    def test_incomplete_backend(self):
        activities = copy.deepcopy(self.activities); activities[0].completions = 0
        with self.assertRaises(ValueError): self.native(activities)

    def test_native_vlm_not_architectural_VL(self):
        activities = copy.deepcopy(self.activities); activities[0].vl = 1024
        with self.assertRaises(ValueError): self.native(activities)


class RunAndGainTests(unittest.TestCase):
    def test_exact_command_600_budget(self):
        cmd = q.runner.command(q.life.OUT / 'unit-not-run')
        self.assertEqual(cmd[0], str(q.life.IMAGE)); self.assertIn('+PRELOAD=' + str(q.runner.ELF), cmd)
        self.assertIn('+NO_FSDB', cmd); self.assertEqual(q.runner.BUDGET, 600)

    def test_existing_output_not_fresh_prepare(self):
        with self.assertRaises(ValueError): q.runner.prepare(q.life.OUT)

    def test_lifecycle_namespace_does_not_mutate_frozen_worker(self):
        original = q.runner.worker.BUDGET
        with tempfile.TemporaryDirectory(dir=q.life.OUT) as parent:
            out = Path(parent).with_name(Path(parent).name + '-not-created')
            manifest = dict(timeout_s=600, command=q.runner.command(out), output=str(out), pins={'fixture': '0' * 64})
            process = SimpleNamespace(pid=123, wait=lambda timeout: 0)
            with patch.object(q.life, 'check'), patch.object(q.runner.worker.subprocess, 'Popen', return_value=process):
                try:
                    q.runner.invoke_run(out, manifest)
                    self.assertEqual(json.loads((out / 'started.json').read_bytes())['budget_s'], 600)
                    self.assertEqual(json.loads((out / 'started.json').read_bytes())['input_elf'], str(q.runner.ELF))
                finally:
                    import shutil
                    if out.exists(): shutil.rmtree(out)
        self.assertEqual(q.runner.worker.BUDGET, original)

    def test_terminal_exit0_not_timeout(self):
        with tempfile.TemporaryDirectory(dir=q.life.OUT) as tmp:
            run = Path(tmp); manifest = dict(command=q.runner.command(run))
            state = dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=0, timeout=False,
                case=q.runner.NAME, coverage_admitted=False, admission_performed=False, pid=123, wall_seconds=1)
            started = dict(command=manifest['command'], input_elf=str(q.runner.ELF), elf_sha256=q.runner.ELF_SHA,
                image=str(q.life.IMAGE), image_sha256=q.runner.IMAGE_SHA, pid=123, process_group=123,
                budget_s=600, foreground_lifetime=True)
            for name, value in (('simulation-status.json', state), ('started.json', started),
                                ('manifest.json', dict(manifest, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))):
                q.life.save(run / name, value)
            q.terminal(run, manifest)
            state['timeout'] = True; (run / 'simulation-status.json').write_text(json.dumps(state))
            with self.assertRaises(ValueError): q.terminal(run, manifest)
            state['timeout'] = False; state['returncode'] = False
            (run / 'simulation-status.json').write_text(json.dumps(state))
            with self.assertRaises(ValueError): q.terminal(run, manifest)

    def test_twenty_slot_gain_and_checksum_guard(self):
        static = q.life.read_bound(q.runner.STATIC, q.runner.STATIC_SHA); scope = static['scope']
        before = {scope: dict(width=static['serialized_width'], checksum=static['toggle_checksum'], bits='0x0')}
        positions = [i for t in static['targets'] for i in t['serialized_slots']]
        sample = {scope: dict(before[scope], bits=hex(sum(1 << (static['serialized_width'] - 1 - i) for i in positions)))}
        result, scoped = q.target_gain(before, sample, static['targets'])
        self.assertEqual(result['target_hit_count'], 20); self.assertIsNone(result['official_percentage'])
        sample[scope]['checksum'] = 'foreign'
        with self.assertRaises(ValueError): q.target_gain(before, sample, static['targets'])

    def test_exact775_before_targets_zero(self):
        static = q.life.read_bound(q.runner.STATIC, q.runner.STATIC_SHA)
        base, bits, before = q.runner.baseline(static)
        self.assertEqual(len(bits['tests']), 775)
        self.assertEqual(before[static['scope']]['width'], 16358)


class Actual775UnionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = q.life.read_bound(q.runner.BASE / 'admission-manifest.json', q.runner.BASE_SHA)
        path = q.runner.BASE / 'combined-bits.json'
        cls.before = q.life.read_bound(path, base['output_pins'][str(path)])
        cls.single = copy.deepcopy(cls.before)
        cls.single['tests'] = ['/synthetic-independent-candidate-not-DUT/code.vdb']
        cls.combined = q.runner.bitmap.combine(cls.before, cls.single)

    def test_real_metric_population_not_unique_scope_count(self):
        result = q.exact_raw_union(self.before, self.single, self.combined)
        self.assertEqual(result['metric_instance_counts'], dict(line=1892, cond=2023, branch=2155, fsm=92))
        self.assertEqual(result['metric_instance_records'], 6162)
        self.assertEqual(result['unique_hierarchy_scopes'], 2624)

    def test_missing_scope(self):
        single = copy.deepcopy(self.single); single['metrics']['line'].pop(next(iter(single['metrics']['line'])))
        with self.assertRaises(ValueError): q.exact_raw_union(self.before, single, self.combined)

    def test_extra_scope(self):
        single = copy.deepcopy(self.single); single['metrics']['cond']['foreign.scope'] = dict(width=0, checksum='0', bits='0x0')
        with self.assertRaises(ValueError): q.exact_raw_union(self.before, single, self.combined)

    def test_same_count_replaced_scope(self):
        single = copy.deepcopy(self.single); rows = single['metrics']['branch']
        rows['foreign.scope'] = rows.pop(next(iter(rows)))
        with self.assertRaises(ValueError): q.exact_raw_union(self.before, single, self.combined)

    def test_width_drift(self):
        single = copy.deepcopy(self.single); next(iter(single['metrics']['line'].values()))['width'] += 1
        with self.assertRaises(ValueError): q.exact_raw_union(self.before, single, self.combined)

    def test_checksum_drift(self):
        single = copy.deepcopy(self.single); next(iter(single['metrics']['line'].values()))['checksum'] = 'foreign'
        with self.assertRaises(ValueError): q.exact_raw_union(self.before, single, self.combined)

    def test_not_mathematical_OR(self):
        combined = copy.deepcopy(self.combined)
        row = next(r for r in combined['metrics']['line'].values() if r['width'] > 0)
        row['bits'] = hex(int(row['bits'], 16) ^ 1)
        with self.assertRaises(ValueError): q.exact_raw_union(self.before, self.single, combined)

    def test_prefix_changed(self):
        combined = copy.deepcopy(self.combined); combined['tests'][0], combined['tests'][1] = combined['tests'][1], combined['tests'][0]
        with self.assertRaises(ValueError): q.exact_raw_union(self.before, self.single, combined)


class RealPrepareContractTests(unittest.TestCase):
    def test_actual_prepare_all_dependencies_and_collector_pin_contract(self):
        # Actual prepare, not a mocked preflight/image/baseline. Never invoke run.
        import shutil
        with tempfile.TemporaryDirectory(dir=q.life.OUT) as temporary:
            run = Path(temporary).with_name(Path(temporary).name + '-prepare-fixture')
            record = run.with_name(run.name + '.prepared.json')
            try:
                manifest = q.runner.prepare(run)
                self.assertFalse(run.exists())
                self.assertEqual(manifest['baseline'], 775)
                self.assertEqual(manifest['timeout_s'], 600)
                image = q.life.read_bound(q.life.PLAN, q.life.PLAN_SEAL)['image']
                self.assertEqual(len(image), 66)
                self.assertTrue(all(manifest['pins'][path] == sha for path, sha in image.items()))
                for path in (q.runner.PRE, q.runner.STATIC, q.runner.COMPILE, q.runner.BASE / 'combined-bits.json',
                             Path(q.__file__).resolve(), Path(q.runner.worker.__file__).resolve(),
                             Path(q.control.previous.__file__).resolve(), Path(q.vc.__file__).resolve()):
                    self.assertEqual(manifest['pins'][str(path)], q.life.digest(path))
                q.life.save(record, manifest)
                seal = q.life.digest(record)
                run.mkdir()
                witness = run / 'synthetic-host-witness.txt'
                witness.write_text('HOST_FIXTURE_NOT_SIMULATION\n')
                pins = q.evidence_pins(run, seal, manifest)
                self.assertEqual(pins[str(record)], seal)
                self.assertEqual(pins[str(witness)], q.life.digest(witness))
                q.life.check(pins)
                bad = dict(manifest, pins=dict(manifest['pins'], **{str(witness): '0' * 64}))
                with self.assertRaises(ValueError): q.evidence_pins(run, seal, bad)
                bad = dict(manifest, pins=dict(manifest['pins'], **{str(record): '0' * 64}))
                with self.assertRaises(ValueError): q.evidence_pins(run, seal, bad)
                self.assertFalse((run / 'started.json').exists())
                self.assertFalse((run / 'code.vdb').exists())
            finally:
                if run.exists(): shutil.rmtree(run)
                if record.exists(): record.unlink()

    def test_all_merge_calls_have_exactly_two_arguments(self):
        import ast
        for module in (q, q.runner):
            tree = ast.parse(Path(module.__file__).read_text())
            calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and
                     isinstance(node.func, ast.Attribute) and node.func.attr == 'merge_pins']
            self.assertTrue(calls)
            self.assertTrue(all(len(call.args) == 2 and not call.keywords for call in calls))


if __name__ == '__main__': unittest.main()

#!/usr/bin/env python3
"""Runner host tests only. Illegal instructions are NOT fabricated as RVFI retires."""
import csv
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run as r


class ProtocolScope(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vectors = json.loads((r.BUILD/'vectors/vectors.json').read_text())
        self.software = json.loads((r.BUILD/'build.json').read_text())
        self.commit = self.root/'commit.csv'
        # Only successful PVs retire. Cause2 is observed in handler CSR reads.
        rows = []
        for s in r.cases.attempts(self.vectors['cases']):
            pc = self.software['fault_pc'][str(s['instruction'])]
            if s['error']:
                rows += [dict(event='retire', insn='34202373', pc='80002000', trap=0, rd_wdata='0000000000000002'),
                         dict(event='retire', insn='341023f3', pc='80002004', trap=0, rd_wdata=f'{pc:016x}')]
            else:
                rows.append(dict(event='retire', insn=f'{s["instruction"]:08x}', pc=f'{pc:016x}', trap=0, rd_wdata='0'))
        self.write_commit(rows)
        self.requests = [(s['instruction'], s['error']) for s in r.cases.attempts(self.vectors['cases'])
                         if not (s['error'] and s['kind'] in ('fs_off', 'vs_off'))]
        self.requests += [(r.cases.QBS_INSN, 0), (r.cases.VADD_INSN, 0)]

    def write_commit(self, rows):
        with self.commit.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=('event', 'insn', 'pc', 'trap', 'rd_wdata'))
            writer.writeheader(); writer.writerows(rows)

    def events(self, requests=None):
        rows = []
        for i, (insn, exc) in enumerate(self.requests if requests is None else requests):
            cycle, tid = 10+3*i, i % 8
            rows += [f'[ARA_CONTRACT_TRACE] sample=pre_edge cycle={cycle} req=1/1 fire=1 id={tid:x} '
                     f'insn={insn:08x} resp=0/1 fire=0 id=0 exc=0 pending=0 stalled=00 errors=0000000',
                     f'[ARA_CONTRACT_TRACE] sample=pre_edge cycle={cycle+1} req=0/1 fire=0 id=0 '
                     f'insn=00000000 resp=1/1 fire=1 id={tid:x} exc={exc} pending=0 stalled=00 errors=0000000',
                     f'UVM_INFO @ 100: monitor [CVXIF/EVENT] cycle={cycle+1} req_fire=1 req_id={tid} '
                     f'insn={insn:08x} resp_fire=0 resp_id=0 exc=0',
                     f'UVM_INFO @ 100: monitor [CVXIF/EVENT] cycle={cycle+2} req_fire=0 req_id=0 '
                     f'insn=00000000 resp_fire=1 resp_id={tid} exc={exc}']
        return '\n'.join(rows)+'\n'

    def scope(self, text=None, proof=None):
        return r.scoped_illegals(text or self.events(), self.commit, self.vectors, self.software,
                                proof or dict(contract_counts=dict(exceptions=10)))

    def test_actual_rvfi_scope_has_21_successes_not_33_fault_retires(self):
        result = self.scope()
        self.assertEqual((result['successful_pv_retires'], result['accelerator_exceptions']), (21, 10))
        self.assertEqual(result['issues_ignored'], 0)

    def test_synthetic_illegal_retire_is_rejected(self):
        with self.commit.open() as stream: rows = list(csv.DictReader(stream))
        rows.append(dict(rows[0], insn=f'{r.cases.PV_INSN:08x}', trap='1'))
        self.write_commit(rows)
        with self.assertRaisesRegex(ValueError, 'synthetic illegal'): self.scope()

    def test_wrong_success_pc_or_missing_retire_is_rejected(self):
        with self.commit.open() as stream: original = list(csv.DictReader(stream))
        for mutated in ([dict(original[0], pc='8000abcd')]+original[1:], original[1:]):
            self.write_commit(mutated)
            with self.assertRaises(ValueError): self.scope()

    def test_missing_extra_or_reclassified_accelerator_fault_is_rejected(self):
        for rows in (self.requests[:-1]+[(r.cases.PV_INSN, 0)],
                     [(insn, 0) for insn, _ in self.requests],
                     self.requests+[(r.cases.PV_INSN, 1)],
                     self.requests[:-1]+[(r.cases.VADD_INSN, 1)]):
            with self.assertRaises(ValueError): self.scope(self.events(rows))

    def test_missing_or_orphan_response_is_rejected(self):
        lines = self.events().splitlines()
        bad = '\n'.join(x for x in lines if not ('cycle=11 ' in x and x.startswith('[ARA_CONTRACT_TRACE]')))
        with self.assertRaises(ValueError): self.scope(bad)
        with self.assertRaises(ValueError): self.scope(self.events().replace('resp=1/1 fire=1 id=0', 'resp=1/1 fire=1 id=f', 1))

    def test_unchanged_global_protocol_allows_expected_exceptions_but_not_errors(self):
        n = len(self.requests)
        log = self.root/'run.log'
        vector = self.root/'vector.csv'
        vector.write_text('cycle,event,vid\n1000,alloc,1\n1001,done,1\n')
        text = (self.events()+f'[ARA_CONTRACT] requests={n} responses={n} exceptions=10 '
                'mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0\n'
                f'UVM_INFO @ 100: scoreboard [CVXIF/COUNT] observed requests={n} responses={n} '
                'aborted=0 reused=0 immediate=0\n'
                'UVM_INFO @ 100: scoreboard [VID/COUNT] allocations=1 completions=1 aborted=0 max_live=1\n'
                'UVM_INFO @ 100: monitor [VID/EVENT] cycle=200 alloc=1 alloc_id=1 done=00\n'
                'UVM_INFO @ 100: monitor [VID/EVENT] cycle=201 alloc=0 alloc_id=0 done=02\n'
                'UVM_INFO @ 100: scoreboard [AXI/READ_COUNT] ar=1 r_beats=1 completed=1 aborted=0 pending=0 max_pending=1\n'
                'UVM_INFO @ 100: scoreboard [AXI/WRITE_COUNT] aw=1 w_beats=1 w_bursts=1 matched=1 b=1 aborted=0 pending=0 max_pending=1\n'
                'UVM_INFO @ 100: reporter [TEST_DONE] complete\nUVM_ERROR : 0\nUVM_FATAL : 0\n'
                'Core Test *** SUCCESS ***\n')
        log.write_text(text)
        proof = r.uvm_dut.check_real_uvm_log(log, require_events=True, require_backend=True,
                    require_axi=True, require_axi_write=True, vector_trace=vector)
        self.assertEqual((proof['status'], proof['issues']), ('PASS', []))
        self.scope(text, proof)
        for bad in (text.replace('protocol_errors=0', 'protocol_errors=1'),
                    text+'\n[ARA_CONTRACT_ERROR] payload changed\n', text.replace('UVM_ERROR : 0', 'UVM_ERROR : 1')):
            log.write_text(bad)
            proof = r.uvm_dut.check_real_uvm_log(log, require_events=True, require_backend=True,
                    require_axi=True, require_axi_write=True, vector_trace=vector)
            self.assertEqual(proof['status'], 'FAIL')

    def test_pending_successor_blocks_before_hardware_collection(self):
        with patch.object(r, 'CHECKER_SHA', ''), patch.object(r.e, 'checked_soc') as soc:
            with self.assertRaisesRegex(ValueError, 'LAUNCH BLOCKED'): r.collect()
            soc.assert_not_called()

    def test_recipe_never_runs_old_checker_or_disables_protocol_requirements(self):
        cmds = r.recipes(self.root, dict(simv='/fake/simv'), dict(elf='/fake/boundary.elf'), '/usr/bin/python3')
        self.assertIn(str(r.SCOPED_CHECKER), cmds['boundary'])
        self.assertNotIn(str(r.HERE/'check.py'), cmds['boundary'])
        self.assertTrue({'--require-events', '--require-backend', '--require-axi', '--require-axi-write'} <= set(cmds['protocol']))
        self.assertIn('+RESIDENT_PV_PERF', cmds['simulation'])
        self.assertIn('+COMMIT_TRACE='+str(self.root/'work/commit.csv'), cmds['simulation'])
        self.assertNotIn('+NO_UVM', cmds['simulation'])


class FrozenRunner(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.out = root/'resident_pv_soc_boundary_vcs_test'
        self.source = root/'source'
        self.source.mkdir()
        (self.out/'inputs').mkdir(parents=True)
        (self.out/'work').mkdir()
        pins = {}
        for n in r.OWN:
            for p in (self.source/n, self.out/'inputs'/n):
                p.write_text(n+'\n'); pins[str(p)] = r.sha(p)
        self.soc = dict(simv='/fake/simv')
        self.software = dict(elf='/fake/boundary.elf')
        self.inventory = {'test.py': '0'*64}
        self.s = r.selection(self.out, self.soc, self.software, self.inventory, r.smoke.environment())
        r.save(self.out/'selection.json', self.s)
        for n in ('selection.json', 'host-tests.log', 'host-tests.command.json',
                  'scoped-tests.log', 'scoped-tests.command.json',
                  'image-contract.log', 'image-contract.command.json'):
            p = self.out/n
            if not p.exists(): p.write_text('fixture\n')
            pins[str(p)] = r.sha(p)
        self.pins = pins
        r.save(self.out/'source-pins.json', pins)
        r.save(self.out/'prepared.json', r.frozen_receipt(self.out))
        for patcher in (patch.object(r, 'OUT', root), patch.object(r, 'HERE', self.source),
            patch.object(r, 'collect', return_value=(self.soc, self.software, dict(pins), self.inventory))):
            patcher.start(); self.addCleanup(patcher.stop)

    def test_document_or_source_inventory_drift_rejected(self):
        r.verify_prepared(self.out)
        (self.source/'RUN.md').write_text('drift\n')
        with self.assertRaises(ValueError): r.verify_prepared(self.out)

    def test_selection_and_snapshot_inventory_fail_closed(self):
        r.verify_prepared(self.out)
        (self.out/'inputs/extra.py').write_text('unreviewed\n')
        with self.assertRaises(ValueError): r.verify_prepared(self.out)

    def test_direct_owner_and_print_only_service_recipe(self):
        command = r.service_command(self.out, r.sha(self.out/'source-pins.json'))
        self.assertIn('--property=RuntimeMaxSec=7200', command)
        self.assertIn('--property=KillMode=control-group', command)
        self.assertIn(str(self.out/'inputs/run.py'), command)
        unit = r.service_unit(self.out)
        r.smoke.direct_owner('/user.slice/'+unit, unit, 12, 12)
        with self.assertRaises(ValueError): r.smoke.direct_owner('/other.service', unit, 12, 12)
        with self.assertRaises(ValueError): r.smoke.direct_owner('/user.slice/'+unit, unit, 11, 12)
        with self.assertRaises(ValueError): r.service_command(self.out, '0'*64)

    def test_live_worker_or_missing_review_cannot_execute(self):
        with self.assertRaises(ValueError): r.run(self.out, False, r.sha(self.out/'source-pins.json'))
        with self.assertRaises(ValueError): r.run(self.out, True, r.sha(self.out/'source-pins.json'))
        self.assertFalse((self.out/'attempt.json').exists())

    def test_prepare_failure_retained_without_simulation_or_retry(self):
        out = self.out.parent/'resident_pv_soc_boundary_vcs_failure'
        with patch.object(r, '__file__', str(self.source/'run.py')), \
             patch.object(r, 'collect', side_effect=ValueError('successor not ready')), \
             patch.object(r, 'execute', side_effect=AssertionError('No child allowed')):
            with self.assertRaisesRegex(ValueError, 'retained'): r.prepare(out)
            self.assertEqual(json.loads((out/'prepare-report.json').read_text())['state'], 'FAIL')
            with self.assertRaisesRegex(ValueError, 'Preserve'): r.prepare(out)

    def test_owner_failure_is_terminal_and_not_retried(self):
        review = r.sha(self.out/'source-pins.json')
        with patch.object(r, '__file__', str(self.out/'inputs/run.py')), \
             patch.object(r.subprocess, 'check_output', return_value='12'), \
             patch.object(r.smoke, 'direct_owner', side_effect=ValueError('wrong owner')), \
             patch.object(r, 'execute') as execute:
            result = r.run(self.out, True, review)
            self.assertEqual(result['state'], 'FAIL'); execute.assert_not_called()
            self.assertTrue((self.out/'attempt.json').exists())
            with self.assertRaisesRegex(ValueError, 'no retries'): r.run(self.out, True, review)

    def test_full_image_proof_and_raw_log_cannot_be_relaxed(self):
        simv, library, log, vector = [self.out/n for n in ('simv', 'dut.so', 'log', 'vector')]
        for p in (simv, library, log, vector): p.write_text(p.name)
        image = {str(p): r.sha(p) for p in (simv, library)}
        soc = dict(simv=str(simv), image_pins=image)
        software = dict(elf_sha256='a'*64)
        proof = dict(status='PASS', issues=[], elf_sha256='a'*64, simv_sha256=r.sha(simv),
                     sim_image_sha256=image, log_sha256=r.sha(log), vector_trace_sha256=r.sha(vector))
        r.smoke.check_protocol(proof, soc, software, log, vector)
        for changed in (dict(issues=['expected illegal']), dict(status='FAIL'), dict(sim_image_sha256={}),
                        dict(elf_sha256='b'*64), dict(log_sha256='c'*64)):
            with self.assertRaises(ValueError): r.smoke.check_protocol(dict(proof, **changed), soc, software, log, vector)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Independent host checks of source lineage, tuple values, and frozen artifacts."""
import json
from pathlib import Path
import re
import sys
import unittest

from prepare_batch import ARCHIVE, CAMPAIGN, FROZEN, HERE, INTEGRATION, ROOT, sha, save


class Sources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads((HERE / 'inventory83.json').read_text())
        cls.provenance = json.loads((HERE / 'prepared01/provenance.json').read_text())

    def test_original_source_and_partition_lineage(self):
        mapping_path = CAMPAIGN / 'rvv_permute_partitions01/parent_mapping.json'
        mapping = json.loads(mapping_path.read_text())
        children = {c['name']: (p['parent'], c) for p in mapping['parents']
                    for c in p['partitions']}
        lineage = []
        for record in self.inventory['records']:
            case = record['case']
            folder = CAMPAIGN / 'rvv_small_gather02' / case['name']
            original = folder / 'original.c'
            reduced = (ARCHIVE / case['name'] / 'scenario.c').read_text()
            pattern = r'^            if\(!\(seed==0 && op==\d+ && s==0 && l==2 && mode==0 && trial==0\)\)continue;\n'
            restored, count = re.subn(pattern, '', reduced, flags=re.MULTILINE)
            self.assertEqual(count, 1)
            self.assertEqual(restored, original.read_text())
            parent = None
            if case['original_name'] in children:
                parent, child = children[case['original_name']]
                self.assertEqual(child['sha256'], case['original_elf_sha256'])
                self.assertEqual(child['operation_ids'], [case['selected_trial']['op']])
            lineage.append(dict(name=case['name'], original_c=str(original),
                                original_c_sha256=sha(original),
                                parent=None if parent is None else dict(
                                    name=parent['name'], sha256=parent['sha256'],
                                    configurations=parent['configurations']),
                                reduction_change='one exact-trial filter only'))
        self.assertEqual(sum(r['parent'] is not None for r in lineage), 80)
        save(HERE / 'lineage83.json', dict(parent_mapping=str(mapping_path),
                                          parent_mapping_sha256=sha(mapping_path), records=lineage))

    def test_independent_xorshift_and_prestart_tuple(self):
        mask64 = (1 << 64) - 1
        selected_results = []
        for record in self.inventory['records']:
            case = record['case']
            trial = case['selected_trial']
            self.assertEqual({k: v for k, v in trial.items() if k not in ('op', 'actual')},
                             dict(seed=0, scalar=0, vl=2, mask=0, element=0, vstart=1, expected=91))
            multiplier = {'mf8': 1/8, 'mf4': 1/4, 'mf2': 1/2,
                          'm1': 1, 'm2': 2, 'm4': 4, 'm8': 8}[case['lmul']]
            cap = int(1024 // case['sew'] * multiplier)
            rng = 0xe736815b449aec21
            data = []
            for _ in range(cap):
                rng ^= (rng << 13) & mask64
                rng ^= rng >> 7
                rng ^= (rng << 17) & mask64
                data.append(rng & ((1 << case['sew']) - 1))
            index0 = 31 if trial['op'] == 3 else 0
            self.assertEqual(trial['actual'], data[index0] if index0 < cap else 0)
            index1 = 1 if trial['op'] in (0, 20) else index0
            expected_first_two = [91, data[index1] if index1 < cap else 0]
            if record['selected']:
                selected_results.append(dict(name=case['name'], capacity=cap,
                                             expected_first_two=expected_first_two))
        save(HERE / 'host_tuple_checks.json', dict(status='PASS', checked=83,
                                                  scope='independent scalar tuple values, not DUT execution',
                                                  selected=selected_results))

    def test_ports_unchanged_oracle_asm_and_runtime(self):
        sys.path.insert(0, str(INTEGRATION))
        from prepare import adapt
        prepared = HERE / 'prepared01'
        for file, digest in self.provenance['files'].items():
            self.assertEqual(sha(prepared / file), digest)
        for case in self.provenance['cases']:
            folder = prepared / case['id']
            archived = Path(case['source_directory'])
            for file in case['original_case']['scenario_sources']:
                self.assertEqual((folder / 'original' / file).read_bytes(), (archived / file).read_bytes())
            self.assertEqual((folder / 'case.c').read_text(),
                             adapt((archived / 'scenario.c').read_text(), case['id']))
        for file in ('startup.S', 'runtime.c', 'replay.ld'):
            self.assertEqual((prepared / file).read_bytes(), (INTEGRATION / file).read_bytes())
        for backend in ('soc', 'spike'):
            programs = json.loads((HERE / (backend + '01/programs.json')).read_text())
            self.assertEqual(programs['backend'], 'vcs-soc' if backend == 'soc' else 'spike-htif')
            self.assertEqual(programs['provenance_sha256'], sha(prepared / 'provenance.json'))
            self.assertEqual(len(programs['programs']), 8)
            for program in programs['programs'].values():
                self.assertEqual(sha(Path(program['path'])), program['sha256'])
        reference = json.loads((HERE / 'reference01/reference.json').read_text())
        self.assertEqual(len(reference['results']), 8)
        self.assertTrue(all(r['status'] == 'PASS' and r['returncode'] == 0 for r in reference['results']))
        self.assertEqual(sha(FROZEN / 'snapshot.json'), self.inventory['candidate03_snapshot_sha256'])
        self.assertEqual(sha(ROOT / 'hardware/src/masku/masku.sv'), self.inventory['masku_sha256'])


if __name__ == '__main__':
    unittest.main()

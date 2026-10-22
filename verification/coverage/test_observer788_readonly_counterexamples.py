"""Frozen-input negative replay against the draft owner; never edits or launches.

Failures here mean a counterexample is still accepted, not a DUT failure.
The in-memory inventory is a host fixture, never a native capture.
"""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import report_population788_observers as owner

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT/'verification/out/cvxif-passive-bind-testbench-scope-source-review770-agent-20261007-01.json'
REVIEW_SHA = 'a274a9ae809ab2bcc8823cf45e1b3a259ef263ed7a9cb0a903d021796cfa5b08'
EL = ROOT/'verification/out/current-population785-rr190-prepared-agent-20261008-01/combined.el'
EL_SHA = '08a1ee3d307672d7f75c4956b312dc5affebaa8366213ebb7c5f2592978f5dc5'
BITS = ROOT/'verification/out/scalar-entropy64-offline-admitted788-agent-20261008-01/combined-bits.json'
BITS_SHA = 'd2227227a30dc2a76fad0ef611c033110c83427916c6545a4154ea850857ab06'
SCOPES = ('ara_tb.dut.i_ara_soc.i_system.i_ara_cvxif_dut_bind',
          'ara_tb.dut.i_ara_soc.i_system.i_ara_cvxif_dut_bind.cvxif')
STAGES = ('before', 'selected', 'reset', 'reloaded', 'final')


def bound(path, sha):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != sha:
        raise ValueError('Counterexample frozen input drift: '+str(path))
    return data


def fixtures():
    review = json.loads(bound(REVIEW, REVIEW_SHA))
    text = bound(EL, EL_SHA).decode('ascii')
    chunks = text.split('CHECKSUM:')[1:]
    target = [b for b in chunks if any('INSTANCE: '+s+'\n' in b for s in SCOPES)]
    # One real nonobserver block keeps the outside-scope preservation gate active.
    guard = next(b for b in chunks if not any('INSTANCE: '+s+'\n' in b for s in SCOPES))
    inherited = 'CHECKSUM:'+guard+''.join('CHECKSUM:'+b for b in target)
    compiled = copy.deepcopy(review['compiled_scopes'])
    identities = {i['scope']: str(i['toggle_checksum']) for i in compiled}
    bits = json.loads(bound(BITS, BITS_SHA))
    capacities, checks = {}, {}
    for scope in SCOPES:
        capacities[scope], checks[scope] = {}, {}
        for metric in ('line', 'cond', 'branch', 'fsm'):
            row = bits['metrics'][metric].get(scope)
            capacities[scope][metric] = row['width'] if row else 0
            checks[scope][metric] = [str(row['checksum'])] if row else []
        capacities[scope]['tgl'] = len(next(i for i in compiled if i['scope'] == scope)['typed_inventory'])
        checks[scope]['tgl'] = [identities[scope]]
    ob = dict(compiled_scopes=compiled, metric_checksums={s: [v for group in checks[s].values() for v in group] for s in SCOPES},
              per_metric_checksums=checks, capacities=capacities)
    header = 'CHECKSUM: "2332976182 498965595"\nINSTANCE: '+SCOPES[0]+'\n'
    fabricated = header+'Toggle not_a_compiled_object "logic not_a_compiled_object"\n'
    valid_but_incomplete = header+'Toggle req_valid_i "logic req_valid_i"\n'
    return ob, inherited, 'CHECKSUM:'+guard, fabricated, valid_but_incomplete


def inventory_fixture(ob):
    """Synthetic native-shaped host rows, with authoritative Toggle labels only."""
    result = {}
    availability = dict.fromkeys(owner.observer.METRICS, True)
    availability.update(dict.fromkeys(owner.observer.PROTECTED, False))
    for stage in STAGES:
        result[stage+'_availability.json'] = json.dumps(availability)
        for metric in owner.observer.METRICS:
            for index, scope in enumerate(SCOPES):
                item = next(i for i in ob['compiled_scopes'] if i['scope'] == scope)
                capacity = ob['capacities'][scope][dict(zip(owner.observer.METRICS, ('line','cond','branch','fsm','tgl')))[metric]]
                stem = '%s_%s_%d' % (stage, metric, index)
                if not capacity:
                    result[stem+'.skipped.json'] = json.dumps(dict(status='SKIPPED_COMPILED_ZERO', scope=scope, metric=metric, capacity=0))
                    continue
                labels = [n if kind == 'node' else n+'['+left+':'+right+']'
                          for kind, n, _, _, _, left, right in item['typed_inventory']]
                if metric != 'Toggle':
                    labels = ['host_point_%d' % i for i in range(capacity)]
                flag = '1' if stage in ('selected', 'reloaded') else '0'
                stream = io.StringIO(); writer = csv.writer(stream, delimiter='\t', lineterminator='\n')
                writer.writerow(['path', 'meta', 'name', 'excluded', 'cells'])
                for label in labels:
                    writer.writerow([scope+'/'+label, scope+'/'+label, label, flag, 'host_fixture'])
                result[stem+'.tsv'] = stream.getvalue()
                result[stem+'.columns'] = 'Name Excluded HostFixture\n'
    return result


class ReadonlyCounterexamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ob, cls.inherited, cls.guard, cls.foreign, cls.incomplete = fixtures()

    def test_fixture_is_bound_to_real_two_scopes_and_padding(self):
        self.assertEqual({x['scope'] for x in self.ob['compiled_scopes']}, set(SCOPES))
        self.assertEqual(owner.padding_covered(self.inherited, self.ob), 18516)
        for row in self.ob['compiled_scopes']:
            self.assertNotIn('not_a_compiled_object', [v[1] for v in row['typed_inventory']])

    def test_fabricated_field_with_real_checksum_must_reject(self):
        with self.assertRaises(ValueError, msg='BLOCKER: foreign typed field accepted under real checksum'):
            owner.native_gate(self.inherited+self.foreign, self.inherited, self.ob)

    def test_deleted_padding_valid_field_only_must_reject(self):
        with self.assertRaises(ValueError, msg='BLOCKER: all inherited padding deleted; one valid scalar accepted'):
            owner.native_gate(self.guard+self.incomplete, self.inherited, self.ob)

    def test_same_count_missing_toggle_label_must_reject(self):
        data = inventory_fixture(self.ob)
        item = next(i for i in self.ob['compiled_scopes'] if i['scope'] == SCOPES[0])
        old = item['typed_inventory'][0][1]
        for stage in STAGES:
            key = stage+'_Toggle_0.tsv'
            lines = list(csv.reader(io.StringIO(data[key]), delimiter='\t'))
            self.assertEqual(lines[1][2], old)
            lines[1][:3] = ['foreign/path', 'foreign/meta', 'not_a_compiled_object']
            stream = io.StringIO(); csv.writer(stream, delimiter='\t', lineterminator='\n').writerows(lines)
            data[key] = stream.getvalue()
        with patch.object(Path, 'read_text', lambda path, *a, **k: data[path.name]):
            with self.assertRaises(ValueError, msg='BLOCKER: same-count foreign Toggle label accepted'):
                owner.observer_audit(ROOT/'verification/out/readonly-counterexample-not-created', dict(observer=self.ob))

    def test_same_count_missing_line_label_must_reject(self):
        data = inventory_fixture(self.ob)
        expected = tuple('host_point_%d' % i for i in range(8))
        for stage in STAGES:
            key = stage+'_Line_0.tsv'
            rows = list(csv.DictReader(io.StringIO(data[key]), delimiter='\t'))
            self.assertEqual(tuple(r['name'] for r in rows), expected)
            data[key] = data[key].replace('host_point_0', 'foreign_point_0')
            mutated = list(csv.DictReader(io.StringIO(data[key]), delimiter='\t'))
            self.assertEqual(len(rows), len(mutated))
            self.assertNotEqual({r['name'] for r in rows}, {r['name'] for r in mutated})
        with patch.object(Path, 'read_text', lambda path, *a, **k: data[path.name]):
            with self.assertRaises(ValueError, msg='BLOCKER: same-count missing Line label has no compiled point binding'):
                owner.observer_audit(ROOT/'verification/out/readonly-counterexample-not-created', dict(observer=self.ob))


if __name__ == '__main__':
    unittest.main()

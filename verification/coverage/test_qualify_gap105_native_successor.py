"""Explicit build binding regression; no running simulation artifacts read."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import qualify_gap105_native_v2 as q


class Binding(unittest.TestCase):
    def test_missing_original_build_pin_is_added_explicitly(self):
        pins = q.bind_sources({})
        self.assertEqual(pins[str(q.BUILD)],q.BUILD_SEAL)
        self.assertEqual(pins[str(q.SNAPSHOT/'ara_dispatcher.sv')],q.frozen.DISPATCHER_SHA)
        for path in ('hardware/src/vlsu/qbs/qbs_commit.sv','hardware/tb/ara_commit_monitor.sv'):
            self.assertIn(str(q.life.ROOT/path),pins)

    def test_conflicting_build_pin_not_overwritten(self):
        original = {str(q.BUILD):'0'*64}
        with self.assertRaisesRegex(ValueError,'Conflicting'): q.bind_sources(original)
        self.assertEqual(original[str(q.BUILD)],'0'*64)

    def test_build_manifest_byte_drift_rejected(self):
        read = Path.read_bytes
        def changed(path): return read(path)+b' ' if path==q.BUILD else read(path)
        with patch.object(Path,'read_bytes',changed):
            with self.assertRaisesRegex(ValueError,'Sealed manifest'): q.bind_sources({})

    def test_snapshot_identity_cannot_redirect_to_current_rtl(self):
        read = q.life.read_bound
        def changed(path,seal):
            value = read(path,seal)
            if path==q.SNAPSHOT/'manifest.json':
                value = copy.deepcopy(value); value['files'][0]['snapshot_file'] = '../../hardware/src/ara_dispatcher.sv'
            return value
        with patch.object(q.life,'read_bound',changed):
            with self.assertRaisesRegex(ValueError,'snapshot binding'): q.bind_sources({})

    def test_commit_monitor_snapshot_byte_drift_rejected(self):
        original = q.life.digest
        for path in (q.life.ROOT/'hardware/src/vlsu/qbs/qbs_commit.sv',
                     q.life.ROOT/'hardware/tb/ara_commit_monitor.sv',q.SNAPSHOT/'ara_dispatcher.sv'):
            def changed(p): return '0'*64 if Path(p)==path else original(p)
            with patch.object(q.life,'digest',changed):
                with self.assertRaisesRegex(ValueError,'Pinned input changed'): q.bind_sources({})

    def test_conflicting_source_expected_pin_rejected(self):
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            q.bind_sources({str(q.life.ROOT/'hardware/src/vlsu/qbs/qbs_commit.sv'):'0'*64})

    def test_reviewed_test_successor_has_explicit_fixed_pin(self):
        path = Path(q.__file__).with_name('test_qualify_gap105_native_v2.py')
        self.assertEqual(q.life.digest(path),q.TEST_SEALS[path.name])
        self.assertEqual(q.life.digest(Path(q.frozen.__file__)),q.FROZEN_SEAL)


if __name__=='__main__': unittest.main()

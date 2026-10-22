"""Frozen negative gates plus actual disk prepare/check and re-sealed writer tampering."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import c910_lane23_padding1424_local_v3 as successor
import test_c910_lane23_padding1424_local as cases

cases.m = successor


class Padding1424V3(cases.Padding1424):
    def test_canonical_comparison_keeps_all_writer_checks(self):
        saved = json.loads(json.dumps(self.proof))
        successor.source_packet_gate(saved, self.proof)
        for change in ('expression', 'missing', 'extra'):
            bad = copy.deepcopy(saved)
            writers = bad['source_argument']['complete_prepare_writers']['ex1_remainder']
            if change == 'expression':
                writers[0][2] = "60'b1"
            elif change == 'missing':
                writers.clear()
            else:
                writers.append(writers[0])
            with self.assertRaises(ValueError):
                successor.source_packet_gate(bad, self.proof)

    def test_real_prepare_check_and_resealed_source_packet_rejection(self):
        # Only this test's fresh directory is created, modified and removed.
        with tempfile.TemporaryDirectory(prefix='c9101424-v3-realprepare-host-', dir=successor.life.OUT) as directory:
            out = Path(directory)
            out.rmdir()
            receipt = successor.prepare(out)
            self.assertFalse(receipt['EDA_started'])
            c = successor.check(out, receipt['seal'])
            proof_path = out / 'source-proof.json'
            saved = json.loads(proof_path.read_bytes())
            self.assertIsInstance(self.proof['source_argument']['complete_prepare_writers']['ex1_remainder'][0], tuple)
            self.assertIsInstance(saved['source_argument']['complete_prepare_writers']['ex1_remainder'][0], list)
            saved['source_argument']['complete_prepare_writers']['ex1_remainder'][0][2] = "60'b1"
            proof_path.write_text(json.dumps(saved, indent=2) + '\n')
            with self.assertRaisesRegex(ValueError, 'drift|changed|hash|pin|SHA|differs|digest|Frozen'):
                successor.check(out, receipt['seal'])
            # Re-pin the changed packet to exercise semantic replay, not merely SHA rejection.
            c['pins'][str(proof_path)] = successor.life.digest(proof_path)
            (out / 'config.json').write_text(json.dumps(c, indent=2) + '\n')
            seal = successor.life.digest(out / 'config.json')
            with self.assertRaisesRegex(ValueError, 'Exact canonical source packet including all writers'):
                successor.check(out, seal)


if __name__ == '__main__':
    unittest.main()

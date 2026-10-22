"""Run every frozen predecessor adversarial gate against the JSON-only successor."""
import json
import unittest

import c910_lane23_padding1424_local_v2 as successor
import test_c910_lane23_padding1424_local as cases

cases.m = successor


class Padding1424V2(cases.Padding1424):
    def test_source_packet_json_roundtrip_and_preserved_gates(self):
        self.assertEqual(json.loads(json.dumps(self.proof)), self.proof)
        self.assertEqual(self.proof['source_argument'],
                         json.loads(json.dumps(successor.old.source_guard(self.texts, self.seals))))
        for p, sha in successor.PREDECESSORS.items():
            self.assertEqual(self.proof['pins'][p], sha)
        self.assertEqual(successor.candidate(self.c), successor.old.candidate(self.c))
        self.assertEqual(successor.TCL, successor.old.TCL)
        self.assertEqual(len(successor.el_gate(self.el, self.c)), 1424)


if __name__ == '__main__':
    unittest.main()

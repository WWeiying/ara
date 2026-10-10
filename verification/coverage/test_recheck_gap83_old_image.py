"""Focused offline tests for full-comparison policy."""
import copy
import unittest
import recheck_gap83_old_image as r


class PolicyTests(unittest.TestCase):
    def test_full_comparison_and_prefix_negative(self):
        scalar = dict(status="TERMINAL_TOHOST_MATCH",ara_trap_events=0,skipped_unobservable_register_values=0,
            stopped_at_unobservable=None,matched_instructions=10,ara_retired_instructions=10)
        vector = dict(status="PASS",selected_index=None,stopped_at_spike_index=None,
            prefix_vector_destination_requests=2,vector_destination_requests=2,compared_instructions=2,
            skipped_unknown_bytes=0,non_bit_exact_instructions=0,unobservable_instructions=0,
            incomplete_requests=[],unretired_requests=[],trapped_requests=[])
        r.comparison_gate(scalar,vector)
        for key,value in (("status","PREFIX_MATCH"),("matched_instructions",9),("ara_trap_events",1),
                          ("skipped_unobservable_register_values",1)):
            bad = dict(scalar,**{key:value})
            with self.assertRaises(ValueError):r.comparison_gate(bad,vector)
        for key,value in (("selected_index",1),("stopped_at_spike_index",1),("compared_instructions",1),
                          ("skipped_unknown_bytes",1),("non_bit_exact_instructions",1),("incomplete_requests",[1])):
            bad = dict(vector,**{key:value})
            with self.assertRaises(ValueError):r.comparison_gate(scalar,bad)

    def test_signature_negative(self):
        with self.assertRaises(ValueError):r.g.signature({1:1,2:262,6:1},1,2)


if __name__ == "__main__":unittest.main()

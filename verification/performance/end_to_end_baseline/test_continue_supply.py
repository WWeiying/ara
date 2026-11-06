import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import continue_supply_sdk as campaign


class SupplyCampaignTests(unittest.TestCase):
    def test_existing_terminal_is_checked_not_polled_or_restarted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'result.json').write_text('{}')
            with patch.object(campaign.runner, 'GATE', root), \
                 patch.object(campaign.runner, 'acceptance_gate', return_value='accepted') as accept:
                pins = {}
                self.assertEqual(campaign.wait_gate(pins, 1), 'accepted'); accept.assert_called_once_with(pins)

    def test_failed_prerequisite_stops_before_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'result.json').write_text(json.dumps(dict(state='FAIL')))
            with patch.object(campaign.runner, 'GATE', root), self.assertRaises(ValueError):
                campaign.wait_gate({}, 1)

    def test_deadline_is_not_a_fake_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(campaign.runner, 'GATE', Path(tmp)), self.assertRaises(ValueError):
                campaign.wait_gate({}, .01)


if __name__ == '__main__': unittest.main()

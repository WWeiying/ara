import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import apply_branch_combo_six_latest_v2 as m


class SuccessorTests(unittest.TestCase):
    def test_actual_frozen_library_load_then_adapter_install(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name)
            for filename in ('root-helpers.tcl', 'capture-helpers.tcl', 'combo-library.tcl', 'root-row-helpers.tcl', 'population-selection.tcl'):
                (output / filename).write_bytes((m.ATTEMPT / filename).read_bytes())
            prefix = 'set env(DVE_COVERAGE_OUTPUT) {%s}\n' % output
            text = m.TCL.read_text().split('uplevel #0 $six2_tail')[0]
            commands = '\nsix_initialize\nif {[string first six2_dbg_select [info body dbg_select]] < 0} {error BAD_ADAPTER}\nputs LOADED\n'
            result = subprocess.run(['tclsh'], input='if {[catch {\n' + prefix + text + commands +
                                    '\n} message]} {puts stderr $message; exit 1}\n',
                                    text=True, capture_output=True, check=True)
            self.assertEqual(result.stderr, '')
            self.assertIn('SIX2_SELECTION_ADAPTER_INSTALLED', result.stdout)
            self.assertIn('LOADED', result.stdout)

    def test_inherited_contract_includes_all_protected_and_actual_base(self):
        frozen = json.loads((m.ATTEMPT / 'config.json').read_bytes())
        adapted = copy.deepcopy(frozen)
        adapted.update(schema=m.SCHEMA, command=['new'], core_config_path='core', core_config_sha256='hash',
                       previous_attempt='original', previous_config_sha256=m.ATTEMPT_SHA, selection_adapter=str(m.HELPER))
        self.assertEqual(m.inherited_view(adapted, frozen), m.inherited_view(frozen, frozen))
        for field in ('protected', 'targets', 'coordinate_review', 'inputs', 'selected_tests', 'audit_stages'):
            changed = copy.deepcopy(adapted)
            changed[field] = None
            self.assertNotEqual(m.inherited_view(changed, frozen), m.inherited_view(frozen, frozen))

    def test_frozen_full_verifier_receives_actual_successor_config(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name)
            (output / 'DVEfiles').mkdir()
            (output / 'DVEfiles/dve_gui.log').write_text('SIX2_SELECTION_ADAPTER_INSTALLED\n')
            config = {'actual_config': True}
            with mock.patch.object(m.core, 'verify_artifacts', return_value={'audited': 19370}) as verify:
                self.assertEqual(m.verify_artifacts(output, config)['audited'], 19370)
                verify.assert_called_once_with(output, config)

    def test_missing_adapter_marker_is_rejected_before_verifier(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name)
            (output / 'DVEfiles').mkdir()
            (output / 'DVEfiles/dve_gui.log').write_text('')
            with mock.patch.object(m.core, 'verify_artifacts') as verify:
                with self.assertRaises(ValueError):
                    m.verify_artifacts(output, {})
                verify.assert_not_called()


if __name__ == '__main__':
    unittest.main()

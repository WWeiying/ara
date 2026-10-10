"""Complete disk entry using real03 typed EL bytes and the actual04 stage checker."""
from pathlib import Path
import tempfile

import fma_expanded_native_04 as native
import fma_expanded_session_mock_03 as gui


def qualify_disk_entry(selection):
    native.require(selection.read_bytes() == native.selection_text().encode('ascii') and
                   not selection.read_bytes().startswith(b'"') and b'\\n' not in selection.read_bytes(),
                   'Actual selection serialization differs')
    c, real = native.fixture()
    actual_el = (native.OLD / 'first.el').read_text()
    with tempfile.TemporaryDirectory(prefix='fma_expanded_plain_tcl_04_') as tmp:
        out = Path(tmp)
        (out / 'selection.tcl').symlink_to(selection.resolve())
        native.life.save(out / 'config.json', dict(c, output=str(out), pins={}))
        setup = gui.setup(c, out) + 'set expected_helper ' + gui.quote(Path(native.__file__).resolve()) + '\n'
        # No idealized EL generator: the complete saved real03 bytes are reloaded.
        setup += 'set whole_EL ' + gui.quote(actual_el) + '\n'
        result = gui.evaluate(native.ENTRY, setup + gui.STUBS)
        native.require('FMA_EXPANDED_NATIVE_CAPTURE_DONE' in result and
                       'FMA_EXPANDED_NATIVE_CAPTURE_FAILED' not in result and
                       'MOCK_STATE 612 {initial apply reset reload final}' in result and
                       'INFO_SCRIPT {}' in result, 'Actual source/session entry failed: ' + result)
        stages = [native.check_stage(out, stage, c) for stage in native.frozen.STAGES]
        native.require((out / 'first.el').read_bytes() == (native.OLD / 'first.el').read_bytes() ==
                       (out / 'second.el').read_bytes(), 'Actual fixture byte reload differs')
        return dict(status='ACTUAL_DISK_ENTRY_REAL03_EL_GUI_MOCK_PASS_NOT_NATIVE',
                    actual03_full_EL=real, selection_sha256=native.life.digest(selection), stages=stages,
                    source_session_stdout=result, real_python_stage_checker=True,
                    native_qualification=False)

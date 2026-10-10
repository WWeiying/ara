"""Minimal empty-token successor; full247/1533 protection remains unchanged."""
from pathlib import Path

import capture_rvh_branch_full_726 as frozen

SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix('.tcl')
TEST = SCRIPT.with_name('test_capture_rvh_branch_full_empty_v2.py')
SELECTION = SCRIPT.with_suffix('.selection.tcl')
FAILED = frozen.prepared.static.OUT / 'rvh-branch-native-full247-agent-726-20261006-01'
original_library = frozen.pilot.branch_library


def branch_library():
    return original_library() + '\n' + SELECTION.read_text()


def pilot_pins():
    pins = frozen.pilot_pins()
    for path in (Path(frozen.__file__), frozen.TCL, frozen.TEST, SELECTION,
                 FAILED/'config.json', FAILED/'status.json', FAILED/'states_before.tsv',
                 FAILED/'DVEfiles/dve_gui.log'):
        pins[str(path)] = frozen.sha(path)
    return pins


def adapted(function, replacements, **bindings):
    # Keep the established source adapter; route its dependency namespace explicitly.
    return frozen.pilot.private(frozen.adapted, SCRIPT=SCRIPT, TCL=TCL, TEST=TEST,
        branch_library=branch_library, pilot_pins=pilot_pins,
        config_read=config_read, verify_artifacts=verify_artifacts)(function, replacements, **bindings)


def config_read(output, seal):
    return frozen.pilot.private(frozen.config_read, adapted=adapted, pilot_pins=pilot_pins)(output, seal)


def verify_artifacts(output, config):
    return frozen.pilot.private(frozen.verify_artifacts, adapted=adapted)(output, config)


def prepare(output):
    return frozen.pilot.private(frozen.prepare, adapted=adapted, pilot_pins=pilot_pins)(output)


def full_capture():
    return frozen.pilot.private(frozen.full_capture, adapted=adapted)()


def run(output, seal, authorized):
    return frozen.pilot.private(frozen.run, config_read=config_read,
        full_capture=full_capture)(output, seal, authorized)


def main():
    return frozen.pilot.private(frozen.main, prepare=prepare, config_read=config_read,
        verify_artifacts=verify_artifacts, run=run)()


if __name__ == '__main__':
    main()

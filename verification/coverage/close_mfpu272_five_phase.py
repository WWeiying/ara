"""Immutable terminal receipt after full five-phase replay; never launches EDA."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import mfpu272_five_phase as qualification

life, require = qualification.life, qualification.require
RUN = life.OUT / 'mfpu272-five-phase-prepared-agent-20261007-01'
CONFIG_SHA = '810e5ee5f3937adc78be192817c3c79b594e033a9ce2896426298ce6a138dd2e'
QUALIFICATION_SHA = '5b6ec22297d34ce9e7a944c0c9c677bca25d0856c1e39f4c82854e6cfa3e8dc8'
UNIT = 'ara-mfpu272-five-phase-parent-20261007-01.service'


def unit_status():
    names = 'Id,LoadState,ActiveState,SubState,ExecMainCode,ExecMainStatus,ExecMainPID,ExecStart,StandardOutput'
    text = subprocess.check_output(['systemctl', '--user', 'show', UNIT, '--property=' + names], text=True)
    props = dict(line.split('=', 1) for line in text.splitlines())
    require(props.get('Id') == UNIT and props.get('ActiveState') == 'inactive' and
            props.get('SubState') == 'dead', 'No running/failed unit may be closed')
    if props.get('LoadState') == 'not-found':
        # GC default fields are not OS evidence. Native terminal remains
        # independently required by the unchanged complete verifier.
        return props
    require(props.get('LoadState') == 'loaded' and props.get('ExecMainCode') == '1' and
            props.get('ExecMainStatus') == '0', 'Actual retained wrapper OS0 required')
    command = props.get('ExecStart', '')
    require(str(Path(qualification.__file__).resolve()) in command and str(RUN) in command and
            CONFIG_SHA in command, 'Actual unit command/config binding')
    require(props.get('StandardOutput') == 'append', 'Actual append stdout policy required')
    return props


def close(output):
    require(output.parent == life.OUT and not output.exists(), 'Fresh independent receipt only')
    result_path = RUN / 'capture-result.json'
    original = life.read_bound(result_path, QUALIFICATION_SHA)
    require(original['status'] == 'MFPU272_EXACT_FIVE_PHASE_LOCAL_QUALIFIED_NOT_APPLIED',
            'Exact sealed native qualification required')
    source = Path(qualification.__file__).resolve()
    require(original['pins'].get(str(source)) == life.digest(source), 'Qualified verifier source identity')
    stdout = RUN / 'service.log'
    require(str(stdout) not in original['pins'], 'Unexpected mutable current stdout self-pin')
    before = stdout.read_bytes()
    live = json.loads((RUN / 'live-identity.json').read_bytes())
    require(json.loads(before) == dict(actual_dve=live, output=str(RUN)),
            'Service stdout must be exact original live receipt, no errors/extra records')
    properties = unit_status()
    replay = qualification.verify(RUN, CONFIG_SHA)
    require(replay == original and life.digest(result_path) == QUALIFICATION_SHA,
            'Full replay/result SHA must remain identical')
    after = stdout.read_bytes()
    require(after == before, 'Stdout changed during terminal closure; do not silently repin')
    require(unit_status() == properties, 'Terminal unit identity changed during replay')
    sha = hashlib.sha256(after).hexdigest()
    pins = life.merge_pins(original['pins'], {str(result_path): QUALIFICATION_SHA,
        str(stdout): sha, str(Path(__file__).resolve()): life.digest(__file__)})
    life.check(pins)
    retained = properties['LoadState'] == 'loaded'
    receipt = dict(schema='MFPU272_FIVE_PHASE_TERMINAL_CLOSURE_V1',
        status='FULL_NATIVE_REPLAY_PASS_NOT_APPLIED',
        original_qualification=str(result_path), qualification_sha256=QUALIFICATION_SHA,
        config_sha256=CONFIG_SHA, systemd_unit=UNIT, systemd_properties=properties,
        terminal=json.loads((RUN / 'terminal.json').read_bytes()),
        wrapper_OS_exit_status=0 if retained else None,
        wrapper_OS_evidence='RETAINED_ACTUAL_SYSTEMD_UNIT' if retained else 'UNIT_GC_NOT_INDEPENDENTLY_RECAPTURED',
        parent_reported_wrapper_OS_exit_status=0,
        parent_reported_wrapper_status_source='Parent message: authoritative inactive/dead ExecMainStatus0; not substituted for missing machine receipt',
        stdout=dict(path=str(stdout), sha256=sha, bytes=len(after),
            original_current_service_self_pinned=False,
            historic_append_not_inferred=True, replay_append_bytes=0,
            policy='Exact completed live receipt; unchanged during full replay; newly pinned only in closure'),
        stages=original['stages'], targets=272, directions=34816, protected_child_scopes=744,
        EL_semantic_roundtrip=True, global_reset_empty=True, all_protected_rows_verified=True,
        original_files_unchanged=True, population_application=False, EDA_launched=False, pins=pins)
    life.save(output, receipt)
    print(json.dumps(dict(output=str(output), seal=life.digest(output),
        qualification_sha=QUALIFICATION_SHA, status=receipt['status'], EDA_launched=False)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    close(args.output.resolve())

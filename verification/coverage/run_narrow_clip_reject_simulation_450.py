"""One parent-reviewed same-ELF450 successor to sealed300 timeout; no auto retry."""
import hashlib
from pathlib import Path

import run_narrow_clip_reject_simulation as prior

life, require = prior.life, prior.require
PRIOR_SHA = '4a31a0eac990dcf301ec4c836319dec8fcaff0917dda5b332b921f6bb6658b44'
OLD = life.OUT / 'narrow-clip-reject-old-image-parent-20261006-01'
OLD_PREPARED = OLD.with_name(OLD.name + '.prepared.json')
OLD_SEAL = '7e5095088a6e15fd7108d3ee11a658dc709f2cf121b7084435ca18000205acdb'
TIMEOUT_PINS = {
    str(OLD_PREPARED): OLD_SEAL,
    str(OLD / 'manifest.json'): OLD_SEAL,
    str(OLD / 'simulation-status.json'): '104ff135614a51be6d4fec588e90c5079ed717d66f050ea204c2656155075ae5',
    str(OLD / 'started.json'): 'd5da9ea38d7971cc2724d41c088eb2f5d95c763bf2a9854329771f04c1de6dd8',
    str(OLD / 'commit_trace.csv'): '44222fc040e9437ad3a67f3ee4cf23b680d5d020c6f63d7397e0bfa35252cb32',
    str(OLD / 'vector_trace.csv'): 'b02fdba10a257aa59343652595c2c292a01bbda8aba3484883b029872ed1f4e3',
    str(OLD / 'console.log'): 'c72bdf431ed3191763881b99e2a1b33564d94bf7ff0801547463cc958af7bed5',
    str(OLD / 'run.vcs.log'): '20a0a516f6170beccce3567267582a3227a9105ab01a0216ab9dfc2bc920f9c0',
}


def timeout_evidence():
    life.check(TIMEOUT_PINS)
    record = life.read_bound(OLD_PREPARED, OLD_SEAL)
    state = life.read_bound(OLD / 'simulation-status.json', TIMEOUT_PINS[str(OLD / 'simulation-status.json')])
    started = life.read_bound(OLD / 'started.json', TIMEOUT_PINS[str(OLD / 'started.json')])
    require(life.read_bound(OLD / 'manifest.json', OLD_SEAL) == record and
            record['output'] == str(OLD) and record['command'] == prior.command(OLD) and
            record['timeout_s'] == 300 and record['elf_sha256'] == prior.ELF_SHA and
            record['preflight_seal'] == prior.PRE_SEAL and record['software_checks'] == 2094 and
            record['exact_illegal_traps'] == 17 and record['old_image_files_checked'] == 66 and
            record['coverage_admitted'] is False and record['automatic_retry'] is False,
            'Exact original300 prepared contract required')
    require(state['status'] == 'SIMULATION_FAILED_OR_TIMEOUT_NOT_ADMITTED' and
            state['timeout'] is True and state['process_group_cleanup'] is True and
            state['post_failure_pin_error'] is None and state['returncode'] == -9 and
            state['case'] == prior.NAME and state['coverage_admitted'] is False and
            state['admission_performed'] is False and state['terminal_oracle_verified'] is False and
            state['reason'].startswith('TimeoutExpired:') and
            state['reason'].endswith('timed out after 300 seconds'), 'Only clean sealed timeout allowed')
    require(started['command'] == record['command'] and started['budget_s'] == 300 and
            started['input_elf'] == str(prior.ELF) and started['elf_sha256'] == prior.ELF_SHA and
            started['image'] == str(life.IMAGE) and started['image_sha256'] == prior.IMAGE_SHA and
            type(started['pid']) is int and started['pid'] > 0 and
            started['pid'] == started['process_group'] and started['foreground_lifetime'] is True,
            'Original startup identity differs')
    require(not Path('/proc/%d' % started['pid']).exists(), 'Old simulator PID still exists; HOLD')
    life.check(record['pins'])
    return record


def namespace():
    path = Path(prior.__file__).resolve()
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == PRIOR_SHA, 'Frozen300 runner drift')
    text = raw.decode()
    replacements = [('BUDGET = 300', 'BUDGET = 450'),
                    ('RuntimeMaxSec=360', 'RuntimeMaxSec=510'),
                    ('test_run_narrow_clip_reject_simulation.py', 'test_run_narrow_clip_reject_simulation_450.py')]
    for old, new in replacements:
        require(text.count(old) == (2 if old.startswith('test_') else 1), 'Exact source adaptation differs')
        text = text.replace(old, new)
    ns = dict(__name__='clip17_private_450', __file__=str(Path(__file__).resolve()))
    exec(compile(text, str(Path(__file__).resolve()) + ':sealed300-source', 'exec'), ns)
    original_manifest = ns['manifest']

    def manifest(out):
        require(out != OLD, 'Original failed output must be preserved')
        record = timeout_evidence()
        result = original_manifest(out)
        require(result['input_elf'] == record['input_elf'] and result['elf_sha256'] == record['elf_sha256'] and
                result['targets'] == record['targets'] and result['scalar_reference_counts'] == record['scalar_reference_counts'] and
                all(result['pins'].get(p) == h for p, h in record['pins'].items()
                    if p not in (str(path), str(path.with_name('test_run_narrow_clip_reject_simulation.py')))),
                'Same ELF/oracle/targets/original dependency pins required')
        pins = life.merge_pins(result['pins'], record['pins'])
        pins = life.merge_pins(pins, TIMEOUT_PINS)
        result['pins'] = life.merge_pins(pins, {str(path): PRIOR_SHA})
        result.update(predecessor_run=str(OLD), predecessor_prepared=str(OLD_PREPARED),
                      predecessor_prepared_seal=OLD_SEAL, predecessor_status='SEALED300_TIMEOUT_NOT_DUT_FAIL_NOT_ADMITTED',
                      predecessor_timeout_pins=TIMEOUT_PINS, budget_successor=True,
                      budget_change_only=True, original_timeout_preserved=True)
        life.check(result['pins'])
        return result

    ns['manifest'] = manifest
    return ns


def main(argv=None):
    namespace()['main'](argv)


if __name__ == '__main__':
    main()

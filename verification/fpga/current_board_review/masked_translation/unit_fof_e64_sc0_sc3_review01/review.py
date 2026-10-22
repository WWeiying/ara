"""Short source/metadata/ELF review. No Host, raw trace, or simulation rerun."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PREP = HERE.parent / 'unit_fof_e64_sc0_sc3_prepare01'
ARCH = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
READY = '8c2f89e677e1cf6148ad3d1013f1598a91ed77506a73266603d956ffe9672e1e'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def read(p):
    return json.loads(p.read_text())

def main():
    assert not (HERE / 'result.json').exists()
    previous = HERE.parent / 'unit_fof_e64_suffix_two_review01/review_check.py'
    loader = importlib.util.spec_from_file_location('previous_readonly_elf_reader', previous)
    util = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(util)
    assert sha(PREP / 'READY.json') == READY
    ready = read(PREP / 'READY.json')
    manifest = read(PREP / 'input_pins.json')
    assert len(manifest) == 725 and sha(PREP / 'input_pins.json') == ready['input_pins_sha256']
    files = [Path(__file__), previous, PREP / 'READY.json', PREP / 'input_pins.json']
    files += [PREP / n for n in ('fixture.c', 'fixture.S', 'fixture.h', 'prepare.py',
        'observer.py', 'csv_check.py', 'source_owners.py', 'test_host.py', 'host01.json', 'host01.log')]
    archive_manifest = ARCH / 'rvv_small_exceptions01/manifest.json'
    symptoms_path = ARCH / 'rvv_exception_symptoms02/symptoms.json'
    files += [archive_manifest, symptoms_path]
    symptoms = read(symptoms_path)['cases']
    archived = read(archive_manifest)['cases']
    cases = []
    for case in ready['cases']:
        n = case['scenario']; assert n in (0, 3)
        path = PREP / 'software01' / f'scenario{n}'
        ref = PREP / f'reference_scenario{n}_01'
        proof = read(path / 'source_proof.json'); spec = read(path / 'soc.spec.json')
        name = case['original']['name']
        original = ARCH / 'rvv_small_exceptions01/binaries' / name
        record = next(x for x in archived if x['name'] == name)
        symptom = next(x for x in symptoms if x['name'] == name)
        assert sha(original) == case['original']['elf'] == record['sha256']
        assert symptom['confirmed'] and symptom['status'] == 'failed'
        assert symptom['trap']['epc'] == case['original']['target'] and symptom['trap']['cause'] == 13
        for source, key in [('scenario.c', 'c'), ('scenario.S', 'asm')]:
            p = ARCH / 'rvv_small_exceptions01' / name / source
            assert sha(p) == case['original'][key] == record['scenario_sources'][source]
            files.append(p)
        old_bytes = util.elf_reader(original)
        compared = 0
        for backend in ('soc', 'spike'):
            elf = path / (backend + '.elf'); new_bytes = util.elf_reader(elf)
            assert sha(elf) == proof['backend'][backend]['sha256']
            files.append(elf)
            for label, helper in proof['backend'][backend]['helpers'].items():
                assert len(helper['pcs']) == (3 if label == 'capacity' else 11)
                for pc, oldpc, encoding in zip(helper['pcs'], helper['original_pcs'], helper['encodings']):
                    value = int(encoding, 16); width = 4 if value & 3 == 3 else 2
                    assert new_bytes(pc, width) == old_bytes(oldpc, width) == value.to_bytes(width, 'little')
                    compared += 1
        assert sha(path / 'soc.elf') == case['soc_sha256'] == spec['elf_sha256']
        elf = util.elf_reader(path / 'soc.elf')
        assert elf(spec['exit_store'], 4) == bytes.fromhex('23b0a200')
        assert elf(spec['park'], 2) == bytes.fromhex('01a0') and 'tohost' not in spec['symbols']
        status = read(ref / 'status.json'); outcome = read(ref / 'execution.json')
        assert sha(ref / 'status.json') == case['reference_sha256']
        assert status['status'] == 'REFERENCE_CHECKER_PASS_NOT_DUT' and status['pins_unchanged']
        assert outcome == status['execution'] and outcome['actual_wait_returncode'] == 0 and not outcome['timeout']
        assert status['scalar_checks'] == (5477 if n == 0 else 5481) and status['htif'] == [1]
        assert len(status['traps']) == 1 and status['traps'][0][0] == 'trap_supervisor_ecall'
        assert status['actual_handler_csrs'][0]['5'] == 8
        assert status['allowed_undefined_output_indices'] == ([5, 6, 7, 8] if n == 0 else [])
        files += [original, path / 'source_proof.json', path / 'soc.spec.json', ref / 'status.json', ref / 'execution.json']
        cases.append(dict(scenario=n, original_target=hex(symptom['trap']['epc']),
            original_tval=hex(symptom['trap']['tval']), helper_encodings_compared=compared,
            soc_elf_sha256=case['soc_sha256'], reference_actual_rc=0,
            recorded_firmware_commits_including_park=status['firmware_commits'],
            firmware_to_htif=status['firmware_to_htif'], checks=status['scalar_checks'],
            returned_vl=4 if n == 0 else 8, post_helper_vl=8))
    assert read(PREP / 'host01.json')['actual_wait_returncode'] == 0
    assert 'Ran 12 tests' in (PREP / 'host01.log').read_text()
    pins = {str(p): sha(p) for p in files}
    for p, digest in pins.items():
        if p in manifest:
            assert digest == manifest[p], 'Scoped pin drift: ' + p
    assert sha(PREP / 'source_owners.py') == 'f79ad8975dd348cbe1ef25c04c4a67b8d7144cfa6cb9838bdd4210c5de83a11a'
    assert sha(PREP / 'READY.json') == READY
    result = dict(decision='NO_BLOCKER', blockers=[], source_reference_accepted=True,
        scope='Original e64/sc0 and sc3 Sv39 source/reference and checker review, not DUT acceptance',
        reference_ready_sha256=READY, source_owners_sha256=sha(PREP / 'source_owners.py'),
        cases=cases, evidence_pins=pins, inherited_manifest_entries=725,
        all725_rehashed=False, raw_trace_reparsed=False, Host_rerun=False,
        reference_executed=False, DUT_executed=False, worker_plan_reviewed=False,
        worker_requirement='Use source_owners.analyze plus generic protocol, persisted child0 and raw failure veto',
        FOF_owner_vl8_means_preinstruction_model=True, alloff_target_owner_required=True,
        physical_MMU_zero_proved=False, Linux_signal_equivalence=False)
    with (HERE / 'result.json').open('x') as f:
        json.dump(result, f, indent=2); f.write('\n')
    print('NO_BLOCKER source/reference/checker; actual ELF helper comparisons100; no raw/Host rerun')

if __name__ == '__main__':
    main()

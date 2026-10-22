"""Short frozen-source/ELF/metadata audit; never executes Host/reference/DUT."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PREP = HERE.parent / 'small_exceptions_remaining14_prepare01'
ARCH = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
READY = '3e3b774785788916e41031ef652c63c8b6e0b9cc507dc9a0dc67e9746006824a'
MEMBERS = [(w, n) for w in (8, 16, 32) for n in ((1, 2, 3, 5) if w == 8 else (0, 1, 2, 3, 5))]
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    assert not (HERE / 'result.json').exists()
    assert sha(PREP / 'READY.json') == READY
    ready = read(PREP / 'READY.json'); manifest = read(PREP / 'input_pins.json')
    assert len(manifest) == 1253 and sha(PREP / 'input_pins.json') == ready['pins_sha256']
    assert [(x['sew'], x['scenario']) for x in ready['members']] == MEMBERS
    assert ready['reference_attempts'] == 14 and ready['DUT_runs'] == 0
    old = HERE.parent / 'unit_fof_e64_suffix_two_review01/review_check.py'
    loader = importlib.util.spec_from_file_location('old_readonly_elf_reader', old)
    util = importlib.util.module_from_spec(loader); loader.loader.exec_module(util)
    sys.path.insert(0, str(PREP))
    import abi_check
    archive_manifest = ARCH / 'rvv_small_exceptions01/manifest.json'
    symptom_file = ARCH / 'rvv_exception_symptoms02/symptoms.json'
    records = read(archive_manifest)['cases']; symptoms = read(symptom_file)['cases']
    files = [Path(__file__), old, archive_manifest, symptom_file, PREP / 'READY.json', PREP / 'input_pins.json']
    files += [PREP / name for name in ('fixture.c', 'fixture.S', 'fixture.h', 'observer.py',
              'csv_check.py', 'source_owners.py', 'abi_check.py', 'diagnostics.py', 'test_host.py',
              'host01.json', 'host01.log', 'prepare.py', 'parse_reference.py', 'M9_BINDING.json')]
    cases = []
    for item in ready['members']:
        w, n = item['sew'], item['scenario']; width = w // 8
        name = f'rvv_small_exceptions_e{w}_scenario{n}'
        record = next(x for x in records if x['name'] == name)
        symptom = next(x for x in symptoms if x['name'] == name)
        p = PREP / 'software01' / item['member']; ref = PREP / 'reference01' / item['member']
        proof = read(p / 'source_proof.json'); spec = read(p / 'soc.spec.json')
        original = ARCH / 'rvv_small_exceptions01/binaries' / name
        assert sha(original) == record['sha256'] and proof['source']['manifest'] == record
        assert symptom['confirmed'] and symptom['status'] == 'failed' and symptom['trap']['cause'] == 13
        files += [original, p / 'source_proof.json', p / 'soc.spec.json', p / 'host.stdout']
        for filename, digest in record['scenario_sources'].items():
            source = ARCH / 'rvv_small_exceptions01' / name / filename
            assert sha(source) == digest; files.append(source)
        assert sha(p / 'prepared/original.S') == record['scenario_sources']['scenario.S']
        files.append(p / 'prepared/original.S')
        oldbytes = util.elf_reader(original); count = 0
        for backend in ('soc', 'spike'):
            elf = p / (backend + '.elf'); actual = util.elf_reader(elf)
            assert sha(elf) == proof['backend'][backend]['sha256']; files.append(elf)
            for name_, entry in proof['backend'][backend]['helpers'].items():
                assert len(entry['pcs']) == (3 if name_ == 'capacity' else 11)
                for pc, oldpc, encoding in zip(entry['pcs'], entry['original_pcs'], entry['encodings']):
                    value = int(encoding, 16); size = 4 if value & 3 == 3 else 2
                    assert actual(pc, size) == oldbytes(oldpc, size) == value.to_bytes(size, 'little')
                    count += 1
        assert sha(p / 'soc.elf') == spec['elf_sha256'] == item['soc_elf_sha256']
        q = abi_check.Checker(spec)
        assert q.regs == {0: 0} and len(q.memory_owners.expected) == 4
        assert q.cfg['base'] == 0x40001000 - (4 * width if n < 3 else 0)
        assert q.cfg['vtype'] == {8: 0, 16: 8, 32: 16}[w]
        assert q.cfg['returned_vl'] == (4 if n == 0 else 8)
        actual = util.elf_reader(p / 'soc.elf')
        assert actual(spec['exit_store'], 4) == bytes.fromhex('23b0a200') and 'tohost' not in spec['symbols']
        lines = (p / 'host.stdout').read_text().splitlines()
        outputs = []
        for phase in (0, 1):
            for i in range(130):
                defined = not (n == 0 and phase == 1 and 5 <= i <= 8)
                value = (i - 1) * 37 + 11 if phase == 1 and n < 3 and 1 <= i <= 4 else 91
                outputs.append(f'O {phase} {i} {int(defined)} {value}')
        assert lines[:260] == outputs
        mask = 255 if n == 0 else 15 if n in (1, 2) else 0
        assert lines[260:276] == [f'M {i} {mask if i == 0 else 0}' for i in range(16)]
        data = bytearray(4096)
        for i, value in enumerate((11, 48, 85, 122)):
            pos = 4096 - 4 * width + i * width; data[pos:pos + width] = value.to_bytes(width, 'little')
        for i in range(508, 512):
            assert lines[276 + i] == f'P {i} {int.from_bytes(data[i*8:i*8+8], "little")}'
        status = read(ref / 'status.json')
        assert status['status'] == 'REFERENCE_CHECKER_PASS_NOT_DUT' and status['htif'] == [1]
        assert status['scalar_checks'] == item['checks'] == (5477 if n == 0 else 5481)
        assert status['allowed_undefined_output_indices'] == ([5, 6, 7, 8] if n == 0 else [])
        assert len(status['traps']) == 1 and status['traps'][0][0] == 'trap_supervisor_ecall'
        assert status['firmware_to_htif'] == item['firmware_retired']
        for filename in ('spike_exit.json', 'parser.log.execution.json', 'preparation_exit.json'):
            outcome = read(ref / filename)
            assert type(outcome['actual_wait_returncode']) is int and outcome['actual_wait_returncode'] == 0
            assert not outcome.get('timeout', False); files.append(ref / filename)
        assert read(ref / 'input_pins.json') == read(ref / 'pins_post.json')
        files += [ref / 'status.json', ref / 'input_pins.json', ref / 'pins_post.json']
        cases.append(dict(member=item['member'], soc_elf_sha256=item['soc_elf_sha256'],
            original_elf_sha256=record['sha256'], original_target=hex(symptom['trap']['epc']),
            helper_instruction_comparisons=count, checks=status['scalar_checks'],
            firmware_to_htif=status['firmware_to_htif'], actual_spike_parser_child_returncodes=[0, 0, 0],
            actual_ELF_ABI_profile_verified=True))
    host = read(PREP / 'host01.json')
    assert host['actual_wait_returncode'] == 0 and sha(PREP / 'host01.log') == host['log_sha256']
    assert 'Ran 17 tests' in (PREP / 'host01.log').read_text()
    pins = {str(p): sha(p) for p in files}
    for path, digest in pins.items():
        if path in manifest: assert digest == manifest[path], 'Scoped pin drift: ' + path
    assert sha(PREP / 'READY.json') == READY
    result = dict(decision='NO_BLOCKER', blockers=[], source_reference_accepted=True,
        reference_ready_sha256=READY, cases=cases, pins=pins, inherited_pin_count=1253,
        all1253_rehashed=False, helper_instruction_comparisons=sum(x['helper_instruction_comparisons'] for x in cases),
        recorded_reference_checks=sum(x['checks'] for x in cases), existing_Host_tests=17,
        no_reference_or_Host_rerun=True, no_raw_CSV_or_Spike_trace_parse=True, DUT_acceptance=False,
        final_worker_plan_reviewed=False,
        required_worker_entry='abi_check.analyze, exact PASS_SMALL_EXCEPTIONS_14, four owners, generic protocol validator, durable numeric0 and raw failure veto',
        scope='14 original single-call source-derived Sv39 preparations, not original Linux parents')
    with (HERE / 'result.json').open('x') as f: json.dump(result, f, indent=2); f.write('\n')
    print('NO_BLOCKER: 14 exact members, 700 actual ELF helper comparisons, ABI constructors, typed oracle tables and durable reference metadata; no raw/Host rerun')

if __name__ == '__main__': main()

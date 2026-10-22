#!/usr/bin/env python3
"""Pin existing ELFs/models and M4 cycle endpoints; no build or simulation."""
import csv
from collections import Counter
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BEFORE = HERE.parent
GATHER = BEFORE.parent
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate05/campaign/image')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def save(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def endpoint(path):
    events, exit_rows = Counter(), []
    last, last_retire, retired, nonretire_last = None, None, 0, None
    with path.open() as stream:
        for row in csv.DictReader(stream):
            events[row['event']] += 1
            last = row
            if row['event'] != 'retire':
                nonretire_last = row
                continue
            last_retire = row
            retired += 1
            if int(row['mem_addr'],16) == 0xd0000000 and int(row['mem_wmask'],16):
                exit_rows.append(row)
    return dict(last_cycle=int(last['cycle']), last_event=last, last_retire=last_retire,
                retired=retired, nonretire_last=nonretire_last, event_counts=dict(events),
                ctrl_exit_stores=exit_rows, csv_sha256=sha(path))


def source_delta():
    roots = [Path('/home/wangwy/fpga_runs/current_board_memory_candidate'+n+'/frozen') for n in ('04','05')]
    old, new = [read(root/'snapshot.json') for root in roots]
    assert old['settings'] == new['settings'] and old['files'].keys() == new['files'].keys()
    changed = sorted(k for k in old['files'] if old['files'][k] != new['files'][k])
    assert changed == ['frozen.filelist','hardware/bender','hardware/src/lane/lane_sequencer.sv'], changed
    for name in ('frozen.filelist','hardware/bender'):
        a,b = [(root/'sources'/name).read_text() for root in roots]
        assert a.replace(str(roots[0]/'sources'), '<FROZEN>') == b.replace(str(roots[1]/'sources'), '<FROZEN>')
    filename = 'hardware/src/lane/lane_sequencer.sv'
    a,b = [(root/'sources'/filename).read_text() for root in roots]
    expected = a.replace(
        '// VALU processes the full source stream; MASKU packs from bit zero\n'
        '            // and separately preserves the architectural vstart prefix.\n'
        '            if (pe_req.op inside {[VMSEQ:VMSBC]})',
        '// MASKU scans comparisons and gather indices from element zero;\n'
        '            // its destination byte enables separately preserve vstart.\n'
        '            if (pe_req.op inside {[VMSEQ:VMSBC], VRGATHER, VRGATHEREI16})')
    assert expected != a and expected == b, 'Not exact approved gather source-origin repair'
    with (HERE/'approved_m4_m5.diff').open('x') as stream:
        stream.write(''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile='M4/'+filename,tofile='M5/'+filename)))
    return dict(status='EXACT_APPROVED_GATHER_PATCH_ONLY', changed=changed,
                path_relocations_only=['frozen.filelist','hardware/bender'],
                snapshot_hashes=[sha(root/'snapshot.json') for root in roots],
                lane_hashes=[sha(root/'sources'/filename) for root in roots])


def main():
    before = read(BEFORE/'plan.json')
    programs = read(BEFORE/'soc01/programs.json')
    pins = {}
    for case in before['cases']:
        name = case['name']
        entry = programs['programs'][name]
        assert sha(Path(entry['path'])) == entry['sha256'] == case['soc_elf_sha256']
        for path in (Path(entry['path']), BEFORE/(name+'.expected.json')):
            pins[str(path)] = sha(path)
    for path in (BEFORE/'prepared/provenance.json', BEFORE/'soc01/programs.json', BEFORE/'plan.json',
                 BEFORE/'capture.py', BEFORE/'vcs_candidate04_01/complete.json',
                 BEFORE/'vcs_candidate04_01/capture.tcl', BEFORE/'vcs_candidate04_01/signals.json'):
        pins[str(path)] = sha(path)
    focus = dict(status='PREPARED_WAIT_M5_BUILD_NO_DUT', image=str(IMAGE),
        unit='ara-gather-focused-candidate05-01.service', output=str(HERE/'vcs_candidate05_01'),
        programs=str(BEFORE/'soc01'), jobs=2, timeout_s=180, runtime_max_s=240, retries=0,
        bounded_window_ns=[0,90000], force=False, fail_stop=True, cases=before['cases'],
        expected='PASS2, exact unchanged13asm, full514unique reads, returnedvstart0, CTRLexit0',
        wave_expected='AluA origin0/address64; scan128 idx511/oor0; active BE and data79',
        m4_endpoints={case['name']:endpoint(BEFORE/'vcs_candidate04_01/replay/tests'/case['name']/'commit_trace.csv')
                      for case in before['cases']}, pins=pins, source_delta=source_delta())
    save(HERE/'focus_plan.json', focus)
    old_prefix = read(GATHER/'stall_prefix2_launch02/vcs_candidate04_01/plan.json')
    prefix_programs = read(GATHER/'stall_prefix2_03/soc01/programs.json')['programs']
    for case in old_prefix['cases']:
        entry = prefix_programs[case['name']]
        assert sha(Path(entry['path'])) == entry['sha256'] == case['elf_sha256']
    save(HERE/'prefix_plan.json', dict(status='PREPARED_ONLY_WAIT_FOCUS_PASS_AND_PREFIX_SCHEDULING',
        image=str(IMAGE), programs=str(GATHER/'stall_prefix2_03/soc01'), cases=old_prefix['cases'],
        unit='ara-gather-prefix2-candidate05-01.service', output=str(HERE/'prefix_vcs_candidate05_01'),
        jobs=2, timeout_per_case_s=9000, runtime_max_s=9600, retries=0, fail_stop=True,
        expected_calls_per_case=98, fullcap_checks_per_case=50176, guards_per_case=196,
        expected_scalar_loads_per_case=50372, original_stopped_tuple=None,
        exact11_failure_reproduction=False, full_parent_closure=False, source_programs_unchanged=True))
    print('PREPARED_SAME_ELFS_NO_BUILD_NO_DUT', HERE)
    print('focus_plan_sha256', sha(HERE/'focus_plan.json'))


if __name__ == '__main__':
    main()

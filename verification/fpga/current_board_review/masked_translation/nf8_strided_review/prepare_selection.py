#!/usr/bin/env python3
"""Read archived evidence and enumerate original tuples. No build or execution."""
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
CAMPAIGN = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
SOURCES = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix')
NAME = 'rvv_fault_replay_segment_nf8_strided_e32_mf2'
SHA = 'c90e2ac2ab90fba392ca887842ce07c78244405ef41428f7e8f760373e658282'


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    original = CAMPAIGN / 'rvv_additions54/binaries' / NAME
    reference = CAMPAIGN / 'rvv_strided_fault_reference54'
    old_source = reference / 'source_nf8_mf2'
    rebuilt = CAMPAIGN / 'rvv_fault_identity_regression57/source_mf2_False_0_nf8_stridedTrue_reverseFalse'
    identity = CAMPAIGN / 'rvv_fault_identity_regression57/identity_verification.json'
    files = [Path(__file__), original, old_source / 'manifest.json', old_source / (NAME+'.S'),
        old_source / 'overlay/opt/ara-tests' / NAME, rebuilt / 'manifest.json',
        rebuilt / 'overlay/opt/ara-tests' / NAME, identity,
        SOURCES / 'fault_replay_oracle.c', SOURCES / 'fault_replay.py']
    for elf in (original, old_source / 'overlay/opt/ara-tests' / NAME, rebuilt / 'overlay/opt/ara-tests' / NAME):
        assert sha(elf) == SHA
    assert read(identity)['verified_elf_hashes'][NAME] == SHA
    rebuilt_manifest = read(rebuilt / 'manifest.json')
    for name in ('fault_replay_oracle.c', 'fault_replay.py'):
        assert sha(SOURCES / name) == rebuilt_manifest['source_sha256'][name]
    spec = importlib.util.spec_from_file_location('nf8_readonly_source', SOURCES / 'fault_replay.py')
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    assert generator.assembly(32, lmul='mf2', fields=8, strided=True) == (old_source / (NAME+'.S')).read_text()
    reports = []
    for relative in ('rvv_recovery08_12/terminal_scene/report.json', 'rvv_recovery08_13/previous_report.json'):
        path = CAMPAIGN / relative
        result = [r for r in read(path)['results'] if r['name'] == NAME]
        assert len(result) == 1 and 'errors=169' in result[0]['output']
        reports.append(dict(path=str(path), result=result[0]))
        files.append(path)
    retest = CAMPAIGN / 'rvv_failure_retest01/results.json'
    case = next(r for r in read(retest)['cases'] if r['name'] == NAME and r['scope'] == 'original')
    assert case['sha256'] == SHA and 'errors=128' in case['retest_attempts'][0]['output']
    files.append(retest)
    refs = []
    for vlen in (512, 1024):
        path = reference / f'reference_{vlen}.json'
        entry = next(r for r in read(path)['results'] if r['name'] == NAME)
        assert 'cases=192 signals=144 errors=0' in entry['output']
        refs.append(dict(vlen=vlen, result=entry))
        files.append(path)
    tuples = []
    for trial, (unmapped, store, boundary, mode, gap, split) in enumerate(itertools.product(
            range(2), range(2), (1, 3, 5), range(4), (1, 3), range(2))):
        mask = (0xff, 0xaa, 0x24, 0)[mode]
        stride = (8+gap)*4
        base = 4096-boundary*stride-split*16
        start = next((i for i in range(boundary, 8) if mask & (1 << i)), 8)
        addresses = [[base+i*stride+f*4 for f in range(8)] for i in range(8)]
        tuples.append(dict(trial=trial, unmapped=unmapped, store=store, boundary=boundary,
            mode=mode, gap=gap, split=split, mask=mask, stride_bytes=stride,
            base_offset=base, expected_vstart=start, expected_fault=start<8,
            permitted_tval_offsets=[a for a in addresses[start] if a>=4096] if start<8 else [],
            field_address_offsets=addresses))
    assert len(tuples) == 192 and sum(t['expected_fault'] for t in tuples) == 144
    rtl = {}
    frozen = Path('/home/wangwy/fpga_runs/current_board_memory_candidate02/frozen/sources')
    for name in ('vlsu/addrgen.sv', 'vlsu/vldu.sv', 'vlsu/vstu.sv', 'segment_sequencer.sv',
                 'ara_sequencer.sv', 'ara_dispatcher.sv'):
        current = ROOT / 'hardware/src' / name
        sealed = frozen / 'hardware/src' / name
        rtl[name] = dict(current_sha256=sha(current), candidate02_sha256=sha(sealed), identical=sha(current)==sha(sealed))
        files.extend((current, sealed))
    result = dict(status='STATIC_SELECTION_ONLY_NO_NEW_TEST', original_name=NAME, original_sha256=SHA,
        archived_169_reports=reports, later_same_elf_retest=case['retest_attempts'], archived_references=refs,
        original_inner_failure_tuple_known=False, extra41_error_kind_known=False,
        provenance='Current C/generator hashes match archived identity57 manifest; its rebuilt ELF equals released ELF; no rebuild performed here',
        tuples=tuples, proposed_only=[tuples[i] for i in (19, 17, 67, 31)], rtl=rtl,
        pins={str(p):sha(p) for p in files}, jobs_started=False, RTL_modified=False,
        NF7_progress_not_read=True)
    with (HERE / 'selection01.json').open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(result['status'], '192 tuples, 144 expected faults; proposed', [x['trial'] for x in result['proposed_only']])
    print(json.dumps(rtl, indent=2))


if __name__ == '__main__':
    main()

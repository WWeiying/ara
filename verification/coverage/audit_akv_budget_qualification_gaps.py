"""Offline evidence inventory and independent descriptor group readback; never admits."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

import akv_historical_budget_oracle_717 as old

ROOT = old.ROOT
OUT = ROOT / 'verification/out'
RUNS = {
    old.DESCRIPTOR: OUT / 'akv-gap35-descriptor-budget1800-old-image-717-20261006-02',
    old.SKEW: OUT / 'akv-gap46-skew-context-budget3000-old-image-717-20261006-02',
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def expected_halfword(phase, index):
    old.require(0 <= phase < 26 and 0 <= index < 256, 'Bad readback coordinate')
    return 0x7700 + index*7 if phase == 24 and index < 64 else 0x9000 + index*13


def descriptor_readback(rows, symbols):
    commands = [r for r in rows if r['event'] == 'cvx_req' and int(r['insn'],16)&127 == 91]
    old.require([int(r['insn'],16) for r in commands] == old.DESCRIPTOR_WORDS, 'Wrong command sequence')
    base = symbols['got']['value']
    frames = [dict() for _ in commands]
    for r in rows:
        if r['event'] != 'retire' or not int(r['mem_rmask'],16):
            continue
        address = int(r['mem_addr'],16)
        if not base <= address < base+512:
            continue
        # The software compare loop is lhu over all256 halfwords. Bind the
        # command window by cycle, never by arch_start's placeholder PC.
        word = int(r['insn'],16)
        old.require(word&127 == 3 and word>>12&7 == 5 and int(r['rd']) != 0 and
                    address%2 == 0, 'Unexpected/unobservable destination load')
        phase = sum(int(c['cycle']) <= int(r['cycle']) for c in commands)-1
        old.require(0 <= phase < 26, 'Readback outside command windows')
        index = (address-base)//2
        value = int(r['rd_wdata'],16)
        old.require(value == expected_halfword(phase,index),
                    'Independent destination mismatch phase=%d halfword=%d' % (phase,index))
        frames[phase][index] = value
    old.require(all(set(frame) == set(range(256)) for frame in frames), 'Incomplete26 group readbacks')
    return dict(status='INDEPENDENT_DESCRIPTOR_ALL26_DESTINATION_GROUP_READBACK_PASS',
                frames=26, halfwords_per_frame=256, independently_checked_bytes=13312,
                protected_group='v8..v11,512 bytes; not full32VRF or native write-port observation',
                independent_expected='Static seed0x9000+13*i; phase24 V-row2 active64 halfwords0x7700+7*i; tails retained',
                illegal_phase_frames=list(range(23)), guard_scope='No guard allocation in original group app',
                full_ISA_qualified=False, full_native_vector_qualified=False)


def inspect(case, run):
    manifest = json.loads((run/'manifest.json').read_text())
    result = json.loads((run/'oracle-result.json').read_text())
    sealed = json.loads((run/'result-seal.json').read_text())
    old.require(all(digest(Path(p)) == h for p,h in sealed.items()), 'Historical result pin drift')
    old.require(digest(run/'input.elf') == manifest['elf_sha256'], 'ELF drift')
    with (run/'commit_trace.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    retired = [r for r in rows if r['event'] == 'retire']
    words = Counter(int(r['insn'],16) for r in retired)
    csr = Counter(hex(w>>20) for w,n in words.items() if w&127 == 0x73 and w>>12&7 for _ in range(n))
    terminal = json.loads((run/'terminal.json').read_text())
    pins = dict(sealed)
    for name in ('result-seal.json','manifest.json'):
        pins[str(run/name)] = digest(run/name)
    drift = []
    for path, expected in manifest['pins'].items():
        actual = digest(path) if Path(path).is_file() else None
        if actual != expected:
            drift.append(dict(path=path, expected=expected, actual=actual))
        if actual is not None:
            pins[path] = actual
    paths = [str(run/'vector_trace.csv'), str(run/'spike.trace')]
    record = dict(case=case, run=str(run), elf_sha256=manifest['elf_sha256'],
        image_hash=manifest['image'][manifest['command'][0]], image_files=len(manifest['image']),
        historical_status=result['status'], terminal=terminal,
        original_checks=result['checks'], retirements=len(retired),
        compressed_retirements=sum(n for w,n in words.items() if w&3 != 3),
        executed_opcode_counts={hex(op):sum(n for w,n in words.items() if w&3 == 3 and w&127 == op)
                                for op in sorted({w&127 for w in words if w&3 == 3})},
        csr_instruction_counts=dict(csr), mret_count=words[0x30200073],
        scalar_terminal_stores=[dict(pc=r['pc'],address=r['mem_addr'],value=r['mem_wdata'])
            for r in retired if int(r['mem_wmask'],16) and int(r['mem_addr'],16) == 0xd0000000],
        original_oracle_scope=result['data_oracle_scope'],
        original_manifest_pin_drift=drift,
        original_manifest_all_pins_match=not drift,
        missing_files=[p for p in paths if not Path(p).exists()],
        full_ISA_qualified=False, native_vector_write_qualified=False,
        source_bindings={p:h for p,h in manifest['pins'].items() if p.endswith(('.c','.h','.S'))},
        qualification_gaps=['No independently executed complete ELF scalar ISA comparison.',
            'No vector write trace: native alloc/done/write bytes and full32VRF complement cannot be recovered from UART PASS.',
            'Existing scalar Model explicitly rejects compressed ELF, M-to-U startup and original MMIO terminal; not drop-in reusable.',
            'Formal fresh gain/ELF dedup must be checked against latest admitted base, independently of this qualification audit.'])
    if case == old.DESCRIPTOR:
        record['independent_destination_readback'] = descriptor_readback(rows,result['elf_layout']['symbols'])
    return record,pins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    out = parser.parse_args().output.absolute()
    old.require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh direct report required')
    records,pins = [],{}
    for case,run in RUNS.items():
        record,bound = inspect(case,run)
        records.append(record)
        pins.update(bound)
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_audit_akv_budget_qualification_gaps.py'),
                 Path(old.__file__).resolve()):
        pins[str(path)] = digest(path)
    report = dict(status='AKV_BUDGET_QUALIFICATION_GAPS_ACTUAL_AUDIT_HOLD_NOT_ADMITTED',
        preferred_case=old.DESCRIPTOR,cases=records,pins=pins,
        shortest_closure=['Descriptor first: retain the exact ELF and 23traps/26command oracle; independent destination13312bytes now checked.',
            'Create a bounded original-ELF ISA successor: RV64C + executed M/CSR subset, M->U initialization, U illegal trap/MRET, UART and d0000000 terminal. Reuse comparison and reset source anchors, not no-C workload assumptions.',
            'Bind custom commands to independently validated descriptors/selector/context and scalar readback of the entire512-byte group. Prove rejected commands have no backend allocation from commit lifecycle; no invented native write observation.',
            'Parent must explicitly accept complete architectural group reconstruction as supersession for unavailable vector-port trace; otherwise native write-port/full32VRF requirement remains irrecoverable from these logs. No VCS retry authorized.',
            'Only after full independent ISA/native architectural contract qualifies, check latest base unique ELF/VDB and positive exactcompiled gain in a separate nonadmission candidate.'],
        coverage_admitted=False,simulations_started=False,rtl_changed=False)
    old.require(all(digest(Path(p)) == h for p,h in pins.items()), 'Final evidence drift')
    with out.open('x') as stream:
        json.dump(report,stream,indent=2,sort_keys=True)
        stream.write('\n')
    print(json.dumps(dict(output=str(out),seal=digest(out),pins=len(pins),
                         status=report['status'],preferred=report['preferred_case'])))


if __name__ == '__main__':
    main()

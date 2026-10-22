"""Read-only first-exception audit; no simulation, qualification or admission."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'verification/out'
RUN = OUT/'qbs-payload-matrix4-old-image-agent-20261007-01'
PRE = OUT/'qbs-payload-matrix4-preflight764-agent-20261007-02'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def audit():
    paths = [RUN/n for n in ('simulation-status.json','manifest.json','started.json',
                              'commit_trace.csv','trace_hart_0.log','console.log')]
    paths += [PRE/'preflight-manifest.json', PRE/'dut.metadata.log',
              PRE/'qbs_payload_matrix4.elf', PRE/'dut.link.log', PRE/'execute.S',
              ROOT/'apps/qbs_payload_matrix4/main.c', ROOT/'apps/common/printf.h',
              ROOT/'apps/common/crt0.S',
              OUT/'qbs-payload-phase-preflight763-agent-20261007-01/checked_body.inc',
              Path(__file__).resolve()]
    pins = {str(p):sha(p) for p in paths}
    status = json.loads(paths[0].read_bytes())
    require(status['status']=='SIMULATION_NOT_ADMITTED' and
            status['reason'].startswith('TimeoutExpired:') and
            status['post_failure_pin_error'] is None, 'Not the preserved clean-pin timeout')
    meta = json.loads((PRE/'dut.metadata.log').read_bytes())[0]
    symbols = {r['Symbol']['Name']['Name']:r['Symbol'] for r in meta['Symbols']}
    fstat = symbols['_fstat']
    pc = fstat['Value']+16
    require(pc==0x800069f6, 'Unexpected syscall site')
    elf = (PRE/'qbs_payload_matrix4.elf').read_bytes()
    sections = [r['Section'] for r in meta['Sections'] if
                r['Section']['Type']['Name']!='SHT_NOBITS' and
                r['Section']['Address']<=pc and pc+4<=r['Section']['Address']+r['Section']['Size']]
    require(len(sections)==1, 'Ambiguous ELF instruction')
    sec = sections[0]
    pos = sec['Offset']+pc-sec['Address']
    require(elf[pos:pos+4]==b'\x73\x00\x00\x00', 'First fault is not ELF ECALL')
    trace = RUN/'trace_hart_0.log'
    prefix = []; first = None; second = None
    with trace.open() as f:
        for line in f:
            if line.startswith('Exception'):
                if first is None:
                    first = line.strip()
                else:
                    second = line.strip(); break
            prefix.append(line.rstrip())
    require(first is not None and 'PC: 00000000800069f6' in first and
            'Environment Call User Mode' in first, 'Different first architectural error')
    require(second is not None and 'PC: 001fffffffffff00' in second and
            'Instruction Access Fault' in second, 'Different trap-vector failure')
    require(any('00000000800069f2' in l and '05000893' in l and
                '0000000000000050' in l for l in prefix[-10:]), 'Missing independent a7=80 setup')
    app = (ROOT/'apps/qbs_payload_matrix4/main.c').read_text()
    good = paths[-2].read_text()
    require('#include <stdio.h>' in app and 'printf.h' not in app and
            '#include "printf.h"' in good, 'Printf source-difference hypothesis unsupported')
    require('#define printf printf_' in (ROOT/'apps/common/printf.h').read_text(),
            'Missing tiny printf remapping')
    require('libc_a-printf.o' in (PRE/'dut.link.log').read_text(), 'Newlib provenance missing')
    valid = []; partial = []; events = {}
    with (RUN/'commit_trace.csv').open() as f:
        for row in csv.DictReader(f):
            if any(v is None for v in row.values()):
                partial.append(row); continue
            valid.append(row)
            events[row['event']] = events.get(row['event'],0)+1
    require(len(partial)==1 and partial[0]['pc']=='0000000080005e42', 'Unexpected partial trace')
    require(events.get('uop_alloc')==events.get('uop_done')==9, 'Unexpected first-command lifecycle')
    require(all(r['trap']=='0' for r in valid), 'Earlier CSV trap requires investigation')
    stores = {}
    for name in ('checks','errors'):
        address = symbols[name]['Value']
        matches = [r for r in valid if int(r['mem_addr'],16)==address and int(r['mem_wmask'],16)]
        require(matches, 'Missing first-phase '+name+' store')
        stores[name] = matches[-1]
    require(int(stores['checks']['mem_wdata'],16)==6 and
            int(stores['errors']['mem_wdata'],16)==0, 'First-phase self-check failed')
    for p, expected in pins.items():
        require(sha(Path(p))==expected, 'Diagnostic input drift')
    return dict(status='MATRIX4_TIMEOUT_PRINTF_SYSCALL_ROOT_CAUSE_HOLD', input_pins=pins,
        first_architectural_exception=first, next_exception=second,
        first_exception_pc=hex(pc), opcode='0x00000073', syscall_a7=80,
        root_cause='DUT app includes stdio.h but not common/printf.h; linked newlib printf invokes unsupported user-mode _fstat syscall. Existing good phase2 uses printf_ UART implementation.',
        call_chain=['printf','_vfprintf_r','__swsetup_r','__smakebuf_r','_fstat_r','_fstat'],
        chain_symbols={n:dict(pc=hex(symbols[n]['Value']),size=symbols[n]['Size']) for n in
                       ('printf','_vfprintf_r','__swsetup_r','__smakebuf_r','_fstat_r','_fstat')},
        csv_complete_rows=len(valid), csv_events=events, csv_partial_tail=partial,
        csv_is_not_complete_exception_ledger=True, first_phase_check_stores=stores,
        first_phase_checks=6, first_phase_errors=0, complete_functional_qualification=False,
        full_scalar_isa_verified=False, coverage_admitted=False,
        measured_qualified_toggle_gain=None, simulation_rerun=False,
        discriminants=['ELF DUT main calls printf_ not printf; no newlib _fstat syscall reachable from logging',
                      'First printing returns through UART without ECALL; all four exact commands and complete gold readbacks retire',
                      'No unexpected architectural exception, unique successful terminal and complete CSV rows'],
        next_action='Separate reviewed software successor only; preserve current ELF/run/preflight. No timeout increase, RTL change or automatic retry.')


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    result = audit()
    with a.output.open('x') as f:
        json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(dict(output=str(a.output),seal=sha(a.output),status=result['status'])))

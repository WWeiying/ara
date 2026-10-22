#!/usr/bin/env python3
"""Independent read/hash/ELF review and tiny event counterexamples; no raw parse."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent/'unit_fof_e64_suffix_two_prepare01'
ARCHIVE = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
READY_SHA = '816491edd10f338f435c3bcf473cb7cc4434d1ce65fbe7cfb419dab9bce6a2c5'

def read(path): return json.loads(path.read_text())
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as fp:
        for block in iter(lambda:fp.read(1024*1024),b''): h.update(block)
    return h.hexdigest()
def require(ok, message):
    if not ok: raise ValueError(message)
def save(path, value):
    with path.open('x') as fp: json.dump(value,fp,indent=2); fp.write('\n')

def elf_reader(path):
    raw=path.read_bytes()
    require(raw[:6] == b'\x7fELF\x02\x01', 'ELF64 little endian')
    off=struct.unpack_from('<Q',raw,32)[0]
    size,count=struct.unpack_from('<HH',raw,54)
    segments=[]
    for i in range(count):
        kind,flags,start,va,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',raw,off+i*size)
        if kind==1: segments.append((va,filesz,start))
    def bytes_at(pc,width):
        for va,n,start in segments:
            if va<=pc and pc+width<=va+n: return raw[start+pc-va:start+pc-va+width]
        raise ValueError('Unmapped file instruction '+hex(pc))
    return bytes_at

def main():
    start=time.monotonic()
    require(sha(SOURCE/'READY.json') == READY_SHA, 'Handoff READY identity')
    ready=read(SOURCE/'READY.json'); pins=read(SOURCE/'input_pins.json')
    require(sha(SOURCE/'input_pins.json') == ready['input_pins_sha256'], 'Input map identity')
    require(len(pins)==732, 'Exact input membership')
    for path,digest in pins.items(): require(sha(path)==digest,'Input drift '+path)
    manifest=read(ARCHIVE/'rvv_small_exceptions01/manifest.json')
    symptoms=read(ARCHIVE/'rvv_exception_symptoms02/symptoms.json')
    reports=[]
    for item in ready['cases']:
        scenario=item['scenario']; name=item['id']
        path=SOURCE/'software01'/f'scenario{scenario}'
        proof=read(path/'source_proof.json'); spec=read(path/'soc.spec.json')
        original=ARCHIVE/'rvv_small_exceptions01/binaries'/name
        record=next(x for x in manifest['cases'] if x['name']==name)
        symptom=next(x for x in symptoms['cases'] if x['name']==name)
        require(sha(original)==record['sha256']==item['original_elf'], 'Original single identity')
        require(symptom['confirmed'] and symptom['status']=='failed' and symptom['trap']['cause']==13
                and symptom['trap']['offset']==32 and symptom['trap']['signal']==11, 'Real board failure')
        require(symptom['trap']['epc']==(0x10456 if scenario==1 else 0x1047e), 'Exact historical target')
        original_bytes=elf_reader(original)
        helper_count=0
        for backend in ('soc','spike'):
            backend_bytes=elf_reader(path/(backend+'.elf'))
            for helper,entry in proof['backend'][backend]['helpers'].items():
                require(len(entry['pcs'])==(3 if helper=='capacity' else 11), 'Complete original helper')
                for pc,original_pc,encoding in zip(entry['pcs'],entry['original_pcs'],entry['encodings']):
                    value=int(encoding,16); width=4 if value&3==3 else 2
                    require(backend_bytes(pc,width)==original_bytes(original_pc,width)==value.to_bytes(width,'little'),
                            'Actual original/port helper machine bytes')
                    helper_count+=1
        actual=elf_reader(Path(spec['elf']))
        require(actual(spec['exit_store'],4)==bytes.fromhex('23b0a200') and
                actual(spec['park'],2)==bytes.fromhex('01a0') and 'tohost' not in spec['symbols'], 'Real CTRL store/park')
        host_lines=(path/'host.stdout').read_text().splitlines()
        output=[f'O {phase} {i} 1 {11+(i-1)*37 if phase==1 and 1<=i<=4 else 91}'
                for phase in (0,1) for i in range(130)]
        require(host_lines[:260]==output,'Independent full130 typed e64 output model')
        require(host_lines[260:276]==[f'M {i} {15 if i==0 else 0}' for i in range(16)],'Full mask16')
        status=read(SOURCE/f'reference_scenario{scenario}_01/status.json')
        require(status['status']=='REFERENCE_CHECKER_PASS_NOT_DUT' and status['commits']==172731 and
                status['scalar_checks']==5481 and status['htif']==[1] and status['pins_unchanged'] and
                status['execution']['actual_wait_returncode']==0 and not status['execution']['timeout'],
                'Durable original reference status')
        require(len(status['traps'])==1 and status['traps'][0][0]=='trap_supervisor_ecall','No target fault reference')
        reports.append(dict(scenario=scenario,original_elf_sha256=sha(original),
             original_target=hex(symptom['trap']['epc']),original_tval=hex(symptom['trap']['tval']),
             helper_encodings_compared=helper_count,source_result=[11,48,85,122,91,91,91,91],
             actual_reference_rc=0,reference_records=172731,reference_checks=5481))

    # These are observer unit counterexamples, not artificial DUT evidence.
    sys.path.insert(0,str(SOURCE))
    import csv_check as c
    weaknesses=[]
    for scenario in (1,2):
        spec=read(SOURCE/'software01'/f'scenario{scenario}'/'soc.spec.json')
        q=c.Checker(spec)
        before=copy.deepcopy({k:v for k,v in vars(q).items() if k not in ('rows','last_cycle')})
        for event,order,port in [('arch_start',7,0),('uop_alloc',7,2),('uop_done',7,2),('uop_done',999,3)]:
            row={key:'0' for key in c.FIELDS}
            row.update(event=event,order=str(order),port=str(port),insn='deadbeef')
            q.row(row)
        after={k:v for k,v in vars(q).items() if k not in ('rows','last_cycle')}
        require(before==after,'Counterexample no longer reproduces; reassess review')
        weaknesses.append(dict(scenario=scenario,accepted_invalid_opcode_arch=True,
            accepted_orphan_done=True,balanced_pair_has_no_semantic_checker_state_effect=True,
            full_synthetic_DUT_PASS_claimed=False))
    require(sha(SOURCE/'READY.json')==READY_SHA,'Late READY drift')
    for path in (SOURCE/'csv_check.py',SOURCE/'observer.py'):
        require(sha(path)==pins[str(path)],'Late checker drift')
    evidence={**pins,str(SOURCE/'READY.json'):READY_SHA,
              str(SOURCE/'input_pins.json'):sha(SOURCE/'input_pins.json'),str(Path(__file__).resolve()):sha(Path(__file__))}
    save(HERE/'evidence_pins.json',evidence)
    result=dict(schema='UNIT_FOF_SUFFIX_INDEPENDENT_REVIEW_V1',
        decision='SOURCE_REFERENCE_NO_BLOCKER_DUT_CHECKER_HOLD',
        source_reference_accepted=True,worker_entry_accepted=False,DUT_admitted=False,
        reference_raw_reparsed=False,reference_or_DUT_executed=False,
        reference_READY_sha256=READY_SHA,pins_verified=len(pins),cases=reports,
        blocking_findings=[dict(id='P1_OWNER_COVERAGE',file=str(SOURCE/'csv_check.py'),
           detail='arch_start/uop_alloc/uop_done ignored; no required per-owner completed-backend contract')],
        host_counterexamples=weaknesses,evidence_pins_sha256=sha(HERE/'evidence_pins.json'),
        elapsed_s=time.monotonic()-start)
    save(HERE/'result.json',result)
    print(json.dumps({k:result[k] for k in ('decision','pins_verified','elapsed_s')}))

if __name__=='__main__':main()

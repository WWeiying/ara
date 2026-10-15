"""Closed software receipts and actual ELF sites; no firmware execution."""
import hashlib
import json
from pathlib import Path
import re
import struct
import prepare as p
from lifecycle import INIT,READS,INPUT_CODE,scalar_width
HERE=Path(__file__).resolve().parent
def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def code(path):
    return {int(m[1],16):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',Path(path).read_text(),re.M)}
def segments(path,stack):
    raw=Path(path).read_bytes();assert raw[:6]==b'\x7fELF\x02\x01'
    offset=struct.unpack_from('<Q',raw,32)[0];size,count=struct.unpack_from('<HH',raw,54)
    result=[]
    for index in range(count):
        kind,flags,off,vaddr,paddr,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',raw,offset+index*size)
        if kind==1:
            assert filesz<=memsz and 0x80000000<=vaddr and vaddr+memsz<=stack-65536
            assert vaddr==paddr and off+filesz<=len(raw)
            result.append(dict(address=vaddr,filesz=filesz,memsz=memsz,flags=flags))
    assert result
    return result
def main():
    numeric=read(HERE/'software_execution.json')
    assert numeric['actual_wait_returncode']==0 and not numeric['timed_out'] and numeric['retries']==0
    oldpins=read(HERE/'pins.json');pins=dict(oldpins);changes={}
    for path,digest in oldpins.items():
        actual=sha(path)
        if actual!=digest:
            assert Path(path)==HERE/'software.log','Unexpected immutable source/software drift'
            raw=Path(path).read_bytes();lines=raw.splitlines(keepends=True)
            assert json.loads(lines[-1])==read(HERE/'preflight.json')
            assert hashlib.sha256(b''.join(lines[:-1])).hexdigest()==digest,'Not exact final print append'
            changes[path]=dict(old_preterminal_sha256=digest,actual_closed_sha256=actual,
                cause='Only final preflight JSON print after old pins snapshot; original snapshot retained')
            pins[path]=actual
    assert len(changes)<=1
    receipts=[]
    for path in sorted(HERE.glob('host_*/case*.log.exit.json')):
        receipt=read(path);mutation=int(re.search(r'case(\d+)',path.name)[1])
        assert receipt['returncode']==(-4 if mutation==8 else 0 if mutation==0 else 1)
        receipts.append(dict(path=str(path),sha256=sha(path),**receipt))
    assert len(receipts)==20
    for mutation in range(10):
        assert (HERE/'host_original'/f'case{mutation}.log').read_bytes()==(HERE/'host_packed'/f'case{mutation}.log').read_bytes()
    proof=read(HERE/'proof.json');backends={}
    for name,backend in proof['backends'].items():
        assert sha(backend['elf'])==backend['sha256'] and not backend['extra_vector_instructions']
        symbols=read(HERE/name/'symbols.json')
        backends[name]=dict(sha256=backend['sha256'],stack_gap=backend['stack_gap'],
            LOADs=segments(backend['elf'],symbols['__stack_top']))
    actual=code(HERE/'spike/program.dis')
    assert all(actual[pc]==insn for pc,insn,_,_ in INIT)
    assert all(actual[pc]==insn for pc,insn in INPUT_CODE.items())
    assert [scalar_width(actual[pc],False) for pc,_,_ in READS]==[8]*32+[4]
    assert actual[0x8000007a]==0x00a2b023 and actual[0x8000007e]==0xa001
    assert all((w[j]['insn']>>20)&0x7ff==9 for w in
        proof['backends']['spike']['helpers'].values() if len(w)==13 for j in (0,5,10))
    for path in (HERE/'software_execution.json',HERE/'software_status.json',HERE/'pins.json',
        HERE/'inspect_compiled.py'):
        pins[str(path)]=sha(path)
    p.save(HERE/'software_terminal_pins.json',pins)
    p.save(HERE/'compiled_review.json',dict(status='HOST_COMPILED_ACTUAL_TYPED16_NOT_REFERENCE_NOT_DUT',
        actual_producer=numeric,host_actual_receipts=receipts,oldpins_retained=True,terminal_changes=changes,
        terminal_pins_sha256=sha(HERE/'software_terminal_pins.json'),backends=backends,
        exact_spike_init=INIT,exact_spike_reads=READS,typed_seed_SHs=INPUT_CODE,
        scope=dict(calls=4095,results=524160,guards=8190,vstart=4095,helper_instructions=53235,
            output_reads=135135,checked_bytes=260,vlm_bytes=16,mask_bytes=128,physical_registers=2,vtype=9),
        estimate=dict(success_path_only=True,not_measured_retired=True,
            conservative_firmware_envelope=2000000,arithmetic=4095*400+1575*200+30000,
            note='Actual32words+tail4/block64 lowering; per-call400 and per-maskgroup200 success-path proxy, not a proved instruction upper bound or measured cost'),
        DUT_runs=0))
    print('COMPILED_CLOSED_TYPED16_RECEIPTS_ACCEPTED',flush=True)
if __name__=='__main__':main()

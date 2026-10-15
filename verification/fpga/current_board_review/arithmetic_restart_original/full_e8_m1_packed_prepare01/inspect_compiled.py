#!/usr/bin/env python3
"""Inspect actual linked software and durable Host receipts; never run firmware."""
import json
from pathlib import Path
import re
import prepare as p
from lifecycle import INIT, READS, INPUT_CODE

HERE=Path(__file__).resolve().parent
def read(path):return json.loads(path.read_text())
def main():
    pins=read(HERE/'pins.json')
    for path,digest in pins.items():p.old.require(p.sha(Path(path))==digest,'Input drift '+path)
    proof=read(HERE/'proof.json');backends={}
    for backend in ('soc','spike'):
        folder=HERE/backend;text=(folder/'program.dis').read_text()
        code={int(m[1],16):dict(insn=int(m[2],16),asm=m[3].strip()) for m in
            re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\n]+)',text,re.M)}
        symbols=read(folder/'symbols.json');shift=0 if backend=='spike' else -12
        init=[(pc+shift,insn,size,offset) for pc,insn,size,offset in INIT]
        reads=[(pc+shift,size,offset) for pc,size,offset in READS]
        assert len(init)==len(reads)==17
        for pc,insn,size,offset in init:
            assert code[pc]['insn']==insn
            assert code[pc]['asm'].startswith(('sh\t' if size==2 else 'sd\t'))
            assert (insn>>15)&31==22
        assert [x[3] for x in init]==[128]+list(range(0,128,8))
        for pc,size,offset in reads:
            assert code[pc]['asm'].startswith('lhu\t' if size==2 else 'ld\t')
            if size==8:
                assert (code[pc]['insn']>>15)&31==22
                assert code[pc]['insn']>>20==offset
            else:assert '<out+0x80>' in code[pc]['asm']
        assert code[symbols['arithmetic_main']]['asm']=='addi\tsp,sp,-304'
        assert symbols['__bss_end']<symbols['__stack_top']-65536
        assert len(proof['backends'][backend]['helpers'])==26
        assert not proof['backends'][backend]['extra_vector_instructions']
        if backend=='spike':
            assert all(code[pc]['insn']==insn for pc,insn in INPUT_CODE.items())
            assert code[0x800004da]['insn']==0xe394
            assert code[0x8000007a]['insn']==0x00a2b023 and code[0x8000007e]['insn']==0xa001
        p.run([p.old.CC.with_name('riscv64-unknown-elf-size'),'-A',folder/'program.elf'],folder/'size.log')
        sections={}
        for line in (folder/'size.log').read_text().splitlines():
            match=re.match(r'(\.\S+)\s+(\d+)\s+(\d+)$',line)
            if match:sections[match[1]]=dict(bytes=int(match[2]),address=int(match[3]))
        assert sections['.rodata']['bytes']>=556920+384
        assert symbols['__stack_top']==0x800ffff0
        backends[backend]=dict(elf_sha256=p.sha(folder/'program.elf'),sections=sections,
            stack_top=symbols['__stack_top'],bss_end=symbols['__bss_end'],
            stack_gap=symbols['__stack_top']-symbols['__bss_end'],main_frame_bytes=304,
            actual_init=[dict(pc=hex(pc),size=size,offset=offset,**code[pc]) for pc,_,size,offset in init],
            actual_output_reads=[dict(pc=hex(pc),size=size,offset=offset,**code[pc]) for pc,size,offset in reads])
    receipts=[]
    for path in sorted(HERE.glob('host_*/case*.log.exit.json')):
        item=read(path);mutation=int(re.search(r'case(\d+)',path.name)[1])
        assert type(item['returncode']) is int and item['returncode']==(-4 if mutation==8 else 0 if mutation==0 else 1)
        receipts.append(dict(path=str(path),sha256=p.sha(path),**item))
    assert len(receipts)==20
    assert len(INIT)==17 and len(READS)==17
    for path,digest in pins.items():p.old.require(p.sha(Path(path))==digest,'Post-inspection drift '+path)
    report=dict(status='HOST_COMPILED_STATIC_COST_ONLY_NOT_REFERENCE_NOT_DUT',
        prepare_actual_returncode=0,prepare_command=['python3','-B','prepare.py'],
        prepare_terminal_evidence=dict(session_id=20543,completed_chunk='c5b136'),
        source_review_sha256=p.sha(HERE.parent/'e8_m1_packed_source_review01/REVIEW.md'),
        pins=len(pins),pins_unchanged=True,proof_sha256=p.sha(HERE/'proof.json'),
        backends=backends,host_actual_receipts=receipts,
        scope=dict(calls=4095,results=524160,guards=8190,vstart_checks=4095,
            helper_instructions=53235,output_reads=69615,mask_buffers=1575,
            physical_mask_bytes=128,actual_vlm_bytes=16,physical_register_bytes=128),
        static_instruction_ranges=dict(initializer_and_arguments=[hex(0x80000502),hex(0x80000568)],
            first_compare=[hex(0x8000056c),hex(0x8000058a)],remaining_compare=[hex(0x80000844),hex(0x800008e6)],
            mask_loop=[hex(0x800004d6),hex(0x800004e2)]),
        estimate=dict(success_path_only=True,not_measured_retired=True,conservative_firmware_envelope=2000000,
            arithmetic=4095*300+1575*200+3*128*50+40000,
            note='Each successful call including helper/init/17 compares and loop control <300; each full16-copy mask group <200; seed50/element plus40k boot/console allowance. Rounded to2M, not measured.'),
        reference_proposal=dict(hard_steps=4000000,firmware_to_HTIF_limit=3000000,wall_s=120,
            raw_bytes=768*1024**2,attempts=1,requires_independent_checker_review=True,started=False),
        DUT_authorized=False)
    p.save(HERE/'compiled_review.json',report)
    print(json.dumps(dict(status=report['status'],backends={k:dict(elf_sha256=v['elf_sha256'],
        stack_gap=v['stack_gap'],sections=v['sections']) for k,v in backends.items()},host_receipts=len(receipts))),flush=True)

if __name__=='__main__':main()

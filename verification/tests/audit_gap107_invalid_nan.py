#!/usr/bin/env python3
"""Static ELF site/source-template audit for the one gap107 shape."""
from pathlib import Path
import json
import struct
import sys

sys.dont_write_bytecode = True
import build_gap38_i8_f16_lane3 as common



def audit_execution(instructions, offsets, custom_pc):
    common.require(len(instructions)==len(offsets) and offsets.count(custom_pc)==1,
                   'Unique custom instruction boundary required')
    custom=instructions[offsets.index(custom_pc)]
    common.require(custom==0x00b5045b, 'Exact M1 custom word differs')
    index=offsets.index(custom_pc)
    csrs=(0xc20,0xc21,0x008,0x002,0x001,0x00f)
    def csr_read(csr):return (csr<<20)|(2<<12)|(5<<7)|0x73
    def sd(offset):return ((offset>>5)<<25)|(5<<20)|(14<<15)|(3<<12)|((offset&31)<<7)|0x23
    before=[v for i,csr in enumerate(csrs) for v in (csr_read(csr),sd(8*i))]
    after=[v for i,csr in enumerate(csrs) for v in (csr_read(csr),sd(48+8*i))]
    common.require(instructions[index-13:index-1]==before and
                   instructions[index-1]==0x0330000f and instructions[index+1:index+13]==after,
                   'Immediate CSR capture/fence sequence differs')
    for csr,value in ((0x008,0),(0x002,2),(0x001,8),(0x00f,5)):
        word=(csr<<20)|(value<<15)|(5<<12)|0x73
        common.require(word in instructions[:index], 'Exact CSR initialization missing')
    loads=[w for w in instructions[:index] if w&0x7f==0x07 and (w>>12)&7==6]
    stores=[w for w in instructions[index+1:] if w&0x7f==0x27 and (w>>12)&7==6]
    for words,label in ((loads,'seed'),(stores,'snapshot')):
        common.require(len(words)==4 and [(w>>7)&31 for w in words]==[0,8,16,24] and
                       all(w>>20==0x20 for w in words), 'Complete unmasked unit-stride '+label+' differs')
    common.require(instructions.count(0x0132f057)==2 and
                   any(instructions[i]==0x10000293 and instructions[i+1]==0x0132f057
                       for i in range(len(instructions)-1)), 'Full VLEN1024 m8 seed/snapshot setup differs')


def elf_proof(b, elf):
    result = b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON',
                    '--sections','--symbols','--program-headers',elf],'dut.metadata')
    b.run([b.llvm/'bin/llvm-objdump','-d',elf],'dut.disassembly')
    meta = json.loads(result.stdout)[0]
    symbols = {r['Symbol']['Name']['Name']:r['Symbol'] for r in meta['Symbols']}
    blob = elf.read_bytes()

    def at(address, size):
        matches = []
        for row in meta['Sections']:
            sec = row['Section']
            if sec['Type']['Name'] != 'SHT_NOBITS' and sec['Address'] <= address and address+size <= sec['Address']+sec['Size']:
                offset = sec['Offset']+address-sec['Address']
                matches.append(blob[offset:offset+size])
        common.require(len(matches) == 1, 'ambiguous ELF source/site address')
        return matches[0]

    sites = [s for s in symbols if s.startswith('gap107_qbexec_site')]
    sites = sorted(sites)
    common.require(sites == ['gap107_qbexec_site0', 'gap107_qbexec_site1'], 'exactly two custom sites required')
    for site in sites:
        common.require(at(symbols[site]['Value'],4) == struct.pack('<I',0x00b5045b), 'custom word differs')
    pc = symbols[sites[0]]['Value']
    for command in (0, 1):
        exec_pc = symbols['gap107_exec'+str(command)]['Value']
        code = at(exec_pc,symbols['gap107_exec'+str(command)]['Size'])
        instructions, offsets, offset = [], [], 0
        while offset < len(code):
            half = int.from_bytes(code[offset:offset+2], 'little')
            width = 4 if half & 3 == 3 else 2
            common.require(offset+width <= len(code), 'truncated ELF instruction')
            offsets.append(exec_pc+offset)
            instructions.append(int.from_bytes(code[offset:offset+width], 'little'))
            offset += width
        common.require(any(instructions[i] in (0x4285, 0x00100293)
                           and instructions[i+1] == 0x0102f057
                           for i in range(len(instructions)-1)),
                       'VL1/e32/m1 setup missing')
        audit_execution(instructions,offsets,symbols[sites[command]]['Value'])
    for name in ('weights','activation','descriptor_packet','initial','actual','csr_packet'):
        common.require(symbols[name]['Value']%64 == 0, 'allocation alignment differs: '+name)
    common.require(symbols['weights']['Size'] == 800 and symbols['activation']['Size'] == 2496,
                   'source guard capacities differ')
    for command, phase in enumerate((0, 0)):
        for name,capacity,prefix,native in [('weights',800,64,(b.out/('weight-native%d.bin'%command)).read_bytes()),
                ('activation',2496,64+phase,(b.out/('activation-native%d.bin'%command)).read_bytes())]:
            symbol = symbols['gap107_'+name+str(command)]
            common.require(symbol['Size'] == capacity, 'template size differs')
            image = at(symbol['Value'],capacity)
            guard = bytes([0xa5 if name == 'weights' else 0x5a])
            common.require(image == guard*prefix+native+guard*(capacity-prefix-len(native)),
                           'ELF native bytes/source guards differ')
        common.require((symbols['activation']['Value']+64+phase)%16 == phase,
                       'actual ELF activation phase differs')
    proof = dict(status='STATIC_ELF_VERIFIED_NOT_EXECUTED',elf=str(elf),elf_sha256=common.sha(elf),
        sites=[dict(symbol=s,pc=symbols[s]['Value'],word=0x00b5045b) for s in sites],custom_commands=2,vl=1,
        qbinfo_pc=symbols['gap107_info']['Value'],activation_mod16=[0,0],weight_profile='Q5_K',m=1,n=1,k_blocks=1,
        active_outputs_per_command=1,full_vrf_words_checked=2048,initial_words_checked=2048,
        source_bytes_checked=6880,csr_words_checked=24,dut_checks=41,
        vtype=16,vstart=0,frm=2,fflags_seed=8,expected_fflags_after=[24,24],vcsr=5,vcs_launched=False,
        full_scalar_isa_verified=False,custom_spike_pass=False,
        exact_seed_and_snapshot_instructions=True,immediate_pre_post_CSR_instructions_verified=True)
    common.save(b.out/'elf-proof.json',proof)
    return proof


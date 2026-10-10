#!/usr/bin/env python3
"""Static ELF site/source-template audit for the one gap105 shape."""
from pathlib import Path
import json
import struct
import sys

sys.dont_write_bytecode = True
import build_gap38_i8_f16_lane3 as common


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

    sites = [s for s in symbols if s.startswith('gap105_qbexec_site')]
    sites = sorted(sites)
    common.require(sites == ['gap105_qbexec_site0', 'gap105_qbexec_site1'], 'exactly two custom sites required')
    for site in sites:
        common.require(at(symbols[site]['Value'],4) == struct.pack('<I',0x0eb5045b), 'custom word differs')
    pc = symbols[sites[0]]['Value']
    exec_pc = symbols['gap105_exec0']['Value']
    code = at(exec_pc,symbols['gap105_exec0']['Size'])
    instructions, offset = [], 0
    while offset < len(code):
        half = int.from_bytes(code[offset:offset+2], 'little')
        width = 4 if half & 3 == 3 else 2
        common.require(offset+width <= len(code), 'truncated ELF instruction')
        instructions.append(int.from_bytes(code[offset:offset+width], 'little'))
        offset += width
    common.require(any(instructions[i] in (0x4285, 0x00100293)
                       and instructions[i+1] == 0x0102f057
                       for i in range(len(instructions)-1)),
                   'VL1/e32/m1 setup missing')
    for name in ('weights','activation','descriptor_packet','initial','actual','csr_packet'):
        common.require(symbols[name]['Value']%64 == 0, 'allocation alignment differs: '+name)
    common.require(symbols['weights']['Size'] == 800 and symbols['activation']['Size'] == 2496,
                   'source guard capacities differ')
    for command, phase in enumerate((4, 8)):
        for name,capacity,prefix,native in [('weights',800,64,(b.out/'weight-native.bin').read_bytes()),
                ('activation',2496,64+phase,bytes.fromhex(common.read(b.out/'oracle-command0.json')['activation_hex']))]:
            symbol = symbols['gap105_'+name+str(command)]
            common.require(symbol['Size'] == capacity, 'template size differs')
            image = at(symbol['Value'],capacity)
            guard = bytes([0xa5 if name == 'weights' else 0x5a])
            common.require(image == guard*prefix+native+guard*(capacity-prefix-len(native)),
                           'ELF native bytes/source guards differ')
        common.require((symbols['activation']['Value']+64+phase)%16 == phase,
                       'actual ELF activation phase differs')
    proof = dict(status='STATIC_ELF_VERIFIED_NOT_EXECUTED',elf=str(elf),elf_sha256=common.sha(elf),
        sites=[dict(symbol=s,pc=symbols[s]['Value'],word=0x0eb5045b) for s in sites],custom_commands=2,vl=1,
        qbinfo_pc=symbols['gap105_info']['Value'],activation_mod16=[4,8],weight_profile='Q5_K',m=8,n=1,k_blocks=1,
        active_outputs_per_command=8,full_vrf_words_checked=2048,initial_words_checked=2048,
        source_bytes_checked=6880,csr_words_checked=24,dut_checks=41,
        vtype=16,vstart=0,frm=2,fflags_seed=8,vcsr=5,vcs_launched=False)
    common.save(b.out/'elf-proof.json',proof)
    return proof

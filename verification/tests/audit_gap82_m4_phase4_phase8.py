#!/usr/bin/env python3
"""Verify both custom sites, phases, native templates and VL1 in the ELF."""
import json
import struct
import sys

sys.dont_write_bytecode = True
import build_gap38_i8_f16_lane3 as common


def elf_proof(b,elf):
    result = b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON',
                    '--sections','--symbols','--program-headers',elf],'dut.metadata')
    b.run([b.llvm/'bin/llvm-objdump','-d',elf],'dut.disassembly')
    meta = json.loads(result.stdout)[0]
    symbols = {r['Symbol']['Name']['Name']:r['Symbol'] for r in meta['Symbols']}
    blob = elf.read_bytes()

    def at(address,size):
        matches = []
        for row in meta['Sections']:
            sec = row['Section']
            if sec['Type']['Name'] != 'SHT_NOBITS' and sec['Address'] <= address and address+size <= sec['Address']+sec['Size']:
                offset = sec['Offset']+address-sec['Address']
                matches.append(blob[offset:offset+size])
        common.require(len(matches) == 1, 'ELF bytes not uniquely bound')
        return matches[0]

    wanted = ['gap82_qbexec_site0','gap82_qbexec_site1']
    common.require(sorted(s for s in symbols if s.startswith('gap82_qbexec_site')) == wanted,
                   'exactly two static sites required')
    for name in ('weights','activation','descriptor_packet','initial','actual','csr_packet'):
        common.require(symbols[name]['Value']%64 == 0, 'allocation alignment differs: '+name)
    common.require(symbols['weights']['Size'] == 800 and symbols['activation']['Size'] == 2496,
                   'source guard capacities differ')
    sites = []
    for command,phase in enumerate((4,8)):
        site = symbols[wanted[command]]['Value']
        common.require(at(site,4) == struct.pack('<I',0x06b5045b), 'custom word differs')
        routine = symbols['gap82_exec'+str(command)]
        code = at(routine['Value'],routine['Size'])
        instructions,offset = [],0
        while offset < len(code):
            width = 4 if int.from_bytes(code[offset:offset+2],'little') & 3 == 3 else 2
            common.require(offset+width <= len(code), 'truncated instruction')
            instructions.append(int.from_bytes(code[offset:offset+width],'little'))
            offset += width
        common.require(any(instructions[i] in (0x4285,0x00100293) and instructions[i+1] == 0x0102f057
                           for i in range(len(instructions)-1)), 'VL1/e32/m1 setup missing')
        for name,capacity,prefix,native in [
                ('weights',800,64,(b.out/'weight-native.bin').read_bytes()),
                ('activation',2496,64+phase,bytes.fromhex(common.read(b.out/'oracle-command0.json')['activation_hex']))]:
            symbol = symbols['gap82_'+name+str(command)]
            common.require(symbol['Size'] == capacity, 'template extent differs')
            guard = bytes([0xa5 if name == 'weights' else 0x5a])
            common.require(at(symbol['Value'],capacity) ==
                           guard*prefix+native+guard*(capacity-prefix-len(native)),
                           'ELF source/native/guard image differs')
        ap = symbols['activation']['Value']+64+phase
        common.require(ap%16 == phase, 'ELF activation phase differs')
        sites.append(dict(command=command,symbol=wanted[command],pc=site,word=0x06b5045b,vl=1,
                          activation_address=ap,activation_mod16=phase,
                          target_raw_index=408 if phase == 4 else 404))
    common.require(sites[0]['pc'] != sites[1]['pc'], 'custom sites alias')
    proof = dict(status='STATIC_ELF_VERIFIED_NOT_EXECUTED',elf=str(elf),elf_sha256=common.sha(elf),
        sites=sites,custom_commands=2,vl=1,weight_profile='Q5_K',m=4,n=1,k_blocks=1,
        active_outputs=8,full_vrf_words_checked=2048,initial_words_checked=2048,
        source_bytes_checked=6880,csr_words_checked=24,dut_checks=41,
        per_command_dut_checks=17,per_command_host_checks=18,
        vtype=16,vstart=0,frm=2,fflags_seed=8,vcsr=5,vcs_launched=False)
    common.save(b.out/'elf-proof.json',proof)
    return proof

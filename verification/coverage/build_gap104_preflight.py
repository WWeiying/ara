"""Two reserved whole-register NF traps, independent host/Spike oracle; no VCS."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct
import subprocess

import collect_gap103_strict as old
from closure_point_inventory import points

s, require = old.proof.s, old.require
ROOT, OUT = old.proof.ROOT, old.life.OUT
BASE = OUT/'gap103-offline-admitted-720-20261006-01'
BASE_SEAL = '2a39f961402fd2ec536f58672466583942b6407e2028638736145713ba13955e'
NAME = 'vgap104_whole_nf_reserved'
APP = ROOT/'apps/riscv-tests/isa/rv64uv'/(NAME+'.c')
WORDS = (0x42850407,0x42850427)
CHECKS = 1309
SYMBOLS = ('g104_bad_a','g104_bad_b','g104_dump','g104_target_dump','g104_recovery_dump',
           'g104_ledger','g104_traps','g104_restore','g104_csr','g75_result','num_failed','tohost','trap_fail')


def decode(word):
    return dict(nf=(word>>29)&7,mew=(word>>28)&1,mop=(word>>26)&3,vm=(word>>25)&1,
                rs2=(word>>20)&31,rs1=(word>>15)&31,width=(word>>12)&7,
                vd=(word>>7)&31,opcode=word&127)


def expected_words():
    result = {('g104_traps',0):2}
    for phase in range(2):
        for i in range(512):
            value = int.from_bytes(bytes([0x40+i//16])*8,'little')
            result['g104_dump',phase*4096+i*8] = value
        for i in range(64):
            result['g104_target_dump',phase*512+i*8] = 0xa5a5a5a5a5a5a5a5
            result['g104_recovery_dump',phase*512+i*8] = (
                0xa5a5a5a5a5a5a548 if i==2 else 0xa5a5a5a5a5a5a5a5)
        for i in range(5): result['g104_csr',phase*40+i*8] = 1 if i==0 else 0
    return result


def validate(commits,symbols,trace):
    pcs = [symbols['g104_bad_a'],symbols['g104_bad_b']]
    events = re.findall(r'exception ([^,\n]+), epc (0x[0-9a-fA-F]+)',trace)
    require([(name,int(pc,16)) for name,pc in events] ==
            [('trap_illegal_instruction',pc) for pc in pcs] and trace.count('exception ')==2,
            'Not exactly two reserved NF traps')
    require(not any(c.pc in pcs+[symbols['trap_fail']] for c in commits),'Bad retirement')
    writes = {a:v for c in commits for a,v in c.memory_accesses if v is not None}
    terminal = [v for c in commits for a,v in c.memory_accesses if a==symbols['tohost'] and v is not None]
    require(terminal==[1] and writes.get(symbols['g75_result'])==CHECKS and
            writes.get(symbols['g75_result']+4)==writes.get(symbols['num_failed'])==0,
            'Software result differs')
    for (name,offset),value in expected_words().items():
        require(writes.get(symbols[name]+offset)==value,'Canonical VRF/guard/CSR/recovery differs: %s+%d'%(name,offset))
    for phase in range(2):
        ledger = [writes.get(symbols['g104_ledger']+phase*80+i*8) for i in range(8)]
        require(ledger==[2,pcs[phase],WORDS[phase],1,0,0,0,phase+1],'Trap ledger differs')
    restored = [writes.get(symbols['g104_restore']+i*8) for i in range(4)]
    require(all(v is not None for v in restored) and restored[0]==restored[1] and restored[2]==restored[3],
            'Handler restoration differs')
    count = Counter()
    for c in commits:
        for reg,value in c.vector_writes.items():
            require(reg in range(32) and value==int.from_bytes(bytes([0x40+reg])*128,'little'),
                    'Unexpected vector architectural change')
            count[reg] += 1
    require(count==Counter({r:2 for r in range(32)}),'Exact VRF initialization population differs')
    return dict(status='GAP104_RESERVED_NF_SPIKE_PREFLIGHT_PASS_NOT_DUT',checks=CHECKS,
                illegal_traps=2,phases=2,unchanged_vrf_bytes=8192,unchanged_target_guard_bytes=1024,
                recovery_guard_bytes=1024,coverage_admitted=False)


def target_evidence():
    manifest = old.life.read_bound(BASE/'admission-manifest.json',BASE_SEAL)
    def approved(name):
        path=BASE/name
        return old.life.read_bound(path,manifest['output_pins'][str(path)])
    before,book=approved('combined-bits.json'),approved('evidence-pins.json')
    require(len(before['tests'])==len(set(before['tests']))==720,'Not exact720')
    pins = {str(BASE/'admission-manifest.json'):BASE_SEAL}
    for name in ('combined-bits.json','evidence-pins.json'): pins[str(BASE/name)] = manifest['output_pins'][str(BASE/name)]
    src = OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    expected='9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43'
    require(book[str(src)]==expected and old.life.digest(src)==expected,'Wrong frozen dispatcher')
    pins[str(src)]=expected
    source=src.read_text().splitlines()
    require(source[4319].strip()=="illegal_insn_load = 1'b1;" and
            source[4579].strip()=="illegal_insn_store = 1'b1;",'Reserved NF source default differs')
    for relative,digest in before['design'].items():
        path=old.DESIGN/'snps/coverage/db'/relative
        require(old.life.digest(path)==digest,'Compiled design changed');pins[str(path)]=digest
    design=old.proof.old.shared.Design(old.DESIGN)
    targets=[]
    for metric,indices in (('branch',(390,336)),('line',(1263,1346))):
        row=before['metrics'][metric][old.proof.old.SCOPE]
        node=design.definition(old.proof.old.SCOPE,metric)
        require(row['checksum']==node.get('chksum'),'Compiled checksum differs')
        mapped=points(metric,node,row['width'])
        for index in indices:
            point=next(p for p in mapped if p['raw_index']==index)
            require(not int(row['bits'],16)&(1<<(row['width']-1-index)),'Target already covered')
            if metric=='branch':
                v=point['native_vector']['vector']; selected=922 if index==390 else 995
                require(point['native_id']=='25' and point['vector']==('739' if index==390 else '793') and
                        len(v)==1270 and v[len(v)-selected]=='1','Whole NF default compiled path differs')
            else:
                require(point['line']==('4320' if index==1263 else '4580') and
                        point['attributes']['default_case']=='1','Wrong default body')
            targets.append(dict(scope=old.proof.old.SCOPE,metric=metric,width=row['width'],
                                checksum=row['checksum'],point=point,hit_before=False))
    return dict(status='GAP104_EXACT720_TARGETS_NOT_MEASURED',baseline_tests=720,pins=pins,
                targets=targets,index_convention='one-based expression index from right; raw bitmap MSB-first',
                native_exclusion_generated=False)


def elf_words(elf,symbols):
    blob=elf.read_bytes();h=struct.unpack_from('<HHIQQQIHHHHHH',blob,16)
    result=[]
    for name in ('g104_bad_a','g104_bad_b'):
        pc=symbols[name];owners=[]
        for i in range(h[11]):
            sec=struct.unpack_from('<IIQQQQIIQQ',blob,h[5]+i*64)
            if sec[1]==1 and sec[2]&4 and sec[3]<=pc and pc+4<=sec[3]+sec[5]:
                owners.append(struct.unpack_from('<I',blob,sec[4]+pc-sec[3])[0])
        require(len(owners)==1,'Ambiguous opcode owner');result.extend(owners)
    require(tuple(result)==WORDS,'ELF reserved NF words differ')
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args(argv).output.absolute()
    require(out.parent==OUT and out.resolve()==out and not out.exists(),'Fresh direct preflight required')
    evidence=target_evidence()
    previous=old.life.read_bound(old.runner.PRE/'preflight-manifest.json',old.runner.PRE_SEAL)
    command_path=old.runner.PRE/'compile-command.json'
    require(old.life.digest(command_path)==previous['pins'][str(command_path)],'Frozen compiler command changed')
    pins=s.merge_pins(evidence['pins'],previous['pins'])
    for path in (APP,Path(__file__).resolve(),Path(__file__).with_name('test_build_gap104_preflight.py'),
                 ROOT/'verification/tests/gap104_reference.h',ROOT/'verification/tests/gap104_host_reference.c'):
        pins=s.merge_pins(pins,{str(path):s.sha(path)})
    s.check(pins);out.mkdir();s.save(out/'input-pins.json',pins);s.save(out/'target-before.json',evidence)
    try:
        host=['/usr/bin/cc','-std=c11','-Wall','-Wextra','-Werror',str(ROOT/'verification/tests/gap104_host_reference.c'),
              '-o',str(out/'host-reference')]
        s.save(out/'host-command.json',host)
        with (out/'host.log').open('x') as log:
            subprocess.run(host,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60)
            subprocess.run([str(out/'host-reference')],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=10)
        elf=out/'input.elf';command=json.loads(command_path.read_bytes())
        command=[str(APP) if x==str(old.proof.APP) else str(elf) if x==previous['input_elf'] else x for x in command]
        require(str(APP) in command and str(elf) in command and str(old.proof.APP) not in command,'Compile substitution differs')
        s.save(out/'compile-command.json',command)
        with (out/'compile.log').open('x') as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        symbols={key:s._elf_symbol(elf,s.LLVM/'llvm-readelf',key) for key in SYMBOLS}
        words=elf_words(elf,symbols)
        command=[str(s.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(elf)]
        s.save(out/'spike-command.json',command)
        with (out/'spike.stdout').open('x') as stdout,(out/'spike.trace').open('x') as trace:
            subprocess.run(command,stdout=stdout,stderr=trace,check=True,timeout=120)
        validation=validate(s.parse_spike_commits(out/'spike.trace'),symbols,(out/'spike.trace').read_text())
        s.save(out/'spike-validation.json',validation);s.check(pins)
        pins=s.merge_pins(pins,{str(p):s.sha(p) for p in out.iterdir() if p.is_file()})
        s.save(out/'preflight-manifest.json',dict(status='GAP104_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS',
            case=NAME,baseline_tests=720,baseline_seal=BASE_SEAL,checks=CHECKS,symbols=symbols,opcodes=words,
            pins=pins,validation=validation,target_unhit_count=4,input_elf=str(elf),
            input_spike_trace=str(out/'spike.trace'),coverage_admitted=False,rtl_changed=False,vcs_started=False,
            measured_raw_increment=None))
        print(json.dumps(dict(output=str(out),seal=s.sha(out/'preflight-manifest.json'),pins=len(pins),checks=CHECKS)))
    except Exception as error:
        s.save(out/'failure.json',dict(status='GAP104_PREFLIGHT_FAILED',reason=str(error)));raise


if __name__=='__main__':main()

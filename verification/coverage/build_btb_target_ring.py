"""BTB32 A/B/A: bounded LLVM/real Spike preflight, no DUT/coverage PASS claim."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from elftools.elf.elffile import ELFFile
import build_gap98_preflight as build
import collect_gap103_strict as arch
import run_gap95_simulation as life
import targeted_toggle_evidence_v2 as toggle

ROOT, OUT, require = life.ROOT, life.OUT, build.require
APP = ROOT/'apps/riscv-tests/isa/rv64uv/vbtb_target_ring_sv39.c'
BASE = OUT/'akv-entropy-offline-admitted777-parent-20261007-01'
BASE_SHA = '39ad0375146e5a6d98f1ef0141030f95309e2a8409dc71f6d510b59631bc3d52'
BOOK = OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
CACHE = OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
CACHE_SHA = '8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.i_frontend.btb_gen.i_btb'
TARGETS = (0x1555555554, 0xffffffeaaaaaaaaa, 0x1555555554)
SYMBOLS = ('tohost','num_failed','g75_result','trap_fail','btb_bank0','btb_bank1_base','btb_bank1',
           'btb_s_entry','btb_s_ecall','btb_resume','btb_handler','btb_unexpected','btb_page','btb_root','btb_mid',
           'btb_leaf','btb_results','btb_trap','btb_original','btb_restored','btb_csr','btb_vrf')


def page():
    data = bytearray(4096)
    for offset, word in ((0x554,0x05500513),(0x558,0x00008067),
                         (0xaaa,0x0aa00513),(0xaae,0x00008067)):
        data[offset:offset+4] = word.to_bytes(4,'little')
    return bytes(data)


def tables(s):
    pte = lambda p,f: ((p>>12)<<10)|f
    root, mid, leaf = [0]*512, [0]*512, [0]*512
    root[2] = pte(0x80000000,0xcf)
    for a in TARGETS[:2]:
        require(a>>39 == (0x1ffffff if a>>38&1 else 0), 'Noncanonical Sv39 target')
        vpn=(a>>12)&0x7ffffff
        require(vpn>>18 != 2, 'Target/identity root collision')
        root[vpn>>18]=pte(s['btb_mid'],1)
        mid[vpn>>9&511]=pte(s['btb_leaf'],1)
        leaf[vpn&511]=pte(s['btb_page'],0x4b)
    return root, mid, leaf


def elf_contract(path, s):
    with path.open('rb') as stream:
        elf=ELFFile(stream)
        require(elf['e_entry']==0x80000000 and elf.elfclass==64 and elf.little_endian and
                elf['e_machine']=='EM_RISCV', 'Fixed ELF64 entry')
        def data(address,size):
            matches=[seg for seg in elf.iter_segments() if seg['p_type']=='PT_LOAD' and
                     seg['p_vaddr']<=address and address+size<=seg['p_vaddr']+seg['p_filesz']]
            require(len(matches)==1 and matches[0]['p_paddr']==matches[0]['p_vaddr'], 'File-backed exact physical load')
            seg=matches[0];off=address-seg['p_vaddr'];return seg.data()[off:off+size]
        require(s['btb_bank0']%64==s['btb_bank1_base']%64==0 and
                s['btb_bank1']==s['btb_bank1_base']+2 and
                s['btb_bank1_base']>=s['btb_bank0']+64, 'Nonoverlapping two aligned codebanks')
        for bank in (0,1):
            require(data(s['btb_bank%d'%bank],64)==(0x00030067).to_bytes(4,'little')*16,
                    'All32 source JALRs are rd0 rs1x6 imm0, not returns')
        require(data(s['btb_bank1_base'],2)==b'\x01\x00', 'Exact halfword slot1 padding')
        require(s['btb_page']%4096==0 and data(s['btb_page'],4096)==page(), 'Entire immutable page/guards')
        for n in ('btb_root','btb_mid','btb_leaf'): require(s[n]%4096==0, 'Page table alignment')
    return dict(bank0=s['btb_bank0'],bank1=s['btb_bank1'],source_opcode='00030067',
                rows=16,slots=2,halfword_padding=True,whole_page_bytes=4096,file_backed=True)


def interval(commits):
    start=[i for i,c in enumerate(commits) if c.pc==0x80000000]
    end=[i for i,c in enumerate(commits) if (0x80001000,1) in c.memory_accesses]
    require(len(start)==len(end)==1 and start[0]<=end[0], 'Exact entry and successful terminal')
    return commits[start[0]:end[0]+1]


def ld_destination(word):
    if word&3==3:
        return word>>7&31 if word&127==3 and word>>12&7==3 else None
    if word&3==0 and word>>13&7==3: return 8+(word>>2&7)  # RV64 C.LD
    if word&3==2 and word>>13&7==3 and word>>7&31: return word>>7&31  # C.LDSP
    return None


def validate(commits, s, exceptions):
    require(exceptions==[('trap_supervisor_ecall',s['btb_s_ecall'])], 'One precise S-mode completion trap')
    require(not any(c.pc in (s['trap_fail'],s['btb_unexpected']) for c in commits), 'Trap failure')
    expected=[(s['btb_bank%d'%b]+4*r,TARGETS[p]) for b in (0,1) for r in range(16) for p in range(3)]
    sources=set(pc for pc,_ in expected)
    observed=[(i,c) for i,c in enumerate(commits) if c.pc in sources]
    require(len(observed)==96, 'Exact96 source executions')
    for (index,c),(pc,target) in zip(observed,expected):
        require(c.pc==pc and c.instruction==0x30067 and not c.gpr_writes and
                commits[index+1].pc==target and commits[index+1].instruction==
                (0x0aa00513 if target==TARGETS[1] else 0x05500513) and
                commits[index+1].gpr_writes=={10:0xaa if target==TARGETS[1] else 0x55} and
                commits[index+2].pc==target+4 and commits[index+2].instruction==0x8067,
                'Exact sourcePC/target/result/return trace')
    # Direct JAL calls and return-classified leaf exits cannot update source BTB slots.
    for index,_ in observed:
        c=commits[index-1]
        require(c.instruction&127==0x6f and c.instruction>>7&31==1,
                'Each source entry must be direct JAL ra, not an aliasing indirect dispatcher')
    writes={}; loads={}
    for c in commits:
        for address,value in c.memory_accesses:
            if value is not None: writes[address]=value
            else:
                rd=ld_destination(c.instruction)
                if rd in c.gpr_writes: loads[address]=c.gpr_writes[rd]
    def checked(name, values):
        for i,gold in enumerate(values):
            require(loads.get(s[name]+8*i)==gold, 'Actual complete readback differs: '+name)
    checked('btb_results',[0xaa if i%3==1 else 0x55 for i in range(96)])
    checked('btb_trap',[9,s['btb_s_ecall'],0])
    for name,values in zip(('btb_root','btb_mid','btb_leaf'),tables(s)): checked(name,values)
    checked('btb_page',[int.from_bytes(page()[i:i+8],'little') for i in range(0,4096,8)])
    checked('btb_vrf',[0x5a5a5a5a5a5a5a5a if 8<=i<520 else 0x9696969696969696 for i in range(528)])
    original=[writes.get(s['btb_original']+8*i) for i in range(9)]
    require(all(v is not None for v in original) and original[1]==0, 'Original machine CSR frame')
    checked('btb_restored',original);checked('btb_csr',[8,24,0,0,0])
    require([writes.get(s[n]) for n in ('g75_result','num_failed','tohost')]==[2690,0,1] and
            writes.get(s['g75_result']+4)==0, 'Exact2690 software checks/zero failures')
    require(not any(s['btb_page']<=a<s['btb_page']+4096 or
            any(s['btb_bank%d'%b]<=a<s['btb_bank%d'%b]+64 for b in (0,1)) for a in writes),
            'Immutable executable bytes modified')
    return arch.reference_counts(commits,s)


def static_evidence():
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    book=life.read_bound(BOOK,BOOK_SHA)
    pins={str(BASE/'admission-manifest.json'):BASE_SHA,str(BOOK):BOOK_SHA,str(CACHE):CACHE_SHA}
    rels=('hardware/deps/cva6/core/frontend/btb.sv','hardware/deps/cva6/core/frontend/frontend.sv',
          'hardware/deps/cva6/core/branch_unit.sv','hardware/deps/cva6/core/frontend/instr_scan.sv',
          'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
          'hardware/deps/cva6/core/include/build_config_pkg.sv')
    for rel in rels:
        p=ROOT/rel;require(life.digest(p)==book[str(p)],'Frozen producer source');pins[str(p)]=book[str(p)]
    ledger=BASE/'combined-inputs.txt';pins[str(ledger)]=base['output_pins'][str(ledger)]
    require(life.digest(ledger)==pins[str(ledger)],'Formal ledger');ld=ledger.read_text().splitlines()
    require(len(ld)==len(set(ld))==778 and base['coverage_admitted'] is True,'Formal777')
    cache=life.read_bound(CACHE,CACHE_SHA)
    prior=next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    pins[str(prior)]=cache['input_pins'][str(prior)]
    require(life.digest(prior)==pins[str(prior)] and ld[:742]==prior.read_text().splitlines(),'741 exact prefix')
    merged={SCOPE:{k:cache['instances'][SCOPE][k] for k in ('width','checksum','bits')}}
    for db in ld[742:]:
        fs=list((Path(db)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(fs)==1,'One Toggle suffix');sample,h=toggle.rows(fs[0],[SCOPE])
        require(h==base['input_pins'][str(fs[0])],'Admitted sample pin');pins[str(fs[0])]=h
        merged=toggle.union(merged,sample)
    db=Path(ld[0])/'snps/coverage/db'
    paths=[db/'design/verilog.design.xml',db/'shape/tgl.verilog.info.xml',db/'shape/tgl.verilog.shape.xml']
    for p in paths: pins[str(p)]=base['input_pins'][str(p)]
    life.check(pins)
    checks,defs=toggle.definitions(*(toggle.xml(p) for p in paths),[SCOPE])
    require(checks[SCOPE]==merged[SCOPE]['checksum']=='1574888635' and
            defs[SCOPE]['module']['chksum']=='3392269442','Exact BTB compiled identity')
    root=ET.fromstring(defs[SCOPE]['shape']);offset=0;objects=[];row=merged[SCOPE]
    for node in root.find('tglshape'):
        require(node.tag in ('node','vectornode'),'No inferred array serialization')
        width=1 if node.tag=='node' else abs(int(node.get('left'))-int(node.get('right')))+1
        if re.fullmatch(r'gen_asic_btb.btb_[dq]\[\d+\]\[\d+\].target_address',node.get('name','')):
            require(width==64,'Target width')
            zeros=[i for i in range(offset,offset+128) if not(int(row['bits'],16)>>(row['width']-1-i)&1)]
            objects.append(dict(name=node.get('name'),offset=offset,missing_positions=zeros))
        offset+=2*width
    require(offset==row['width']==8992 and len(objects)==64,'All32 d/q target slots')
    return dict(scope=SCOPE,baseline_tests=777,baseline=merged[SCOPE],objects=objects,
                target_A_B_A=list(TARGETS),serialized_pair_direction_not_assigned=True,
                missing_positions=sum(len(o['missing_positions']) for o in objects),
                conditional_gain_only=True,RTL_coverage_measured=False),pins


def prepare(out, replay=None):
    require(out.parent==OUT and not out.exists(),'Fresh preflight')
    prediction,pins=static_evidence()
    command=[str(build.LLVM/'clang'),'--target=riscv64-unknown-elf','-march=rv64gcv_zfh_zvfh',
        '-mabi=lp64d','-mcmodel=medany','-mno-relax','-msmall-data-limit=0','-O2',
        '-fno-vectorize','-fno-slp-vectorize','-ffreestanding','-DG75_NO_PRINT','-D__SPIKE__',
        '-DVLEN=1024','-DNR_LANES=4',*[ '-I'+str(ROOT/p) for p in
        ('apps/riscv-tests/isa/macros/vector','apps/riscv-tests/env','apps/common')],
        '-fuse-ld=lld','-nostdlib','-T'+str(ROOT/'verification/tests/gap75.ld'),
        str(ROOT/'verification/tests/gap75_start.S'),str(APP),'-o',str(out/'input.elf')]
    files=[APP,ROOT/'verification/tests/gap75.ld',ROOT/'verification/tests/gap75_start.S',
           Path(__file__).resolve(),Path(__file__).with_name('test_btb_target_ring.py'),
           build.LLVM/'clang',build.LLVM/'llvm-readelf',build.LLVM/'llvm-objdump',build.SPIKE]
    for directory in ('apps/riscv-tests/isa/macros','apps/riscv-tests/env','apps/common'):
        files.extend(p for p in (ROOT/directory).rglob('*') if p.is_file())
    for module in (build,arch,life,toggle,toggle.base): files.append(Path(module.__file__).resolve())
    for function in (build.parse_spike_commits,build._elf_symbol,arch.reference_counts):
        files.append(Path(function.__code__.co_filename).resolve())
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files});life.check(pins)
    if replay is not None:
        require(replay==OUT/'btb-target-ring-preflight777-agent-20261007-02','Only preserved exact compiler/Spike attempt')
        old=json.loads((replay/'input-pins.json').read_bytes())
        changed={str(Path(__file__).resolve()),str(Path(__file__).with_name('test_btb_target_ring.py'))}
        life.check({p:h for p,h in old.items() if p not in changed})
        require(old[str(APP)]==pins[str(APP)] and
                json.loads((replay/'failure.json').read_bytes())['reason']==
                'Actual complete readback differs: btb_results','Exact preserved checker-only failure')
        expected=json.loads((replay/'compile-command.json').read_bytes())
        require(expected==[str(replay/'input.elf') if x==str(out/'input.elf') else x for x in command],
                'Unchanged compilation inputs/command')
        for p in replay.iterdir():
            if p.is_file(): pins=life.merge_pins(pins,{str(p):life.digest(p)})
    out.mkdir();life.save(out/'input-pins.json',pins);life.save(out/'compile-command.json',command)
    try:
        if replay is None:
            with (out/'build.log').open('x') as f: subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
        else:
            for name in ('input.elf','build.log','input.disasm','spike.trace'):
                shutil.copyfile(replay/name,out/name)
                require(life.digest(out/name)==pins[str(replay/name)],'Unchanged actual reference artifact')
            life.save(out/'reference-replay.json',dict(original=str(replay),ELF_source_unchanged=True,
                compiler_rerun=False,Spike_rerun=False,old_checker_SHA=old[str(Path(__file__).resolve())],
                new_checker_SHA=pins[str(Path(__file__).resolve())],correction='Exact RV64 C.LD/C.LDSP integer readback decode'))
        s={n:build._elf_symbol(out/'input.elf',build.LLVM/'llvm-readelf',n) for n in SYMBOLS}
        elf=elf_contract(out/'input.elf',s);life.save(out/'elf-proof.json',elf)
        if replay is None:
            with (out/'input.disasm').open('x') as f:
                subprocess.run([str(build.LLVM/'llvm-objdump'),'-d',str(out/'input.elf')],stdout=f,check=True,timeout=30)
        cmd=[str(build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
             '-m0x80000000:0x20000000','-l','--log-commits',str(out/'input.elf')]
        life.save(out/'spike-command.json',cmd)
        if replay is None:
            with (out/'spike.trace').open('x') as f: subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
        commits=interval(build.parse_spike_commits(out/'spike.trace'))
        exceptions=[(k,int(pc,16)) for k,pc in re.findall(r'exception (\w+), epc (0x[0-9a-f]+)',(out/'spike.trace').read_text())]
        counts=validate(commits,s,exceptions);life.save(out/'prediction.json',prediction)
        require(counts['matched_instructions']<100000,'Software budget cap before VCS')
        life.check(pins)
        pins=life.merge_pins(pins,{str(p):life.digest(p) for p in out.iterdir() if p.is_file()})
        life.save(out/'preflight.json',dict(status='BTB32_SPIKE_ARCHITECTURE_PASS_NOT_RTL',input_pins=pins,
            symbols=s,counts=counts,checks=2690,precise_ecalls=1,baseline=777,baseline_seal=BASE_SHA,
            source_executions=96,elf_proof=elf,prediction=prediction,VCS_launched=False,coverage_admitted=False))
        print('BTB_PREFLIGHT_PASS',str(out/'preflight.json'),life.digest(out/'preflight.json'),counts,flush=True)
    except Exception as error:
        life.save(out/'failure.json',dict(reason=str(error),coverage_admitted=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--replay',type=Path);a=p.parse_args()
    prepare(a.output.absolute(),a.replay.absolute() if a.replay else None)

"""Real S-mode instruction-page ASID replacement; pinned771, no coverage claim."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import shutil
import xml.etree.ElementTree as ET
import build_tlb_asid_matrix as shared

life, build, architecture, native = shared.life, shared.build, shared.architecture, shared.native
ROOT, OUT, require = shared.ROOT, shared.OUT, shared.require
APP = ROOT/'apps/riscv-tests/isa/rv64uv/vitlb_asid_exec_matrix.c'
BASE = OUT/'sv39-alias-offline-admitted-771-agent-20261007-01'
BASE_SHA = 'ad9e01dcd0ea3ef442d7f28934bf1695dca61c7b6d1c7580bd2a49f0c2569860'
DESIGN = OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb'
SCOPE = shared.SCOPE.replace('.i_dtlb','.i_itlb')
GUARD, CHECKS = shared.GUARD, 10966
SYMBOLS = ('tohost','num_failed','g75_result','trap_fail','itm_enter','itm_resume','itm_handler',
           'itm_code','itm_root','itm_mid','itm_leaf','itm_observed','itm_ledger','itm_csr',
           'itm_original','itm_restored','itm_phase','itm_expected_ecall','itm_ledger_ptr')


def address(phase, entry):
    return (shared.address(phase,entry) & ~4095) | 64


def codeword(entry, word):
    if word == 8: return (0x00150513 << 32) | ((0x100+entry) << 20) | 0x513
    if word == 9: return (GUARD & 0xffffffff00000000) | 0x73
    return GUARD


def tables(symbols, phase):
    pte = lambda a,f: ((a >> 12) << 10) | f
    root, mid, leaf = [0]*512, [0]*512, [0]*512
    root[2] = pte(0x80000000,0xcf)
    for p in range(2):
        for e in range(16):
            v = shared.vpn(p,e)
            require(v >> 18 != 2,'Target overlaps identity mapping')
            root[v >> 18] = pte(symbols['itm_mid'],1)
            mid[(v >> 9)&511] = pte(symbols['itm_leaf'],1)
    require(len({shared.vpn(phase,e)&511 for e in range(16)}) == 16,'Leaf alias collision')
    for e in range(16):
        leaf[shared.vpn(phase,e)&511] = pte(symbols['itm_code']+4096*e,0x4b)
    return root,mid,leaf


def validate(commits, symbols):
    require(not any(c.vector_writes or c.pc == symbols['trap_fail'] for c in commits),'Unexpected vector/trap fail')
    writes = {}; phases = []; target = []; histories = {}
    allpcs = {(address(p,e)+off)&((1<<64)-1): (p,e,off) for p in range(2) for e in range(16) for off in (0,4,8)}
    # Phases0 and2 share PCs; order is checked below rather than dictionary counts.
    for c in commits:
        if c.pc in allpcs: target.append(c)
        for a,v in c.memory_accesses:
            if v is None: continue
            writes[a] = v
            histories.setdefault(a,[]).append(v)
            if a == symbols['itm_phase']:
                if len(histories[a]) == 1:
                    require(v == 0,'CRT phase initialization differs')
                    continue
                require(v == len(phases) and v < 3,'Phase order differs')
                gold = tables(symbols,v)
                require(all(writes.get(symbols[n]+8*i) == values[i]
                    for n,values in zip(('itm_root','itm_mid','itm_leaf'),gold) for i in range(512)),
                    'Complete phase PTE image differs')
                phases.append(v)
    require(phases == [0,1,2] and len(target) == 144,'Missing/extra exact thunk instructions')
    for index,c in enumerate(target):
        p,e,off = index//48,(index%48)//3,(index%3)*4
        insn = ((0x100+e)<<20)|0x513 if off == 0 else 0x00150513 if off == 4 else 0x73
        require(c.pc == address(p,e)+off and c.instruction == insn and not c.memory_accesses and
                c.gpr_writes == ({10:0x100+e} if off == 0 else {10:0x101+e} if off == 4 else {}),
                'Exact S-mode PC/opcode/result differs')
    require([writes.get(symbols['g75_result']),writes.get(symbols['g75_result']+4),
             writes.get(symbols['num_failed']),writes.get(symbols['tohost'])] == [CHECKS,0,0,1],
            'Complete selfcheck terminal differs')
    original = [writes.get(symbols['itm_original']+8*i) for i in range(3)]
    require(all(v is not None for v in original) and original[1] == 0,'Original CSR missing/nonbare')
    require([writes.get(symbols['itm_restored']+8*i) for i in range(3)] == original,'CSR restoration differs')
    for p in range(3):
        satp = (8<<60)|((0xaaaa if p == 1 else 0x5555)<<44)|(symbols['itm_root']>>12)
        require([writes.get(symbols['itm_csr']+8*(p*6+i)) for i in range(6)] ==
                [satp,original[0],symbols['itm_handler'],0,0,0],'Phase CSR/guards differ')
        for e in range(16):
            index=p*16+e
            require(writes.get(symbols['itm_observed']+8*index) == 0x101+e and
                [writes.get(symbols['itm_ledger']+8*(3*index+i)) for i in range(3)] ==
                [9,address(p,e)+8,0],'Trap ledger/result differs')
    for e in range(16):
        for w in range(512):
            a=symbols['itm_code']+4096*e+8*w
            require(writes.get(a) == codeword(e,w),'Full executable code/guard image differs')
            require(histories[a] == [0,codeword(e,w)],'Code modified after CRT initialization/construction')
    # Every guard is actually read after all S-mode execution, not merely initialized.
    reads = {a for c in commits for a,v in c.memory_accesses if v is None}
    require(all(symbols['itm_code']+4096*e+8*w in reads for e in range(16) for w in range(512)),
            'Code guard readback incomplete')
    require(not any(0xd0000000 <= a < 0xd0001000 for a in writes),'Forbidden CTRL write')
    return architecture.reference_counts(commits,symbols)


def baseline():
    b = life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(b['coverage_admitted'] is True,'Formal771 required')
    pins = life.merge_pins(b['input_pins'],b['output_pins'])
    pins = life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA})
    bits = life.read_bound(BASE/'combined-bits.json',pins[str(BASE/'combined-bits.json')])
    ledger = (BASE/'combined-inputs.txt').read_text().splitlines()
    require(life.digest(BASE/'combined-inputs.txt') == pins[str(BASE/'combined-inputs.txt')] and
            ledger == [str(DESIGN),*bits['tests']] and len(bits['tests']) == len(set(bits['tests'])) == 771,
            'Exact771 prefix differs')
    return bits,ledger,pins


def toggle_baseline(ledger,pins):
    cache=life.read_bound(shared.CACHE,shared.CACHE_SHA)
    prior=next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    require(life.digest(prior) == cache['input_pins'][str(prior)] and
            ledger[:742] == prior.read_text().splitlines(),'Cached741 prefix differs')
    pins=life.merge_pins(pins,{str(shared.CACHE):shared.CACHE_SHA,str(prior):cache['input_pins'][str(prior)]})
    merged={SCOPE:cache['instances'][SCOPE]}
    for vdb in ledger[742:]:
        files=list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files) == 1,'Ambiguous Toggle suffix')
        sample,sha=native.rows(files[0],[SCOPE]);require(sha == pins[str(files[0])],'Suffix Toggle pin differs')
        merged=native.union(merged,sample)
    return merged,pins


def prediction():
    _,ledger,pins=baseline();merged,pins=toggle_baseline(ledger,pins)
    db=DESIGN/'snps/coverage/db'
    paths=[db/'design/verilog.design.xml',db/'shape/tgl.verilog.info.xml',db/'shape/tgl.verilog.shape.xml']
    require(all(str(p) in pins for p in paths),'Unbound compiled Toggle inputs')
    life.check({str(p):pins[str(p)] for p in paths})
    checks,defs=native.definitions(*(native.xml(p) for p in paths),[SCOPE])
    require(checks[SCOPE] == '817233724' and merged[SCOPE]['checksum'] == checks[SCOPE],
            'Compiled ITLB identity differs')
    width=merged[SCOPE]['width'];bits=format(int(merged[SCOPE]['bits'],16),'0%db'%width)
    offset=0;targets=[]
    for n in ET.fromstring(defs[SCOPE]['shape']).find('tglshape'):
        # "arrays" is aggregate metadata; its flattened node/vectornode leaves
        # follow in this shape. Counting it twice breaks the serialized width.
        if n.tag == 'arrays': continue
        require(n.tag in ('node','vectornode'),'Unexpected ITLB typed shape')
        w=1 if n.tag == 'node' else abs(int(n.get('left'))-int(n.get('right')))+1
        if re.fullmatch(r'tags_[qn]\[\d+\]\.(?:asid|vpn\[\d+\])',n.get('name','')):
            targets.append(dict(native=dict(n.attrib),fresh_positions=[i for i in range(offset,offset+2*w) if bits[i]=='0']))
        offset+=2*w
    require(offset == width and targets,'ITLB typed serialization differs')
    return dict(scope=SCOPE,checksum=checks[SCOPE],width=width,targets=targets,
        conditional_fresh_positions=sum(len(t['fresh_positions']) for t in targets),baseline=771,
        official_percentage=False,direction_order_calibrated=False,
        condition='Actual translated updates and PLRU entry visits required; 16 calls alone do not prove16victims'),pins


def source_contract():
    book=life.read_bound(shared.SOURCE,shared.SOURCE_SHA)
    rels=['hardware/src/ara_soc.sv']+['hardware/deps/cva6/'+p for p in (
        'core/cva6_mmu/cva6_tlb.sv','core/cva6_mmu/cva6_mmu.sv','core/cva6_mmu/cva6_ptw.sv',
        'core/csr_regfile.sv','core/include/build_config_pkg.sv','core/include/cv64a6_imafdcv_sv39_config_pkg.sv')]
    pins={str(ROOT/p):book[str(ROOT/p)] for p in rels};pins[str(shared.SOURCE)]=shared.SOURCE_SHA
    life.check(pins)
    clean=lambda s:re.sub(r'\s+','',re.sub(r'/\*.*?\*/|//[^\n]*','',s,flags=re.S))
    text={Path(p).name:clean(Path(p).read_text()) for p in pins if p.endswith('.sv')}
    cfg=text['cv64a6_imafdcv_sv39_config_pkg.sv'];mmu=text['cva6_mmu.sv'];tlb=text['cva6_tlb.sv']
    require("InstrTlbEntries:int'(16)" in cfg and "UseSharedTlb:bit'(0)" in cfg and
            'localparamCVA6ConfigHExtEn=0;' in cfg,'Frozen16/RVH0 configuration differs')
    for token in ('assignitlb_lu_access=icache_areq_i.fetch_req;', '.TLB_ENTRIES(CVA6Cfg.InstrTlbEntries)',
                  '.s_st_enbl_i(enable_translation_i)', '.lu_access_i(itlb_lu_access)'):
        require(token in mmu,'ITLB producer differs: '+token)
    for token in ('if(lu_hit[i]&lu_access_i)', 'elseif(update_i.valid&replace_en[i]&!lu_hit_o)',
                  "if(asid_to_be_flushed_is0&&vaddr_to_be_flushed_is0)tags_n[i].valid=1'b0;",
                  "plru_tree_q<='{default:0};",'plru_tree_n=plru_tree_q;',
                  'tags_n[i]={update_i.asid,update_i.vmid,',
                  "((CVA6Cfg.PtLevels+HYP_EXT)*(CVA6Cfg.VpnLen/CVA6Cfg.PtLevels))'(update_i.vpn)"):
        require(token in tlb,'TLB driver semantics differ: '+token)
    return dict(entries=16,RVH=0,shared_tlb=0,ASIDs=[0x5555,0xaaaa,0x5555],
        flush='SFENCE invalidates valid, preserves PLRU',execution='48 true S-mode entries, no MPRV-only substitute',
        physical_pages=16,PTE_flags=0x4b,protection='R/X/A, no W/U/G; identity safety mapping outside target'),pins


def prepare(output, replay=None):
    require(not output.exists(),'Fresh preflight only')
    pred,pins=prediction();proof,spins=source_contract();pins=life.merge_pins(pins,spins)
    require(pred['conditional_fresh_positions'] >= 300,'Insufficient current771 target capacity')
    command=json.loads(shared.TEMPLATE.read_bytes());old=str(ROOT/'apps/riscv-tests/isa/rv64uv/vgap99_csr_satp_mprv.c')
    require(command.count(old)==1,'Exact mature scalar template required')
    command=[str(APP) if x == old else str(output/'input.elf') if x.endswith('/input.elf') else x for x in command]
    for p in (APP,shared.TEMPLATE,Path(__file__).resolve(),Path(__file__).with_name('test_itlb_asid_exec.py'),
        ROOT/'verification/tests/gap75_start.S',ROOT/'verification/tests/gap75.ld',Path(command[0]),
        build.LLVM/'llvm-readelf',build.LLVM/'llvm-objdump',build.SPIKE):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    for directory in ('apps/riscv-tests/isa/macros','apps/riscv-tests/env','apps/common'):
        for p in (ROOT/directory).rglob('*'):
            if p.is_file():pins=life.merge_pins(pins,{str(p):life.digest(p)})
    for module in (shared,life,build,architecture,native,native.base):
        p=Path(module.__file__).resolve();pins=life.merge_pins(pins,{str(p):life.digest(p)})
    if replay is not None:
        require(replay.name == 'itlb-asid-exec-preflight-771-agent-20261007-01' and replay.parent==OUT,
                'Only the preserved first reference is eligible')
        oldbook=replay/'input-pins.json';oldpins=json.loads(oldbook.read_bytes())
        changed={str(Path(__file__).resolve()),str(Path(__file__).with_name('test_itlb_asid_exec.py'))}
        # The failed driver/test are not compilation inputs. Their recorded old
        # hashes remain provenance; no RTL/app/compiler/include pin is relaxed.
        unchanged={p:h for p,h in oldpins.items() if p not in changed}
        life.check(unchanged)
        require(oldpins[str(APP)]==life.digest(APP) and
                json.loads((replay/'failure.json').read_bytes())['reason']=='Exact48 Spike S-mode traps differ',
                'Wrong historical failure/source')
        original_command=json.loads((replay/'compile-command.json').read_bytes())
        require(original_command == [str(replay/'input.elf') if x==str(output/'input.elf') else x for x in command],
                'Compile command/source equivalence differs')
        for name in ('input-pins.json','failure.json','compile-command.json','build.log','input.elf','input.disasm','spike-command.json','spike.trace'):
            p=replay/name;pins=life.merge_pins(pins,{str(p):life.digest(p)})
        replay_proof=dict(original=str(replay),compiled_application_unchanged=True,compiler_and_include_pins_unchanged=True,
            reference_rerun=False,oracle_only_replacements={p:dict(recorded_old_sha=oldpins[p],new_sha=life.digest(Path(p))) for p in changed},
            corrections=['strict numeric64bit ECALL PC comparison','CRT phase-zero distinguished from actualphase0',
                         'CRT code-zero initialization followed by one construction'],old_failure_preserved=True)
    life.check(pins);output.mkdir();life.save(output/'input-pins.json',pins)
    try:
        life.save(output/'prediction.json',pred);life.save(output/'source-contract.json',proof)
        life.save(output/'compile-command.json',command)
        if replay is None:
            with (output/'build.log').open('x') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,timeout=120,check=True)
        else:
            life.save(output/'reference-replay.json',replay_proof)
            for name in ('input.elf','build.log','input.disasm','spike.trace'):
                shutil.copyfile(replay/name,output/name)
                require(life.digest(output/name)==pins[str(replay/name)],'Reference artifact copy differs')
        symbols={n:build._elf_symbol(output/'input.elf',build.LLVM/'llvm-readelf',n) for n in SYMBOLS}
        require(symbols['itm_code']%4096 == 0,'Code page alignment differs')
        if replay is None:
            with (output/'input.disasm').open('x') as f:
                subprocess.run([str(build.LLVM/'llvm-objdump'),'-d',str(output/'input.elf')],stdout=f,timeout=30,check=True)
        spike=[str(build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
               '-m0x80000000:0x20000000','-l','--log-commits',str(output/'input.elf')]
        life.save(output/'spike-command.json',spike)
        if replay is None:
            with (output/'spike.trace').open('x') as f:subprocess.run(spike,stdout=f,stderr=subprocess.STDOUT,timeout=120,check=True)
        commits=build.parse_spike_commits(output/'spike.trace')
        # Spike commit parser omits trapped instructions; include explicit log ecalls for oraclePC checks.
        exceptions=re.findall(r'exception (\w+), epc (0x[0-9a-f]+)',(output/'spike.trace').read_text())
        require([(kind,int(pc,16)) for kind,pc in exceptions] ==
                [('trap_supervisor_ecall',address(p,e)+8) for p in range(3) for e in range(16)],
                'Exact48 Spike S-mode traps differ')
        expanded=with_ecalls(commits,symbols)
        validate(expanded,symbols);counts=architecture.reference_counts(commits,symbols)
        life.check(pins)
        pins=life.merge_pins(pins,{str(p):life.digest(p) for p in output.iterdir() if p.is_file()})
        life.save(output/'preflight.json',dict(status='ITLB_TRUE_SMODE48_SPIKE_PTE_CODE_CSR_PASS_NOT_RTL',
            input_pins=pins,symbols=symbols,counts=counts,software_checks=CHECKS,trap_count=48,baseline=771,
            prediction=pred,coverage_admitted=False,VCS_launched=False))
        print('PREFLIGHT_PASS',life.digest(output/'preflight.json'),counts,flush=True)
    except Exception as e:
        life.save(output/'failure.json',dict(reason=str(e),coverage_admitted=False));raise


def with_ecalls(commits,symbols):
    result=[]
    for c in commits:
        if c.pc == symbols['itm_handler']:
            p,e=divmod(sum(x.instruction == 0x73 for x in result),16)
            require(p < 3,'Extra handler entry')
            result.append(architecture.spike_trace.SpikeCommit(pc=address(p,e)+8,instruction=0x73,
                gpr_writes={},fpr_writes={},vector_writes={},csr_writes={},memory_accesses=()))
        result.append(c)
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--replay',type=Path);a=p.parse_args()
    prepare(a.output.absolute(),a.replay.absolute() if a.replay else None)
